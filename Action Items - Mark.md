# Action Items — Mark

Things only Mark can do (runbooks, live-app verification, Azure resources, gate
decisions). Claude/Codex work is tracked in `CLAUDE.md` "Where We Left Off" and
`Undelivered Handoffs/Azure Migration Roadmap.md`; this file is the human
checklist. Update in place — check items off, add new ones.

*Last updated: 2026-09-08.*

---

## Now — unblocks the next Azure step

- [ ] **H72 Phase 1 — Entra sign-in and Reflex event-channel verification.** Mark and Gary
      are assigned to the `lucidpm` Enterprise Application; Paula remains deliberately unassigned
      for the denial test. From an IP currently allowed by the Container App, verify Mark can sign
      in and then navigate pages, open a record, and load/update live Test data. Verify Paula is
      denied. Do not remove IP restrictions or restore the Test/Prod toggle until this passes.
      Active Container Apps EasyAuth client-secret expiry: **2028-09-13 07:08 UTC**.

- [ ] **H63 Fernet key rotation runbook** (finishes Cycle 0.4 → Stage 0 complete).
      Code is committed (`cc9af6b`); this is the manual part. Order matters:
  1. `SELECT SettingValue FROM dbo.AppSettings WHERE SettingKey = 'LocalEncryptionKey';`
     on **both** `TenantCRM` and `TenantCRM_Test`. Record both (the May-2026
     export snapshots show them identical, but confirm against live).
  2. Generate a new key:
     `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  3. `.env` at repo root → `LUCIDPM_FERNET_KEY=<NEW>,<OLD_PROD>[,<OLD_TEST> if different]`
  4. Restart app. In Admin Settings, on **each** DB (toggle Prod/Test):
     re-enter + save the SMTP password, re-enter + save the Anthropic API key
     (4 saves total). Each re-encrypts under `<NEW>`.
  5. `.env` → `LUCIDPM_FERNET_KEY=<NEW>` only. Restart. Verify on both DBs:
     Email + AI show *configured*, a test email sends, "Test AI connection"
     succeeds. (If anything fails, put the old keys back — nothing deleted yet.)
  6. `DELETE FROM dbo.AppSettings WHERE SettingKey = 'LocalEncryptionKey';` on
     **both** DBs. Re-verify step 5's checks.
  7. **Delete the local files that carry the old key + ciphertext:**
     `db/TenantCRM_full.sql`, `db/TenantCRM_azure.sql`,
     `db/TenantCRM_Test_azure.sql` (gitignored — regenerate from Azure later if
     needed) **and** `C:\Inspirion\Dev\TenantCRM\Database\TenantCRM_Azure.bacpac`,
     `…\TenantCRM_Backup\`, `…\TenantCRM_Test_Backup\`.
  8. *(Recommended, independent)* rotate the actual SMTP app-password and
     Anthropic API key — they were recoverable in plaintext from those files.
  9. Tell Claude → move the H63 handoff to `Completed Handoffs/`, mark Stage 0
     complete in the roadmap.

- [ ] **Commit the untracked files** (or decide to leave them):
      `git add "Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_63_FernetKeyFromEnv.md"`
      (handoff doc was never committed); `Start-LucidPM.bat`, `Start-LucidPM.ps1`
      (your launcher scripts).

---

## Azure migration — next milestones

- [ ] **Cycle 2.2 / Gate 2 — local app against Azure SQL** (the real go/no-go
      before container work). Point the local app at Azure SQL using **process
      env vars in one shell** (not a persistent `.env`):
      `$env:LUCIDPM_SQL_SERVER='lucidpm-sql-24899.database.windows.net'`,
      `$env:LUCIDPM_SQL_AUTH='sql'`, `$env:LUCIDPM_SQL_USER='lucidadmin'`,
      `$env:LUCIDPM_SQL_TRUST_CERT='no'`, `$env:LUCIDPM_SQL_LOGIN_TIMEOUT='60'`,
      `$env:LUCIDPM_SQL_CONNECT_RETRIES='3'`; prompt for the password with
      `Read-Host -AsSecureString` (don't paste a quoted literal); run on ports
      3002/8002. Then:
  - [ ] Walk the major workflows: tenant/lease CRUD, rent schedules, property
        financials, analytics, lease-document generation, PDF generation.
  - [ ] **First real test of the SQL-auth connection string** — if login fails
        despite correct creds, suspect the `UID={}`/`PWD={}` brace-escaping in
        `state._odbc_brace`.
  - [ ] Note latency (local app → cloud DB is slower; confirm it's tolerable).
  - [ ] **H60 checklist D** — with the Azure Test DB idle-paused >60 min, start
        the app pointed at it, load a data page, record: wall-clock to first
        usable page, how many retries, which SQLSTATE(s), the exact
        `str(exc)` / `exc.args` of the first failure. Feed back into the H60
        defaults (bump `LUCIDPM_SQL_CONNECT_RETRIES` / `_RETRY_BACKOFF` if 9s of
        backoff is too short).
  - [ ] **Gate 2 decision:** any blocking pyodbc/Azure-SQL incompatibility or
        unworkable latency surfaces here, before container work starts.

- [ ] **H60 A/B/C acceptance checklist** (no Azure needed — can do anytime).
      Isolated subprocess checks of the transient-error predicate + retry loop
      against synthetic `pyodbc.OperationalError`s; wrong-password + unreachable-
      host fail-fast against a real local server. See the H60 doc in
      `Completed Handoffs/`.

- [ ] **Contained non-admin SQL user** for the cloud build — must be created in
      **both** `TenantCRM` and `TenantCRM_Test` (contained users are per-DB) if
      the Test/Prod toggle stays. Needed by Stage 3; `lucidadmin` is Cycle 2.2
      smoke-test only.

- [ ] **Install the Azure CLI locally** before Stage 3 (currently using Cloud
      Shell).

---

## Standing — do when ready

- [ ] **TOP PRIORITY — stale `StoredFilePath` in `dbo.LeaseDocumentSections`,
      both DBs.** Every PDF-only section's absolute path still points at the old
      laptop root `C:\Dell Inspirion\…` (~4 active rows in Prod, ~16 in Test) —
      blocks package generation for any document that includes one. Two fixes:
  - Quick / zero DB change: `mklink /J "C:\Dell Inspirion" "C:\Users\msluc\OneDrive\Inspirion Backup"`
  - Permanent: one-time `UPDATE … SET StoredFilePath = REPLACE(StoredFilePath,
    'C:\Dell Inspirion', 'C:\Users\msluc\OneDrive\Inspirion Backup')` across both DBs.
  - Should land before Azure Stage 5.1 regardless.

- [ ] **H54 Phase 3 follow-up** — once the local path/junction above is restored,
      click through one real batch PDF split in the app (the F3 "advance range,
      split again" happy path could not be exercised locally — every source PDF
      hits the stale root).

- [ ] **Sequence the queued feature handoffs** (all written, none started):
      H55 (merge-token catalog P1), H56 (retire the Load tab), H57 (Suite Rent
      PSF tab). Say when.

- [ ] Add a per-DB Azure metric alert: `Free amount remaining` < 10,000
      vCore-sec, on both `TenantCRM` and `TenantCRM_Test`.

---

## Done

- [x] 2026-09-08 — H61 (Cycle 0.1 scaffolding) implemented + committed `e20d735`.
- [x] 2026-09-08 — H62 (Cycle 0.2, retire file picker) implemented + committed
      `7f5e931` / `401b8c3`.
- [x] 2026-09-08 — H63 (Cycle 0.4 code) implemented + committed `cc9af6b`
      (rotation runbook still pending — see above).
