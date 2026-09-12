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
  written by `save_uploaded_pdf()` / `copy_existing_pdf()` / `split_pdf_pages()`, read at package-
  generation time and by the admin Library's PDF viewer/preview.

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

**The write side**, all in `LucidPM/pages/lease_documents_pdf.py`, all raw local filesystem I/O today:
- `save_uploaded_pdf()` (~170-186) — new source-PDF uploads, `open(target, "wb")`.
- `copy_existing_pdf()` (~190-207) — duplicating an existing template's file, `shutil.copyfile`.
- `split_pdf_pages()` (~214+) — writes split section PDFs, `open(target, "wb")`, same shape as the
  original (pre-H66) `merge_pdf_files()`.
- `page_count()` (~209-211) — reads via `PdfReader(path)`, called both at generation-validation time
  and right after a split/upload to confirm the result.
- Path helpers already in this file, admin-configurable via `LeaseDocumentStorageRoot`:
  `template_folder()`, `sections_folder()`, `normalize_storage_root()`, `ensure_folder()` — these stay
  exactly as they are for the **local** backend, same reasoning H66 landed on after 3 rounds: don't
  reroute local's existing convention through a shared abstraction that forces a different shape.

**`DocumentStorage` already exists** (`LucidPM/document_storage.py`, Handoff 66/`cbf2038`) — `save`,
`read`, `exists`, two implementations. This handoff reuses the interface and the
`LUCIDPM_STORAGE_BACKEND` switch; it does **not** redesign it. The one interface question this
surfaces: H66's `save(lease_id, filename, data)` signature is generated-package-specific (keyed by
lease). Source/section documents are keyed by **property + document category** (`template_folder()`'s
existing convention) or by **source document ID** (for splits) — not by lease at all. Phase A needs a
`save(scope_key: str, filename: str, data: bytes)`-shaped call (or a second, source-specific method on
the same class) rather than reusing the lease-specific one as-is. Design this explicitly in Phase A,
don't bolt source documents onto the generated-package method's signature.

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
   go through the new storage method instead of raw `open()`/`shutil.copyfile`.
3. Rewire `page_count()` and the two generation-time gate checks (`1486`, `1742`) plus the two
   merge-time reads (`1573`, `~2260`) to use `storage.exists()` / `storage.read()` instead of
   `os.path.isfile()` / raw `PdfReader(path)`. `PdfReader` accepts a file-like object
   (`io.BytesIO(storage.read(identifier))`) exactly like H66's `merge_pdf_files()` already
   demonstrates for the local-vs-blob-agnostic read pattern.
4. Find and fix the admin Library's PDF preview/view path too (search `lease_documents.py` for
   wherever a source PDF gets opened for display, not just generation) — an unmigrated preview button
   is a smaller, quieter version of the same bug and easy to miss if this handoff only chases the
   generation error message.
5. Validate locally exactly like H66's checklist: both backends, byte-identical local default,
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
   call the Phase A storage method to persist it to Blob, and `UPDATE` the row's `StoredFilePath` to
   the returned Blob identifier. **Do not delete the local files** — leave them in place as a fallback
   until Phase B is verified, matching this project's existing "archive, don't delete" discipline
   (`_vN` files, the H63 Fernet rotation keeping old keys until verified).
3. **Dry-run first**: log what *would* migrate (row ID, old path, new key) without executing any
   `UPDATE`, and review the list before running it for real.
4. After migration, spot-check a sample: download the Blob-stored version of a few rows and diff
   against the original local file, byte-for-byte — same verification discipline as Cycle 2.1's
   "row counts + FK/CHECK trust" checks, applied to file content instead of table rows.
5. Re-run the exact failing scenario from the deployed container: generate Lease Package #2 (the one
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
- **Any Container App redeploy or Gate-4-adjacent infra work.** This is application code + a data
  migration; it doesn't need a new image build until Phase A is ready to actually run in the
  container, which is a natural follow-on step, not part of Phase A/B themselves.

---

## Validation Checklist

**Phase A:**
- [ ] Both backends work locally for upload, copy, split, and generation-time read, byte-identical
      local default (same rigor as H66 — verify the *exact* local path, not just "no error").
- [ ] The admin Library's PDF preview/view path also goes through the storage abstraction (Step 4).
- [ ] `import LucidPM.LucidPM` exits 0.

**Phase B:**
- [ ] Stale-path prerequisite confirmed resolved before running.
- [ ] Real row counts captured (Step 1's queries) before migrating.
- [ ] Dry run reviewed before the real run.
- [ ] Sample of migrated files verified byte-identical to their local originals.
- [ ] Local files still present after migration (not deleted).
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
  LucidPM\pages\lease_documents.py            ← Phase A (find + fix the PDF preview/view path)
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
