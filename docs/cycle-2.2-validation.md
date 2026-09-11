# Cycle 2.2 / Gate 2 — LucidPM local app against Azure SQL

**Goal:** confirm the app works correctly and tolerably against Azure SQL over `sql` auth, and
capture the cold-resume-from-auto-pause latency that tunes the Handoff 60 retry defaults.

Run with **process env vars in one PowerShell shell**, ports **3002 / 8002** (see the recipe in
`.env.example` / the completed H58 doc). Do **not** put the Azure connection in `.env`.

- Server `lucidpm-sql-24899.database.windows.net`, user `lucidpm_app` (contained,
  `db_datareader` + `db_datawriter`, created 2026-09-09 via `db/azure_app_user.sql`).
- Azure DB copies predated the 2026-09-09 Fernet rotation → their `EmailConfig` / `AIConfig`
  ciphertext was under the **old** key (`InvalidToken` on inbox load). **Resolved 2026-09-09** by
  re-entering the SMTP password + Anthropic key in Admin Settings while connected to Azure and
  saving — re-encrypts under the new key (which is in `.env`). No old key needed. This doubled as
  the write-path test (section C).

---

## A. Connection + startup

- [x] App launches on 3002/8002 against Azure SQL (`sql` auth), via the contained `lucidpm_app`
      user. — 2026-09-09/10, including a clean re-launch via `Start-LucidPM-Azure.ps1`.
- [x] Sidebar DB banner shows the correct database. Confirmed via the Test→Prod toggle (section F).
- [x] No `ConfigError` at startup; no ODBC errors outside the expected transient cold-resume ones
      (section E), which recovered cleanly.

## B. Read workflows (each should load with Azure data)

- [x] Every page in the app loads with Azure data (Tenants, Leases, Properties, Rent Roll,
      Property Financials, Property Financials Analytics, Work Items, Leases Expiring). — 2026-09-09,
      confirmed directly: "it looks like every page loads." Property Financials Analytics threw
      transiently early on (a cold-resume window, see section E) then normalized — not re-verified
      page-by-page in isolation, but no persistent failures were reported anywhere.
- [x] Communications — inbox loads (IMAP) after secret re-save; AI (Anthropic) reachable. — 2026-09-09

## C. Write workflows

- [x] Write via the contained `lucidpm_app` user (not `lucidadmin`): re-saved SMTP password +
      Anthropic key in Admin Settings against Azure `EmailConfig` / `AIConfig`, encrypted under the
      new Fernet key, then read back + used successfully by Communications. — 2026-09-09
- [x] Bulk write: ran a **tally import** against Azure (multi-row insert through `lucidpm_app`),
      then restarted the backend server and reloaded the web page — data verified saved. — 2026-09-09.
      This supersedes the originally-planned single-tenant-create / single-lease-edit checks as a
      stronger write-path test; those specific narrow round-trips were not separately re-verified.
- [ ] Application report PDF — not exercised this cycle. Not a Gate 2 blocker (same connection/write
      path as everything else that passed); pick up on a future touch of the app.

## D. Lease document generation

- [ ] Not exercised this cycle. Not a Gate 2 blocker — it's the same read/write path already
      validated elsewhere, and any failure here is more likely to be the standing stale-path data
      issue (`C:\Dell Inspirion\...`) than an Azure connectivity problem. Pick up on a future touch.

## E. Latency + cold resume  ← the Gate 2 measurement — DONE 2026-09-10

- [x] **Warm query latency** — no complaints once the app had spun up; page-to-page navigation
      not separately timed, but nothing was flagged as slow after the initial warm-up.
- [x] **Cold resume, attempt 1 (shipped defaults `retries=2`/`backoff=3`, ~9s budget):** app hung
      after 2 failed retry attempts and had to be restarted. **Confirmed the shipped defaults are
      too small** for a real resume.
- [x] **Cold resume, attempt 2 (bumped to `retries=8`/`backoff=4` via `Start-LucidPM-Azure.ps1`,
      ~144s budget):**
  - App start after an overnight pause (laptop had been shut down): **~20-30s**, 2 retry lines
    logged (`SQLSTATE HY000`, native code embedded), succeeded on attempt 3. No error.
  - DB toggle Test→Prod: **1m18s (78s)**. Console showed retry sequences for BOTH `TenantCRM_Test`
    and `TenantCRM` — both databases were cold at once (idle since the overnight gap), and the
    toggle's re-render fires several independent `get_conn(self.current_db)` calls that landed on
    both sides of the flip. Both resumed successfully, independently, no error.
  - **Confirms an open H60 review question:** the native-code substring match (not just the exact
    SQLSTATE set) is what's catching these — this ODBC build does format the `40613`-style code in
    the message text.
