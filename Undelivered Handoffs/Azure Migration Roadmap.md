# Azure Migration Roadmap — LucidPM (+ Portfolio Manager)

Sequences the phased plan and 2026-08-07 architect addendum in `Undelivered Handoffs/Azure Planning`
into cycle-sized units of work with explicit go/no-go gates.

- A **cycle** = one delivery loop: Claude designs → Codex or Claude implements → Mark verifies → commit.
- A **gate** = a point where Mark decides whether to keep going, based on what the previous cycles proved.
- Estimates are ranges. The two HIGH-risk cycles (3.1, 3.2) can each double if Reflex fights containerization.

Guiding constraints (unchanged from `Azure Planning`): target **$0**, no framework rewrites (Reflex stays,
Flask stays), no PostgreSQL, local development keeps working throughout, nothing destructive to the current
local production setup until the cloud version is proven.

---

## At a glance

| Stage | Outcome | Cycles | Gate |
|---|---|---|---|
| 0 — Code prep | App is deploy-ready; no Windows-only assumptions; config is env-driven | 4–5 | **✅ Gate 0 PASSED 2026-09-09** |
| 1 — Azure foundation | Subscription, resource group, SQL server, free DB confirmed at ~$0 | 2 | **G1: free tier real?** |
| 2 — App vs Azure SQL | LucidPM runs locally against Azure SQL, core workflows validated | 2–3 | **✅ G2 PASSED 2026-09-10** |
| 3 — Containerize + deploy | LucidPM live on a temp `*.azurecontainerapps.io` URL, scaling to zero | 3–5 | **✅ Gate 3 PASSED 2026-09-11** |
| 4 — Blob storage | One lease PDF survives a container restart — **POC COMPLETE** | 2 | **✅ Gate 4 PASSED 2026-09-11 — POC COMPLETE** |
| 5 — LucidPM production | Real data migrated, auth, custom subdomain, cutover | 6–8 | — |
| 6 — Portfolio Manager | Second Container App, cross-DB refactor, its own subdomain | 8–12 (soft) | — |

**To POC complete (Stages 0–4): 11–15 cycles — ✅ DONE 2026-09-11** (see progress log for Gate 4).
**LucidPM fully in production (through Stage 5): 17–23 cycles.**
**Both apps done (through Stage 6): 25–35 cycles.**

At the current part-time cadence (~1–2 cycles/week with verification in the loop): POC ≈ 2–3 months,
everything ≈ 6–12 months.

---

## Progress log

- **2026-09-11 — Cycle 4.2 / GATE 4 PASSED — POC COMPLETE.** Completed the restart-survival proof left
  outstanding in the entry below: scaled `lucidpm` to zero (`az containerapp update --min-replicas 0`),
  confirmed `replica list` empty, reopened the app from cold, and re-downloaded the same text-only
  package generated before the scale-down — **it downloaded correctly**, proving Blob storage is what
  makes generated documents durable across Container Apps restarts. Two things came out of the
  restart cycle itself, worth recording as real operational characteristics, not regressions:
  - **Scale-to-zero took longer than the configured cooldown at first**, traced to two still-open
    browser tabs holding live WebSocket connections — Container Apps' concurrency-based scaler counts
    an idle-but-open WS connection as active even though it generates no new entries in the `Requests`
    metric (confirmed via Log Analytics: `Requests` = 0 for 17+ minutes while the replica stayed up).
    Once genuinely closed, it scaled down within the configured 5-minute cooldown as expected.
  - **A real Caddy/Reflex startup race on cold start**, confirmed directly in the container's own
    console logs: Caddy started accepting connections before the Reflex backend's ASGI server was
    actually ready (backend printed its "running" banner ~2s after Caddy, but was still loading page
    modules for ~2 more seconds after that) — the first WebSocket upgrade attempt landed in that gap
    and got a clean 502 (`dial tcp 127.0.0.1:8000: connect: connection refused`) from Caddy's
    reverse_proxy. **`entrypoint.sh` (Handoff 64) has no "wait for backend ready" handshake between
    starting the two processes** — worth a small hardening fix later (have Caddy wait for a successful
    local health check before serving, or accept/queue rather than fail during that window), not
    blocking since a retry recovers. Observed end-to-end cold-start timeline (container had been idle
    long enough that `TenantCRM_Test` had likely also auto-paused): first attempt failed at ~55s,
    second at ~75s, succeeded at ~85s — consistent with the container-startup race resolving quickly
    but a concurrent SQL serverless resume (Cycle 2.2 measured 20-80s on its own) also being in play.
  Full record: `docs/cycle-4.2-validation.md`. **This closes Stages 0-4 — the POC is complete.**
  Everything past this point (Stage 5) touches production data and is a larger commitment; Mark
  decides when to start it. H68 (source-PDF/section Blob migration, see below) is separately tracked,
  not a Gate 4 blocker.
