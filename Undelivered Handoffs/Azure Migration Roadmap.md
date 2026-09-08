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
| 0 — Code prep | App is deploy-ready; no Windows-only assumptions; config is env-driven | 4–5 | — |
| 1 — Azure foundation | Subscription, resource group, SQL server, free DB confirmed at ~$0 | 2 | **G1: free tier real?** |
| 2 — App vs Azure SQL | LucidPM runs locally against Azure SQL, core workflows validated | 2–3 | **G2: SQL works?** |
| 3 — Containerize + deploy | LucidPM live on a temp `*.azurecontainerapps.io` URL, scaling to zero | 3–5 | **G3: Reflex in a container?** |
| 4 — Blob storage | One lease PDF survives a container restart — **POC COMPLETE** | 2 | **G4: commit to production?** |
| 5 — LucidPM production | Real data migrated, auth, custom subdomain, cutover | 6–8 | — |
| 6 — Portfolio Manager | Second Container App, cross-DB refactor, its own subdomain | 8–12 (soft) | — |

**To POC complete (Stages 0–4): 11–15 cycles.**
**LucidPM fully in production (through Stage 5): 17–23 cycles.**
**Both apps done (through Stage 6): 25–35 cycles.**

At the current part-time cadence (~1–2 cycles/week with verification in the loop): POC ≈ 2–3 months,
everything ≈ 6–12 months.

---

## Progress log

- **2026-09-05** — Roadmap written.
- **2026-09-06 — Stage 1 complete, Gate 1 PASSED.** Subscription `Lucido-Apps` (Azure Plan / pay-as-you-go
  under Microsoft Customer Agreement, ID `76290cf4-215e-4da5-b9ae-572e0fad7052`) in the personal
  `mslucidogmail.onmicrosoft.com` tenant. `$1` budget alert set (actual + forecasted at 100%). Resources:
  - Resource group `Lucido-Apps-RG` (RG metadata location eastus2).
  - SQL logical server `lucidpm-sql-24899` in **westus3** — East US / East US 2 / South Central US all
    rejected new SQL servers with `RegionDoesNotAllowProvisioning` (new-subscription throttle); westus3
    worked and supports the free offer, so **westus3 is the project region** for Container Apps + Storage too.
  - Admin login `lucidadmin` (password in Mark's password manager).
  - Firewall rule `AllowAzureServices` (0.0.0.0). Mark's client IP still to be added for SSMS (Cycle 2.1).
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
- **Next:** Cycle 2.2 / Gate 2 — run H58's Part B checklist against Azure SQL (process env vars in one shell,
  ports 3002/8002), capture cold-resume-from-auto-pause latency as the retry-wrapper input.
  Stage 0 code prep 0.1 / 0.2 / 0.4 has no Azure dependency and can run in parallel.

---

## Stage 0 — Code prep (no Azure resource required; can start now)

These fix the blockers the architect addendum found in the real repo. None need Azure to exist, and each
leaves local behaviour unchanged when no cloud env vars are set.

### Cycle 0.1 — Project scaffolding *(Claude-direct or small handoff)*
- Add `pyproject.toml` / `requirements.txt` with pinned versions, reconstructed from source imports
  (`reflex`, `pyodbc`, `fastapi`, `reportlab`, `pypdf`, `cryptography`, + whatever grep turns up).
- Add `rxconfig.py` if the tracked repo genuinely lacks one; document setup in `docs/Developer Setup`.
- **Done when:** a fresh clone → install → `reflex run` works with no tribal knowledge.
- Risk: low. May take iteration to pin exact working versions.

### Cycle 0.2 — Browser-native file input *(handoff)*
- Replace `/api/pick-files` in `LucidPM_Reflex.py` (~lines 39–76) — it shells out to PowerShell for a native
  Windows `OpenFileDialog` against a hardcoded `Generated` path. No Linux equivalent, no fallback.
- Swap for `rx.upload` / a browser file input; update every call site that consumes the picker's result.
- **Done when:** file selection works with zero Windows/PowerShell dependency.
- Risk: medium — downstream code assumes a local absolute path came back.

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

### Cycle 0.4 — Fernet key out of the database *(handoff)*
- `settings.py` (~lines 35–57) stores the Fernet key (`LocalEncryptionKey`) in the same `AppSettings` table as
  the SMTP / AI-key ciphertext it protects — which defeats encrypting at rest.
- Move the key to an env var / mounted secret (later: Container Apps secret or Key Vault). Preserve the current
  key as the first value so existing encrypted rows still decrypt; document rotation.
- **Done when:** secrets still decrypt, key is no longer in any DB row.
- Risk: medium — losing the key makes encrypted config unrecoverable. Extract the current key first.

**Gate 0:** all four committed, `git` clean, local app fully working. Zero Azure spend so far.

---

## Stage 1 — Azure foundation

### Cycle 1.1 — Subscription + CLI + resource group *(mostly Mark; POC-A)* — ✅ DONE 2026-09-06
- Used an existing pay-as-you-go subscription (`Lucido-Apps`) in the personal tenant; no new signup needed.
- `az` not installed locally — used **Azure Cloud Shell** (Bash, no storage). Install the CLI locally before
  Stage 3.
- `Lucido-Apps-RG` created; `$1` budget alert set.

### Cycle 1.2 — SQL server + free database *(POC-B)* — **GATE 1** ✅ PASSED 2026-09-06
- Server `lucidpm-sql-24899` in **westus3** (East US regions were throttled for the new subscription).
- Database `TenantCRM`, serverless, `useFreeLimit: true`, `AutoPause` on exhaustion — confirmed $0.
- **G1 — PASSED.** The free tier applies. Proceed.
- Outstanding: add Mark's client IP to the server firewall for SSMS (Cycle 2.1).

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

### Cycle 2.2 — Local app against Azure SQL *(POC-C, part 2)* — **GATE 2**
- Point local LucidPM at the Azure DB via the Stage 0.3 env vars (SQL auth). H58 shipped the plumbing;
  Part B of its checklist **is** this cycle.
- **First real test of the SQL-auth connection string** (H58 review finding 3 — string construction is
  verified, a live SQL-auth login is not). If login fails despite correct credentials, suspect the
  `UID={...}` / `PWD={...}` brace-escaping in `state._odbc_brace` / `get_conn` — try an unbraced `UID=` and
  a password without `}` to isolate.
- Walk the major workflows: tenant / lease CRUD, rent schedules, property financials, analytics, lease document
  generation, PDF generation.
- Measure latency — a local app against a cloud DB is slower; confirm it's tolerable. Capture the
  **cold-resume-from-auto-pause** number (H58 Part B) as the retry-wrapper input.
- **G2 — GO/NO-GO:** any blocking pyodbc/Azure-SQL incompatibility, or unworkable latency, surfaces here before
  the container work starts.
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
- **Fix the hardcoded `http://localhost:8000` URLs before this ships — Handoff 59 written + Codex-reviewed
  2026-09-07** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_59_ApiBaseUrl.md`, not started). 8 live page
  modules; fix = `state.api_base_url()` off Reflex's `api_url` config. No Azure dependency — can land any time
  before 3.1; then set `REFLEX_API_URL` (or `rxconfig.py`) to the ingress host here in 3.1.
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
