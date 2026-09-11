# LucidoPM — ChatGPT Handoff 64
*Containerize LucidPM: a single Docker image running Reflex + ODBC Driver 18, verified locally against Azure SQL*
*Prepared: 2026-09-10*
*Azure Migration — Stage 3, Cycle 3.1. HIGH risk — this is the cycle the roadmap flags as most likely to blow the schedule.*

---

## What This Is

Roadmap **Cycle 3.1** (`Undelivered Handoffs/Azure Migration Roadmap.md`, Stage 3). Package LucidPM into
one Docker image that runs both the Reflex frontend and backend as a single process, installs ODBC
Driver 18, and connects to Azure SQL — verified with `docker build` + `docker run` on Mark's machine.

**Scope constraint — this is Cycle 3.1 only.** It does **not** cover:
- Pushing the image anywhere (GHCR, private or otherwise) — that's Cycle 3.2.
- Creating an Azure Container App, Container Apps secrets, or ingress config — Cycle 3.2.
- Microsoft Entra authentication — Cycle 5.3.
- Blob storage for lease documents — Stage 4.

Done when: the image builds, runs locally, loads the real compiled app in a browser (not a blank
page), the Reflex event channel works (clicking things updates the UI), a PDF downloads, and it
connects to Azure SQL through the contained `lucidpm_app` user validated in Cycle 2.2 (Gate 2 PASSED
2026-09-10, `docs/cycle-2.2-validation.md`). Gate 3 (temp public URL, Container Apps ingress,
websocket-through-ingress, scale-to-zero) is Cycle 3.2's problem, not this one's.

Why this is HIGH risk: Reflex normally runs as **two** processes during development — a Vite/bun
frontend dev server (port 3000) and a Python/FastAPI backend (port 8000) — glued together by
`reflex run`. A production container needs **one** process serving everything on **one** port,
because that's what an ingress (or a person hitting `docker run -p`) can reasonably point at. Getting
that collapse right, without breaking the websocket event channel the whole UI depends on, is the
actual unknown. This handoff front-loads that specific question as a 15-minute, no-Docker spike
(Step 0) before committing to a full multi-stage build.

---

## Current State

**No Dockerfile or `.dockerignore` exist in this repo yet** (`ls .dockerignore` → not found).
`docs/Deployment.md:5` still reads *"no Docker/infrastructure-as-code in this repo"* — accurate today,
stale after this cycle lands.

**Pinned versions** (`requirements.txt` header, `pyproject.toml`, `.python-version`):
- Python **3.12.10** exact (`.python-version`) — match this in the base image tag, not a floating `3.12`.
- `reflex==0.8.9` — **load-bearing pin, do not bump.** App code uses `rx.Base` (14 live files under
  `LucidPM/pages/`), removed in Reflex 0.9.0. `pydantic<2.11` + `sqlmodel==0.0.24` are pinned together
  with it for the same reason (`requirements.txt` lines 6–13).
- `pyodbc==5.3.0` — confirmed in Cycle 2.2 to connect correctly over `sql` auth against Azure SQL
  (Windows Driver 18). This cycle's job is confirming the same on **Linux / unixODBC**, which H58's
  review flagged as "flakier" for the `UID={}`/`PWD={}` brace-escaping (`state._odbc_brace`,
  `state.py` ~line 151) — never tested on Linux until now.

**Entry point** (`LucidPM/LucidPM.py`):
- Line 37: `api = FastAPI()` — a real FastAPI instance.
- Lines 927–929: `app = rx.App(..., api_transformer=api)` — Reflex attaches its own routes
  (websocket event channel, `/ping`, uploads, etc.) onto this same `api` object rather than creating
  its own. This is the anchor for the static-file fallback in Step 1 below, if needed.
- Lines 932+: ~19 `app.add_page(..., route="/...")` calls. The custom `/api/*` PDF/report endpoints
  (rent roll, application report, leases-expiring) are registered on `api` elsewhere in the file —
  leave those untouched; they already work locally and were exercised again in Cycle 2.2.
- `/api/pick-files` (the old PowerShell file dialog) was deleted in Handoff 62 — nothing to worry
  about there.

**Config** (`rxconfig.py`): minimal — `rx.Config(app_name="LucidPM")` only. No `api_url` override in
code; `state.api_base_url()` (`state.py:232`, Handoff 59) reads Reflex's own resolved `api_url`,
which is `REFLEX_API_URL` env-driven. That env var will need to be set for the container test too
(see Validation Checklist), same mechanism Cycle 2.2 already exercised.

