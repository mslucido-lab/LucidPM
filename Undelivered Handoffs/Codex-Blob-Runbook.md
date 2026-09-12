# Codex Runbook — resume H69 (Prod source-PDF Blob migration)

Companion to `Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_69_ProdSourcePdfBlobMigration.md`. That
handoff is still the design of record — this runbook exists because the stale-path prerequisite
(H69 Step 0) turned up a real data problem mid-run that needed resolving before continuing, and this
captures exactly where things stand and what to do next so nothing has to be re-derived.

**Status (2026-09-12):** H69 is paused **before any Blob upload**. The revert in Step 1 below has not
been applied yet, and its input (the 17-row breakdown) has only been checked from one machine's shell
session, not saved anywhere durable — **Step 0 re-derives it independently before anything is written.**

---

## What happened, in order

1. H69's Step 0 stale-path repair ran as a **live SQL change against Azure `TenantCRM`** — not tracked
   in git, and not the same thing as `653d60c` (that commit only adds the migration script,
   `db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py`; verified via `git show --stat`,
   it touches exactly that one file). The repair repointed 17 rows (8 `LeaseSourceDocuments`, 9
   `LeaseDocumentSections`) from `C:\Dell Inspirion\...` to `C:\Users\msluc\OneDrive\Inspirion
   Backup\...` directly in the database — there is no commit that records it.
2. The Step 3 dry run then found **6 of those 17 rows** point to files that don't exist anywhere in the
   OneDrive backup: `LeaseSourceDocuments` 7 and 8; `LeaseDocumentSections` 51, 52, 62, and 63.
3. Investigation (this session, against the local filesystem) found a likely cause: **`C:\Dell
   Inspirion` still exists on this machine** — 962 PDFs, newest dated 2026-09-10 — and is *more
   current* than the OneDrive backup, which tops out at 2026-08-13. Mark's laptop migration was a
   cut-and-paste that landed the folder back at the same absolute path, which is presumably also what
   CLAUDE.md's older "Mark is unblocking locally by recreating the old path" note was describing.
4. A one-off check (this session, PowerShell, against local disk only) compared all 17 rows' current
   paths against both `C:\Dell Inspirion` and the OneDrive backup by existence and SHA-256 hash where
   both had a copy, and got a clean 8/3/6 split (see Step 0 below for the exact shape). **That check
   was never saved anywhere durable — Step 0 re-runs it as a real step, not something to take on
   faith from this write-up.**

---

## Step 0 — re-derive the 17-row breakdown (don't trust the summary above blindly)

Pull the current paths from Azure `TenantCRM`:
```sql
SELECT LeaseSourceDocumentID AS id, StoredFilePath FROM dbo.LeaseSourceDocuments
  WHERE StoredFilePath LIKE '%Inspirion Backup%' ORDER BY LeaseSourceDocumentID;
SELECT LeaseDocumentSectionID AS id, StoredFilePath FROM dbo.LeaseDocumentSections
  WHERE StoredFilePath LIKE '%Inspirion Backup%' ORDER BY LeaseDocumentSectionID;
```
For each row, check both candidate paths — the one already recorded (OneDrive backup) and its
`C:\Dell Inspirion` equivalent (replace the OneDrive root prefix with `C:\Dell Inspirion`) — for
existence, and hash both when both exist:
```powershell
$dellPath = $recordedPath -replace [regex]::Escape('C:\Users\msluc\OneDrive\Inspirion Backup'), 'C:\Dell Inspirion'
Test-Path -LiteralPath $recordedPath
Test-Path -LiteralPath $dellPath
# if both exist: Get-FileHash -Algorithm SHA256 on each, compare
```
Confirm the result matches what step 3-4 above described: 8 rows only in the OneDrive backup (no
action), 3 rows identical in both (no action), and exactly the 6 rows already named by the dry run
only present under `C:\Dell Inspirion`. **If this check turns up anything different — a 7th row, a
hash mismatch on one of the "identical" 3, anything — stop and re-assess before Step 1.** This
runbook's revert is only correct for the specific 6-row picture confirmed here.

## Step 1 — revert exactly the 6 broken rows, with an optimistic guard

Run against Azure `TenantCRM`, review the `SELECT`s inside the transaction, then commit:

```sql
BEGIN TRANSACTION;

UPDATE dbo.LeaseSourceDocuments
SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Users\msluc\OneDrive\Inspirion Backup', 'C:\Dell Inspirion')
WHERE LeaseSourceDocumentID IN (7, 8)
  AND StoredFilePath LIKE 'C:\Users\msluc\OneDrive\Inspirion Backup%';

UPDATE dbo.LeaseDocumentSections
SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Users\msluc\OneDrive\Inspirion Backup', 'C:\Dell Inspirion')
WHERE LeaseDocumentSectionID IN (51, 52, 62, 63)
  AND StoredFilePath LIKE 'C:\Users\msluc\OneDrive\Inspirion Backup%';

-- Confirm exactly 6 rows total (2 + 4) show the corrected C:\Dell Inspirion path before committing:
SELECT LeaseSourceDocumentID, StoredFilePath FROM dbo.LeaseSourceDocuments WHERE LeaseSourceDocumentID IN (7,8);
SELECT LeaseDocumentSectionID, StoredFilePath FROM dbo.LeaseDocumentSections WHERE LeaseDocumentSectionID IN (51,52,62,63);

-- COMMIT TRANSACTION;
-- ROLLBACK TRANSACTION;
```
The `AND StoredFilePath LIKE '...OneDrive\Inspirion Backup%'` guard means this only touches rows still
in the exact state Step 0 just confirmed — if any of the 6 changed between Step 0 and now, its
`UPDATE` affects 0 rows instead of blindly rewriting whatever's there. If either `UPDATE`'s row count
isn't what you expect (2 and 4 respectively), stop and check why before committing.