- **2026-09-11 — Cycle 4.2 deployed; Gate 4's restart-survival proof still outstanding — Handoff 68
  written for a separate new finding.** H67's changes deployed successfully: Container App revision
  `0000002` healthy, running `ghcr.io/mslucido-lab/lucidpm:0.2.0`, Blob storage enabled for generated
  packages. A text-only lease package generates and downloads correctly through the live app (H67
  Step 4's first half). **Gate 4 itself is NOT yet passed** — the actual test the roadmap and H67 both
  define is "generate → scale to zero → retrieve the same file intact" (H67 Steps 4b/5), and that
  scale-to-zero-then-retrieve sequence has not been run in this session yet. (An earlier version of
  this entry recorded Gate 4 as passed on the generation step alone — that overstated what had
  actually been verified; corrected here.) Remaining before Gate 4 can be marked passed: (1) confirm
  the text-only package's blob object exists, (2) `az containerapp update --min-replicas 0`, wait for
  zero replicas, (3) reopen the app and re-download that exact package, confirming it survived.
  **New finding, not a Gate 4 regression:** generating a
  package that includes a *PDF-backed* section (e.g. Lease Package #2 / "General Lease") fails with
  "Missing PDF files for these PDF-only sections" — `LeaseSourceDocuments`/`LeaseDocumentSections`
  still store Windows local filesystem paths, which a Container App replica has no access to at all
  (not the stale-path bug specifically — structural, affects every PDF-backed section regardless of
  path validity). H66/H67 explicitly scoped this out (Do Not Touch: "Cycle 5.1's job, not this one's")
  — it's the roadmap's own already-anticipated Cycle 5.1 work, arriving via POC testing earlier than
  planned. **Handoff 68 written** to extend the storage abstraction to source/section documents and
  migrate `TenantCRM_Test`'s existing files — two phases (code, then data migration), Test DB only,
  gated on the standing TOP-PRIORITY stale-path cleanup landing first. Prod migration and the admin
  storage-root UI redesign remain separately tracked, not part of H68.
- **2026-09-11 — Handoff 67 written** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_67_BlobStorageDeploy.md`,
  not started). Cycle 4.2 / **Gate 4** — deploy Cycle 4.1's storage abstraction to the live `lucidpm`
  Container App and prove a generated lease PDF survives a scale-to-zero restart, closing the POC.
  No application code changes (Handoff 66 already wrote it) — deployment/verification only, tagged
  [Mark] / [Claude via `az`] / [Mark verifies]. Two things verified live before writing the doc: (1)
  user-delegation SAS tokens cap at 7 days (confirmed by trying it), too short for a standing
  deployment — using a key-based container SAS instead (90-day expiry, `racw` only, container-scoped,
  needs zero code changes since it's the same connection-string format `AzureBlobStorage` already
  takes); (2) `az containerapp update --set-env-vars` merges rather than replaces (confirmed via
  `--help`), so the 3 new storage env vars can be added without touching the existing SQL/Fernet vars
  or Cycle 3.2's ingress restrictions.
- **2026-09-11 - Cycle 4.1 COMPLETE: Handoff 66 storage abstraction passed.** Generated lease packages now use `DocumentStorage`, selected by `LUCIDPM_STORAGE_BACKEND`: the local backend preserves the flat `Generated` folder and original `_2` collision suffix, while the private Azure Blob backend uses collision-resistant lease-specific keys. Local filesystem regression checks plus live Blob generation, listing, app download, direct Blob download, history/Review status, and regeneration passed. The implementation also fixed the history status badge, which initially still tested Blob identifiers with `os.path.isfile`. The Storage Account connection string remains local-only in ignored `.env`; **Cycle 4.2 must use a scoped SAS token or managed identity before deployment.** Evidence: `docs/cycle-4.1-validation.md`. **Next: Cycle 4.2 / Gate 4 - deploy, scale to zero, and retrieve a generated package.**

- **2026-09-11 - Cycle 3.2 COMPLETE; Gate 3 PASSED.** Private image `ghcr.io/mslucido-lab/lucidpm:0.1.0` deployed as the IP-restricted Container App `lucidpm` in the shared `lucido-apps-env`, temporarily locked to `TenantCRM_Test`. The real HTTPS ingress, Reflex websocket events, Test banner/data, Rent Roll PDF, and cellular denial outside the Office/Home allowlist passed. The app reached zero replicas after idle; a cold request took about **one minute** to display a Test-data list, covering both container scale-up and any SQL serverless resume. The Azure CLI YAML wrapper failed with a Boolean-conversion 400, so the valid initial restricted deployment was sent successfully with an ARM `az rest` PUT. Evidence: `docs/cycle-3.2-validation.md`. **Next: Stage 4 (blob storage); POC completion is Gate 4.**

- **2026-09-11 — Handoff 65 written** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_65_GhcrContainerAppsDeploy.md`,
  not started). Cycle 3.2 / Gate 3 — push the Cycle 3.1 image to private GHCR
  (`ghcr.io/mslucido-lab/lucidpm`, namespace confirmed live from Portfolio Manager's own registry
  config), deploy to the shared `lucido-apps-env`, temporary `*.azurecontainerapps.io` URL,
  IP-restricted (no Entra yet — Stage 5.3), locked to `TenantCRM_Test` only via `LUCIDPM_SINGLE_DB`.
  Resolves H64's baked-absolute-URL open question for this cycle: the environment's domain suffix is
  fixed and already known (`icyocean-a1d9520f.westus3.azurecontainerapps.io`, confirmed live), so the
  app's FQDN is predictable before creation — rebuild with the real URL baked in via `--build-arg`, no
  same-origin/relative-URL spike needed yet. Not primarily a code handoff — mostly Azure/GitHub account
  operations, tagged per-step [Mark] / [Claude via `az`] / [Mark verifies].
- **2026-09-11 — Cycle 3.1 COMPLETE: Handoff 64 container image built and verified locally.**
  `lucidpm:dev` is a multi-stage image: the builder exports the Reflex frontend with
  `REFLEX_API_URL=http://localhost:8080`; the non-root runtime image contains ODBC Driver 18, Reflex, and
  Caddy. Caddy serves the frontend and proxies Reflex event/upload/API/health routes through port 8080 to
  loopback-only port 8000. `.env`, `.env.docker`, and database exports are excluded. Caddy configuration,
  entrypoint syntax, image isolation, frontend fallback, health, and read-only SQL access to both Azure DBs
  passed. Mark verified browser navigation and switching between Demo and Prod. Killing Reflex made the full
  container exit, proving supervision works. **Next: Cycle 3.2** — private GHCR push and temporary Container
  Apps deployment; ingress WebSocket behavior and the absolute-URL decision remain the Gate 3 risks.

- **2026-09-05** — Roadmap written.
- **2026-09-06 — Stage 1 complete, Gate 1 PASSED.** Subscription `Lucido-Apps` (Azure Plan / pay-as-you-go
  under Microsoft Customer Agreement, ID `76290cf4-215e-4da5-b9ae-572e0fad7052`) in the personal
  `mslucidogmail.onmicrosoft.com` tenant. `$1` budget alert set (actual + forecasted at 100%). Resources:
  - Resource group `Lucido-Apps-RG` (RG metadata location eastus2).
  - SQL logical server `lucidpm-sql-24899` in **westus3** — East US / East US 2 / South Central US all
    rejected new SQL servers with `RegionDoesNotAllowProvisioning` (new-subscription throttle); westus3
    worked and supports the free offer, so **westus3 is the project region** for Container Apps + Storage too.
  - Admin login `lucidadmin` (password in Mark's password manager).
  - Firewall rule `AllowAzureServices` (0.0.0.0). Mark's home + office IPs added (Cycle 2.1 / 2026-09-09).
  - Database `TenantCRM` — serverless GP_S_Gen5_2, 32 GB, `useFreeLimit: true`,
    `freeLimitExhaustionBehavior: AutoPause`, 60-min auto-pause. Confirmed $0.
  - Provider `Microsoft.Sql` registered.
- **2026-09-06 — Cycle 2.1 complete.** Local `TenantCRM` schema + data loaded onto the Azure free DB.
  - Mark's client IP added to the SQL firewall (SSMS connects).
  - BACPAC route abandoned: `az sql db import` / SSMS import recreate the database, which drops it off the
    free tier (`useFreeLimit` is CREATE-only, not updatable). Can't import into the pre-created free DB.
  - Used SSMS **Generate Scripts** (schema + data) → single `.sql` → executed in SSMS against Azure `TenantCRM`.
    The generated script still carried a `CREATE DATABASE` + `ALTER DATABASE ... SET` header block and
    `ON [PRIMARY]` / `TEXTIMAGE_ON [PRIMARY]` filegroup clauses even with the Azure engine-type option set;
    SSMS ran past the header errors harmlessly (DB already exists) and Azure tolerated the filegroup clauses,
    so no script surgery was needed for this one-off. A cleaned `TenantCRM_azure.sql` (strip the header +
    filegroup clauses) is still the plan for the Stage 5.2 production migration into fresh DBs.
  - Verified local vs Azure: 41 app tables, **every table's row count identical**, 49 FKs + 4 CHECK
    constraints all trusted (`is_not_trusted = 0`), all user indexes present. Only `sysdiagrams` (SSMS
    diagram table, 2 indexes) not carried over — correct to leave behind.
  - Script copies left at `C:\Inspirion\Dev\TenantCRM\Database\TenantCRM_full.sql` and `db\TenantCRM_full.sql`
    (repo copy — contains tenant PII, must not be committed; add to `.gitignore` or delete).
- **2026-09-06 — `TenantCRM_Test` also migrated.** Second Azure DB `TenantCRM_Test` created on the same
  server and loaded the same way (SSMS Generate Scripts, schema + data). Verified local vs Azure: 42 app
  tables, all row counts identical, 51 FKs + 4 CHECKs trusted, only `sysdiagrams` left behind.
  **Free-offer facts (from the MS Learn free-offer doc, confirmed 2026-09-06):** the allowance is
  **per database, not shared** — each free DB gets its own 100,000 vCore-seconds compute + 32 GB data +
  32 GB backup per month, renewed monthly; **up to 10** free General Purpose databases per subscription.
  `TenantCRM` + `TenantCRM_Test` = 2 of 10. With auto-pause: max 4 vCores, 32 GB, 7-day PITR, LRS backup.
  **Region is locked** — the first free DB's region (westus3) now applies to every free DB in the
  subscription and can't be changed. Keep the exhaustion behaviour at **AutoPause** (not
  `Continue using database for additional charges`) on both. Add a per-DB metric alert on
  `Free amount remaining` < 10,000 vCore-sec. `$1` budget alert is the other backstop.
  → the Test/Prod toggle can stay in cloud (both DBs reachable by the `lucidadmin` server admin; app
  opens a per-query connection with the DB name in the string — no cross-DB queries).
  Ref: https://learn.microsoft.com/en-us/azure/azure-sql/database/free-offer?view=azuresql
- **2026-09-06 — Handoff 58 written** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_58_EnvDrivenSqlConnection.md`,
  uncommitted, not started). Stage 0.3: `state.py` env-driven connection + `sql` auth branch + dependency-free
  `.env` loader. **Being revised** — the first draft's `CLOUD_DB_NAME` forced single-DB mode and hid the
  toggle; since `TenantCRM_Test` is now on Azure too, the toggle stays (`LUCIDPM_PROD_DB` / `LUCIDPM_TEST_DB`
  point at the Azure names; optional `LUCIDPM_SINGLE_DB=1` to hide it for a future multi-user deployment).
- **2026-09-07 — Portfolio Manager cloud-migration knowledge share landed** in
  `Undelivered Handoffs/lucidpm-cloud-migration-knowledge-share.md` (untracked as of writing). PM is **already
  running as a public HTTPS Azure Container App** in this subscription, which turns most of Stage 3 from
  "unknown" into "follow the proven pattern." Reusable now:
  - Shared **Container Apps environment `lucido-apps-env`** + Log Analytics **`lucido-apps-logs`** (both
    westus3) already exist — LucidPM reuses them, does **not** create a second environment.
  - Private **GHCR** image pattern (`ghcr.io/mslucido-lab/<image>`, kept private, separate read-only pull
    token for Azure) — confirms the roadmap's "not ACR" call.
  - `python:3.12-slim-bookworm` + ODBC Driver 18 + non-root user + `.dockerignore` excludes.
  - Container Apps secrets via `secretref:` env vars; explicit schema bootstrap (not on-start); Entra
    built-in auth (single-tenant app reg, `/.auth/login/aad/callback`, ID-token issuance, require assignment);
    scale-to-zero with an explicit HTTP scale rule and the 5-min idle cooldown.
  - Still LucidPM-specific unknowns: Reflex frontend/backend split in one container, and the Reflex
    websocket event channel surviving Container Apps ingress (Gate 3).
- **2026-09-07 — Handoff 58 reconciled against that knowledge share.** Edits: (a) `lucidadmin` is Cycle 2.2
  only — cloud uses a dedicated **contained non-admin SQL user**, provisioned in **both** DBs if the toggle
  is kept; (b) added a `LUCIDPM_ENV` marker (`local`|`cloud`), orthogonal to `LUCIDPM_SINGLE_DB`, as the hook
  Stage 5.3 Entra header-trust will gate on — nothing branches on it yet; (c) cold-resume-from-auto-pause is
  now a **required Cycle 2.2 measurement** feeding a retry-on-resume wrapper as the expected next cycle, not
  a "maybe"; (d) stale `.gitignore` note removed (`/db/TenantCRM*.sql` already committed in `1de81d2`),
  replaced with a `.dockerignore` forward-reference for Cycle 3.1.
- **2026-09-07 — Handoff 58 revised again after Codex's pre-implementation review.** Five points, all
  accepted: (a) **in scope** now — 3 constant-swap lines in `LucidPM.py` (`"TenantCRM"` literal → `PROD_DB_NAME`
  in the leases-expiring label + the application-report fallback list) so an env-overridden prod DB name
  actually works; (b) `state.py` gains a `_validate_sql_config()` that **fails fast** with a named
  `ConfigError` on unknown auth mode, `auth=sql` without user/password, bad encrypt/trust value, or a
  non-integer/negative timeout — no silent degrade; (c) the `.env` loader strips **one** matching quote pair
  only, preserving password bytes exactly; (d) the validation checklist is split into **Part A (H58
  acceptance, blocking, no Azure needed)** and **Part B (Cycle 2.2 / Gate 2 data capture, non-blocking)** —
  a slow/failed cold-resume feeds a follow-up handoff, doesn't reopen H58; (e) Cycle 2.2 is run with
  **process env vars in one shell**, not a persistent repo-root `.env` that every `reflex run` from the
  checkout would pick up. H58 is now ready to implement.
- **2026-09-07 — Handoff 58 IMPLEMENTED + Claude-reviewed + committed.** `b47b6f8` (impl: all 6 steps),
  `d18a256` (19 `state_*.py` → `Archived Versions/`), `67b7e91` (review follow-ups). Doc → `Completed Handoffs/`.
  `docs/H58-validation.md` records Part A pass (default Windows-auth path, fail-fast `ConfigError` × all
  branches, `.env` quote handling, single-DB lock, Step-6 label — all green in headless Chromium + subprocess
  checks). Claude review: sound, no blocking issues; Windows-auth default conn string verified byte-equivalent
  (ODBC ignores segment order); `pyodbc 5.3.0` `connect(timeout=)` confirmed to be the *login* timeout (no
  query-timeout regression). Applied findings: `.env.example` now documents "full-line comments only" (an
  inline `# …` becomes part of the value → `ConfigError`); dropped a reference to a `Start-LucidPM-Azure.ps1`
  that was never created (inline `$env:` recipe kept). Deferred/tracked: the `sql`-auth connection string is
  **still untested against a live server** (→ Cycle 2.2, then re-check on unixODBC at Cycle 3.1 — the
  `UID={}`/`PWD={}` brace-escaping is the suspect if login fails); `tenants.py:703` `self.db or "TenantCRM"`
  stale literal (→ next `tenants.py` touch); hardcoded `http://localhost:8000` in `tenants.py:704` +
  `lease_package_builder.py` 364/370/1825 (→ Stage 3 blocker, now in `CLAUDE.md` standing backlog + Cycle 3.1).
- **2026-09-08 — Handoff 59 implemented + Claude-reviewed** (`fc615e8` impl, `6bfeabc` orphan+sibling
  archive; doc → `Completed Handoffs/`; `docs/H59-validation.md`). 7 page modules → `state.api_base_url()`
  off Reflex's `api_url`; default `http://localhost:8000` byte-identical, `--backend-port N` and
  `REFLEX_API_URL` both verified. Review: clean, no bugs. Stage 3.1 still sets `REFLEX_API_URL` to the
  ingress host.
- **2026-09-08 — Handoff 60 written** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_60_SqlResumeRetry.md`,
  not started). Bounded transient-only retry around `pyodbc.connect` in `state.get_conn()` for Azure
  serverless auto-pause. `LUCIDPM_SQL_CONNECT_RETRIES` (2) + `_RETRY_BACKOFF` (3); retries SQLSTATE
  `08*`/`HYT*` + native `40613` etc., fails fast on auth (`28000`) / bad-db (`4060`). Predicate + timeout
  behaviour verified against real `pyodbc 5.3.0` errors. Byte-identical when the DB answers first try.
  A/B/C acceptance needs no Azure; D is the Cycle 2.2 resume measurement.
- **2026-09-08 — Handoff 60 post-impl review + fixes, committed `cde6374`.** Claude reviewed `d8f6754`: retry
  mechanism sound. Applied — upper-bound `LUCIDPM_SQL_CONNECT_RETRIES` (≤10) / `_RETRY_BACKOFF` (≤30) via a
  new `maximum=` arg on `_non_negative_int_env` (a config typo was an unbounded blocking `time.sleep` in a
  Reflex worker); moved that helper above its caller. Deferred to Cycle 2.2 (need a real resume): whether the
  9 s default backoff bridges a fast-`40613` resume, and whether this ODBC build formats throttle native codes
  with the `(NNNNN)` substring the predicate matches. `state.py` + `.env.example` + H60 doc ("Post-Implementation
  Review Fixes" section + checklist A/B/D).
- **2026-09-08 — Handoff 61 implemented.** Review folded in 4 points: `.python-version` = exact `3.12.10`; pyproject `dev` extra mirrors
  `requirements-dev.txt` (pyee included); app-import check is `import LucidPM.LucidPM` (the empty package init
  doesn't exercise the pages); checklist D scoped to `requirements.txt` + `docs/` so it doesn't match the
  handoff's own quoted-stale-text. Stage 0 / Cycle 0.1 — closes the gaps left after the 2026-08-16 stand-up: new `pyproject.toml`
  (direct-dependency manifest — 8 runtime deps reconstructed from live imports: reflex, pyodbc, fastapi,
  pypdf, reportlab, pandas, cryptography, anthropic — pins copied verbatim from `requirements.txt`, no
  `[build-system]`), new `requirements-dev.txt` (playwright/pyee, the H58/H59 validation-harness deps that
  are in `.venv` but not tracked), new `.python-version` (`3.12.10`), fix `requirements.txt`'s stale
  self-contradictory "does NOT fully boot / Handoff_49_UploadHandlerCompat" header, reconcile
  `docs/DeveloperSetup.md`. Manifest + docs only — zero pin changes, zero app code, `/api/pick-files` stays
  for Cycle 0.2. Acceptance = clean-venv install + `import LucidPM` + `reflex run` compile, all local.
- **2026-09-08 — Handoff 62 written** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_62_RetireNativeFilePicker.md`,
  complete). Stage 0 / Cycle 0.2. Investigation found the `rx.upload` migration the roadmap called for
  **already happened** (H49 + Studio): live tenant/communications/lease-template/waiting-list uploads all use
  `rx.upload`, and `GET /api/pick-files` (PowerShell `OpenFileDialog` in `LucidPM.py`) has **zero live
  callers** — only archived `_vN` files reference it. So H62 is a deletion + doc reconcile, not a rewrite;
  risk low, not medium. Phase 1 deletes the endpoint (the last `subprocess`/PowerShell call in the entry
  module) + fixes `Architecture.md` / `Deployment.md` / `DeveloperSetup.md`. Phase 2 archives `LucidPM.py`'s
  40 `LucidPM_Reflex_*.py` siblings (incremental `_vN` rule).
