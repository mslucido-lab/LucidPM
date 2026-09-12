# LucidoPM — ChatGPT Handoff 68
*Extend the Blob storage abstraction to source PDFs and split PDF sections, and migrate
`TenantCRM_Test`'s existing files — closes the gap H67's container testing found*
*Prepared: 2026-09-11*
*Azure Migration — pulls forward part of the roadmap's Stage 5.1 ("full production data migration"),
found necessary earlier than planned by container testing after Gate 4. HIGH risk (matches the
roadmap's own existing risk rating for this work) — real data migration, not just new code.*

---

## What This Is

Generating a lease package that includes a PDF-backed section (a source PDF, or a split section cut
from one) fails inside the deployed `lucidpm` Container App with *"Missing PDF files for these
PDF-only sections."* This is **not** a container bug and **not** the stale-`StoredFilePath` bug
specifically — it's structural: `LeaseSourceDocuments` and `LeaseDocumentSections` still store
Windows local filesystem paths, and a Container App replica has no access to *any* Windows
filesystem, correct path or not. Handoffs 66/67 deliberately left this out of scope (H66's Do Not
Touch: *"Source-PDF upload/copy/split... untouched... Cycle 5.1's job, not this one's"*) — this
handoff is that job, pulled forward because POC testing found it blocking real usage sooner than
Stage 5 was going to.

**Explicitly not the same problem H66/H67 solved** — different tables, different helper functions,
different call sites:
- H66/H67: `LeaseGeneratedDocuments.StoredFilePath`, written by `merge_pdf_files()` +
  `save_generated_package()`, read by `/api/lease-generated-pdf`.
- This handoff: `LeaseSourceDocuments.StoredFilePath` / `LeaseDocumentSections.StoredFilePath`,
  written by `save_uploaded_pdf()` / `copy_existing_pdf()` / `split_pdf_pages()`, read only at
  package-generation time (pre-flight check + merge). There is no separate source-PDF preview/view
  route to worry about — confirmed by grep, see Current State.

**Two phases, two commits — do not collapse them:**
- **Phase A** — extend `DocumentStorage` usage to source/section documents (code only, local-behavior-
  preserving, proven with both backends locally before touching any real data). Mirrors H66's own
  discipline, including the lesson from H66's three review rounds: **don't force one key/path
  convention across both backends** — local keeps exactly what `template_folder()`/`sections_folder()`
  already do, Blob gets its own scheme.
- **Phase B** — migrate `TenantCRM_Test`'s *existing* rows and files to Blob. Real data mutation. Test
  DB only — **Prod (`TenantCRM`) is explicitly out of scope for this handoff**, matching the
  Test-then-Prod discipline every other DB-touching step of this migration has followed (Cycle 2.1's
  "verify Test, then repeat for Prod separately" pattern).

**Hard prerequisite, not this handoff's job:** the standing TOP-PRIORITY stale-`StoredFilePath`
cleanup (junction or bulk `UPDATE`, already scoped in `CLAUDE.md`) **must land before Phase B runs.**
A file that's unreadable locally (the ~16 Test rows still pointing at the old
`C:\Dell Inspirion\...` root) can't be migrated to Blob either — Phase B's migration script will
report exactly the same "missing" failure for those rows that the app does today. Confirm this is
done (or do it as literally the first sub-step of Phase B) before migrating anything.

---

## Current State

**The failing gate**, `lease_package_builder.py:1484-1490`:
```python
missing_sources = [
    p.section_name for p in selected
    if not self._has_renderable_text(p) and not os.path.isfile(p.file_path)
]
if missing_sources:
    self.form_error = _format_actionable_errors("Missing PDF files for these PDF-only sections:", missing_sources)
    return
```
`p.file_path` is `LeaseDocumentSections.StoredFilePath` (queried at lines 746/1083, mapped into
`.file_path`). This is a **pre-flight check** — it correctly fails fast with an actionable message
rather than crashing deep inside the merge, which is exactly why the reported error was clean and
specific rather than a stack trace. Good existing defensive code; it's just now reporting a real,
structural gap rather than an occasional stale-path glitch.

