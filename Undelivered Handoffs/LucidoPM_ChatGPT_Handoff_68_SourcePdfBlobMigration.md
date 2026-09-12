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
class DocumentStorage(Protocol):
    def save(self, lease_id: int, filename: str, data: bytes) -> str: ...   # existing (H66)

    def save_source(self, property_name: str, document_category: str, filename: str, data: bytes) -> str:
        """Persist a source/section document. Each implementation decides its own
        collision handling — see the two call-site behaviors below, which differ
        from each other and must be preserved exactly."""

    def read(self, identifier: str) -> bytes: ...   # existing, identifier-agnostic, no change
    def exists(self, identifier: str) -> bool: ...  # existing, identifier-agnostic, no change
```
- `LocalFilesystemStorage.save_source()`: writes under `template_folder(property, category)` (or
  `sections_folder(...)` for splits — the caller picks which root to construct and passes it as part
  of `filename`'s path, or `save_source` takes an explicit `subfolder` param; decide the exact shape
  during implementation, but the *outcome* must be identical). For callers that already pass a
  timestamp-unique filename (`save_uploaded_pdf`, `copy_existing_pdf`), just write it — no extra
  logic needed. For `split_pdf_pages`, **port its exact counter-suffix loop into this method** (the
  same fix H66 gave `merge_pdf_files`/`LocalFilesystemStorage.save`) — don't leave the loop in
  `split_pdf_pages` itself calling a "does this exist" check against a storage abstraction that may
  not cheaply support that for Blob.
- `AzureBlobStorage.save_source()`: build its own collision-safe key for **all three** callers
  uniformly (e.g. `Sources/<property>/<category>/<uuid>_<filename>`, or
  `Sources/<property>/<category>/Sections/<uuid>_<filename>` for splits) — `overwrite=False`, full
  `uuid.uuid4().hex`, same reasoning as `AzureBlobStorage.save()` in H66. Don't try to reproduce the
  timestamp-suffix or counter-loop conventions for Blob; they're solving a local-disk problem that
  doesn't apply the same way to Blob's namespace.
- **`StorageRoot`/`RelativePath` at write time** (see Current State for why these are display-only,
  not read-path-critical): the three call sites in `lease_documents.py` that currently compute
  `rel = relative_to_root(stored_path, root)` need a backend branch. For the local backend, keep this
  byte-identical. For the Blob backend, **skip `relative_to_root()` entirely** (it's meaningless
  against a Blob key) — store `RelativePath = NULL` and set `StorageRoot` to a fixed sentinel (e.g.
  `"azure_blob"`) instead of the local root string, so a human looking at the row can tell which
  backend it belongs to without cross-referencing `LUCIDPM_STORAGE_BACKEND`.

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

**Local dev after Phase B — the backend must match how the target DB's rows were actually written,
same rule that already exists for `LeaseGeneratedDocuments` post-Cycle-4.2.** `DocumentStorage` has no
cross-backend dispatch — `LocalFilesystemStorage.read()` on a Blob key just fails, and vice versa
(confirmed by reading `document_storage.py`: `get_document_storage()` picks one backend for the whole
process from `LUCIDPM_STORAGE_BACKEND`, nothing inspects the identifier shape to route across
backends). This is an existing, accepted property of the design — not new. Once Phase B rewrites
`TenantCRM_Test`'s source/section rows to Blob keys, a local run against `TenantCRM_Test` with the
default `LUCIDPM_STORAGE_BACKEND=local` will show "Missing PDF" for every migrated row, even though
the original file is still sitting on disk (Do Not Touch forbids deleting it) — because the DB no
longer points at it. **This is not a new class of problem**: Cycle 4.1's validation notes already
established that local dev needs `LUCIDPM_STORAGE_BACKEND=azure_blob` (using the account-key
connection string already in the local, gitignored `.env`) to see Blob-backed rows, for generated
packages. Phase A doesn't change that contract, it just extends which document types follow it. No
new resolver/dual-backend logic — document the requirement, don't build around it: **after Phase B,
local work against `TenantCRM_Test` needs `LUCIDPM_STORAGE_BACKEND=azure_blob` set** (same `.env`
credential already proven working); local work against local SQL Server Express / local files is
unaffected (`LUCIDPM_STORAGE_BACKEND=local`, the default, stays correct for that). `TenantCRM` (Prod)
is untouched by this handoff, so its local dev experience doesn't change at all.

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
   go through the new storage method instead of raw `open()`/`shutil.copyfile`. At each of the three
   `lease_documents.py` call sites, branch the `RelativePath`/`StorageRoot` write per the rule above
   (local: byte-identical `relative_to_root()`; blob: `NULL` / `"azure_blob"` sentinel).
3. Rewire `page_count()` and the two generation-time gate checks (`1486`, `1742`) plus the two
   merge-time reads (`1573`, `~2260`) to use `storage.exists()` / `storage.read()` instead of
   `os.path.isfile()` / raw `PdfReader(path)`. `PdfReader` accepts a file-like object
   (`io.BytesIO(storage.read(identifier))`) exactly like H66's `merge_pdf_files()` already
   demonstrates for the local-vs-blob-agnostic read pattern.
4. Validate locally exactly like H66's checklist: both backends, byte-identical local default,
   collision behavior unchanged for local, collision-safe for Blob, `import LucidPM.LucidPM` still
   exits 0.

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
2. Write a one-time migration script (`db/data_updates/` or a scratch script, Mark's call which):
   for each row with a non-null `StoredFilePath` that resolves to a real local file, read its bytes,
   compute a content hash (e.g. `sha256`), call the Phase A storage method to persist it to Blob, and
   `UPDATE` the row's `StoredFilePath`/`RelativePath`/`StorageRoot` per the Phase A write rule (Blob
   sentinel + `NULL`). **Do not delete the local files** — leave them in place as a fallback until
   Phase B is verified, matching this project's existing "archive, don't delete" discipline (`_vN`
   files, the H63 Fernet rotation keeping old keys until verified).
3. **Write a migration manifest as the script runs** (CSV or JSON, committed alongside the script or
   kept as a durable artifact — Mark's call which): one row per migrated document with table, row ID,
   old `StoredFilePath`, new Blob key, content hash, and status (migrated / skipped / failed). Blob
   writes and the SQL `UPDATE` can't share one transaction, so this manifest is what makes the
   migration auditable and reversible — generate the rollback as a plain SQL script from the manifest
   (`UPDATE ... SET StoredFilePath = <old>, RelativePath = <old>, StorageRoot = <old> WHERE ID = <row
   ID>`) rather than trying to reconstruct it after the fact. Local files are untouched regardless, so
   rollback only ever needs to restore DB state.
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
- **The `LeaseGeneratedDocuments` pair from H66/H67** (`merge_pdf_files`, `save_generated_package`,
  `/api/lease-generated-pdf`) — already correct, already deployed, don't touch.
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
- [ ] `import LucidPM.LucidPM` exits 0.

**Phase B:**
- [ ] Stale-path prerequisite confirmed resolved before running.
- [ ] Real row counts captured (Step 1's queries) before migrating.
- [ ] Migration manifest (row ID, old path, new key, content hash, status) produced and reviewed;
      rollback SQL generated from it.
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
  LucidPM\document_storage.py               ← Phase A, extend the interface
  LucidPM\pages\lease_documents_pdf.py        ← Phase A (save_uploaded_pdf, copy_existing_pdf,
                                                  split_pdf_pages, page_count)
  LucidPM\pages\lease_package_builder.py      ← Phase A (lines ~1486, ~1573, ~1742, ~2260 area)
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