The other 11 rows need no change — confirmed correct as they stand (Step 0).

## Step 2 — lock the shell session to Prod before running any H69 command

**Confirmed directly in `LucidPM/state.py:212-216` (`get_conn`):** `target_db = SINGLE_DB_NAME or db`
— when `LUCIDPM_SINGLE_DB` is set, it overrides *every* connection regardless of what database name is
actually requested (the code comment above it says exactly this: "EVERY connection goes to it,
ignoring the `db=` argument"). The local, gitignored `.env` has `LUCIDPM_SINGLE_DB=TenantCRM_Test` —
so without overriding it, H69's script (which calls `get_conn(PROD_DB_NAME)`) would actually connect to
`TenantCRM_Test`, and its own `DB_NAME()` guard would then correctly refuse to proceed (not silently
touch Test — the guard catches this) but the run would just fail with a confusing "Refusing to
migrate 'TenantCRM_Test'" error. Set this once per shell session, before Step 3:
```powershell
$env:LUCIDPM_SINGLE_DB = 'TenantCRM'
```
This applies to **both** the migration script (Steps 4-5) and the local validation app run (Step 7) —
anywhere `get_conn()` is called in that shell session.

## Step 3 — open the maintenance window *first*

**Before the dry run, not after it.** The dry run's reviewed output (row count, fallback count, every
planned `azblob:` key) needs to stay valid all the way through commit and validation — a concurrent
edit between the dry run and the commit would make the reviewed list stale even though the run itself
is still individually row-safe. Stop the local app (or at minimum avoid any lease-document edits
against `TenantCRM`) now, and keep it stopped through Step 7 completing.

## Step 4 — dry run

```powershell
.\.venv\Scripts\python.exe db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py
```
Confirm the "missing" list is now empty and all 17 rows show a planned `azblob:` key. If anything is
still missing, stop — that means Step 0's picture was incomplete, not that it's safe to substitute a
file.

## Step 5 — commit

```powershell
.\.venv\Scripts\python.exe db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py --commit
```
Same per-row manifest/rollback safety net H69 already specifies.

## Step 6 — restore normal `LUCIDPM_SINGLE_DB` behavior before Step 7 if needed

Step 7's local validation just needs the app to be able to reach `TenantCRM` — leaving
`$env:LUCIDPM_SINGLE_DB = 'TenantCRM'` set for that same shell session is the simplest way to guarantee
that (no toggle needed, every connection goes straight to Prod). Only clear it (or start a fresh shell)
once Step 7 is done, to go back to normal local dev with the toggle available.

## Step 7 — local validation

Per H69 Step 5, with one addition: **specifically regenerate a package that includes one of the 6
previously-broken rows** (not just any PDF-backed package) — that's the actual proof this specific
problem is resolved, not just that the migration ran without error. Confirm it downloads correctly;
spot-check hashes for a sample that includes at least one of the 6.

## Step 8 — record it

Add a section to H69's evidence doc (mirroring `docs/cycle-5.1-early-validation.md`'s shape) covering
this whole detour — the 6-row mismatch, the root cause (a locally-recreated `C:\Dell Inspirion` newer
than the OneDrive backup), Step 0's re-derived breakdown, and the revert. This is a real, reusable
finding for any future stale-path work (including the eventual Test-side spot check and anything in
Stage 5), not just a one-off fix — see Lessons below.

---

## Lessons for future stale-path / backup work

- **The OneDrive backup is not unconditionally authoritative.** It's a point-in-time snapshot (stopped
  updating 2026-08-13) sitting alongside a separately-maintained live folder (`C:\Dell Inspirion`,
  still being added to as of 2026-09-10). A bulk path-rewrite that assumes "the old root is gone,
  redirect to the backup" needs to check whether the old root is actually gone first — it wasn't, here.
- **Before trusting a rewritten path, check existence (and hash, if both sides have a file) against
  every candidate source, not just the one the fix was written for** — and re-derive that check as an
  actual step when using it, rather than treating a one-off investigation from an earlier session as a
  durable record. That's the whole reason Step 0 exists above instead of just restating a conclusion.
- **A local, gitignored `.env` value can silently redirect a script that looks database-parameterized.**
  `LUCIDPM_SINGLE_DB` overrides `get_conn()`'s `db=` argument entirely — a script written to take a DB
  name explicitly (like H69's migration script) can still land on the wrong database if this env var is
  set from an unrelated purpose (here, locking the deployed container to Test). Check for this kind of
  override before assuming a script's own DB-name argument is authoritative.
- **This same risk applies to Test.** H68's ~16 Test rows went through the same style of stale-path
  repair. H68's own validation exercised specific packages successfully, which doesn't rule out other
  Test rows having the same OneDrive-vs-`C:\Dell Inspirion` mismatch on rows that validation didn't
  happen to touch. Worth a similar spot-check against Test at some point — not blocking, since Test's
  migration already succeeded for what it was tested against, but worth knowing about.
