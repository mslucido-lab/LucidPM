# LucidoPM — ChatGPT Handoff 64
*Containerize LucidPM: a single Docker image running Reflex + ODBC Driver 18, verified locally against Azure SQL*
*Prepared: 2026-09-10 · revised 2026-09-11 (Codex pre-implementation review, 4 points + 1 preflight, all accepted):*
*(1) `REFLEX_API_URL` is baked into the compiled frontend bundle by `reflex export` — setting it at*
*`docker run` time is too late, and Step 0's original wording (export first, then run the backend on a*
*different port) would have given a false failure. Fixed: set it as a Docker build ARG, and set it*
*before `reflex export` in Step 0 too. Verified against Reflex 0.8.9's own source — see Step 0.*
*(2) The static-file fallback's `LUCIDPM_FRONTEND_BUILD_DIR` was never actually set anywhere — added,*
*conditional on Step 0 needing the fallback. (3) `compileall` ran before `COPY . .`, compiling nothing —*
*moved after. (4) "Single process" reworded to "single container, single exposed port" — `reflex run*
*--backend-only` is a CLI launcher and may supervise more than one OS process; the real bar is one port*
*serving frontend + backend + websocket + `/api/*`, proven by the browser event-channel test, not by*
*counting processes. Plus: Docker Desktop's engine must be running (installed but stopped is not*
*enough) before Step 2's `docker build`.*
*Revised again 2026-09-11 (Codex follow-up, 3 points, all accepted): two leftover "single process"*
*references (opening paragraph, Step 3) reworded to match point 4 above; `.venv\Scripts\reflex.exe`*
*fixed to `.\.venv\Scripts\reflex.exe` in Step 0 (a bare relative path isn't directly executable in*
*PowerShell — the same class of issue hit during Handoff 63); Validation B's env-var delivery changed*
*from individual `-e` flags to `docker run --env-file .env.docker` (a new, gitignored file — NOT the*
*main `.env`, which is Windows-auth-defaulted for host dev and would launch the container with an*
*auth mode that cannot work on Linux at all) to keep secrets out of PowerShell history.*
*Revised a third time 2026-09-11 (Codex ran Step 0's spike; result required a design change, not a*
*wording fix): the manual `StaticFiles` mount fallback is REMOVED — Reflex attaches its own internal*
*ASGI routes (websocket event channel, `/_upload`, `/ping`) onto the `api` object only when the server*
*factory runs, which is after `LucidPM.py` finishes importing. There is no point in application code*
*where a mount is guaranteed to register after Reflex's own routes, so any `LucidPM.py`-level mount*
*would always intercept them first and break the websocket channel. (No tracked source file was*
*changed proving this — only gitignored `.web/` build output was touched.) Fix: **Caddy**, a second*
*process in the same container, added in front of Reflex instead of a mount inside it — Caddy owns*
*the one exposed port (8080), serves the static export directly, and reverse-proxies*
*`/_event`/`/_upload`/`/api/*`/`/ping`/`/_health` to the Reflex backend on internal-only*
*`127.0.0.1:8000`. Net effect: no `LucidPM.py` change at all (a simplification), `Caddyfile` and*
*`entrypoint.sh` added as new files, `LUCIDPM_FRONTEND_BUILD_DIR` fully removed (it was only ever for*
*the now-deleted fallback). See Step 0 and Step 2.*
*Azure Migration — Stage 3, Cycle 3.1. HIGH risk — this is the cycle the roadmap flags as most likely to blow the schedule.*

---

## Status

**Implemented and verified locally 2026-09-11.** Docker built `lucidpm:dev`; the image runs as non-root
`lucidpm`, passed Caddy and entrypoint syntax checks, and excludes `.env`, `.env.docker`, and local database
exports. With `.env.docker`, Caddy served the exported app and `/ping` on port 8080 while port 8000 remained
unreachable from the host. Read-only SQL checks reached both Azure databases through Linux ODBC Driver 18.
Mark verified browser navigation and switching between Demo and Prod. Terminating Reflex stopped Caddy and
exited the full container, confirming the two-process supervisor works.

The implementation added `unixodbc-dev` to the builder stage because Reflex's frontend export imports
`pyodbc`, and retains `curl` until after the Caddy binary download. These are required build-order details,
not scope changes.