**DB connection** (Handoffs 58/60/63, all shipped and Cycle-2.2-verified): `state.get_conn()` builds
its connection string from `LUCIDPM_SQL_*` env vars, `sql`-auth branch confirmed working live against
`lucidpm-sql-24899.database.windows.net` with the contained `lucidpm_app` user
(`db/azure_app_user.sql`). Retry-on-resume defaults are `LUCIDPM_SQL_CONNECT_RETRIES=8` /
`_RETRY_BACKOFF=4` as of this session (`state.py` ~line 126–127). **None of this needs to change** —
the container just needs the same env vars set at `docker run` time. `_validate_sql_config()` runs at
**module import time** (`state.py:93`) with defaults that are internally consistent even when no env
vars are set (auth defaults to `"windows"`, which validates fine even though it'd never actually
connect on Linux) — so it will **not** raise during the Docker build step that imports the app to
compile the frontend (see Step 2). `get_fernet()`/`_fernet()` (Handoff 63) is lazy — not called at
import time — so a missing `LUCIDPM_FERNET_KEY` during the build is also not a build-time failure.

**Frontend toolchain — no system Node.js needed.** Confirmed from this week's local investigation
(the Smart App Control incident): Reflex manages its own frontend runtime under `.web/node_modules/`
via a bundled `bun` executable that it downloads on first `reflex init`/`export`/`run` — the blocked
file was `.web/node_modules/@rolldown/binding-win32-x64-msvc/...node`, a **platform-specific** binary
bun pulled down itself. Inside a Linux container, the equivalent Linux binary gets pulled instead,
and Windows Smart App Control (a Windows-only OS feature) is irrelevant — this whole class of problem
does not exist in the container. The build stage needs outbound network access (to fetch bun +
npm-style packages) and `curl`/`ca-certificates`, not a `nodejs` apt package.

---

## The Fix

### Step 0 — spike: does Reflex serve its own export? (no Docker, ~15 min)

Do this **before** writing the Dockerfile. It's the one real unknown, and it's cheap to check without
a container at all.