- **2026-09-08 — Handoff 63 code implemented; rotation runbook pending** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_63_FernetKeyFromEnv.md`,
  code complete; Mark rotation runbook pending). Stage 0 / Cycle 0.4 — the last Stage 0 item. `state.get_fernet()` previously read the config-secret
  Fernet key (`dbo.AppSettings` `'LocalEncryptionKey'`, per-DB, auto-generated) — the same DB it protects the
  `EmailConfig.PasswordEncrypted` / `AIConfig.APIKeyEncrypted` ciphertext in (roadmap's old `settings.py`
  pointer was stale — dead module). H63: `get_fernet` → `_fernet()` reads `LUCIDPM_FERNET_KEY` from env,
  comma-separated → `MultiFernet` (first encrypts, all decrypt). Fail-fast `ConfigError` when unset OR
  all-whitespace/separators (review pt 2 — was an `IndexError`). Lazy so the app still boots. Mirrors the
  existing `tally_import.py` `TENANTCRM_FERNET_KEY` precedent (separate SSN/DL key, left alone).
  **Migration is a key ROTATION** (review pt 3), not a straight move: generate a NEW key,
  `LUCIDPM_FERNET_KEY=<new>,<old-prod>[,<old-test>]`, re-save the 4 config secrets (SMTP pw + Anthropic key ×
  Prod/Test) in Admin Settings → re-encrypted under `<new>`, verify under `<new>` alone, then `DELETE` the
  rows, then **delete the local files that carry old key + ciphertext** (review r2): the 3 gitignored
  `db/TenantCRM*.sql` exports (UTF-16 — they *do* hold the `AppSettings`/`EmailConfig`/`AIConfig` INSERTs; a
  byte-`grep` missed them) + `C:\…\Database\TenantCRM_Azure.bacpac` + `*_Backup\`; recommend also rotating the
  underlying SMTP/Anthropic creds. **Git history verified clean** (those exports were never `git add`ed;
  nothing but the SQL query literal in history) → no `git filter-repo`. No bulk re-encryption in code — Mark
  re-saves via the UI. Files: `state.py` + `.env.example` + `DeveloperSetup.md` §5 + `Deployment.md` +
  `Database.md` (§Secrets lines 36–41, wrong after the change — review pt 1). Optional `db/data_updates/`
  delete script.
- **2026-09-09 — Handoff 63 rotation complete → Stage 0 (code prep) DONE, Gate 0 PASSED.** Mark ran the key
  rotation: new `LUCIDPM_FERNET_KEY` generated, the 4 config secrets re-saved under it, app verified on the
  new key alone, `LocalEncryptionKey` rows `DELETE`d from **both** `TenantCRM` and `TenantCRM_Test`. New key
  lives only in `.env` (gitignored). **Conscious deviations (Mark's call, recorded — not open issues):** old
  key kept as a commented line in `.env` for recovery insurance; runbook steps 8–9 (purge the local
  `db/TenantCRM*.sql` / `.bacpac` / `*_Backup\` copies that still carry old key + old ciphertext; rotate the
  underlying SMTP/Anthropic creds) not done — so on a stolen-laptop basis the old secrets stay recoverable.
  The realised gain: the key is out of the database, so a DB-only compromise no longer yields it (the point
  that matters for the cloud move). H63 doc → `Completed Handoffs/` with a Status section. All four Stage 0
  cycles now complete (0.1 `e20d735`, 0.2 `7f5e931`/`401b8c3`, 0.3 `b47b6f8`, 0.4 `cc9af6b` + rotation).
- **2026-09-09 — housekeeping.** `az` CLI **is now installed locally** (v2.90.0, logged in to `Lucido-Apps`) —
  the "not installed / use Cloud Shell" notes below are stale. Mark's **office IP added** to the SQL firewall
  (`Mark-Office` = 72.183.200.115); `Update-AzureSqlFirewall.ps1` at the repo root repoints a single
  `Mark-Laptop` rule to the current public IP for home/office switching. Rules now: `AllowAzureServices`,
  `ClientIPAddress_2026-9-5_19-28-48` (home), `Mark-Office`.
  - *SAC note (2026-09-09):* Windows Smart App Control blocked Reflex's `rolldown` native `.node` module
    (CodeIntegrity 3033/3077). Mark toggled SAC off then back on — it re-enabled cleanly (state 1, enforced);
    the app then started (frontend likely already compiled, or ISG reputation caught up). If a clean `.web/`
    rebuild re-triggers the block: run Reflex in a Docker dev container or WSL2 (Linux binaries dodge Windows
    CI). Docker Desktop already installed from the PM migration.
- **2026-09-09 — contained SQL user created, both DBs.** `db/azure_app_user.sql` (least-privilege
  `lucidpm_app`, `db_datareader`+`db_datawriter` — verified sufficient against live code, which does
  plain parameterized DML only, no DDL/sprocs/catalog reads) run against `TenantCRM` and
  `TenantCRM_Test`. Login verified. Resolves the "cloud build needs a dedicated contained user, both
  DBs" item from the Handoff 58 reconciliation. `lucidadmin` remains break-glass only.
- **2026-09-09 — free-compute metric alerts + action group.** `LucidPM-TenantCRM-free-compute-low` /
  `LucidPM-TenantCRM_Test-free-compute-low` (min `free_amount_remaining` < 10,000 over 6h, hourly eval)
  on both DBs, notifying `mlucido@lucidoproperties.net` via a reusable `LucidPM-Alerts` action group.
  Closes the standing roadmap alert item. (Gotcha hit while setting these up: Git Bash's MSYS path
  conversion mangles `/subscriptions/...` resource-ID arguments passed to `az` — fix is
  `MSYS_NO_PATHCONV=1`.)
- **2026-09-10 — Cycle 2.2 / GATE 2 PASSED.** Full walkthrough against Azure SQL via the contained
  `lucidpm_app` user — see the Cycle 2.2 section above and `docs/cycle-2.2-validation.md` for detail.
  Headline results: no pyodbc/Azure-SQL incompatibility; all reads, writes (simple + bulk), email/AI,
  and restart/reconnect work; cold-resume-from-auto-pause bridges cleanly once the H60 retry budget
  is sized to the measured range (`retries=8`/`backoff=4`, now committed as the default — was `2`/`3`).
  New non-blocking follow-up: a frontend DB-toggle-state null-read race exposed by Azure latency,
  re-check at Stage 3. `Start-LucidPM-Azure.ps1` (repo root) is the reusable launcher for future Azure
  test sessions.
- **2026-09-10 — Handoff 64 written** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_64_ContainerizeReflexODBC.md`,
  committed `b3044e2`, not started). Cycle 3.1 only — Dockerfile + `.dockerignore`, single container /
  single exposed port (8080), verified via local `docker build`/`run` against Azure SQL through the
  Cycle 2.2 `lucidpm_app` user. Explicitly excludes Cycle 3.2 (GHCR, Container App, Entra).
