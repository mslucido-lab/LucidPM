# LucidoPM — ChatGPT Handoff 69
*Migrate `TenantCRM` (Production)'s source PDFs and split PDF sections to Blob — the Prod counterpart
to Handoff 68, deferred there on purpose*
*Prepared: 2026-09-12*
*Azure Migration — Stage 5.1, Prod half. HIGH risk: real tenant document data, no dry-run rehearsal
possible against Prod itself. LOW code risk: the storage abstraction is already implemented, reviewed
through 4 rounds, and proven correct on Test (Handoff 68, `Completed Handoffs/`).*

---

## What This Is

H68 extended `DocumentStorage` to source/section PDFs and migrated `TenantCRM_Test`'s existing rows —
deliberately Test-only throughout, with Prod explicitly deferred to "a separate, later handoff, run
only after Phase B is fully verified on Test." That verification is done (25 Test rows migrated,
hash-checked, Lease Package #2 generating live). This handoff is that deferred follow-up.

**This is almost entirely a data migration, not a code change.** Every piece of application code H68
built — `DocumentStorage`/`AzureBlobStorage`/`LocalFilesystemStorage` (`document_storage.py`), the
`azblob:`-prefixed identifier resolver (`read_source_document()`/`source_document_exists()`), the
`get_source_document_storage()` factory, and the fixed `merge_pdf_files()`/`split_pdf_pages()`/
`page_count()` — is already generic across databases. None of it knows or cares whether the active
connection is `TenantCRM` or `TenantCRM_Test`; that's decided the same way it always has been, by
LucidPM's existing Prod/Test toggle. **No changes to any of those files are in scope here.**

What *is* in scope: H68's migration script (`db/data_updates/2026-09-11_h68_source_pdf_blob_migration.py`)
is hardcoded to Test — verified directly, not assumed (see Current State). Reusing it for Prod means
writing a new, near-duplicate script, not flipping a flag on the existing one.

