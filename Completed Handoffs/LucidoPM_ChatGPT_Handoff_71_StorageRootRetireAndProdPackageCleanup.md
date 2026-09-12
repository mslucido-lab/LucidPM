# LucidoPM — ChatGPT Handoff 71
*Retire the admin storage-root screen's now-dead editable path (Cycle 5.1's last leftover) + remove
6 POC-testing lease packages from Production's Azure copy*
*Prepared: 2026-09-12; revised same day after review (deploy step for Part A, explicit
`LUCIDPM_SINGLE_DB` handling, and a manifest+rollback file for Part B's delete)*
*Completed: 2026-09-12. Final deployment is `lucidpm--0000007` on image `0.4.2`; see `docs/h71-validation.md`. Post-implementation corrections: Blob display state must be evaluated by the running Reflex backend rather than at module import during static export, and every deployment image must be built with the public `REFLEX_API_URL` build argument.*
*Azure Migration — Stage 5. Both parts LOW risk: Part A is UI-only, no schema/data change, but does
require a Container App redeploy to take effect live. Part B is a small, fully-identified,
hand-verified DELETE (6 rows + their 24 child rows) with a full-row manifest and reviewable rollback
SQL written before anything is deleted — not a database migration.*

---

## What This Is

Two pieces of Stage 5, combined because Part A falls directly out of Part B's own scope:

- **Part A — retire the storage-root screen's editable path.** H68/H69 (`Completed Handoffs/`)
  made `LUCIDPM_STORAGE_BACKEND=azure_blob` the deployed backend for source/section documents. When
  that backend is active, Admin Settings' "Lease document storage root" text input — and Lease
  Documents' "Files stored in: `<path>` [Edit in Settings]" badge — both still show and let you edit
  a local filesystem path that **does nothing**: `get_source_document_storage()`
  (`document_storage.py:194-207`) ignores `storage_root` entirely once the backend is `azure_blob`.
  Both H68 and H69 explicitly deferred this — this handoff is that follow-up. Unchanged from the
  original draft of this handoff.

- **Part B — a small, verified cleanup, not a migration.** This handoff originally proposed
  Cycle 5.2 as written in the roadmap: reload `TenantCRM`/`TenantCRM_Test` into fresh Azure SQL DBs
  from local, on the theory that local had drifted ahead since the 2026-09-06 Stage-1 load. **That
  theory was checked directly against both databases (row counts + per-table checksums, local SQL
  Express vs. Azure) and turned out to be backwards.** Local has not drifted ahead — Azure has. Every
  table where the two sides differ in row count has **more** rows on Azure, not local, and every one
  of those extra rows traces to a specific, identifiable testing session:
  - `Contacts`/`Tenants` (Test only) — extra rows, higher IDs than local's max, from Cycle 2.2's
    "full walkthrough" testing.
  - `LeaseGeneratedDocuments`/`LeasePackageSections` (both DBs) — extra rows dated 2026-09-11/09-12,
    from Cycle 4.2/H69's live package-generation testing.
  There is no real production data on local that Azure is missing. **The only thing worth carrying
  forward is what Azure already has correctly** — including the H68/H69 blob-path migration, which
  is exactly the content-only difference (`LeaseDocumentSections`/`LeaseSourceDocuments`, same row
  count) that a from-scratch reload would have destroyed. Per Mark's call, `TenantCRM_Test`'s test
  artifacts are left alone — a Test database picking up test rows is its actual job, not a defect.
  **Only `TenantCRM` (Production)** gets a cleanup, and only for the specific rows identified below —
  not a database rebuild.

---

## Current State

### Part A — the dead editable path, by file and line

`document_storage.py:194-207` (`get_source_document_storage`) branches on
`LUCIDPM_STORAGE_BACKEND`: `local` uses `storage_root` (rooted via `normalize_storage_root`);
`azure_blob` calls `_blob_storage()` and never looks at `storage_root` again. Same shape in
`get_document_storage()` (lines 180-191) for generated packages. This is correct and needs no
change — it's exactly why the UI now needs to stop implying the field matters in blob mode.

Two UI spots still show it as if it did:
- `pages/admin_settings.py:454-455` — a live `rx.input` bound to
  `AdminSettingsState.storage_root` / `set_storage_root`, with a warning callout at line 458
  ("Changing this path does not move existing files...") that fires on edit.
- `pages/lease_documents.py:3471` — `rx.hstack(rx.text("Files stored in:", ...),
  rx.text(LeaseDocumentState.storage_root, ...), rx.spacer(), rx.badge("Edit in Settings", ...))`.

Both read `AppSettings.LeaseDocumentStorageRoot` (`admin_settings.py:104-110`,
`lease_documents.py:911-949`) — a per-database, admin-editable value with a real purpose in `local`
mode. Nothing about that table or its plumbing needs to change; only what's rendered when the
deployed backend is `azure_blob`.

The file's own top-of-file planning comment (`lease_documents.py:172-185`, "Issue 10 - Storage
root: move out of Load tab into Admin Settings screen") describes exactly this field's *original*
design intent and is now stale twice over — the move it describes already happened, and this handoff
adds the blob-aware branch it didn't anticipate.

### Part B — exactly what's on Production that shouldn't be, verified row by row

Comparison method: connected directly to local SQL Express `TenantCRM` and Azure `TenantCRM`
(via the contained `lucidpm_app` login already used by the deployed app) and, for every `dbo` table,
compared row count and `CHECKSUM_AGG(BINARY_CHECKSUM(*))`. 32 of 41 tables are byte-identical. Of the
9 that differ:

| Table | Difference | What it actually is |
|---|---|---|
| `LeaseDocumentSections`, `LeaseSourceDocuments` | Same count, content differs | H68/H69's blob-path migration — **correct, keep as-is.** |
| `AIConfig`, `EmailConfig` | Same count, content differs | Fernet re-encryption produces different ciphertext for the same secret (random IV) — not a real value change. No action. |
| `SchemaChangeLog` | Same count, content differs | Independent trigger-logged timestamps on each side. Log-only, harmless. No action. |
| `AppSettings` | Local has 3 rows, Azure has 2 | Local still carries a stale `LocalEncryptionKey` row dated 2026-05-18 (untouched since); Azure's was deleted per H63's Fernet rotation. A rotation-runbook loose end on **local**, not a Prod cleanup item — noted, not fixed by this handoff. |
| **`LeaseGeneratedDocuments`, `LeasePackageSections`** | **Azure has 6 more / 24 more rows** | **The actual cleanup target — see below.** |

The 6 extra `LeaseGeneratedDocuments` rows, confirmed directly by `GeneratedOn` date and read one by
one:

| `LeaseGeneratedDocumentID` | `LeaseID` | `GeneratedFileName` | `GeneratedOn` |
|---|---|---|---|
| 2111 | 2093 | `Grace_Family_Fellowship_Church_Lease_Package_20260911.pdf` | 2026-09-11 18:08 |
| 2112 | 2093 | `Grace_Family_Fellowship_Church_Lease_Package_v8.pdf` | 2026-09-11 18:14 |
| 2113 | 1 | `3_Sons_Automotive_Lease_Package_20260911.pdf` | 2026-09-11 18:18 |
| 2114 | 1 | `3_Sons_Automotive_Lease_Package_v4.pdf` | 2026-09-11 18:19 |
| 2115 | 2092 | `4C_s_Mechanical_Lease_Package_20260912.pdf` | 2026-09-12 15:19 |
| 2116 | 2092 | `4C_s_Mechanical_Lease_Package_20260912.pdf` | 2026-09-12 15:20 |

All six fall inside the exact windows CLAUDE.md already documents as live-testing sessions against
Prod: Cycle 4.2's Gate 4 restart-survival proof (2026-09-11) and H69's Step 5 local-against-Prod
validation (2026-09-12, "generated and downloaded 4C's Option Extension Agreement... locally against
Prod"). Each has exactly 4 child rows in `LeasePackageSections` (verified: `SELECT COUNT(*) FROM
dbo.LeasePackageSections WHERE LeaseGeneratedDocumentID IN (2111,2112,2113,2114,2115,2116)` = 24,
matching the table-level diff exactly). No other table has an enforced foreign key to
`LeaseGeneratedDocuments` — the one FK that does exist
(`FK_LeaseGeneratedDocumentPieces_GeneratedDocuments`, on `LeaseGeneratedDocumentSections`) points at
a table with **zero rows total**, confirmed dead/superseded by `LeasePackageSections`, not a blocker.

Each row's `StoredFilePath` is a live Blob key in `lucidpm-documents`
(e.g. `Generated/2093/20260911_180812_8341378816134c27a3b5a91cb2b5f98a_Grace_Family_Fellowship_Church_Lease_Package_20260911.pdf`)
— real objects from real test generations, not broken references. Deleting the DB rows leaves those
Blob objects as harmless orphans; removing them too is an optional last step, not required for
correctness.

---

## The Fix

### Part A — blob-aware storage display (Codex; low risk; no DB change)

**1. `document_storage.py`** — add one small shared helper next to
`get_source_document_storage()` (after line 207), so both pages describe the backend the same way
instead of duplicating the env-var check:

```python
def is_blob_storage_backend() -> bool:
    """Whether source/section/generated documents are Blob-backed in this deployment."""
    return os.getenv("LUCIDPM_STORAGE_BACKEND", "local").strip().lower() == "azure_blob"


def storage_backend_label(storage_root: str | None = None) -> str:
    """Human-readable description of where documents live, for admin/status UI."""
    if is_blob_storage_backend():
        container = os.getenv("LUCIDPM_BLOB_CONTAINER", "lucidpm-documents")
        return f"Azure Blob Storage ({container})"
    from LucidPM.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT, normalize_storage_root

    return normalize_storage_root(storage_root or DEFAULT_DOCUMENT_ROOT)
```

**2. `pages/admin_settings.py`** — import the two new names (extend the existing
`lease_documents_pdf` import block, line 14, with a second import line), and replace the storage
card (lines 450-460) with a version that branches once, in Python, at component-build time (this is
a deployment-time env var, not per-request state — no `rx.cond` needed, same treatment as
`DEFAULT_DOCUMENT_ROOT` already gets):

```python
from LucidPM.document_storage import is_blob_storage_backend, storage_backend_label

USING_BLOB_STORAGE = is_blob_storage_backend()
```

```python
def _storage_settings_card() -> rx.Component:
    children = [rx.text("Lease document storage", size="4", weight="bold", color=BRAND_DARK)]
    if USING_BLOB_STORAGE:
        children += [
            rx.text(
                "Source PDFs, split sections, and generated packages are stored in Azure Blob "
                "Storage. This is a deployment-time setting and isn't editable here.",
                size="2", color="#666",
            ),
            rx.vstack(
                rx.text("Storage backend", size="1", color="#666"),
                rx.text(storage_backend_label(), size="2", weight="bold", color=BRAND_DARK),
                spacing="1", width="100%",
            ),
        ]
    else:
        children += [
            rx.text(
                "Root folder used for uploaded lease PDFs, split sections, and generated packages.",
                size="2", color="#666",
            ),
            rx.vstack(
                rx.text("Lease document storage root", size="1", color="#666"),
                rx.input(
                    value=AdminSettingsState.storage_root,
                    on_change=AdminSettingsState.set_storage_root,
                    placeholder=DEFAULT_DOCUMENT_ROOT, width="100%",
                ),
                spacing="1", width="100%",
            ),
            rx.cond(
                AdminSettingsState.storage_root_changed,
                rx.callout.root(
                    rx.callout.text(
                        "Changing this path does not move existing files. Move existing files "
                        "manually or old StoredFilePath references may break."
                    ),
                    color_scheme="orange", width="100%",
                ),
            ),
        ]
    return responsive_card(rx.vstack(*children, spacing="3", width="100%", align_items="start"), width="100%")
```

Then in `admin_settings_content()`, replace the inline `responsive_card(rx.vstack(...), width="100%")`
block (lines 450-460) with a call to `_storage_settings_card()`. Leave `save_settings()`
(lines 201-215) untouched — `storage_root` still defaults non-empty even when the input is hidden,
so its "required" check keeps passing trivially and Email/AI settings keep saving normally in blob
mode.

**3. `pages/lease_documents.py`** — extend the existing `document_storage` import (line 235) to
`from LucidPM.document_storage import is_blob_storage_backend, source_document_location,
storage_backend_label`, add the same module-level `USING_BLOB_STORAGE = is_blob_storage_backend()`,
and replace the badge block at lines 3470-3473:

```python
rx.box(
    rx.hstack(
        rx.text("Files stored in:", size="1", color="#666"),
        (
            rx.text(storage_backend_label(), size="1", weight="bold", color=BRAND_DARK)
            if USING_BLOB_STORAGE
            else rx.text(LeaseDocumentState.storage_root, size="1", weight="bold", color=BRAND_DARK)
        ),
        rx.spacer(),
        *([] if USING_BLOB_STORAGE else [rx.badge("Edit in Settings", color_scheme="gray", variant="soft")]),
        width="100%", align="center",
    ),
    style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
),
```

**4. Trim the stale "Issue 10" comment** (`lease_documents.py:172-185`) — it describes the move this
field already made into Admin Settings; delete it or shrink it to a one-line pointer at this
handoff, so a future reader isn't following planning notes for a design that shipped two handoffs
ago and just got its blob-aware follow-up.

**5. Deploy Part A to the live Container App.** The deployed `lucidpm` Container App is running
image `ghcr.io/mslucido-lab/lucidpm:0.3.0` (revision `lucidpm--0000004`, per H68) — a code-only fix
to `admin_settings.py`/`lease_documents.py`/`document_storage.py` does nothing for anyone using the
deployed app until a new image ships. This isn't optional cleanup; without it, the deployed app keeps
showing the editable local-path UI indefinitely. Same reusable-app, no-new-resources pattern H68 used
for its own Phase-A deploy:
1. **[Mark]** Build and push a new image tag from a checkout including Part A's commit:
   `ghcr.io/mslucido-lab/lucidpm:0.4.0`.
2. **[Claude via az]** `az containerapp update -n lucidpm -g Lucido-Apps-RG --image
   ghcr.io/mslucido-lab/lucidpm:0.4.0`; wait for the new revision to reach `Healthy`.
3. **[Mark verifies]** Open the deployed app's Admin Settings page and confirm it shows the read-only
   Blob-backend label, not the editable input — this is the actual proof Part A shipped, not just
   that it works when tested locally against `LUCIDPM_STORAGE_BACKEND=azure_blob`. Also spot-check
   Lease Documents' "Files stored in:" badge the same way, and confirm the existing generated-package
   flow (H66/H67/H68, untouched by this handoff) still works.

### Part B — remove the 6 identified test packages from Production (low risk; explicit ID list)

**Do not use a live date-range query for the actual delete.** The `GeneratedOn >= '2026-09-11'`
filter was how these 6 rows were *found* during this handoff's investigation — using it again at
delete time would pick up whatever real packages get generated between now and when this runs. The
delete targets the exact IDs already identified above, nothing computed at run time.

**Step 0 — set the process-level DB override, don't edit `.env`.** `get_conn()`
(`state.py:212-232`) applies `LUCIDPM_SINGLE_DB` as an override *before* the requested database name
even reaches the connection string: `target_db = SINGLE_DB_NAME or db` (line 216). This repo's local
`.env` currently sets `LUCIDPM_SINGLE_DB=TenantCRM_Test` — so calling `get_conn(PROD_DB_NAME)`
as-is would silently connect to `TenantCRM_Test` instead, and only the script's own `DB_NAME()` guard
(Step 2 below) would catch it and refuse. That's safe (fails closed, never touches the wrong
database) but a confusing way to find out. Set the override at the shell/process level, matching the
project's existing "process env vars in one shell, not a persistent `.env`" convention (same pattern
Cycle 2.2 used to point a session at Azure without changing the checked-in default):

**Wrap each invocation in its own `try`/`finally`, not one block covering both.** The env var must
clear even if the script throws — a bare `set` / two calls / `Remove-Item` in sequence leaves the
shell silently locked to `TenantCRM` if either call errors out first. But the dry run and `--commit`
must **not** be chained inside the same `try`, either — the entire point of a dry run is a human
reading its output (and the manifest/rollback files it writes) before deciding to proceed; chaining
both calls unconditionally would run `--commit` the instant the dry run's process exits cleanly, with
no review gate at all. Two separate blocks, review in between:

```powershell
$env:LUCIDPM_SINGLE_DB = "TenantCRM"
try {
    & .\.venv\Scripts\python.exe db\data_updates\2026-09-12_h71_remove_prod_poc_test_packages.py
}
finally {
    Remove-Item Env:\LUCIDPM_SINGLE_DB -ErrorAction SilentlyContinue
}
```

Read the dry run's console output and the manifest/rollback files it wrote (Step 3/4 below). Only
once that's reviewed and matches this handoff's Current State table:

```powershell
$env:LUCIDPM_SINGLE_DB = "TenantCRM"
try {
    & .\.venv\Scripts\python.exe db\data_updates\2026-09-12_h71_remove_prod_poc_test_packages.py --commit
}
finally {
    Remove-Item Env:\LUCIDPM_SINGLE_DB -ErrorAction SilentlyContinue
}
```

`-ErrorAction SilentlyContinue` on the `Remove-Item` covers the case where the variable was somehow
already gone (e.g. a prior run's `finally` already cleared it) — clearing must never itself throw
and mask the real error from the `try` block. Using `.\.venv\Scripts\python.exe` explicitly (not a
bare `python`) also avoids silently running against whatever interpreter happens to be first on
`PATH`, which may not have this project's dependencies (`pyodbc`, etc.) installed at all.

New script, `db/data_updates/2026-09-12_h71_remove_prod_poc_test_packages.py`, following the
existing H68/H69 dry-run-by-default convention **and their manifest+rollback discipline** — this
handoff's first draft argued the console dry-run output was itself enough of a record to skip a
manifest; on review, it isn't: the dry run as originally scoped only prints
`LeaseGeneratedDocumentID`/`LeaseID`/`GeneratedFileName`/`GeneratedOn` for the parent rows and a bare
count for the 24 child rows, not the full column set (notably `LeasePackageSections.Content` and
`ContentSnapshot`, the actual rendered clause text) needed to recreate them. Fixed below.

```python
"""Remove 6 POC-testing lease packages from Production (`TenantCRM`) that were generated directly
against Azure during Cycle 4.2 and H69 testing (2026-09-11/09-12) and never existed locally.

Identified by a direct row-by-row comparison against local SQL Express during Handoff 71's
preparation — see that handoff's Current State for the verification. Targets an explicit,
hand-verified ID list, not a live query, so this never touches a package generated after this
handoff was written. Run with LUCIDPM_SINGLE_DB=TenantCRM set (see the handoff) so this reaches
Production regardless of the local .env's usual TenantCRM_Test lock.

    python db/data_updates/2026-09-12_h71_remove_prod_poc_test_packages.py
    python db/data_updates/2026-09-12_h71_remove_prod_poc_test_packages.py --commit

Default is a dry run: prints the full rows that would be deleted and writes the manifest + rollback
SQL, but issues no DELETE. --commit additionally runs the DELETEs. Refuses to run against anything
but TenantCRM.
"""

TARGET_IDS = [2111, 2112, 2113, 2114, 2115, 2116]

DEFAULT_MANIFEST = Path(__file__).with_name("h71_prod_package_cleanup_manifest.json")
```

Logic:
1. `get_conn(PROD_DB_NAME)` (from `LucidPM.state`) with a `DB_NAME()` guard refusing anything but
   `TenantCRM` — same discipline as H68/H69's `_validate_prod_database`.
2. Read the **full current rows** (`SELECT *`, all columns — `LeaseGeneratedDocuments`:
   `LeaseGeneratedDocumentID`, `TenantID`, `LeaseID`, `GeneratedFileName`, `StoredFilePath`,
   `GeneratedOn`, `PackageNotes`; `LeasePackageSections`: `LeasePackageSectionID`,
   `LeaseGeneratedDocumentID`, `LeaseTemplateSectionID`, `SortOrder`, `IsIncluded`, `PieceID`,
   `Content`, `IsDirty`, `ContentSnapshot`, `SectionID` — confirmed live via `sys.columns`, not
   assumed from an older schema-history script) for `TARGET_IDS` and their `LeasePackageSections`
   children, re-read live rather than trusted from this handoff's cached numbers.
3. Write a gitignored JSON manifest (`h71_prod_package_cleanup_manifest.json`) containing both full
   row sets — this is the actual durable record, unlike the earlier console-only draft. `datetime2`
   values serialize as ISO 8601; `NULL` stays `null`.
4. From the manifest, write a reviewable rollback script
   (`h71_prod_package_cleanup_manifest.rollback.sql`): `SET IDENTITY_INSERT dbo.LeaseGeneratedDocuments
   ON;`, one `INSERT` per parent row with every column including the original
   `LeaseGeneratedDocumentID`, `SET IDENTITY_INSERT ... OFF;`, then the same pattern for
   `LeasePackageSections`/`LeasePackageSectionID`. String/text values (`Content`, `ContentSnapshot`,
   `PackageNotes`, `GeneratedFileName`, `StoredFilePath`) go through a `_sql_literal`-style escaper
   (single quotes doubled, `NULL` for `None`) — same helper shape as H68/H69's `_write_rollback`.
5. Dry run stops after Step 3/4 — no `DELETE`. `--commit`:
   ```sql
   DELETE FROM dbo.LeasePackageSections WHERE LeaseGeneratedDocumentID IN (2111,2112,2113,2114,2115,2116);
   DELETE FROM dbo.LeaseGeneratedDocuments WHERE LeaseGeneratedDocumentID IN (2111,2112,2113,2114,2115,2116);
   ```
   in that order (children first — `LeasePackageSections.LeaseGeneratedDocumentID` isn't a DB-enforced
   FK, but delete order should assume it is), in one transaction, committed only if both `DELETE`s'
   row counts match the manifest's counts (24 and 6) — same "assert the count, don't just run it"
   discipline as H68/H69's `AND StoredFilePath=?` guard. Abort and roll back on any mismatch.
6. Print the before/after row counts for both tables as the final confirmation, and the manifest/
   rollback file paths written.

**Optional, not required:** delete the 6 matching Blob objects from `lucidpm-documents`
(`Generated/2093/...`, `Generated/1/...` ×2, `Generated/2092/...` ×2 — the exact keys are each row's
`StoredFilePath`, already in the manifest). They're harmless orphans either way; clean them up only
if convenient, e.g. via Azure Storage Explorer, not worth its own script.

`.gitignore` needs two new lines, mirroring H68/H69's entries:
```
/db/data_updates/h71_prod_package_cleanup_manifest.json
/db/data_updates/h71_prod_package_cleanup_manifest.rollback.sql
```

---

## Do Not Touch

- **`TenantCRM_Test`.** Per Mark's call, its test artifacts (the extra `Contacts`/`Tenants`/package
  rows identified during this handoff's investigation) are left alone — a Test database
  accumulating test data is correct behavior, not something to clean up.
- **`document_storage.py`'s backend-selection logic** (`get_document_storage`,
  `get_source_document_storage`, `AzureBlobStorage`, `LocalFilesystemStorage`) — already correct,
  already proven on both Test and Prod (H68/H69). Part A only adds two small read-only helper
  functions next to it; nothing about how a backend is chosen or how documents are read/written
  changes.
- **`LeaseDocumentSections`/`LeaseSourceDocuments`'s blob-path content on Azure.** This is H68/H69's
  correct, already-verified migration — the one difference between local and Azure that should stay
  exactly as it is. Nothing in this handoff touches those two tables.
- **The stale local `LocalEncryptionKey` `AppSettings` row.** Real, but a local-only rotation
  loose end (H63), unrelated to Production's data correctness. Not fixed by this handoff — flag it
  separately if it's worth a five-minute cleanup later.
- **`h68_source_pdf_blob_manifest.json` / `h69_prod_source_pdf_blob_manifest.json` and their
  `.rollback.sql` files.** Untouched by this handoff; not relevant to Part B's scope anymore now
  that it isn't a data migration.
- **The live Container App's `LUCIDPM_SINGLE_DB=TenantCRM_Test` environment variable itself.** Part
  A's deploy step (Fix, step 5) only ships a new image; it does not change the Container App's env
  vars or its Test-only lock. Part B's `LUCIDPM_SINGLE_DB=TenantCRM` override is a **local shell-only**
  setting for running the cleanup script from a checkout — never set it on the Container App.
- **Entra/auth, custom domain, cutover-to-primary.** All separately tracked (Stage 5.3-5.5), out of
  scope here.

---

## Validation Checklist

**Part A**
- [ ] `LUCIDPM_STORAGE_BACKEND=azure_blob` locally → Admin Settings shows the read-only backend
      label, no editable input, no orange warning callout.
- [ ] `LUCIDPM_STORAGE_BACKEND=local` (or unset) → Admin Settings behaves exactly as before this
      handoff (editable input, warning callout on change) — this is a regression check, not just a
      new-mode check.
- [ ] Same two states checked on the Lease Documents "Files stored in:" badge — blob mode shows the
      container label with no "Edit in Settings" badge; local mode is unchanged from before.
- [ ] `save_settings()` still saves Email/AI config correctly in blob mode (the hidden `storage_root`
      field doesn't block the save).
- [ ] Stale "Issue 10" comment block trimmed or removed.
- [ ] New image tag built, pushed, and deployed to the live `lucidpm` Container App; revision reaches
      `Healthy`.
- [ ] **Verified against the deployed app itself, not just a local run** — the deployed Admin
      Settings page shows the read-only Blob-backend label, and the deployed Lease Documents page
      shows the container-label badge with no "Edit in Settings" badge.
- [ ] Existing generated-package flow (H66/H67/H68) still works against the deployed revision.

**Part B**
- [ ] `$env:LUCIDPM_SINGLE_DB = "TenantCRM"` set before both the dry run and `--commit`, each inside
      its own `try`/`finally` — confirm the script's own startup output reports connecting to
      `TenantCRM`, not `TenantCRM_Test`.
- [ ] `$env:LUCIDPM_SINGLE_DB` confirmed cleared (`Test-Path Env:\LUCIDPM_SINGLE_DB` returns `False`)
      after **both** invocations — including a deliberate check that the `finally` still clears it if
      a run is interrupted or errors out, not just on the success path.
- [ ] Dry run's printed row data (full columns, both tables) matches this handoff's Current State
      table exactly before running `--commit`.
- [ ] `DB_NAME()` guard confirmed to refuse any database other than `TenantCRM`.
- [ ] Manifest (`h71_prod_package_cleanup_manifest.json`) written and contains all 6 parent rows and
      24 child rows with every column populated (not just the subset printed to console) — spot-check
      that a `Content`/`ContentSnapshot` value round-trips correctly (not truncated/mis-escaped).
- [ ] Rollback SQL (`h71_prod_package_cleanup_manifest.rollback.sql`) reviewed — `IDENTITY_INSERT`
      wraps both tables' inserts, IDs match the manifest, string values are correctly escaped.
- [ ] `--commit` reports exactly 24 `LeasePackageSections` rows and 6 `LeaseGeneratedDocuments` rows
      deleted, matching the manifest's counts — a mismatch means stop and investigate, not proceed.
- [ ] Re-run the Part-B comparison query (row count + `CHECKSUM_AGG(BINARY_CHECKSUM(*))` per table,
      local vs. Azure `TenantCRM`) afterward — `LeaseGeneratedDocuments`/`LeasePackageSections`
      should now match local exactly; `LeaseDocumentSections`/`LeaseSourceDocuments` should still
      differ in content only (the migration, correctly preserved).
- [ ] `TenantCRM_Test` untouched — spot-check its row counts are unchanged from before this handoff.
- [ ] Lease 2093 (Grace Family Fellowship Church), Lease 1 (3 Sons Automotive), and Lease 2092 (4C's
      Mechanical) still generate packages normally after the cleanup — deleting old generated-package
      *history* rows shouldn't affect the ability to generate a new one.

**Done when:** Part A — the storage-root UI never implies a local path controls anything once the
backend is Blob, **and the fix is live in the deployed Container App**, not just verified locally.
Part B — `TenantCRM`'s `LeaseGeneratedDocuments`/`LeasePackageSections` match local's row counts
exactly, with the blob-path migration on `LeaseDocumentSections`/`LeaseSourceDocuments` still intact,
and a reviewed manifest + rollback script on disk before the delete ran.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\document_storage.py                                        ← Part A, add 2 helpers
  LucidPM\pages\admin_settings.py                                    ← Part A, storage card + import
  LucidPM\pages\lease_documents.py                                   ← Part A, badge + import + stale
                                                                          comment trim

  db\data_updates\2026-09-12_h71_remove_prod_poc_test_packages.py     ← Part B, new
  db\data_updates\h71_prod_package_cleanup_manifest.json              ← Part B, generated by the
                                                                          script (gitignored, entry
                                                                          added)
  db\data_updates\h71_prod_package_cleanup_manifest.rollback.sql     ← Part B, generated by the
                                                                          script (gitignored, entry
                                                                          added)
  .gitignore                                                          ← Part B, 2 new lines added,
                                                                          mirroring H68/H69's entries
```

Reference material already in the repo (read, don't modify):
```
Completed Handoffs\LucidoPM_ChatGPT_Handoff_68_SourcePdfBlobMigration.md      ← why
Completed Handoffs\LucidoPM_ChatGPT_Handoff_69_ProdSourcePdfBlobMigration.md     LeaseDocumentSections/
                                                                                  LeaseSourceDocuments
                                                                                  content differs
                                                                                  (correctly)
CLAUDE.md — Cycle 4.2 / H69 progress-log entries                             ← the two testing
                                                                                  sessions that
                                                                                  produced the 6 rows
```