- **2026-09-11 — Handoff 64 Codex pre-implementation review, 4 points + 1 preflight, all accepted,
  doc revised.** (1) `REFLEX_API_URL` is baked into the compiled frontend at `reflex export` time
  (verified against Reflex 0.8.9's own source — `reflex/utils/export.py`, `reflex/reflex.py`), not
  read at `docker run` — fixed via a Docker build ARG, and Step 0's spike corrected to set the env var
  *before* exporting (the original ordering could have produced a false "native serving doesn't work"
  reading from a plain port mismatch). (2) The static-file fallback's `LUCIDPM_FRONTEND_BUILD_DIR` was
  never actually set — added, conditional on Step 0 needing the fallback. (3) `compileall` ran before
  `COPY . .`, compiling nothing — reordered. (4) "Single process" reworded to "single container, single
  exposed port" — `reflex run --backend-only` may supervise more than one OS process; the real
  acceptance bar is proven by the browser event-channel test. Preflight: Docker Desktop's *engine*
  (not just the app) must be running before `docker build`. New open decision surfaced and added to
  the table above: the baked-absolute-URL approach won't survive Cycle 3.2 unchanged (Container Apps
  URL differs from `localhost:8080`) — same-origin relative URLs are the cleaner fix but unverified,
  to be resolved before Cycle 3.2 starts, not mid-cycle.