**A real constraint this handoff must respect, confirmed live this session:** the deployed `lucidpm`
Container App is still locked to `TenantCRM_Test` only —
```
$ az containerapp show -n lucidpm -g Lucido-Apps-RG --query "...env[?name=='LUCIDPM_SINGLE_DB']"
LUCIDPM_SINGLE_DB  TenantCRM_Test
```
(H65's design, unchanged since). **Prod is not reachable through the live container at all today.**
That means this handoff's validation is necessarily **local-only** — there is no live-container
equivalent of H68's "generate Lease Package #2 from the deployed app" step to run against Prod, and
this handoff does not add one. Exposing Prod through the container is Stage 5.3 (Entra auth) territory,
explicitly out of scope here (see Do Not Touch).

---

## Current State

**H68's migration script is Test-only by explicit, deliberate design — not an oversight to route
around quietly.** Read directly (`db/data_updates/2026-09-11_h68_source_pdf_blob_migration.py`):
- Imports `TEST_DB_NAME` (not a parameterized DB name) from `LucidPM.state` (line 35) and connects with
  `get_conn(TEST_DB_NAME)` (line 173) — the target database isn't a runtime argument at all.
- `_validate_test_database()` (lines 154-158) queries `SELECT DB_NAME()` and raises
  `RuntimeError(f"Refusing to migrate {actual!r}; H68 is Test-only ({TEST_DB_NAME!r}).")` if it isn't
  exactly `TenantCRM_Test`. This is a deliberate safety rail matching the project's Test-then-Prod
  discipline (Cycle 2.1's "verify Test, then repeat for Prod separately" pattern) — it is correct that
  this script refuses Prod, and it must **stay** refusing Prod after this handoff (see Do Not Touch).
- Default manifest/rollback paths (`h68_source_pdf_blob_manifest.json` /
  `h68_source_pdf_blob_manifest.rollback.sql`, both gitignored) and the rollback script's own header
  comment ("`TenantCRM_Test only`") are Test-specific artifacts, already the durable record of the real
  Test migration that ran. They must not be overwritten or reused for Prod's run.
- The actual migration logic (candidate row query with the `LeaseSourceDocuments`/
  `LeaseDocumentSections` → `Properties` join, `Unlinked`/`Legacy` fallback, per-row manifest state
  transitions `uploaded_pending_update` → `migrated`/`failed`, explicit `AzureBlobStorage` construction
  from `LUCIDPM_BLOB_CONNECTION_STRING`/`LUCIDPM_BLOB_CONTAINER` — never `LUCIDPM_STORAGE_BACKEND` —
  and the full old-row-triple rollback SQL) is exactly what all 4 rounds of H68's review converged on.
  **None of that logic needs to change for Prod.** The only things that need to differ are: which DB
  it connects to, which DB name the safety guard accepts, and which files it writes its manifest/
  rollback to.

**Prod's stale-path count needs re-verifying, not assumed from memory.** CLAUDE.md's backlog
previously noted "~4 active rows in Prod" with the old `C:\Dell Inspirion\...` root, from before H68's
work. That figure predates this session's cleanup activity and should not be trusted as current — Step
0 below re-runs the same counting queries H68 used, against `TenantCRM` this time, as the first real
step, not an assumption. (H68's original query counted rows *not* matching the old prefix, which
answers "how many non-stale rows exist," not "is the prerequisite satisfied," directly — Step 0's
query below fixes that.)

**The Blob container is shared, and that's fine.** Both Test's already-migrated rows and Prod's
new rows live in the same `lucidpm-documents` container — there's no collision risk: every key
includes a full `uuid.uuid4().hex` (see `AzureBlobStorage.source_identifier()`,
`document_storage.py`), so even a Prod property/category pair that happens to match a Test one
produces a distinct key. No new container, no new credential — this handoff reuses
`LUCIDPM_BLOB_CONNECTION_STRING`/`LUCIDPM_BLOB_CONTAINER` exactly as already configured.

---

## The Fix

### Step 0 — confirm the stale-path prerequisite for Prod

Run against `TenantCRM` (not `TenantCRM_Test`):
```sql
SELECT COUNT(*) FROM dbo.LeaseDocumentSections WHERE StoredFilePath IS NOT NULL;
SELECT COUNT(*) FROM dbo.LeaseDocumentSections
  WHERE StoredFilePath LIKE 'C:\Dell Inspirion%';
SELECT COUNT(*) FROM dbo.LeaseSourceDocuments WHERE StoredFilePath IS NOT NULL;
SELECT COUNT(*) FROM dbo.LeaseSourceDocuments
  WHERE StoredFilePath LIKE 'C:\Dell Inspirion%';
```
The second and fourth queries directly count rows still on the stale prefix — a `LIKE` match, not a
`NOT LIKE` exclusion — so a non-zero result there directly answers "is the prerequisite still
unresolved," rather than requiring a subtraction from the total. (H68's original phrasing used `NOT
LIKE`, which counts non-stale rows instead — harmless for a migration that already succeeded, but
worth stating correctly here rather than copying it forward.) If either stale count is non-zero,
resolve that first — same two options CLAUDE.md already documents (junction, or the one-time bulk
`UPDATE ... REPLACE(...)`) — against Prod specifically. A row unreadable locally cannot be migrated to
Blob any more for Prod than it could for Test.

### Step 1 — write a new, Prod-targeted migration script

**Do not edit `2026-09-11_h68_source_pdf_blob_migration.py` in place.** Copy it to a new file,
`db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py`, and make exactly these changes —
**diff the new file against the old one when done and confirm no other line differs**:

1. Import `PROD_DB_NAME` instead of `TEST_DB_NAME` from `LucidPM.state` (`document_storage.py`
   already exposes both; `LucidPM.state` is where H58 defined them).
2. `_validate_test_database()` → rename to `_validate_prod_database()`; guard against
   `PROD_DB_NAME` instead of `TEST_DB_NAME`, same error-message shape:
   `f"Refusing to migrate {actual!r}; this script is Prod-only ({PROD_DB_NAME!r})."` — the safety
   rail's *purpose* (refuse to run against the wrong database) stays identical, only which database
   it accepts flips. Note this replacement text already drops the old script's "H68 is Test-only"
   wording (line 158) — one of the three self-references point 5 finishes.
3. `main()`'s `get_conn(TEST_DB_NAME)` → `get_conn(PROD_DB_NAME)`.
4. `DEFAULT_MANIFEST` → a new filename, `h69_prod_source_pdf_blob_manifest.json` (the `--rollback-out`
   default already derives from `--manifest`'s stem, so it follows automatically as
   `h69_prod_source_pdf_blob_manifest.rollback.sql` — no separate change needed there).
5. **Replace every "Test"/"TenantCRM_Test"/"H68" reference that identifies this script with
   "Production"/"TenantCRM"/"H69"** — docstring, print statements, CLI `--help` text, and any error or
   header text the script emits. Confirmed by grepping the source: this is 3 exact spots, not a vague
   "swap the wording" instruction —
   - Line 135, `_write_rollback()`'s header comment: `"-- H68 rollback: review before running.
     TenantCRM_Test only."` → `"-- H69 rollback: review before running. TenantCRM only."`
   - Line 158, `_validate_test_database()`'s error message — already replaced by point 2 above (no
     "H68" survives in the new text).
   - Line 166, `_require_blob_writer()`'s error message: `"H68 migration requires both
     LUCIDPM_BLOB_CONNECTION_STRING and LUCIDPM_BLOB_CONTAINER; it never uses
     LUCIDPM_STORAGE_BACKEND."` → `"H69 migration requires both LUCIDPM_BLOB_CONNECTION_STRING and
     LUCIDPM_BLOB_CONTAINER; it never uses LUCIDPM_STORAGE_BACKEND."`
   After this step, `grep -n "H68\|TenantCRM_Test" db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py`
   should return nothing — run that grep as the actual check, don't eyeball it.
6. Everything else — the candidate query, the `Properties` join, the `Unlinked`/`Legacy` fallback, the
   manifest state machine, the per-row transaction with the optimistic `AND StoredFilePath=?` guard,
   the collision-safe Blob key construction — **stays byte-identical**. This is the point of the
   diff-review in this step's opening instruction: if the diff shows anything beyond the 5 points
   above, that's a red flag to stop and re-check before running it against real tenant data.

`.gitignore` already covers this script's output (`h69_prod_source_pdf_blob_manifest.json` /
`.rollback.sql`, mirroring H68's two entries) — done as part of writing this handoff, no separate step
needed.

### Step 2 — open a short maintenance window

The script protects each row it touches (the manifest sequencing plus the optimistic
`AND StoredFilePath=?` guard on its `UPDATE` means a genuinely concurrent edit to a row already in
flight fails loudly rather than corrupting anything) — but that's row-level safety, not a substitute
for avoiding concurrent activity altogether. A source-PDF upload, replacement, or split against Prod
while this runs could add or alter rows outside the snapshot Step 1's script read at start-up, or just
make the dry run's reviewed output (Step 3) stale by the time `--commit` (Step 4) actually runs.
**Stop the local app (or at least avoid any lease-document edits against `TenantCRM`) from immediately
before Step 3 through Step 5's validation completing.** This is real tenant data with no second
database to fall back on if the run and normal usage interleave in a confusing way — a short window
costs little and removes the ambiguity entirely.

### Step 3 — dry run

```
.\.venv\Scripts\python.exe db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py
```
(no `--commit` — this is the script's default). Review the printed row count, the fallback count, and
every planned `azblob:` key. **Do not proceed to Step 4 until this list has been read and makes
sense** — this is the one rehearsal Prod gets; unlike Test, there's no second real database to
practice on first.

### Step 4 — commit

```
.\.venv\Scripts\python.exe db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py --commit
```
Same per-row safety net as H68: a manifest entry (`uploaded_pending_update`) is written before each
row's Blob upload and SQL `UPDATE`, transitioned to `migrated` (or `failed`, rolling back that row's
transaction) once the `UPDATE` commits. **Do not delete local files** — same discipline as H68, they
stay as a fallback.

### Step 5 — local validation (this handoff's actual "does it work" proof)

Since the live container can't reach Prod (see What This Is), validate locally through the existing
Prod/Test toggle:
1. Run the local app with `LUCIDPM_STORAGE_BACKEND=azure_blob` and `LUCIDPM_BLOB_CONNECTION_STRING`/
   `LUCIDPM_BLOB_CONTAINER` set (the same local `.env` values already used for Cycle 4.1's local Blob
   testing).
2. Switch to Prod in the app.
3. Regenerate (or generate fresh, if none previously existed) a Prod lease package that includes a
   PDF-backed section — ideally the same kind of package that would have hit "Missing PDF files for
   these PDF-only sections" before this migration.
4. Confirm it generates and downloads correctly.
5. Spot-check: pick a few migrated rows, download their Blob objects directly, and diff against the
   still-present local originals (the manifest's `sha256` field makes this a hash comparison, not a
   full byte diff, for the rest).

### Step 6 — explicitly NOT part of this handoff

Validating this against the *deployed container* requires either lifting `LUCIDPM_SINGLE_DB` or adding
a second, Prod-facing deployment — both are real decisions (auth, ingress exposure) that belong to
Stage 5.3, not this migration. **Done for this handoff means "Prod's data is correctly in Blob and
generates correctly locally," not "Prod is live in the container."** Don't let Step 5 passing be read
as more than that.

---

## Do Not Touch

- **`TenantCRM_Test` and its H68 artifacts.** Already migrated, already verified. Don't re-run
  anything against it, and don't edit or delete `2026-09-11_h68_source_pdf_blob_migration.py`,
  `h68_source_pdf_blob_manifest.json`, or `h68_source_pdf_blob_manifest.rollback.sql` — they're the
  durable record of what actually happened to Test.
- **`document_storage.py`, `lease_documents_pdf.py`, `lease_package_builder.py`.** Already correct,
  already proven on Test. Zero application-code changes are in scope for this handoff — if anything
  here looks like it needs to change to support Prod, that's a sign something is being misunderstood,
  not a real requirement (the abstraction was built to be database-agnostic from the start).
- **The `lucidpm` Container App / `LUCIDPM_SINGLE_DB`.** Do not remove or change this lock to make
  Prod reachable through the container — that's Stage 5.3 (Entra auth), a separate, larger decision.
- **Local source/section files.** Never delete, before or after migration — same discipline as H68.
- **The admin "storage root" screen redesign.** Still a separately-tracked, later UX decision, not
  touched by this migration either.

---

## Validation Checklist

- [ ] Stale-path prerequisite counts re-run fresh against `TenantCRM` (Step 0) — not assumed from the
      old "~4 rows" backlog note.
- [ ] New script diffed against `2026-09-11_h68_source_pdf_blob_migration.py`; only the 5 enumerated
      changes present (DB name import, guard function, `get_conn` target, manifest filename,
      Test→Prod text) — no incidental logic drift.
- [ ] `grep -n "H68\|TenantCRM_Test" db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py`
      returns nothing — no leftover self-references identifying the script as H68 or Test-only.
- [ ] Dry run reviewed before `--commit`.
- [ ] Manifest and rollback SQL written to the new `h69_prod_...` filenames — the Test manifest/
      rollback files are untouched (check their mtimes/contents didn't change).
- [ ] Every migrated row's manifest entry reaches `migrated` (or is investigated if stuck at
      `uploaded_pending_update`/`failed`).
- [ ] Local app stopped / lease-document edits against `TenantCRM` avoided from before the dry run
      through validation completing (Step 2).
- [ ] Sample of migrated Prod rows verified byte-identical to their local originals (hash match).
- [ ] Local Prod source/section files still present (not deleted).
- [ ] **A PDF-backed Prod lease package generates and downloads correctly locally** (Step 5) — this is
      the actual proof, since the container path isn't available.
- [ ] `TenantCRM_Test` unaffected — spot-check its row count/timestamps are unchanged.
- [ ] Live Container App's `LUCIDPM_SINGLE_DB` still reads `TenantCRM_Test` — confirm nothing in this
      work accidentally changed it.

**Done when:** every Prod row that had a valid local source/section PDF is Blob-backed, verified
byte-identical, and a PDF-backed Prod package generates correctly through the local app. Container-level
Prod access and any admin-UI rework remain explicitly out of scope, tracked separately (Stage 5.3 and
the standing storage-root UI item, respectively).

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  db\data_updates\2026-09-12_h69_prod_source_pdf_blob_migration.py   ← new, Step 1 (copy + 5 edits)
  db\data_updates\h69_prod_source_pdf_blob_manifest.json             ← new, generated by --commit
                                                                         (gitignored, entry added)
  db\data_updates\h69_prod_source_pdf_blob_manifest.rollback.sql     ← new, generated by --commit
                                                                         (gitignored, entry added)
  .gitignore                                                          ← 2 new lines added, mirroring
                                                                         H68's entries
```

Reference material already in the repo (read, don't modify):
```
Completed Handoffs\LucidoPM_ChatGPT_Handoff_68_SourcePdfBlobMigration.md   ← the design this handoff
                                                                               reuses verbatim, and its
                                                                               4 review rounds' lessons
db\data_updates\2026-09-11_h68_source_pdf_blob_migration.py                ← the script this one is
                                                                               copied from
docs\cycle-5.1-early-validation.md                                         ← H68's Test-side evidence,
                                                                               the template this
                                                                               handoff's own evidence
                                                                               doc should follow
CLAUDE.md — standing backlog                                               ← "Source/section PDF Blob
                                                                               migration - Test passed;
                                                                               Prod remains pending"
```