In the existing local `.venv` (any branch, doesn't need Azure):

```powershell
.venv\Scripts\reflex.exe export --frontend-only --no-zip
```

Note exactly where the static build lands (expected: `.web/build/client/`, but confirm — Reflex's
export layout can shift between versions and 0.8.9 hasn't been checked here before). Then:

```powershell
.venv\Scripts\reflex.exe run --env prod --backend-only --backend-port 8080
```

Open `http://localhost:8080/` in a browser.

- **If the real compiled app loads** (not a blank page, not a 404, not Reflex's dev-mode "frontend not
  running" message) — Reflex's own backend serves the exported static build automatically. Proceed to
  Step 1 with the Dockerfile as written below; no code change needed in `LucidPM.py`.
- **If it 404s / serves nothing at `/`** — Reflex expects a separate static host in production mode.
  Fall back to the manual mount, added to `LucidPM/LucidPM.py` **after all `app.add_page(...)` calls**
  (the mount is a catch-all at `/` and must not be registered before Reflex's own routes, or it will
  shadow them):

  ```python
  # LucidPM/LucidPM.py — add near the end of the file, after every app.add_page(...) call.
  # Only activates when LUCIDPM_FRONTEND_BUILD_DIR is set (i.e. inside the container); local
  # `reflex run` dev workflow is completely unaffected since that var is never set there.
  import os
  from fastapi.staticfiles import StaticFiles

  _frontend_build_dir = os.getenv("LUCIDPM_FRONTEND_BUILD_DIR")
  if _frontend_build_dir and os.path.isdir(_frontend_build_dir):
      api.mount("/", StaticFiles(directory=_frontend_build_dir, html=True), name="frontend")
  ```

  If this still doesn't work (a real page route now serves the static `index.html` instead of the
  app, or the websocket 404s), the mount is intercepting requests Reflex's own router should have
  handled first — the fix is registration order, not a different approach: move the `api.mount(...)`
  call later, or check whether Reflex populates `api.routes` at `rx.App()` construction time
  (`LucidPM.py:927`) vs. later at compile/serve time, and place the mount after whichever happens last.

Record which path was needed in the "Do Not Touch" note this handoff leaves behind, so Cycle 3.2
doesn't have to rediscover it.

### Step 1 — `.dockerignore` (new file, repo root)

**Critical:** without this, `COPY . .` bakes live secrets and tenant PII into an image layer —
image layers persist even if a later layer "deletes" the file, and even a private GHCR image (Cycle
3.2) is a real exposure surface. Mirror `.gitignore` plus container-specific excludes:

```
# Secrets / local config — never in an image layer
.env
.env.*
!.env.example

# Tenant PII exports (see CLAUDE.md standing notes — these hold old Fernet
# ciphertext too; also excluded from git)
db/TenantCRM*.sql
*.bacpac
*_Backup/

# Local dev artifacts — each build stage produces its own fresh copies
.web/
.venv/
__pycache__/
**/__pycache__/
*.pyc

# Not needed in the image
.git/
tests/
Archived Versions/
Undelivered Handoffs/
Completed Handoffs/
docs/
*.md
db/history/
db/data_updates/
```

### Step 2 — `Dockerfile` (new file, repo root)

```dockerfile
# ---- Stage 1: produce the Reflex frontend static export ----
FROM python:3.12.10-slim-bookworm AS builder
WORKDIR /app

# bun (Reflex's bundled JS runtime) needs network access + these tools to
# install itself and its packages — no system Node.js required (see Current
# State: this is the same bun-managed toolchain as local dev, Linux binaries).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Confirm this actually excludes what Step 1 lists — .dockerignore applies to
# this COPY the same as any other.

# Verify the exact output path against Step 0's finding before trusting this.
RUN reflex export --frontend-only --no-zip

# ---- Stage 2: runtime image ----
FROM python:3.12.10-slim-bookworm

# Microsoft ODBC Driver 18 — standard Debian 12 (bookworm) recipe.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg2 \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
         | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -o /etc/apt/sources.list.d/mssql-release.list \
         https://packages.microsoft.com/config/debian/12/prod.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
         msodbcsql18 unixodbc-dev \
    && apt-get purge -y --auto-remove curl gnupg2 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin lucidpm
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m compileall -q .

COPY . .
# Adjust this path once Step 0 confirms the real export location, and drop it
# entirely if the manual-mount fallback wasn't needed.
COPY --from=builder /app/.web/build/client ./.web/build/client

# Fix the exact PM lesson from the knowledge-share doc: container ran non-root
# but /app was still root-owned. chown BEFORE the USER switch, not after.
RUN chown -R lucidpm:lucidpm /app
USER lucidpm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LUCIDPM_ENV=cloud

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/ping').status==200 else 1)"

# Single process, single port, serves frontend + backend + the /api/* routes.
# --backend-only skips starting the (now unnecessary) separate frontend dev
# server; the exported static build is what actually serves the UI.
CMD ["reflex", "run", "--env", "prod", "--backend-only", \
     "--backend-host", "0.0.0.0", "--backend-port", "8080"]
```

Notes baked into the comments above, restated:
- Pin the **exact** Python patch version (`3.12.10`, not `3.12`) — same reasoning as `.python-version`.
- `LUCIDPM_ENV=cloud` is set as a build-time default (Handoff 58's inert marker for the Stage 5.3
  Entra header-trust gate) — harmless today, correct value for anything that runs this image.
- Port **8080** is a deliberate convention distinct from every local-dev port already in use
  (3000/8000/3002/8002) so a running container is never confused with a local session. Cycle 3.2
  picks whatever `ingress.targetPort` it wants at deploy time — this is not a constraint on that.
- Do **not** add a `HEALTHCHECK` that queries the database — `/ping` is Reflex's own built-in liveness
  endpoint (used by `Start-LucidPM.ps1` today) and answers without touching SQL. A DB-dependent health
  check would flap unhealthy during a legitimate Azure serverless resume.

### Step 3 — `docs/Deployment.md` reconcile (small)

Current (`docs/Deployment.md:5`):
```
LucidPM runs locally only, on Mark's dev machine, against a local SQL Server Express instance. There is no staging or production deployment, no CI/CD pipeline, and no Docker/infrastructure-as-code in this repo.
```
Replace with a short "Containerization" section noting the Dockerfile exists, what it does (single
image, single process, ports 8080, ODBC 18, contained-user SQL auth), and that it is verified locally
only — no registry push, no Container App yet (that's Cycle 3.2, tracked in the roadmap).

Also fix line 19, which is now stale in the other direction:
```
~~The Fernet key for config secrets was stored in `dbo.AppSettings`~~ — moved to the `LUCIDPM_FERNET_KEY` environment variable in Handoff 63; its rotation runbook is pending.
```
The rotation is done (2026-09-09) — drop "its rotation runbook is pending."

---

## Do Not Touch

- **Reflex version.** `reflex==0.8.9` stays pinned. Do not "just try 0.9" to see if it simplifies the
  export story — it removes `rx.Base`, breaking 14 live page files.
- **`state.py`'s connection/retry/Fernet logic.** All of it was validated end-to-end against Azure SQL
  in Cycle 2.2 (2026-09-10). This cycle only needs it to run on Linux with the same env vars — if it
  doesn't connect, the bug is almost certainly the `_odbc_brace` escaping on unixODBC (H58's flagged
  risk) or a missing/misspelled env var, not the retry/Fernet mechanisms themselves.
- **Windows auth.** Never test `LUCIDPM_SQL_AUTH=windows` in the container — `Trusted_Connection=yes`
  cannot work on Linux against this server. Always `sql` auth with `lucidpm_app`.
- **`pages/*.py` application logic.** Nothing here should require an app-code change beyond the
  possible `LucidPM.py` static-mount fallback in Step 0/1, which is additive and env-gated.
- **Local dev scripts** (`Start-LucidPM.ps1`, `Start-LucidPM-Azure.ps1`) — untouched; they still target
  the un-containerized `.venv` workflow.
- **Cycle 3.2 concerns** — no GHCR account/token creation, no `az containerapp create`, no Entra app
  registration. This handoff's Docker image never leaves Mark's machine.
- **The stale-`StoredFilePath` data issue** (`C:\Dell Inspirion\...`, standing TOP-PRIORITY item) —
  unrelated to this cycle; PDF-only lease sections will still fail to generate inside the container for
  the same pre-existing reason they fail locally. Not a regression to chase here.

---

## Validation Checklist

### A — build, no Azure needed

- [ ] Step 0 spike completed; the "does Reflex serve its own export" question is answered and
      recorded (which path — native or manual mount).
- [ ] `docker build -t lucidpm:dev .` succeeds.
- [ ] `docker run --rm lucidpm:dev whoami` → `lucidpm`, not `root`.
- [ ] `docker run --rm lucidpm:dev sh -c 'ls -la /app.env 2>&1; ls -la /app/.env 2>&1'` → confirms
      `.env` is **not** present inside the image (the `.dockerignore` did its job).
- [ ] `docker run --rm lucidpm:dev sh -c 'ls db/ 2>&1'` — confirms no `TenantCRM*.sql` /`.bacpac` files
      made it in.
- [ ] Image size is reasonable (no accidental inclusion of `Archived Versions/` or `.git/`).

### B — run against Azure SQL (reuses Cycle 2.2's `lucidpm_app`)

- [ ] `docker run -p 8080:8080` with the H58 env vars (`LUCIDPM_SQL_SERVER`, `LUCIDPM_SQL_AUTH=sql`,
      `LUCIDPM_SQL_USER=lucidpm_app`, `LUCIDPM_SQL_PASSWORD`, `LUCIDPM_PROD_DB`, `LUCIDPM_TEST_DB`,
      `LUCIDPM_SQL_TRUST_CERT=no`) + `LUCIDPM_FERNET_KEY` (from `.env`) + `REFLEX_API_URL=http://localhost:8080`.
- [ ] `http://localhost:8080/` loads the **real compiled app** in a browser — not blank, not a 404,
      not Reflex's "frontend not running" placeholder.
- [ ] Click into at least one page that requires the event channel (e.g. the Test/Prod toggle, or
      opening a tenant detail) — **this is the core risk this cycle exists to retire**: confirm the
      websocket-driven UI actually updates inside a single-process container, not just that the
      initial HTML painted.
- [ ] A PDF download works (e.g. Rent Roll) — proves `REFLEX_API_URL` / `state.api_base_url()` and the
      custom `/api/*` routes on `api` still resolve correctly alongside whatever serves the frontend.
- [ ] ODBC connects successfully — **first-ever test of `_odbc_brace`/`UID={}`/`PWD={}` on unixODBC**
      (H58 review finding, flagged since 2026-09-07). If login fails but the same credentials work
      from Windows, this escaping is the prime suspect — try a password without `}`/`;`/`=` to isolate.
- [ ] `docker logs` shows no unhandled exception on startup or on first request.
- [ ] `docker inspect --format='{{.State.Health.Status}}' <container>` → `healthy` after the start
      period.

### C — housekeeping

- [ ] `docs/Deployment.md` reconciled (Step 3).
- [ ] This handoff records, for Cycle 3.2's benefit: the exact export output path found in Step 0,
      whether the native or manual-mount path was used, and any unixODBC surprises.

**Done when:** all of A and B pass. Gate 3 (temp public URL via Container Apps, ingress websocket
survival, scale-to-zero) is Cycle 3.2 — do not attempt it here.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  Dockerfile                  ← new, Step 2
  .dockerignore                ← new, Step 1
  LucidPM\LucidPM.py           ← conditional edit, Step 0 (only if native serving doesn't work)
  docs\Deployment.md            ← Step 3
```

Reference material already in the repo — read before starting, don't re-derive:
```
Undelivered Handoffs\Azure Migration Roadmap.md              ← Stage 3 / Cycle 3.1 definition, open decisions table
Undelivered Handoffs\lucidpm-cloud-migration-knowledge-share.md  ← the PM precedent: non-root/chown fix,
                                                                    .dockerignore categories, "Docker Desktop
                                                                    engine must be running" gotcha, contained-
                                                                    user pattern (already done here, Cycle 2.2)
docs\cycle-2.2-validation.md                                   ← proof the SQL layer already works; don't re-test
                                                                    what Cycle 2.2 already covered end-to-end
db\azure_app_user.sql                                          ← the lucidpm_app user this cycle connects with
```