- **2026-09-11 — Handoff 64 revised a third time: Caddy reverse proxy replaces the static-mount
  fallback (`1c6403c`).** Codex ran Step 0's spike and found the manual `StaticFiles` mount can't be
  made safe — Reflex attaches its own internal ASGI routes (websocket event channel, `/_upload`,
  `/ping`) onto the `api` object only when the server factory runs, **after** `LucidPM.py` finishes
  importing, so any module-level mount would always register first and intercept them. No tracked
  source file changed proving this (only gitignored `.web/` build output touched). Redesigned around
  **Caddy** as a second process in the same container: Caddy owns the one exposed port (8080), serves
  the static export directly, and reverse-proxies `/_event`/`/_upload`/`/api/*`/`/ping`/`/_health` to
  the Reflex backend bound to loopback-only `127.0.0.1:8000`. Net effect: no `LucidPM.py` change needed
  at all (a simplification over the removed fallback). New files: `Caddyfile`, `entrypoint.sh` (minimal
  two-process supervision — either process dying tears down the other, container exits non-zero rather
  than silently serving a half-broken app).
- **Next:** Stage 3 — containerize and deploy. Largely de-risked by the Portfolio Manager precedent
  (shared Container Apps environment `lucido-apps-env`, GHCR pull-token pattern, ODBC 18 base image
  already proven in production). The residual HIGH risk is Reflex-specific: the frontend/backend split
  in one container, and the websocket event channel surviving Container Apps ingress (Gate 3). Also
  outstanding, no urgency: H60 checklist A/B/C formal acceptance (behavior already exercised live, but
  the isolated/synthetic checks were never separately run); the frontend null-race fix; application-report
  PDF and lease-package generation weren't exercised in Cycle 2.2.

---

## Stage 0 — Code prep (no Azure resource required; can start now)

These fix the blockers the architect addendum found in the real repo. None need Azure to exist, and each
leaves local behaviour unchanged when no cloud env vars are set.

### Cycle 0.1 — Project scaffolding — **complete 2026-09-08 (Handoff 61)**
- `requirements.txt` (full pinned freeze), `rxconfig.py`, `LucidPM/__init__.py`, `docs/DeveloperSetup.md`
  all already exist from the 2026-08-16 stand-up (Handoff 49). H61 closes what's left:
  new `pyproject.toml` (the 8 direct deps — `reflex`/`pyodbc`/`fastapi`/`pypdf`/`reportlab`/`pandas`/
  `cryptography`/`anthropic` — pins copied from `requirements.txt`, no `[build-system]`), new
  `requirements-dev.txt` (`playwright`/`pyee`), new `.python-version` (`3.12.10`), fix the stale
  `requirements.txt` header, reconcile `docs/DeveloperSetup.md`.
- **Done when:** a fresh clone → install → `reflex run` works with no tribal knowledge.
- **Validated:** clean Python 3.12.10 virtual environment installed the runtime
  and dev lockfiles; both package and app imports exited 0; Reflex compiled all
  84 units. Existing sitemap-plugin and state-auto-setter warnings remain.
- Risk: low. Manifest + docs only; no pin changes, no app code.