- [x] **New defaults locked in** — `LUCIDPM_SQL_CONNECT_RETRIES=8` / `LUCIDPM_SQL_RETRY_BACKOFF=4`
  (~144s budget) committed as the defaults in `state.py` + `.env.example` 2026-09-10. Comfortable
  margin: even the slowest observed resume (78s) only needed 2 of 8 budgeted retries. See the H60
  doc's "Cycle 2.2 measurement + default bump" section for detail.

## F. DB toggle

- [x] Switch Test → Prod → app reconnects, banner + data change. **~10-12s** warm (2026-09-09);
      **~78s** when both DBs happened to be cold at once (see section E). Slow but tolerable for a
      single-user tool; toggling is infrequent. Expected to improve markedly at Stage 3 (app
      co-located with the DB in westus3 — removes the home-internet ↔ cloud RTT).
- [x] Switched both directions across the session (Test→Prod and back) without incident.
- [x] Within-DB page-to-page navigation once warm — no issues reported; this is treated as
      acceptable by the absence of complaints during the rest of the walk.

---

## Observations / follow-ups (not Gate 2 blockers)

- **`use_test_db_rx_state_` null-read crash** on `._index` and `[lease-package-builder]._index`
  (`Cannot read properties of null`). Frontend state-hydration race — a component reading the
  DB-toggle var renders before Reflex state hydrates from the backend; Azure's slower first
  response exposes it (local SQL wins the race). Not a SQL-layer issue. **To confirm:** clean
  `reflex run` restart + hard refresh; test the same page on local 3000/8000. Fix = null-guard the
  component; re-check at Stage 3 (co-located, faster) before deciding it's a real defect.
- **`state_auto_setters` deprecation** — `property_financials_analytics.py:391,862`
  (`set_active_tab`, `set_selected_property`). Reflex 0.8.9 warning, hard-breaks at 0.9.0.
  Pre-existing, unrelated to Azure. Small cleanup handoff.
- **HMR recompile storm** during testing (`No module update found for route`, `useContext is not
  a function`) — dev-server churn, likely from repo file edits while `reflex run` was live. Not
  runtime behaviour.

## Gate 2 — GO / NO-GO

**GO** if: all read + write workflows work, no pyodbc/Azure-SQL incompatibility, latency is tolerable,
and cold resume either succeeds within the retry budget or points at a specific tuning change.

**NO-GO / investigate** if: any workflow throws a driver or SQL error that doesn't occur locally,
latency makes the app unusable, or cold resume fails outright (feeds a follow-up handoff, doesn't
reopen H58/H60).

## Result: **GO**  —  Date: 2026-09-10

No pyodbc/Azure-SQL incompatibility found. Connection (`sql` auth via the contained `lucidpm_app`
user), all reads, simple + bulk writes, email/AI, and server restart/reconnect all work correctly.
Cold resume — the one real risk this cycle existed to find — recovers cleanly once the retry
defaults are sized to the measured resume range (now committed: `retries=8`/`backoff=4`).

**Carried forward, not blockers:**
- Frontend `use_test_db_rx_state_` null-read race, exposed by Azure latency — needs a null-guard;
  re-check whether it still reproduces once the app is co-located at Stage 3 before treating it as
  a must-fix.
- Application report PDF and lease-package generation not exercised this cycle — low risk (same
  path as everything that did pass), pick up on a future touch.
- DB-toggle latency (10-12s warm, up to ~78s if both DBs are cold) is tolerable for a single-user
  tool today; expected to shrink substantially at Stage 3 co-location.

**Next:** Stage 3 — containerize and deploy. Largely de-risked by the Portfolio Manager precedent
(shared Container Apps environment, GHCR pattern, ODBC 18 base image already proven). The residual
HIGH risk is Reflex-specific: the frontend/backend split in one container, and the websocket event
channel surviving Container Apps ingress (Gate 3).