**The same gate repeats** at line `1742` (the regeneration path's equivalent check). **The actual
merge-time reads** are at `1573` (`pdf_paths_to_merge.append(p.file_path)`, first generation) and the
`~2260` area (regeneration) — both currently pass a raw local path straight into `PdfReader()`
downstream inside `merge_pdf_files()`.

**The merge boundary itself is local-path-only today — verified directly, not just inferred.**
`merge_pdf_files()` (`lease_documents_pdf.py:1174-1197`) takes `section_paths: Iterable[str]`, checks
`os.path.isfile(p)` for each, then calls `PdfReader(path)` per section — there is no
Blob-aware/file-like-object path in it at all yet. (An earlier revision of this handoff claimed
`merge_pdf_files()` already demonstrates a local-vs-blob-agnostic read pattern "like H66's" — that was
wrong; the only place `storage.read()` is actually called is the download route,
`/api/lease-generated-pdf` (`LucidPM.py:819`), a completely different code path. Corrected here.)
`pdf_paths_to_merge` (`lease_package_builder.py:1518`) mixes two origins into that same list: **local
temp files** for rendered-text sections (`render_text_sections_to_pdf_file()` → ReportLab writes to a
real path via `tempfile.NamedTemporaryFile`, deleted in a `finally` block after merge — this is
ephemeral in-process rendering, not `LeaseSourceDocuments`/`LeaseDocumentSections` data, and stays
local-only; H68 does not change it) and **PDF-backed section paths** (`p.file_path`, today always
local, after Phase A potentially `azblob:`-prefixed). `merge_pdf_files()` needs to resolve both
uniformly. **`split_pdf_pages()` has the identical gap on its own read side**: it calls
`PdfReader(source_path)` directly (`lease_documents_pdf.py:231`) against whatever `LeaseSourceDocuments`
row the split is being cut from — after Phase A, that source document can itself already be
Blob-backed (uploaded while `LUCIDPM_STORAGE_BACKEND=azure_blob`, or migrated by Phase B), so this read
needs the same resolver treatment as the merge boundary, not just its own write side (already covered
above).

**`LeaseDocumentSections` has no `PropertyID`/`DocumentCategory` of its own** — confirmed from its
`CREATE TABLE` (`lease_documents.py:741-759`): only `LeaseSourceDocumentID INT NULL`, `LeaseID INT
NULL`. A split section's property/category (needed to build its Blob key, matching
`sections_folder(root, property, category)`'s existing local convention) only exists on the *linked*
`LeaseSourceDocuments` row, reached via `LeaseSourceDocumentID` — which is nullable, so some section
rows may have no link at all (legacy/orphaned rows). Phase B's migration must join through this FK and
needs an explicit, documented fallback for the NULL case (see Phase B below) — it can't assume every
section row resolves to a property/category cleanly.

**The write side**, all in `LucidPM/pages/lease_documents_pdf.py`, all raw local filesystem I/O today
— and **not uniform**, confirmed by reading each function's actual current body:
- `save_uploaded_pdf()` (~170-186) and `copy_existing_pdf()` (~190-207) already build a
  **timestamp-suffixed unique filename** themselves (`f"{prefix}_{slugify(stem)}_{stamp}{ext}"`)
  before writing — collisions are already avoided by construction, no counter-loop.
- `split_pdf_pages()` (215-250), verified directly: uses the **exact same counter-suffix retry loop**
  (`while os.path.exists(target): target = f"{stem}_{counter}{ext}"`) the *original, pre-H66*
  `merge_pdf_files()` used — the identical shape H66's Phase A/round-3 had to fix, because a
  counter-based "does this exist yet" check is fine for local disk but unsafe/awkward for Blob.
- `page_count()` (~209-211) — reads via `PdfReader(path)`, called both at generation-validation time
  and right after a split/upload to confirm the result.
- **No dedicated route serves source PDFs for preview/download** — confirmed by grepping
  `LucidPM.py`'s `@api.get` routes; the only PDF-serving routes are for generated packages and
  reports. Source documents are read only internally (validation checks + merge-time), never served
  standalone. (An earlier draft of this handoff asked Codex to "find and fix the admin Library's PDF
  preview path" — there isn't one; that instruction is removed below.)
- Path helpers already in this file, admin-configurable via `LeaseDocumentStorageRoot`:
  `template_folder()`, `sections_folder()`, `normalize_storage_root()`, `ensure_folder()` — these stay
  exactly as they are for the **local** backend, same reasoning H66 landed on: don't reroute local's
  existing convention through a shared abstraction that forces a different shape.
- `import_local_pdf_for_testing()` (`lease_documents.py:1279`, dev-tool only, gated by
  `developer_tools_enabled`) also calls `copy_existing_pdf()` — covered automatically by fixing that
  function, no separate treatment needed.

**`DocumentStorage` already exists** (`LucidPM/document_storage.py`, Handoff 66/`cbf2038`) — `save`,
`read`, `exists`, two implementations, `save(lease_id, filename, data)`. This handoff extends the
interface rather than redesigning it, and mirrors H66's own final lesson precisely: **each backend
owns its collision strategy; the interface passes semantic parameters, never a pre-built path/key.**
Add a second method:
```python
from typing import Literal

class DocumentStorage(Protocol):
    def save(self, lease_id: int, filename: str, data: bytes) -> str: ...   # existing (H66)

    def save_source(
        self,
        property_name: str,
        document_category: str,
        filename: str,
        data: bytes,
        *,
        kind: Literal["template", "section"] = "template",
        collision: Literal["unique_name", "retry_suffix"] = "unique_name",
    ) -> str:
        """Persist a source/section document.

        kind picks the local subfolder / Blob key segment:
          - "template" -> template_folder(root, property, category)   (uploads, copies)
          - "section"  -> sections_folder(root, property, category)   (PDF splits)

        collision picks the local collision strategy (Blob always uses its own
        uuid-based, overwrite=False strategy regardless of this parameter):
          - "unique_name"  -> caller's filename is already timestamp-unique
                              (save_uploaded_pdf, copy_existing_pdf); write as-is,
                              no retry loop.
          - "retry_suffix" -> caller's filename is NOT guaranteed unique
                              (split_pdf_pages); port the exact existing
                              counter-suffix while-loop
                              (lease_documents_pdf.py:242-246) into this method.
        """

    def read(self, identifier: str) -> bytes: ...   # existing, generated-packages only, no change
    def exists(self, identifier: str) -> bool: ...  # existing, generated-packages only, no change
```
Call sites: `save_uploaded_pdf`/`copy_existing_pdf` → `kind="template", collision="unique_name"`;
`split_pdf_pages` → `kind="section", collision="retry_suffix"`.

Note: source/section reads do **not** go through the Protocol's `read`/`exists` methods at all — they
go through the standalone `read_source_document()`/`source_document_exists()` resolver functions
described below, which dispatch on the identifier's own shape rather than on whichever backend
`save_source()` currently targets. That split (single-backend writes, identifier-dispatched reads) is
deliberate — see "Local dev after Phase B" above for why.
- `LocalFilesystemStorage.save_source()`: `kind` selects `template_folder(root, property, category)`
  vs `sections_folder(root, property, category)` — both already exist, no new path logic needed, just
  branch on `kind`. `collision="unique_name"` writes the given filename directly (matches
  `save_uploaded_pdf`/`copy_existing_pdf`'s current behavior exactly — they already guarantee
  uniqueness). `collision="retry_suffix"` runs the ported counter-suffix loop (matches
  `split_pdf_pages`'s current behavior exactly — same fix H66 gave `merge_pdf_files`/
  `LocalFilesystemStorage.save`, ported here instead of left in `split_pdf_pages` itself, since a
  "does this exist" check belongs with whichever backend actually owns collision detection).
- **`save_source()` needs its own root factory — it cannot reuse `get_document_storage()`.** Verified
  directly: `get_document_storage()` (`document_storage.py:81-96`) constructs
  `LocalFilesystemStorage(generated_folder(storage_root or DEFAULT_DOCUMENT_ROOT))` — its `self._root`
  is already `<root>\Generated`. `template_folder(root, property, category)` treats whatever `root` it's
  given as the *bare* document root and appends `Admin\<property>\<category>` itself. Calling
  `save_source()` on an instance built by `get_document_storage()` would resolve to
  `<root>\Generated\Admin\...` — a doubled, wrong path, not what today's uploads/splits produce
  (`<root>\Admin\...`). **Do not fix this by stripping `"Generated"` back off `self._root`** — add a
  separate factory instead: `get_source_document_storage(storage_root: str | None = None) ->
  DocumentStorage` in `document_storage.py`, parallel to `get_document_storage()`, that for the local
  backend constructs `LocalFilesystemStorage(normalize_storage_root(storage_root or
  DEFAULT_DOCUMENT_ROOT))` — the bare root, no `generated_folder()` call — and for the Blob backend
  returns the same lazily-constructed `AzureBlobStorage` singleton `get_document_storage()` already
  uses (Blob has no such doubling problem — `kind` already picks the full key segment, `Generated/...`
  vs `Sources/...`, independently). Every Phase A write call site uses
  `get_source_document_storage(storage_root).save_source(...)`, never `get_document_storage()`.
  `get_document_storage()` itself is completely unchanged — this is a new sibling function, not a
  modification (see Do Not Touch).
- `AzureBlobStorage.save_source()`: `kind` picks the key segment —
  `Sources/<property>/<category>/<uuid>_<filename>` for `kind="template"`,
  `Sources/<property>/<category>/Sections/<uuid>_<filename>` for `kind="section"` — `overwrite=False`,
  full `uuid.uuid4().hex` in both cases, same reasoning as `AzureBlobStorage.save()` in H66. The
  `collision` parameter is accepted (interface uniformity) but **ignored** — Blob always uses its own
  uuid-based scheme regardless of which collision mode the caller asked for; don't try to reproduce the
  timestamp-suffix or counter-loop conventions for Blob, they're solving a local-disk problem that
  doesn't apply the same way to Blob's namespace. **Return the key prefixed with the `azblob:` scheme**
  (`azblob:Sources/<property>/...`) — this is what makes the identifier self-describing for the
  resolver (see "Local dev after Phase B" above); the un-prefixed key is still what's actually stored
  in Blob, the prefix only exists in the `StoredFilePath` string.
- **`StorageRoot`/`RelativePath` at write time** — meaningful for both backends, not a NULL/sentinel
  placeholder: the three call sites in `lease_documents.py` that currently compute
  `rel = relative_to_root(stored_path, root)` need a backend branch. For the local backend, keep this
  byte-identical. For the Blob backend, skip `relative_to_root()` (it doesn't apply to a Blob key) and
  instead set `StorageRoot` to the Blob container name (`LUCIDPM_BLOB_CONTAINER`, e.g.
  `lucidpm-documents`) and `RelativePath` to the key portion of the identifier with the `azblob:`
  prefix stripped — i.e. exactly what `StoredFilePath` holds minus the scheme, so it stays legible in
  the admin list and stays in sync with `StoredFilePath` by construction (both derived from the same
  key at the same call).

**`StorageRoot`/`RelativePath` are display-only, not load-bearing for reads** — confirmed by reading
every call site. `lease_documents.py` computes `rel = relative_to_root(stored_path, root)` at write
time and stores it alongside `StorageRoot`, but the only place either column is read back is
`_load_source_documents()` (`lease_documents.py:1013`): `saved_path=str(r.get("RelativePath") or
r.get("StoredFilePath") or "")`, used purely to render a friendlier path in the admin list. No code
path reconstructs a file location from `StorageRoot + RelativePath` — every actual read/exists/gate
check uses `StoredFilePath` directly. This matters because `relative_to_root()` calls
`os.path.relpath()` against a local root, which produces a meaningless value if handed a Blob key —
but since nothing consumes that value functionally, it's a cosmetic gap (an ugly string in the admin
list), not a generation-blocking one. Phase A still fixes it properly (see below) rather than leaving
garbage in the column, but it does not need to block Phase A/B on a bigger redesign.

**Local dev after Phase B needs a dual-source resolver, not just an env-var-matching rule.** An
earlier revision of this handoff argued the read side could stay single-backend (match
`LUCIDPM_STORAGE_BACKEND` to whichever backend wrote the row you want to see, the way
`LeaseGeneratedDocuments` already works). Codex's review correctly pushed back: source/section
documents are a long-lived library, not a regenerate-and-replace flow like generated packages —
`TenantCRM_Test` will accumulate **both** local-path rows (anything created locally with the default
`LUCIDPM_STORAGE_BACKEND=local`, which stays the normal local workflow) **and** Blob-key rows
(everything Phase B migrates, plus anything created while pointed at `azure_blob`) side by side,
indefinitely, in the same database. Forcing a global env-var switch per row isn't workable for daily
use. **Fix: make identifiers self-describing and make reads dispatch on the identifier itself, not on
whichever backend is currently selected for writes.**
- Every identifier `AzureBlobStorage.save_source()` returns is prefixed: `azblob:<key>` (e.g.
  `azblob:Sources/<property>/<category>/<uuid>_<filename>`). A local path never starts with `azblob:`,
  so the two are unambiguous by construction — no metadata lookup needed to tell them apart.
- Add two module-level functions in `document_storage.py`, independent of `get_document_storage()`:
  `read_source_document(identifier: str) -> bytes` and `source_document_exists(identifier: str) ->
  bool`. Each checks the `azblob:` prefix: if present, strip it and read/check via a lazily-constructed
  Blob client (built from `LUCIDPM_BLOB_CONNECTION_STRING`/`LUCIDPM_BLOB_CONTAINER`, independent of
  `LUCIDPM_STORAGE_BACKEND`'s value); if absent, treat it as a local path (`os.path.isfile`/`open`).
  All source/section read call sites (the two gate checks, the two merge-time reads, `page_count()`)
  go through these, not through `get_document_storage().read()/.exists()`.
- **`get_document_storage()` / `LUCIDPM_STORAGE_BACKEND` still decides where *new* writes go** — that
  part of the existing design is unchanged and correct. Only the read side becomes identifier-agnostic.
  This means a local machine needs `LUCIDPM_BLOB_CONNECTION_STRING` set (already true today — the
  account-key connection string has been sitting in the local, gitignored `.env` since Cycle 4.1)
  **regardless of `LUCIDPM_STORAGE_BACKEND`'s value**, if it's going to open any Blob-backed
  source/section row. If an `azblob:`-prefixed identifier is encountered and the connection string
  isn't set, raise a clear `RuntimeError` naming the missing variable — not a generic exception.
- **Explicitly not retrofitted onto the existing generated-package path** (`get_document_storage()`'s
  `azure_blob` branch, `AzureBlobStorage.save()`/its un-prefixed `Generated/...` keys) — that's
  deployed and working, Do Not Touch. The `azblob:` prefix convention is new, scoped to `save_source()`
  identifiers only.
- `TenantCRM` (Prod) is untouched by this handoff, so its local dev experience doesn't change at all.

**No Prod (`TenantCRM`) analysis done here** — this handoff's data-migration counts and verification
are Test-only. Prod migration is explicitly deferred (see Do Not Touch).

---

## The Fix

### Phase A — extend the storage abstraction (code, local-only, both backends proven)

1. Add a second save method to `DocumentStorage` (or a sibling interface, reusing `read`/`exists`
   as-is since those are already identifier-agnostic) for source/section documents — keyed by
   whatever `template_folder()`/`sections_folder()` already use (property + category), not by lease
   ID. Local implementation: reproduce today's exact paths (`Admin/<property>/<category>/...` and
   `.../Sections/...`) — genuinely byte-identical, the same standard H66's `LocalFilesystemStorage`
   was held to after three review rounds, not just "close enough." Blob implementation: its own
   collision-safe key scheme (e.g. `Sources/<property>/<category>/<uuid>_<filename>`), independent of
   the local path shape.
2. Rewire the three write functions (`save_uploaded_pdf`, `copy_existing_pdf`, `split_pdf_pages`) to
   go through `get_source_document_storage(storage_root).save_source(...)` instead of raw
   `open()`/`shutil.copyfile` — **not** `get_document_storage()`, which is rooted at `Generated\` and
   would double the path (see the new-factory note above). At each of the three `lease_documents.py`
   call sites, branch the `RelativePath`/`StorageRoot` write per the rule above (local: byte-identical
   `relative_to_root()`; blob: container name / de-prefixed key).
3. Add the `read_source_document(identifier) -> bytes` / `source_document_exists(identifier) -> bool`
   resolver functions in `document_storage.py` (see "Local dev after Phase B" above for the full
   design): dispatch on the `azblob:` prefix, lazily construct a Blob client from
   `LUCIDPM_BLOB_CONNECTION_STRING`/`LUCIDPM_BLOB_CONTAINER` independent of `LUCIDPM_STORAGE_BACKEND`,
   fall back to plain `os.path.isfile`/`open` for anything unprefixed. Clear `RuntimeError` (naming the
   missing env var) if an `azblob:` identifier shows up with no connection string configured.
4. Rewire every place that currently assumes a local path for a source/section identifier — this is
   more than the two gate checks:
   - The two generation-time gate checks (`1486`, `1742` in `lease_package_builder.py`):
     `os.path.isfile(p.file_path)` → `source_document_exists(p.file_path)`. (The two append sites,
     `1573`/`~2260`, need no change themselves — they just add the identifier to
     `pdf_paths_to_merge`; the actual read happens later, inside `merge_pdf_files()`.)
   - **`merge_pdf_files()`'s own internal loop** (`lease_documents_pdf.py:1174-1197`) — its
     `os.path.isfile(p)` missing-check becomes `source_document_exists(p)`, and its
     `reader = PdfReader(path)` becomes `reader = PdfReader(io.BytesIO(read_source_document(path)))`.
     This is the actual mixed-input fix: `pdf_paths_to_merge` entries that are local temp paths (from
     rendered text) fall through the resolver's local branch unchanged; entries that are
     `azblob:`-prefixed PDF-backed sections fall through the Blob branch — same loop, same signature,
     `merge_pdf_files()` still returns `(bytes, page_count)` exactly as before, so
     `save_generated_package()` and `/api/lease-generated-pdf` need no changes (see Do Not Touch).
   - **`split_pdf_pages()`'s own read of the source it's cutting from**
     (`lease_documents_pdf.py:231`): `reader = PdfReader(source_path)` becomes
     `reader = PdfReader(io.BytesIO(read_source_document(source_path)))` — the source document being
     split can itself already be Blob-backed after Phase A, independent of where the *split output*
     gets written.
   - `page_count()` (`~209-211`): `PdfReader(path)` becomes
     `PdfReader(io.BytesIO(read_source_document(path)))`.
5. Validate locally exactly like H66's checklist, plus the resolver specifically: both backends work
   for writes, byte-identical local default, collision behavior unchanged for local, collision-safe for
   Blob; **with `LUCIDPM_STORAGE_BACKEND=local` active, an `azblob:`-prefixed identifier still reads
   correctly** (proves the resolver isn't just following the write backend); removing
   `LUCIDPM_BLOB_CONNECTION_STRING` and pointing at an `azblob:` identifier raises the clear
   `RuntimeError`, not a stack trace; `import LucidPM.LucidPM` still exits 0.

**Commit Phase A on its own**, verified working with both backends against fresh/test data — before
touching any real `TenantCRM_Test` row.

### Phase B — migrate `TenantCRM_Test`'s existing files and rows

1. **Confirm the stale-path prerequisite is resolved first** (see What This Is) — run:
   ```sql
   SELECT COUNT(*) FROM dbo.LeaseDocumentSections WHERE StoredFilePath IS NOT NULL;
   SELECT COUNT(*) FROM dbo.LeaseDocumentSections
     WHERE StoredFilePath IS NOT NULL AND StoredFilePath NOT LIKE 'C:\Dell Inspirion%';
   SELECT COUNT(*) FROM dbo.LeaseSourceDocuments WHERE StoredFilePath IS NOT NULL;
   ```
   against `TenantCRM_Test` to get the real, current counts before estimating scope further — don't
   assume the ~16-row stale-path figure from the standing backlog item is the *total* row count that
   needs migrating; it's only the subset with the *old* root. Every row with a valid local path today
   still needs migrating to Blob — it just isn't blocked on the junction/bulk-update fix first.
2. Write a one-time migration script (`db/data_updates/` or a scratch script, Mark's call which).
   **The script must construct its own Blob writer directly** — instantiate `AzureBlobStorage` (or
   call `save_source()` against an explicitly-constructed Blob instance) rather than going through
   `get_document_storage()`, and never rely on `LUCIDPM_STORAGE_BACKEND` being set to `azure_blob`.
   `get_document_storage()` answers "where do new writes from the running app go," which is the wrong
   question for a migration script — if it were used here and someone ran the script in a normal
   local-default session (`LUCIDPM_STORAGE_BACKEND=local`, unset), it would silently write new *local*
   files and then update `TenantCRM_Test` rows to point at paths that only exist on that one laptop,
   corrupting the very rows it's supposed to fix. Read `LUCIDPM_BLOB_CONNECTION_STRING`/
   `LUCIDPM_BLOB_CONTAINER` directly and fail fast if either is missing — don't fall back to anything.
   For each row (both `LeaseSourceDocuments` and `LeaseDocumentSections`) with a non-null
   `StoredFilePath` that resolves to a real local file, **per row, in this order**:
   1. Resolve `property_name`/`document_category`. Both tables only carry a `PropertyID` (integer FK)
      — the Blob key needs the **name** (`Properties.PropertyName`), the same way the live admin UI
      already does it (`_property_name_for_id()`, `lease_documents.py`; `Properties(PropertyID,
      PropertyName)` confirmed directly). So the migration query needs a real join, not just the FK
      chase:
      - `LeaseSourceDocuments` row: `JOIN Properties ON Properties.PropertyID =
        LeaseSourceDocuments.PropertyID` for `PropertyName`; `DocumentCategory` is already a column on
        the row itself, no join needed for that half.
      - `LeaseDocumentSections` row: `LEFT JOIN LeaseSourceDocuments ON LeaseSourceDocuments.
        LeaseSourceDocumentID = LeaseDocumentSections.LeaseSourceDocumentID`, then the same `JOIN
        Properties` off *that* row's `PropertyID`, for both `PropertyName` and `DocumentCategory` —
        confirmed `LeaseDocumentSections` has neither column itself (see Current State).
      A `NULL PropertyID` on an otherwise linked source is the app's valid **General / All Properties**
      selection, not an orphan; use that label with the row's real category. **Use the fixed fallback
      bucket (`property_name="Unlinked"`, `document_category="Legacy"`) only when a non-null
      PropertyID fails to resolve, the source link is absent, or the category is absent.** Record
      `fallback_used = true` in the manifest for those genuinely orphaned rows, so they are easy to
      find and re-categorize by hand later if it matters.
   2. Read its bytes and compute a content hash (`sha256`).
   3. **Write the manifest entry with status `uploaded_pending_update`** — table, row ID, old
      `StoredFilePath`, old `RelativePath`, old `StorageRoot` (the full old triple, not just the path —
      rollback needs to restore the complete original row, not a partial one), content hash,
      `fallback_used` — **before** calling `save_source()`.
   4. Call the Phase A Blob `save_source()` (`kind="template"` for `LeaseSourceDocuments`,
      `kind="section"` for `LeaseDocumentSections`) to persist it, getting back the `azblob:`-prefixed
      identifier.
   5. `UPDATE` the row's `StoredFilePath` (to the new identifier), `RelativePath` (de-prefixed key), and
      `StorageRoot` (container name) per the Phase A write rule.
   6. **Update that same manifest entry's status to `migrated`** (or `failed` with the error, if the
      `UPDATE` didn't succeed) once step 5 commits. A manifest entry stuck at
      `uploaded_pending_update` after the script exits means exactly what it says: the Blob copy exists
      but the row was never updated to point at it — safe to re-run for those rows specifically (the
      Blob upload is redone, harmless) rather than ambiguous.
   **Do not delete the local files** — leave them in place as a fallback until Phase B is verified,
   matching this project's existing "archive, don't delete" discipline (`_vN` files, the H63 Fernet
   rotation keeping old keys until verified).
3. **The manifest (state transitions above, full old-row triple, `fallback_used`) is what makes the
   migration auditable and reversible** — Blob writes and the SQL `UPDATE` can't share one transaction,
   so there's no other way to know exactly what happened if the script stops partway through. Generate
   the rollback as a plain SQL script from the manifest, one statement per `migrated` row
   (`UPDATE ... SET StoredFilePath = <old>, RelativePath = <old>, StorageRoot = <old> WHERE ID = <row
   ID>`), and separately flag any `uploaded_pending_update` rows for manual follow-up (re-run or
   discard the orphaned Blob copy) rather than rolling them back automatically. Local files are
   untouched regardless, so rollback only ever needs to restore DB state.
4. **Dry-run first**: log what *would* migrate (row ID, old path, new key) without executing any
   `UPDATE` or Blob write, and review the list before running it for real.
5. After migration, spot-check a sample: download the Blob-stored version of a few rows and diff
   against the original local file, byte-for-byte (the manifest's content hash makes this a hash
   comparison, not a full re-download-and-diff, for the full set) — same verification discipline as
   Cycle 2.1's "row counts + FK/CHECK trust" checks, applied to file content instead of table rows.
6. **Deploy Phase A's code to the live container** — reusing the existing `lucidpm` app, no new
   resources: `[Mark]` build and push a new image tag (e.g. `ghcr.io/mslucido-lab/lucidpm:0.3.0`) from
   a checkout including Phase A's commit; `[Claude via az]` `az containerapp update -n lucidpm -g
   Lucido-Apps-RG --image ghcr.io/mslucido-lab/lucidpm:0.3.0`, wait for the new revision to reach
   `Healthy`; `[Mark verifies]` app loads normally, existing generated-package flow (H66/H67, untouched
   by this handoff) still works.
7. Re-run the exact failing scenario from the deployed container: generate Lease Package #2 (the one
   with the "General Lease" PDF-backed section) again, against `TenantCRM_Test`, and confirm it now
   succeeds.

---

## Do Not Touch

- **`TenantCRM` (Prod).** This handoff is Test-only, start to finish. Prod migration is a separate,
  later handoff, run only after Phase B is fully verified on Test — same sequencing the roadmap
  already specifies for Cycle 5.1 ("migrate Test DB and verify before Prod").
- **`save_generated_package()` and `/api/lease-generated-pdf`** (the `LeaseGeneratedDocuments` write
  and read paths from H66/H67) — already correct, already deployed, don't touch.
- **`get_document_storage()` itself** — unchanged, including its `generated_folder()` rooting.
  `get_source_document_storage()` is a new, separate function alongside it, not a modification.
- **`merge_pdf_files()`'s external contract** — its signature (`section_paths: Iterable[str] ->
  (bytes, int)`) and its callers (`save_generated_package()`, the `LeaseGeneratedDocuments` INSERT)
  don't change. Its **internal read loop is in scope** (see The Fix, Phase A step 4) — that's a
  narrower, precise carve-out, not a contradiction of "don't touch H66/H67's generated-package path":
  the function's job (merge N inputs into one PDF) and its output are identical, only how it reads each
  input changes.
- **Deleting local source/section files.** Keep them after migration, at least until Phase B is fully
  verified — this is real tenant-relevant document data, not disposable.
- **The admin "storage root" screen redesign.** The roadmap flags retiring/repurposing it as a
  separate, larger UX decision (Cycle 5.1's own note) — this handoff makes the *storage* correct
  underneath it, not the admin UI's shape.
- **Any new Container Apps infrastructure** — new environment, new secrets scheme, ingress/scaling
  changes, new resources. Phase B's final validation step (below) does require pushing a new image tag
  to the existing `lucidpm` app and updating it in place, exactly the plain image-update pattern H65/
  H67 already established — that is in scope, it's *new infra* that isn't. (An earlier draft of this
  handoff excluded any redeploy at all, which directly contradicted the "Done when" criterion below —
  corrected here.)

---

## Validation Checklist

**Phase A:**
- [ ] Both backends work locally for upload, copy, split, and generation-time read, byte-identical
      local default (same rigor as H66 — verify the *exact* local path, not just "no error").
- [ ] `split_pdf_pages`'s collision behavior is preserved locally (counter-suffix on a real collision)
      and is collision-safe on Blob (no overwrite, unique key per split).
- [ ] With `LUCIDPM_STORAGE_BACKEND=local` active, an `azblob:`-prefixed identifier still reads
      correctly through `read_source_document()`/`source_document_exists()` (proves the resolver
      dispatches on the identifier, not the active write backend).
- [ ] Removing `LUCIDPM_BLOB_CONNECTION_STRING` and resolving an `azblob:` identifier raises the clear
      `RuntimeError`, not a stack trace.
- [ ] `RelativePath`/`StorageRoot` are meaningful for both backends (local: unchanged; Blob: container
      name + de-prefixed key), not `NULL`.
- [ ] **A package generates successfully from a mix of a rendered-text section, a local-path PDF
      section, and an `azblob:`-prefixed PDF section in the same package** — proves `merge_pdf_files()`'s
      internal loop actually handles all three inputs in one merge, not just each in isolation.
- [ ] `split_pdf_pages()` successfully splits a source document whose own `StoredFilePath` is
      `azblob:`-prefixed (not just a local one).
- [ ] **A local upload/copy/split lands at `<root>\Admin\...` (no `Generated` segment) exactly as
      before** — proves `get_source_document_storage()` is rooted correctly and Phase A didn't
      accidentally route source writes through `get_document_storage()`'s `Generated\`-rooted instance.
- [ ] `import LucidPM.LucidPM` exits 0.

**Phase B:**
- [ ] Stale-path prerequisite confirmed resolved before running.
- [ ] Real row counts captured (Step 1's queries) before migrating.
- [ ] Migration script constructs its Blob writer explicitly and does not read
      `LUCIDPM_STORAGE_BACKEND` — confirmed by running it with that variable unset/`local` and checking
      no local files were written as a side effect.
- [ ] Both `LeaseSourceDocuments` and `LeaseDocumentSections` rows resolve `PropertyName` via the
      `Properties` join (not just a `PropertyID` passthrough) and `LeaseDocumentSections` rows resolve
      property/category via the `LeaseSourceDocumentID` join; a `NULL PropertyID` maps to General / All
      Properties, while missing source links, dangling non-null IDs, or missing categories are flagged
      `fallback_used` in the manifest and reviewed by hand.
- [ ] Migration manifest entry written with status `uploaded_pending_update` **before** each row's Blob
      upload and SQL `UPDATE`, transitioned to `migrated` (or `failed`) after — confirm by checking the
      manifest reflects partial, in-progress state if the script is interrupted early, and that every
      entry records the full old triple (`StoredFilePath`, `RelativePath`, `StorageRoot`), not just the
      old path.
- [ ] Rollback SQL generated from the manifest's `migrated` rows and reviewed (not executed, unless a
      rollback is actually needed); any `uploaded_pending_update` rows are flagged separately for manual
      follow-up, not silently rolled back.
- [ ] Dry run reviewed before the real run.
- [ ] Sample of migrated files verified byte-identical to their local originals (hash match).
- [ ] Local files still present after migration (not deleted).
- [ ] New image built, pushed, and deployed to the existing `lucidpm` app; revision reaches `Healthy`;
      existing H66/H67 generated-package flow still works post-deploy.
- [ ] **Lease Package #2 (the originally-failing case) now generates successfully against
      `TenantCRM_Test` from the deployed container.**

**Done when:** a PDF-backed lease package generates correctly from the live Container App against
`TenantCRM_Test`. Prod migration and any admin-UI rework remain open, tracked separately.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\document_storage.py               ← Phase A, extend the interface + new
                                                  get_source_document_storage() factory
                                                  (get_document_storage() itself unchanged)
  LucidPM\pages\lease_documents_pdf.py        ← Phase A (save_uploaded_pdf, copy_existing_pdf,
                                                  split_pdf_pages incl. its own PdfReader(source_path)
                                                  read, page_count, merge_pdf_files' internal read loop)
  LucidPM\pages\lease_package_builder.py      ← Phase A (gate checks ~1486/~1742; append sites
                                                  ~1573/~2260 unchanged, see Current State)
  db\data_updates\  (or a scratch script)      ← Phase B, one-time migration script — Test DB only
```

Reference material already in the repo:
```
Completed Handoffs\LucidoPM_ChatGPT_Handoff_66_DocumentStorageAbstraction.md   ← the interface this
                                                                                   handoff extends,
                                                                                   and its 3 review
                                                                                   rounds' lessons
CLAUDE.md — standing TOP-PRIORITY item                                          ← the stale-path
                                                                                   prerequisite
Undelivered Handoffs\Azure Migration Roadmap.md — Cycle 5.1                     ← this handoff pulls
                                                                                   that work forward
```