### Cycle 0.2 — Browser-native file input — **complete 2026-09-08 (Handoff 62)**
- The `rx.upload` migration already shipped piecemeal (H49 + Studio). H62 removed the orphaned `/api/pick-files` endpoint, its final PowerShell dependency, and the stale documentation.
- **Validated:** the deleted route returns 404; the rent-roll PDF endpoint still returns a PDF; the entry module imports and Reflex compiles all 84 units.
- Risk: low. No live consumer existed; the 40 historical entry-module siblings are archived separately.
### Cycle 0.3 — Connection config: env-driven + SQL auth — ✅ DONE 2026-09-07 (Handoff 58, `b47b6f8`)
- `state.get_conn()` now builds the connection string from env vars (`LUCIDPM_SQL_SERVER` / `_PROD_DB` /
  `_TEST_DB` / `_AUTH` / `_USER` / `_PASSWORD` / `_ENCRYPT` / `_TRUST_CERT` / `_LOGIN_TIMEOUT`), defaults =
  today's hardcoded values → Windows-auth path byte-equivalent. `sql` auth branch added (`UID`/`PWD`
  brace-escaped). Dependency-free `.env` loader (`setdefault`, so real/injected env wins).
- **Decision resolved:** the Test/Prod toggle **stays** in both local and cloud (single-user tool). Optional
  `LUCIDPM_SINGLE_DB=<name>` locks to one DB + hides the Switch button for a future multi-user deployment.
  `LUCIDPM_ENV` (`local`|`cloud`) added as an inert marker for the Stage 5.3 Entra header-trust gate.
- Invalid config **fails fast** with a named `ConfigError` at import — no silent degrade to Windows auth.
- **Outstanding:** the `sql`-auth path is unverified against a live SQL Server — that is Cycle 2.2.

### Cycle 0.4 — Fernet key out of the database — ✅ DONE 2026-09-09 (Handoff 63, code `cc9af6b` + rotation)
- The live key loader is `state.get_fernet(db)` (the roadmap's old `settings.py` pointer is stale — that
  module is dead). It formerly read `dbo.AppSettings` `'LocalEncryptionKey'` per-DB and auto-generates one if missing
  — the key sits in the same DB as the `EmailConfig.PasswordEncrypted` / `AIConfig.APIKeyEncrypted` ciphertext
  it protects.
- H63: `get_fernet` reads `LUCIDPM_FERNET_KEY` (comma-separated → `MultiFernet`; first encrypts, all decrypt).
  Two keys cover the `TenantCRM` / `TenantCRM_Test` pair (independent keys) and rotation. Fail-fast
  `ConfigError` when unset; lazy, so the app still boots. No DB read, no auto-generate. Mirrors the existing
  `tally_import.py` `TENANTCRM_FERNET_KEY` env pattern (separate key, untouched).