## What This Is

Roadmap **Cycle 3.1** (`Undelivered Handoffs/Azure Migration Roadmap.md`, Stage 3). Package LucidPM into
one Docker image that serves both the Reflex frontend and backend through a single exposed port, installs ODBC
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
`reflex run`. A production container needs **one exposed port** serving everything, because that's
what an ingress (or a person hitting `docker run -p`) can reasonably point at. (Not literally one OS
process — `reflex run --backend-only` is itself a CLI launcher and may supervise more than one; what
actually matters is one port answering for frontend + backend + websocket + `/api/*`, which is what
the Validation Checklist proves, not process-counting.) Getting that collapse right, without breaking
the websocket event channel the whole UI depends on, is the actual unknown. This handoff front-loads
that specific question as a 15-minute, no-Docker spike (Step 0) before committing to a full
multi-stage build.

**Preflight:** Docker Desktop is installed on this machine but its engine may not be running —
*installed* is not the same as *running* (hit exactly this in the PM migration per the knowledge-share
doc's "Problems encountered" table). Start Docker Desktop and confirm `docker info` succeeds before
Step 2's `docker build`. Step 0 needs no Docker at all — it runs directly in the existing `.venv`.

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
  (websocket event channel, `/ping`, uploads, etc.) onto this same `api` object, but only when the
  server factory runs — **after** this module finishes importing, not at construction time. That
  timing is exactly why a static-file mount can't safely live in this file (see Step 0) and why Step 2
  puts Caddy in front instead.
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

### Step 0 — RESOLVED: does Reflex serve its own export? (Caddy reverse proxy, not a mount)

Do this **before** writing the Dockerfile. It's the one real unknown, and it's cheap to check without
a container at all.

**RESOLVED by running the spike (2026-09-11): Reflex does not serve its own export from application
code, and the manual `StaticFiles` mount cannot be made safe.** Reflex attaches its own internal ASGI
routes (the websocket event channel, `/_upload`, `/ping`, etc.) onto the `api` object only when the
server factory actually runs — **after** `LucidPM.py` has finished being imported, not at
`rx.App(..., api_transformer=api)` construction time and not after the last `app.add_page(...)` call.
There is no point in application code, at module level, where a manual `api.mount("/", StaticFiles(...))`
is guaranteed to run *after* Reflex's own routes are attached — it would always end up registered
first, and a catch-all mount at `/` intercepts every request before Reflex's own router is ever
reached, breaking the websocket channel. (No tracked source file was changed proving this — the spike
only touched the gitignored `.web/` build output.)

**Fix: a reverse proxy in front of Reflex, not a mount inside it.** Add **Caddy** as a second process
in the same container, and let it own the one externally exposed port instead of Reflex:

- Caddy listens on **`:8080`** (the one exposed port — `REFLEX_API_URL=http://localhost:8080`,
  already decided in the previous revision, still stands and is now *more* clearly correct: it's the
  one origin the browser ever talks to).
- Caddy serves the static export (`.web/build/client`) directly for asset requests, falling back to
  `index.html` for anything else so client-side routing (react-router) still works on a direct page
  load/refresh, not just in-app navigation.
- Caddy reverse-proxies `/_event`, `/_upload`, `/api/*` (the 9 custom PDF/report routes registered on
  `api` in `LucidPM.py`, all under `/api/...` — confirmed: `grep -n '@api\.\(get\|post\)' LucidPM/LucidPM.py`),
  `/ping`, and `/_health` to the Reflex backend, which runs `--backend-only` bound to **`127.0.0.1:8000`**
  — loopback only, never published, never reachable except through Caddy. Caddy's `reverse_proxy`
  handles the WebSocket upgrade (`Connection: Upgrade`) transparently, no special config needed.
- This satisfies the acceptance bar from the previous revision exactly as worded — **one container,
  one exposed port, one origin** — while making zero assumptions about Reflex's internal route-attach
  timing. It also means **no `LucidPM.py` change at all**, which is a net simplification versus the
  fallback this revision removes.

This is Step 2's Dockerfile now — no separate spike command to run before it; the finding above *is*
the resolved Step 0.

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

# REFLEX_API_URL is read by `reflex export` at build.build() time (Reflex
# 0.8.9, reflex/utils/export.py) and baked into the compiled JS bundle — it is
# NOT something `docker run -e` can fix later. Passed as a build ARG so Cycle
# 3.1's local value (this container's own published port) and Cycle 3.2's
# eventual Container Apps URL can differ without touching the Dockerfile —
# see "Open question carried to Cycle 3.2" below for why this must change
# again before that cycle, not just get a new --build-arg value.
ARG REFLEX_API_URL=http://localhost:8080
ENV REFLEX_API_URL=$REFLEX_API_URL

# Verify the exact output path against Step 0's finding before trusting this.
RUN reflex export --frontend-only --no-zip

# ---- Stage 2: runtime image ----
FROM python:3.12.10-slim-bookworm
ARG REFLEX_API_URL=http://localhost:8080
ARG CADDY_VERSION=2.8.4
# ^ Verify this is still current at https://github.com/caddyserver/caddy/releases
#   before implementation — not re-checked as part of this revision.

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

# Caddy: static binary release, not a third-party apt repo — avoids adding a
# second GPG key/source list alongside Microsoft's, for one small binary.
RUN curl -fsSL -o /tmp/caddy.tar.gz \
      "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" \
    && tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy \
    && rm /tmp/caddy.tar.gz \
    && chmod +x /usr/local/bin/caddy

RUN useradd --create-home --shell /usr/sbin/nologin lucidpm
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# compileall must run AFTER the application source is copied in — running it
# against a directory that only holds requirements.txt (the original ordering)
# compiles nothing useful. Runs as root, before the ownership change below.
RUN python -m compileall -q .

COPY --from=builder /app/.web/build/client ./.web/build/client
COPY Caddyfile ./Caddyfile
COPY entrypoint.sh ./entrypoint.sh

# Fix the exact PM lesson from the knowledge-share doc: container ran non-root
# but /app was still root-owned. chown BEFORE the USER switch, not after.
RUN chown -R lucidpm:lucidpm /app && chmod +x ./entrypoint.sh
USER lucidpm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LUCIDPM_ENV=cloud \
    REFLEX_API_URL=$REFLEX_API_URL
# REFLEX_API_URL here is read at RUNTIME by the live Python process
# (state.api_base_url() / rx.config.get_config().api_url) to build PDF/report
# download links — a separate consumer from the JS bundle the builder stage
# baked. Must match the build-time value above or the two disagree about
# where "the API" is.

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/ping').status==200 else 1)"
# Deliberately hits port 8080 (through Caddy), not 8000 directly — this
# verifies the WHOLE chain (Caddy up + proxying correctly + backend
# answering), not just one half of it.

# One container, one exposed port (8080/Caddy). Reflex's backend binds to
# 127.0.0.1:8000 — loopback only, never published, reachable only through
# Caddy. See entrypoint.sh for how the two processes are started/supervised.
CMD ["/bin/bash", "/app/entrypoint.sh"]
```

**`Caddyfile`** (new file, repo root):

```caddyfile
:8080 {
	# The Reflex backend owns these — the websocket event channel, uploads,
	# the 9 custom /api/* PDF/report routes, and health checks. reverse_proxy
	# handles the WebSocket Upgrade transparently, no extra config needed.
	@backend path /_event* /_upload* /api/* /ping /_health*
	handle @backend {
		reverse_proxy 127.0.0.1:8000
	}

	# Everything else: the static export. try_files falls back to index.html
	# for any path that isn't a literal file, so a direct load/refresh of a
	# client-routed page (e.g. GET /tenants) still works, not just in-app
	# navigation.
	handle {
		root * /app/.web/build/client
		try_files {path} /index.html
		file_server
	}
}
```

**`entrypoint.sh`** (new file, repo root):

```bash
#!/bin/bash
set -e

reflex run --env prod --backend-only --backend-host 127.0.0.1 --backend-port 8000 &
BACKEND_PID=$!

caddy run --config /app/Caddyfile --adapter caddyfile &
CADDY_PID=$!

# Minimal supervision for Cycle 3.1's "prove it works" bar: if EITHER process
# exits (crash or otherwise), tear down the other and exit non-zero, so
# `docker ps` / a future Container Apps replica correctly reports the
# container as failed rather than silently serving a half-broken app (e.g.
# Caddy still answering static files with a dead backend behind it). A real
# process manager (tini + supervisor, or splitting Caddy into its own
# sidecar) is a Cycle 3.2+ hardening item if this proves flaky — not needed
# to prove the container works at all.
wait -n "$BACKEND_PID" "$CADDY_PID"
EXIT_CODE=$?
kill "$BACKEND_PID" "$CADDY_PID" 2>/dev/null || true
exit "$EXIT_CODE"
```

`wait -n` needs `bash` (it's not in POSIX `sh`/dash, Debian's default `/bin/sh`) — that's why the
Dockerfile's `CMD` explicitly invokes `/bin/bash /app/entrypoint.sh` rather than relying on the
shebang + exec bit alone.

Build with the matching value explicitly, rather than relying on the `ARG` default silently agreeing
with itself:

```powershell
docker build --build-arg REFLEX_API_URL=http://localhost:8080 -t lucidpm:dev .
```

Notes baked into the comments above, restated:
- Pin the **exact** Python patch version (`3.12.10`, not `3.12`) — same reasoning as `.python-version`.
- `LUCIDPM_ENV=cloud` is set as a build-time default (Handoff 58's inert marker for the Stage 5.3
  Entra header-trust gate) — harmless today, correct value for anything that runs this image.
- Port **8080** is a deliberate convention distinct from every local-dev port already in use
  (3000/8000/3002/8002) so a running container is never confused with a local session. Cycle 3.2
  picks whatever `ingress.targetPort` it wants at deploy time — this is not a constraint on that.
  Internal port **8000** (the Reflex backend) is loopback-only by design — bound to `127.0.0.1`, not
  `0.0.0.0`, so it isn't reachable even if someone adds `-p 8000:8000` at `docker run` time.
- Do **not** add a `HEALTHCHECK` that queries the database — `/ping` is Reflex's own built-in liveness
  endpoint (used by `Start-LucidPM.ps1` today) and answers without touching SQL. A DB-dependent health
  check would flap unhealthy during a legitimate Azure serverless resume.
- Caddy's `:8080` site block (a bare port, no domain name) never attempts automatic HTTPS/ACME — it's
  plain HTTP inside the container, which is correct here; TLS termination is Container Apps ingress's
  job in Cycle 3.2, not this image's.

### Open question carried to Cycle 3.2 — the baked absolute API URL

Baking `REFLEX_API_URL` into the frontend bundle at build time (Step 2) works for Cycle 3.1 — the
value is fixed and known (`http://localhost:8080`) because this cycle only runs the image on the
machine that built it. It will **not** survive Cycle 3.2 unchanged: an image built with
`http://localhost:8080` baked in, then deployed to a Container App, would ship a browser bundle that
tries to call back to the *deploying machine's* localhost — wrong from any other browser, and wrong
again the moment the temporary `*.azurecontainerapps.io` hostname is later replaced by a custom domain
(Stage 5.4), since that's yet another absolute URL.

Two ways to resolve this, to be decided **before** Cycle 3.2, not rediscovered mid-cycle:
1. **Rebuild per environment** — pass a different `--build-arg REFLEX_API_URL=...` for each target
   (local test, Container Apps temp URL, eventual custom domain) and publish a distinct image each
   time. Simple, guaranteed to work, but means "the image" isn't really one portable artifact — Cycle
   3.2's plan to push one versioned tag to GHCR would need to mean one *build recipe*, not one *image*,
   across environments.
2. **Same-origin / relative URLs** — if Reflex can be told to emit relative paths (no host/port at
   all) for its API/websocket calls, the browser naturally targets whatever host served the page,
   and the exact same image works unmodified in local Docker, Container Apps, and behind a future
   custom domain. This is the architecturally cleaner answer and avoids the "which URL was this image
   built with" bookkeeping entirely — but it is **not verified against Reflex 0.8.9** and needs a
   spike of its own (does `config.api_url` accept a bare path, does the websocket upgrade logic in
   `reflex/constants/event.py` cope with one) before it can be trusted.

Cycle 3.1 does not need to answer this — option 1 with a fixed local value is sufficient to prove the
container works at all. Record the decision in the roadmap's "Open decisions to resolve" table before
starting Cycle 3.2.

### Step 3 — `docs/Deployment.md` reconcile (small)

Current (`docs/Deployment.md:5`):
```
LucidPM runs locally only, on Mark's dev machine, against a local SQL Server Express instance. There is no staging or production deployment, no CI/CD pipeline, and no Docker/infrastructure-as-code in this repo.
```
Replace with a short "Containerization" section noting the Dockerfile exists, what it does (single
exposed port 8080 via a Caddy reverse proxy — Caddy serves the static frontend export directly and
proxies the websocket/`/api/*`/health routes to the Reflex backend on internal-only `127.0.0.1:8000`,
ODBC 18, contained-user SQL auth), and that it is verified locally only — no registry push, no
Container App yet (that's Cycle 3.2, tracked in the roadmap).

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
- **`pages/*.py` and `LucidPM.py` application logic.** No app-code change is needed for this cycle at
  all — the Caddy reverse-proxy design (Step 0/2) resolves the frontend-serving problem entirely
  outside application code.
- **Caddy's TLS/ACME behavior.** The `Caddyfile`'s `:8080` block is a bare port with no domain name —
  do not add a `tls` directive or a real hostname; that would make Caddy attempt automatic HTTPS
  certificate provisioning, which cannot work inside a container with no public DNS name and isn't
  this cycle's job (Container Apps ingress owns TLS in Cycle 3.2).
- **The internal backend port.** Reflex's backend binds to `127.0.0.1:8000` deliberately — never
  change that to `0.0.0.0`, and never add `-p 8000:8000` when testing. Caddy is the only thing that
  should ever reach it.
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

- [ ] Docker Desktop's **engine** is running — `docker info` succeeds (not just the app being
      installed; confirm before assuming a build failure is code-related).
- [ ] Verify the pinned `CADDY_VERSION` (`2.8.4` as drafted) is still a current release at
      `https://github.com/caddyserver/caddy/releases` — bump the `ARG` default if not.
- [ ] `docker build --build-arg REFLEX_API_URL=http://localhost:8080 -t lucidpm:dev .` succeeds
      (builder stage's `reflex export` + both apt/binary installs in the runtime stage).
- [ ] `docker run --rm lucidpm:dev whoami` → `lucidpm`, not `root`.
- [ ] `docker run --rm lucidpm:dev caddy validate --config /app/Caddyfile --adapter caddyfile` →
      confirms the Caddyfile syntax is valid before ever starting the full container.
- [ ] `docker run --rm lucidpm:dev sh -c 'ls -la /app.env 2>&1; ls -la /app/.env 2>&1'` → confirms
      `.env` is **not** present inside the image (the `.dockerignore` did its job).
- [ ] `docker run --rm lucidpm:dev sh -c 'ls db/ 2>&1'` — confirms no `TenantCRM*.sql` /`.bacpac` files
      made it in.
- [ ] Image size is reasonable (no accidental inclusion of `Archived Versions/` or `.git/`).

### B — run against Azure SQL (reuses Cycle 2.2's `lucidpm_app`)

- [ ] Create **`.env.docker`** (repo root, gitignored — matches the existing `.env.*` wildcard in
      `.gitignore`, and already excluded from the image by Step 1's `.dockerignore`). **Not** the main
      `.env`: that file is defaulted for host-Windows local dev (Windows auth against
      `localhost\SQLEXPRESS`), which cannot work at all from inside a Linux container, so
      `--env-file .env` would launch the container with an auth mode guaranteed to fail rather than
      just being wrong. `.env.docker` holds:
      ```
      LUCIDPM_SQL_SERVER=lucidpm-sql-24899.database.windows.net
      LUCIDPM_SQL_AUTH=sql
      LUCIDPM_SQL_USER=lucidpm_app
      LUCIDPM_SQL_PASSWORD=<the lucidpm_app password>
      LUCIDPM_SQL_TRUST_CERT=no
      LUCIDPM_PROD_DB=TenantCRM
      LUCIDPM_TEST_DB=TenantCRM_Test
      LUCIDPM_FERNET_KEY=<copy the current value from .env>
      LUCIDPM_ENV=cloud
      REFLEX_API_URL=http://localhost:8080
      ```
      Then: `docker run --env-file .env.docker -p 8080:8080 lucidpm:dev` — keeps every secret out of
      PowerShell history and off the command line. **Do not** additionally pass `-e REFLEX_API_URL=...`
      on the command line expecting it to fix a wrong frontend bundle — that value is already fixed,
      baked in at `docker build` time via `--build-arg`; the `REFLEX_API_URL` line in `.env.docker`
      above only matters for the *Python-side* runtime read (`state.api_base_url()`) and should match
      the build-time value, not override it.
      Aside: `state.py`'s own dependency-free `.env` file loader looks for a literal `.env` in the
      working directory, which won't exist inside the container (excluded by `.dockerignore`) — that's
      fine and expected. `docker run --env-file` sets real OS environment variables before the Python
      process starts, so `os.getenv()` sees them directly; the loader's absence-of-`.env` fallback is a
      silent no-op. This is also a preview of how Cycle 3.2's Container Apps `secretref:` env vars will
      reach the app — same mechanism, no code difference.
- [ ] `http://localhost:8080/` loads the **real compiled app** in a browser — not blank, not a 404,
      not Reflex's "frontend not running" placeholder. Check devtools' Network tab: requests should
      target `localhost:8080`, not `8000` — a `8000` sighting means the build-arg didn't take.
- [ ] Click into at least one page that requires the event channel (e.g. the Test/Prod toggle, or
      opening a tenant detail) — **this is the core risk this cycle exists to retire**: confirm the
      websocket-driven UI actually updates through the container's single exposed port, not just that
      the initial HTML painted.
- [ ] A PDF download works (e.g. Rent Roll) — proves `REFLEX_API_URL` / `state.api_base_url()` and the
      custom `/api/*` routes on `api` still resolve correctly alongside whatever serves the frontend.
- [ ] ODBC connects successfully — **first-ever test of `_odbc_brace`/`UID={}`/`PWD={}` on unixODBC**
      (H58 review finding, flagged since 2026-09-07). If login fails but the same credentials work
      from Windows, this escaping is the prime suspect — try a password without `}`/`;`/`=` to isolate.
- [ ] `docker logs` shows no unhandled exception on startup or on first request; both `reflex run` and
      `caddy run` should have clean startup lines.
- [ ] `docker inspect --format='{{.State.Health.Status}}' <container>` → `healthy` after the start
      period. Because the healthcheck goes through Caddy to `/ping` (not straight to the backend),
      `healthy` here proves the whole chain, not just one process.
- [ ] Confirm port isolation: from the host, `curl http://localhost:8000/ping` should **fail to
      connect** (nothing published on 8000) — only 8080 is reachable.
- [ ] Confirm `entrypoint.sh`'s supervision actually works: `docker exec <container> pkill -f
      "reflex run"` and confirm the **whole container exits** shortly after (check `docker ps`), not
      that Caddy silently keeps serving static files with a dead backend behind it.

### C — housekeeping

- [ ] `docs/Deployment.md` reconciled (Step 3).
- [ ] This handoff records, for Cycle 3.2's benefit: the exact export output path used, any unixODBC
      surprises, and whether `entrypoint.sh`'s minimal supervision held up under the port-isolation and
      backend-crash checks above.
- [ ] The roadmap's "Open decisions to resolve" table gets a row for the baked-absolute-URL question
      (rebuild-per-environment vs. same-origin relative URLs) — see the section above — so Cycle 3.2
      starts with a decision already made, not rediscovers this.

**Done when:** all of A and B pass. Gate 3 (temp public URL via Container Apps, ingress websocket
survival, scale-to-zero) is Cycle 3.2 — do not attempt it here.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  Dockerfile                  ← new, Step 2
  .dockerignore                ← new, Step 1
  Caddyfile                    ← new, Step 2 (reverse proxy + static file serving, port 8080)
  entrypoint.sh                 ← new, Step 2 (starts + minimally supervises Reflex backend + Caddy)
  .env.docker                   ← new, gitignored, NOT committed (Validation B — holds real secrets)
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
