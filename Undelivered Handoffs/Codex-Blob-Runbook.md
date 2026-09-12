# Codex Runbook — resume H69 (Prod source-PDF Blob migration)

Companion to `Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_69_ProdSourcePdfBlobMigration.md`. That
handoff is still the design of record — this runbook exists because the stale-path prerequisite
(H69 Step 0) turned up a real data problem mid-run that needed resolving before continuing, and this
captures exactly where things stand and what to do next so nothing has to be re-derived.

**Status (2026-09-12):** H69 is paused **before any Blob upload**. The revert in Step 1 below has not
been applied yet.

---

## What happened, in order

1. H69's Step 0 stale-path repair ran against Azure `TenantCRM`, repointing 17 rows (8
   `LeaseSourceDocuments`, 9 `LeaseDocumentSections`) from `C:\Dell Inspirion\...` to
   `C:\Users\msluc\OneDrive\Inspirion Backup\...`, committed as `653d60c`.
2. The Step 3 dry run then found **6 of those 17 rows** point to files that don't exist anywhere in the
   OneDrive backup: `LeaseSourceDocuments` 7 and 8; `LeaseDocumentSections` 51, 52, 62, and 63.
3. Investigation (this session, against the local filesystem) found the real cause: **`C:\Dell
   Inspirion` still exists on this machine** — 962 PDFs, newest dated 2026-09-10 — and is *more
   current* than the OneDrive backup, which tops out at 2026-08-13. Mark's laptop migration was a
   cut-and-paste that landed the folder back at the same absolute path, which is presumably also what
   CLAUDE.md's older "Mark is unblocking locally by recreating the old path" note was describing.
4. All 17 rows' current (post-repair) paths were pulled from Azure `TenantCRM` and checked against
   **both** `C:\Dell Inspirion` and the OneDrive backup, by existence and SHA-256 hash where both had a
   copy. Full breakdown:
   - **8 rows** — only in the OneDrive backup, not in `C:\Dell Inspirion` at all (Sources 1-3, Sections
     35-39, all from May 2026). The repair was correct for these. **No action needed.**
   - **3 rows** — in both, byte-identical (Sources 4-6, June 2026). Doesn't matter which is referenced.
     **No action needed.**
   - **6 rows** — only in `C:\Dell Inspirion`, not in the OneDrive backup (Sources 7-8, Sections 51,
     52, 62, 63, all Aug 2026 — after the OneDrive backup's last update). **These need reverting** —
     exactly the same 6 the dry run already flagged. Nothing new turned up beyond what was already
     known.

---

## Step 1 — revert exactly the 6 broken rows

Run against Azure `TenantCRM`, review the `SELECT`s inside the transaction, then commit:

```sql
BEGIN TRANSACTION;

UPDATE dbo.LeaseSourceDocuments
SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Users\msluc\OneDrive\Inspirion Backup', 'C:\Dell Inspirion')
WHERE LeaseSourceDocumentID IN (7, 8);

UPDATE dbo.LeaseDocumentSections
SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Users\msluc\OneDrive\Inspirion Backup', 'C:\Dell Inspirion')
WHERE LeaseDocumentSectionID IN (51, 52, 62, 63);

-- Confirm exactly 6 rows show the corrected C:\Dell Inspirion path before committing:
SELECT LeaseSourceDocumentID, StoredFilePath FROM dbo.LeaseSourceDocuments WHERE LeaseSourceDocumentID IN (7,8);
SELECT LeaseDocumentSectionID, StoredFilePath FROM dbo.LeaseDocumentSections WHERE LeaseDocumentSectionID IN (51,52,62,63);

-- COMMIT TRANSACTION;
-- ROLLBACK TRANSACTION;
```

Do not touch the other 11 rows — confirmed correct as they stand (Step 4 above).

## Step 2 — re-run H69's dry run

```
.\.venv\Scripts\python.exe db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py
```
Confirm the "missing" list is now empty and all 17 rows show a planned `azblob:` key. If anything is
still missing, stop — that means this runbook's understanding of the data is incomplete, not that it's
safe to substitute a file.

## Step 3 — open the maintenance window (H69 Step 2)

Stop the local app / avoid any lease-document edits against `TenantCRM` from here through Step 5
completing below.

## Step 4 — commit

```
.\.venv\Scripts\python.exe db/data_updates/2026-09-12_h69_prod_source_pdf_blob_migration.py --commit
```
Same per-row manifest/rollback safety net H69 already specifies.

## Step 5 — local validation

Per H69 Step 5, with one addition: **specifically regenerate a package that includes one of the 6
previously-broken rows** (not just any PDF-backed package) — that's the actual proof this specific
problem is resolved, not just that the migration ran without error. Confirm it downloads correctly;
spot-check hashes for a sample that includes at least one of the 6.

## Step 6 — record it

Add a section to H69's evidence doc (mirroring `docs/cycle-5.1-early-validation.md`'s shape) covering
this whole detour — the 6-row mismatch, the root cause (a locally-recreated `C:\Dell Inspirion` newer
than the OneDrive backup), and the revert. This is a real, reusable finding for any future stale-path
work (including the eventual Test-side spot check and anything in Stage 5), not just a one-off fix —
see Lessons below.

---

## Lessons for future stale-path / backup work

- **The OneDrive backup is not unconditionally authoritative.** It's a point-in-time snapshot (stopped
  updating 2026-08-13) sitting alongside a separately-maintained live folder (`C:\Dell Inspirion`,
  still being added to as of 2026-09-10). A bulk path-rewrite that assumes "the old root is gone,
  redirect to the backup" needs to check whether the old root is actually gone first — it wasn't, here.
- **Before trusting a rewritten path, check existence (and hash, if both sides have a file) against
  every candidate source, not just the one the fix was written for.** That's what caught this: checking
  the *other* 11 rows (not just the 6 already flagged) confirmed the picture was complete rather than
  assuming the dry run's 6 were the whole story.
- **This same risk applies to Test.** H68's ~16 Test rows went through the same style of stale-path
  repair. H68's own validation exercised specific packages successfully, which doesn't rule out other
  Test rows having the same OneDrive-vs-`C:\Dell Inspirion` mismatch on rows that validation didn't
  happen to touch. Worth a similar spot-check against Test at some point — not blocking, since Test's
  migration already succeeded for what it was tested against, but worth knowing about.