- Migration is a **rotation** (Mark, per DB): extract old keys → generate NEW → `.env`
  `LUCIDPM_FERNET_KEY=<NEW>,<OLD…>` → re-save the 4 config secrets in Admin Settings on both DBs → verify
  under `<NEW>` alone → `DELETE` the `'LocalEncryptionKey'` rows → delete the 3 gitignored `db/TenantCRM*.sql`
  exports + `C:\…\Database\*.bacpac` / `*_Backup\` (all carry old key + ciphertext) → re-verify. Git history
  clean (never `git add`ed) — no `filter-repo`. Recommend rotating the underlying SMTP/Anthropic creds too.
- **Done when:** secrets decrypt from `LUCIDPM_FERNET_KEY=<NEW>` alone, `'LocalEncryptionKey'` row gone from
  both DBs.
- Risk: medium — losing the key makes encrypted config unrecoverable. Runbook keeps old keys live until the
  re-encrypt is verified.

**Gate 0 — ✅ PASSED 2026-09-09.** All four code items committed (0.1 `e20d735`, 0.2 `7f5e931`/`401b8c3`,
0.3 `b47b6f8`, 0.4 `cc9af6b`), H63 rotation complete (with recorded deviations — see progress log), local app
working. Zero Azure spend so far.

---

## Stage 1 — Azure foundation

### Cycle 1.1 — Subscription + CLI + resource group *(mostly Mark; POC-A)* — ✅ DONE 2026-09-06
- Used an existing pay-as-you-go subscription (`Lucido-Apps`) in the personal tenant; no new signup needed.
- Initially used **Azure Cloud Shell** (Bash, no storage); `az` CLI **installed locally 2026-09-09**
  (v2.90.0, logged in to `Lucido-Apps`).
- `Lucido-Apps-RG` created; `$1` budget alert set.

### Cycle 1.2 — SQL server + free database *(POC-B)* — **GATE 1** ✅ PASSED 2026-09-06
- Server `lucidpm-sql-24899` in **westus3** (East US regions were throttled for the new subscription).
- Database `TenantCRM`, serverless, `useFreeLimit: true`, `AutoPause` on exhaustion — confirmed $0.
- **G1 — PASSED.** The free tier applies. Proceed.
- Firewall: Mark's home IP added Cycle 2.1; office IP (`Mark-Office`) added 2026-09-09.
  `Update-AzureSqlFirewall.ps1` (repo root) repoints a `Mark-Laptop` rule to the current public IP.

---

## Stage 2 — App runs against Azure SQL (still local, no container)

### Cycle 2.1 — Schema + data into Azure SQL *(POC-C, part 1)* — ✅ DONE 2026-09-06 (both DBs)
- Loaded **full** local `TenantCRM` **and `TenantCRM_Test`** (not a sample — the DBs are small) via SSMS
  "Generate Scripts" (schema + data) executed against the matching Azure DB. BACPAC was tried first and
  abandoned (import recreates the DB → loses the free tier). Both Azure DBs on the free offer — allowance
  is **per-database** (own 100k vCore-sec + 32 GB/mo each), up to 10 free DBs/subscription.
- Azure rejected only the `CREATE DATABASE` / `ALTER DATABASE ... SET` header (harmless — SSMS continued);
  filegroup clauses (`ON [PRIMARY]`, `TEXTIMAGE_ON [PRIMARY]`) were tolerated. No cross-database refs.
- **Verified:** 41 tables, every row count identical local vs Azure, 49 FKs + 4 CHECKs trusted, all user
  indexes present. Only `sysdiagrams` left behind (correct).
- See the progress log entry for detail. A cleaned `TenantCRM_azure.sql` is deferred to Stage 5.2.

### Cycle 2.2 — Local app against Azure SQL *(POC-C, part 2)* — **GATE 2 ✅ PASSED 2026-09-10**
- Point local LucidPM at the Azure DB via the Stage 0.3 env vars (SQL auth). H58 shipped the plumbing;
  Part B of its checklist **is** this cycle.
- **First real test of the SQL-auth connection string — PASSED.** Connected via the contained
  `lucidpm_app` user (created via `db/azure_app_user.sql`, `db_datareader`+`db_datawriter`, both DBs).
  The `UID={...}`/`PWD={...}` brace-escaping (H58 review finding 3) works correctly against a live
  server. Run via `Start-LucidPM-Azure.ps1` (repo root, untracked launcher) on ports 3002/8002.
- **Workflows walked:** every page in the app loads with Azure data; write path exercised via a
  bulk tally import + a Fernet-secret re-save (both through `lucidpm_app`, both persisted across a
  server restart); email (IMAP) + Anthropic AI work end-to-end; DB toggle works both directions.
  Application-report PDF and lease-package generation not separately exercised — low risk, deferred
  to a future touch. Full detail: `docs/cycle-2.2-validation.md`.
- **Latency:** warm navigation fine; DB toggle 10-12s warm, up to ~78s when both DBs are cold at
  once — tolerable for a single-user tool, expected to shrink at Stage 3 co-location.
- **Cold-resume-from-auto-pause (Handoff 60 checklist D) — MEASURED.** The shipped defaults
  (`retries=2`/`backoff=3`, ~9s budget) were NOT enough — a resume attempt exhausted all 3 attempts
  and hung. With the budget raised to `retries=8`/`backoff=4` (~144s), 3 cold resumes recovered
  cleanly with no errors: ~20-30s (app start after an overnight pause) and ~78s (a DB toggle that
  caught both `TenantCRM` and `TenantCRM_Test` cold simultaneously). This also resolved an H60
  open question: the native-code substring match (not just the exact-SQLSTATE set) is what catches
  these on this ODBC build. **`retries=8`/`backoff=4` is now the committed default** — `state.py` +
  `.env.example`, 2026-09-10; see the H60 doc's "Cycle 2.2 measurement + default bump" section.
- **New follow-up found, not a blocker:** a frontend `use_test_db_rx_state_` null-read race —
  a component reads the DB-toggle state var before Reflex finishes hydrating; Azure's slower first
  response exposes it (local SQL wins the race, so it wasn't seen before). Needs a null-guard;
  re-check whether it still reproduces once the app is co-located at Stage 3 before treating it as
  a must-fix.
- **G2 — PASSED.** No pyodbc/Azure-SQL incompatibility. Proceed to Stage 3.
- Risk: medium.

---

## Stage 3 — Containerize and deploy (the hard part)

**Now largely de-risked by the PM precedent** (`lucidpm-cloud-migration-knowledge-share.md`, 2026-09-07):
Portfolio Manager already runs this exact platform. Reuse — don't rediscover — the shared Container Apps
environment `lucido-apps-env`, Log Analytics `lucido-apps-logs`, the private GHCR + read-only pull-token
pattern, `python:3.12-slim-bookworm` + ODBC Driver 18 + non-root, `.dockerignore` excludes, Container Apps
`secretref:` secrets, explicit (not on-start) schema bootstrap, and the scale-to-zero HTTP-scale-rule setup.
The residual HIGH risk is **Reflex-specific only**: the frontend/backend split in one container, and the
websocket event channel through Container Apps ingress.

### Cycle 3.1 — Dockerfile: Reflex + ODBC *(handoff; HIGH risk — Reflex parts only)*
- Base: `python:3.12-slim-bookworm` + Microsoft ODBC Driver 18 for SQL Server + Python deps from Cycle 0.1.
- Add `.dockerignore` per the knowledge share's exclusion list (mirrors `.gitignore` — `.env`, keys,
  `/db/TenantCRM*.sql`, `.web/`, `.venv/`, tests, handoff dirs).
- Non-root runtime user; `chown` the app dir before the `USER` switch; compile bytecode in the build.
- Resolve the Reflex frontend (port 3000) / backend (port 8000) split into one deployable image — decide the
  single-container topology (build/export the static frontend and serve it from the backend, vs run both
  processes under a supervisor).
- Listen on the port Container Apps injects.
- **Re-verify the SQL-auth connection string on Linux/unixODBC** (H58 review finding 3): the `{}}`
  brace-escaping in `state._odbc_brace` is solid on the Windows MS Driver 18 but historically flakier on
  unixODBC. Confirm a password containing `}` / `;` / `=` still connects from inside the container.
- **API URL plumbing complete - Handoff 59, 2026-09-08.** Seven page modules now use
  `state.api_base_url()`; default/non-default port PDF delivery and isolated config overrides
  verified (`docs/H59-validation.md`). Handoff in `Completed Handoffs/`. Set `REFLEX_API_URL`
  (or `rxconfig.py`) to the browser-reachable ingress host here in Stage 3.1.
- **Done when:** `docker build` + `docker run` locally → app loads and talks to Azure SQL.
- Risk: **HIGH** — Reflex production containerization is the single most likely thing to blow the schedule.

### Cycle 3.2 — Push to a free registry + deploy to a temp hostname *(handoff; HIGH risk)* — **GATE 3**
- Build/push the image to **private GHCR** (`ghcr.io/mslucido-lab/<lucidpm-image>`) — the pattern PM already
  uses. Not ACR (not free). Create a **separate read-only pull token** for Azure; never use a developer
  publish token as the Container Apps registry credential.
- **Reuse the existing shared environment `lucido-apps-env`** (created for PM) — do not create a second one.
- Create the LucidPM Container App: point at GHCR, configure env vars + `secretref:` secrets, `min-replicas 1`
  while bootstrapping, ingress on the temporary `*.azurecontainerapps.io` hostname.
- Run schema bootstrap explicitly via `az containerapp exec` after deploy (keep bootstrap-on-start disabled).
- Validate: loads over HTTPS on the temp URL; **scale-to-zero works**; measure cold-start time; confirm the
  Reflex websocket event channel survives the Container Apps ingress.
- **G3 — GO/NO-GO:** cold start tolerable? websocket stream stable through ingress? compute staying inside the
  free allowance? This gate clears the biggest unknown in the whole migration.
- Risk: **HIGH**.

---

## Stage 4 — Blob storage — POC COMPLETE

### Cycle 4.1 — Storage abstraction *(handoff)*
- Introduce a storage interface with two implementations — local filesystem (dev) and Azure Blob (cloud) —
  selected by env var.
- Route lease source PDF reads and generated PDF writes through it.
- **No schema change yet** — the POC only needs to prove a round-trip.
- **Done when:** both implementations work locally.

### Cycle 4.2 — One PDF survives a restart *(POC-E)* — **GATE 4**
- One Blob container, `lucidpm-documents`.
- In the deployed app: generate/upload a lease PDF → scale the container to zero and back → download it intact.
- **Done when:** the file survived. **POC COMPLETE.**

**Gate 4 — the real decision point.** The POC has now killed the two risks that could have sunk the migration:
the app works against Azure SQL, and it runs containerized on Azure within the free tier. Everything past here
touches production data and is a larger commitment. Mark decides whether to proceed to Stage 5.

Confirmed at this point: SQL free tier ≈ $0 · app correct against Azure SQL · app runs in a container on Azure
with no paid registry · a file survives a container restart.

---

## Stage 5 — LucidPM production

### Cycle 5.1 — Full data migration: document storage paths *(handoff; HIGH risk)*
- Do the **standing TOP-PRIORITY stale-`StoredFilePath` cleanup first** (junction or bulk `UPDATE` — already
  scoped in `CLAUDE.md`), so the source data is consistent before it moves.
- Migrate every `StoredFilePath` / `RelativePath` row in `dbo.LeaseDocumentSections` to blob identifiers; move
  the files themselves into `lucidpm-documents` (`source-documents/`, `generated-leases/`).
- **Decision:** identifier scheme — blob path vs opaque key.
- Retire or repurpose the admin "storage root" screen (`pages/admin_settings.py` / seeded in
  `pages/lease_documents.py` ~883–886) — in cloud it can no longer point at an arbitrary local path.
- Risk: **HIGH** — production data migration, entangled with the stale-path backlog item.

### Cycle 5.2 — Real databases *(handoff)*
- Migrate full `TenantCRM` and `TenantCRM_Test` to Azure SQL — into **fresh** DBs this time, using the
  cleaned `TenantCRM_azure.sql` (strip the `CREATE DATABASE` / `ALTER DATABASE` header + filegroup clauses;
  Codex prompt already drafted) so the load runs with zero errors.
- Free-offer question is **resolved** (see progress log 2026-09-06): up to 10 free DBs/subscription, each
  with its own 100k vCore-sec + 32 GB/month. Per-DB metric alert on `Free amount remaining` < 10k.
- Local production stays authoritative until the cloud copy is proven.

### Cycle 5.3 — Authentication *(handoff)*
- Enable Container Apps **built-in auth with Microsoft Entra ID** — infrastructure-level, no custom auth code.
  Follow the PM knowledge-share recipe: **single-tenant** app registration, redirect URI
  `https://<app-fqdn>/.auth/login/aad/callback`, **ID-token issuance enabled**, service principal created,
  auth mode `RedirectToLoginPage` + HTTPS required, client secret held as a Container Apps secret with a
  recorded rotation date. Route logout through `/.auth/logout` (don't bounce straight back to the app root).
- **Access assignment:** set the enterprise app to *require assignment*, assign Mark first, then enable the
  requirement (assign-before-enable, to avoid locking out the person making the change).
- If LucidPM ever trusts `X-MS-CLIENT-PRINCIPAL-NAME`, gate it on `LUCIDPM_ENV=cloud` (the marker added in
  Handoff 58) — never trust that header in local/arbitrary hosting.
- **Done when:** the app requires login and no application auth code was added.
- Risk: medium — Entra + the Reflex websocket auth handshake (PM's was a Flask app, so this handshake is the
  one part not already proven).

### Cycle 5.4 — Custom domain + TLS *(handoff)*
- Add `lucidpm.<domain>`, DNS records, Azure-managed certificate.
- **Needs from Mark:** DNS access for the chosen domain.

### Cycle 5.5 — Cutover *(handoff)*
- Run cloud as primary; local dev still works (env vars already handle that from Stage 0).
- Only after a stable period: stop treating the local laptop as production.

---

## Stage 6 — Portfolio Manager *(separate repo — never reviewed here; estimates soft)*

### Cycle 6.1 — Gap analysis of the PM repo
- Run the `Azure Planning` "Codex Tasks" inventory, **scoped to live files only** (the repo has hundreds of
  versioned duplicates that will drown real findings).

### Cycle 6.2 — PM Stage-0 equivalents
- Gunicorn (no Flask dev server); env-driven connection + SQL auth; install ODBC driver; remove
  `webbrowser.open()`, `run.bat` deps, Windows-only assumptions; Anthropic key out of SQL.

### Cycles 6.3–6.4 — Cross-database refactor *(the flagged most-important change)*
- Replace the `LucidTenant.dbo.*` cross-database SQL (works locally only because both DBs share one SQL Express
  instance) with a **second explicit connection** (`LUCIDPM_DB_CONNECTION`): connect to the LucidPM Azure SQL
  DB, run the property query there, return rows to Python. No three-part cross-database queries in Azure SQL.

### Cycle 6.5 — PM database migration to Azure SQL
- `PortfolioManager` + `PortfolioManager_Test` (same free-tier caveat as 5.2).

### Cycles 6.6–6.7 — Containerize + deploy
- Flask/Gunicorn container (simpler than Reflex); deploy as the second Container App in the shared environment.

### Cycle 6.8 — Secure + domain
- Container Apps secrets for the Anthropic key; Entra ID auth; `portfolio.<domain>` + managed TLS.

### Cycle 6.9 — End-to-end
- Property-sync workflow across the two Azure SQL databases, verified.

Independence throughout: separate images, revisions, env vars, ingress, secrets, health. Deploying one app
never restarts the other. Shared: subscription, resource group, Container Apps Environment, SQL logical server,
storage account. **Never shared:** the application databases.

---

## Critical path — what only Mark can do

1. **Create the Azure subscription** — blocks everything past Stage 0.
2. **Gate 1 decision** — proceed only if the free SQL tier is confirmed.
3. **Gate 4 decision** — commit (or not) to the production migration after the POC.
4. **Stale-`StoredFilePath` cleanup** — should land before Cycle 5.1 regardless of Azure timing.
5. **DNS / domain access** — Cycles 5.4 and 6.8.
6. **Verification** at each gate.

## Open decisions to resolve

| Decision | When | Default recommendation |
|---|---|---|
| ~~Does the free offer cover 1 database or more per subscription?~~ | ~~Gate 1~~ | **RESOLVED 2026-09-06:** up to **10** free GP databases per subscription, each with its **own** 100k vCore-sec + 32 GB/month allowance (not shared). `TenantCRM` + `TenantCRM_Test` = 2/10. Region locked to westus3 for all free DBs. |
| ~~Prod/Test toggle in cloud builds~~ | ~~Cycle 0.3~~ | **RESOLVED 2026-09-06, refined 2026-09-07:** toggle **stays** in cloud (single-user tool, both DBs on Azure). Optional `LUCIDPM_SINGLE_DB=<name>` hides it for a future multi-user deployment. **Cost of keeping it:** the PM knowledge share bars using the server admin in cloud, so the cloud build needs a dedicated contained SQL user — and contained users are per-DB, so the same user + password must be created in **both** `TenantCRM` and `TenantCRM_Test`. `lucidadmin` is Cycle 2.2 (local smoke test) only. |
| Reflex single-container topology | Cycle 3.1 | Export static frontend, serve from backend process |
| Baked absolute `REFLEX_API_URL` vs. same-origin relative URLs | Before Cycle 3.2 (raised by Handoff 64's pre-impl review, 2026-09-11) | Cycle 3.1 bakes a fixed local URL via a Docker build ARG — fine for a local-only image. Before Cycle 3.2 pushes to Container Apps, decide: rebuild per environment (simple, but "the image" isn't really one portable artifact) vs. same-origin relative URLs (cleaner, works unmodified across local/temp-URL/custom-domain, but unverified against Reflex 0.8.9 — needs its own spike). Default recommendation: attempt the relative-URL spike first; fall back to per-environment rebuild if Reflex 0.8.9 doesn't support it. |
| Document identifier scheme | Cycle 5.1 | Opaque key stored in DB, blob path derived in code |
| Entra ID scope | Cycle 5.3 | Single-user / personal directory |

## Risk register

| Risk | Cycle | Mitigation |
|---|---|---|
| Reflex won't containerize cleanly for production | 3.1–3.2 | This is *why* the POC exists — fail fast, before production work |
| Reflex websocket channel breaks through Container Apps ingress | 3.2 | Explicit test at Gate 3; Container Apps supports websockets but confirm |
| Free SQL tier doesn't apply to the subscription | 1.2 | Gate 1 stops the project before further spend |
| Cold-start latency makes scale-to-zero unusable | 3.2 | Measure at Gate 3; fallback is a minimum-1-replica cost estimate |
| Storage-path data migration corrupts document links | 5.1 | Do the stale-path cleanup first; migrate Test DB and verify before Prod |
| Azure SQL serverless auto-pause: first-request timeout / error after idle | 2.2+ | Measure cold-resume at Cycle 2.2 (H58 checklist); retry-on-resume wrapper as the next cycle; `LUCIDPM_SQL_LOGIN_TIMEOUT=60` interim |
| Cloud build accidentally ships with `lucidadmin` / PII in an image layer | 3.1–3.2 | Contained non-admin SQL user (both DBs); `.dockerignore` mirrors `.gitignore`; secrets only via `secretref:` |
| Entra + Reflex websocket auth handshake (PM proved Flask, not Reflex) | 5.3 | The one auth-path unknown the PM precedent doesn't cover — test with ingress still IP-restricted |
| Portfolio Manager holds surprises (unreviewed repo) | 6.1 | Gap analysis before any PM code change; estimates are soft until then |
