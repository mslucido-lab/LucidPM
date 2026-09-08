# LucidoPM — ChatGPT Handoff 58
*Env-driven SQL connection + SQL-auth branch (Azure Migration Stage 0.3)*
*Prepared: 2026-09-06 · revised 2026-09-06 (toggle stays in cloud) · revised 2026-09-07 (reconciled with the PM cloud-migration knowledge share: contained-user note, LUCIDPM_ENV marker, cold-resume gate, .dockerignore forward-ref)*

---

## What This Is

Make LucidPM's database connection **configurable from environment variables**,
and add a **SQL-authentication** path alongside the current Windows-integrated
auth. Today `LucidPM/state.py` hardcodes `localhost\SQLEXPRESS` and
`Trusted_Connection=yes`. Azure SQL Database supports neither a local instance
name nor Windows auth, so nothing can point the app at the cloud database until
this is done. This is the blocker in front of **Azure Migration Cycle 2.2**
(local app running against the Azure `TenantCRM` / `TenantCRM_Test` that were
loaded in Cycle 2.1).

With **no environment variables set, local behaviour is byte-for-byte identical
to today** — same server, same Windows auth, same Test/Prod toggle. When the
new variables are set, the connection string changes and the app can run
against Azure SQL with the **Test/Prod toggle still working** (the app opens a
fresh connection per query with the database name in the string — it never does
cross-database queries, so the Azure `USE` / 3-part-name limits don't apply).

**Credential note (reconciled with the Portfolio Manager cloud-migration
knowledge share, `Undelivered Handoffs/lucidpm-cloud-migration-knowledge-share.md`).**
For **Cycle 2.2 only** — a local dev app pointed at Azure SQL for the Gate 2
smoke test — using the `lucidadmin` server login is acceptable and expedient
(it reaches both `TenantCRM` and `TenantCRM_Test`, so the toggle just works).
The PM migration established that the **cloud deployment must not use an admin
account**: Stage 3+ switches to a dedicated **contained SQL user** with only the
roles LucidPM needs. Contained users are per-database, so keeping the Test/Prod
toggle in a cloud build then means provisioning the **same contained
username + password in both `TenantCRM` and `TenantCRM_Test`**. This handoff
changes no code for that (user/password are already env-driven) — it is a
provisioning + `.env` step for the later cycle, flagged here so the "toggle
stays in cloud" decision carries its real cost.

**Files that change:**

| File | Change |
|---|---|
| `LucidPM/state.py` | Read connection config from `os.getenv` with today's values as defaults; add a SQL-auth branch in `get_conn`; add a tiny optional `.env` loader; add an *optional* single-DB lock. |
| `LucidPM/components/sidebar.py` | Hide the "Switch" DB button only when the optional single-DB lock is set. |
| `.env.example` | Document the new variables. |

**`LucidPM/LucidPM.py` is not touched.** Its `?db=` PDF endpoints keep working:
in normal (multi-DB) mode they connect to whatever `LUCIDPM_TEST_DB` /
`LUCIDPM_PROD_DB` resolve to; if the single-DB lock is ever set, `get_conn`
redirects them to the locked database.

### Scope constraint

This handoff is **connection plumbing only**. It does **not**:

- Move the Fernet key out of `AppSettings` — that is **Cycle 0.4**, a separate
  handoff. `get_fernet` / `encrypt_value` / `decrypt_value` are untouched here.
- Move the lease-document storage root out of SQL — **Cycle 5.1**.
- Add connection retry-on-resume logic for Azure serverless auto-pause. Only a
  `LUCIDPM_SQL_LOGIN_TIMEOUT` knob is included here (default 30 s; the Azure
  example sets 60 s). The PM knowledge share treats *"graceful behavior when a
  dependent Azure SQL database is paused"* as a **required** validation gate
  from lived experience, so a retry-on-resume wrapper is **the expected next
  cycle after 2.2**, not a maybe — Cycle 2.2 must capture the cold-resume
  measurement (see the Validation Checklist) as its input.
- Add `requirements.txt` / `pyproject.toml` — **Cycle 0.1**. This handoff adds
  **no new package dependency** (the `.env` loader is hand-rolled, ~12 lines).
- Change any SQL, any query, any schema, or any page's behaviour.

---

## The Current State

### `LucidPM/state.py`

**Imports (lines 1–9)** — no `import os`, no `pathlib`:

```python
import reflex as rx
import pyodbc
import datetime
from cryptography.fernet import Fernet
```

**Connection constants (lines 11–13):**

```python
SQL_SERVER = "localhost\\SQLEXPRESS"
PROD_DB_NAME = "TenantCRM"
TEST_DB_NAME = "TenantCRM_Test"
```

**`get_conn` (lines 26–35):**

```python
def get_conn(db: str) -> pyodbc.Connection:
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={db};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)
```

`run_query` (lines 38–43) and `run_exec` (lines 46–50) are the only callers;
both take a `db: str` parameter that defaults to `TEST_DB_NAME`. Dozens of call
sites across `pages/*.py` and `LucidPM.py` pass `db=self.db` or
`db=TEST_DB_NAME` (and one endpoint in `LucidPM.py` ~line 892 tries
`[TEST_DB_NAME, "TenantCRM"]` in turn). **None of those call sites change.**

**`AppState` (lines 372–419):**

```python
class AppState(rx.State):
    """Global state shared across all pages."""
    use_test_db: bool = True
    # Increments each time the DB is toggled — child states watch this to reload
    db_version: int = 0

    @rx.var
    def db(self) -> str:
        return TEST_DB_NAME if self.use_test_db else PROD_DB_NAME

    @rx.var
    def db_label(self) -> str:
        return "TEST" if self.use_test_db else "PRODUCTION"

    @rx.var
    def db_toggle_label(self) -> str:
        return "Switch to Production" if self.use_test_db else "Switch to Test"

    def toggle_db(self):
        self.use_test_db = not self.use_test_db
        self.db_version += 1
        # Yield reload events for all page states that need refreshing
        from LucidPM.pages.dashboard import DashboardState
        ...
        yield WaitingListState.reload_on_db_change
```

### `LucidPM/components/sidebar.py`

Imports (line 6): `from LucidPM.state import AppState, BRAND_PRIMARY, BRAND_DARK`.

The DB status pill (lines ~300–336) — status dot, `AppState.db_label`, and the
**Switch** button:

```python
                    rx.spacer(),
                    rx.button(
                        "Switch",
                        on_click=AppState.toggle_db,
                        size="1",
                        variant="ghost",
                        class_name="sidebar-label",
                        style={"color": "rgba(255,255,255,0.70)", "font_size": "11px"},
                    ),
                    align="center",
                    width="100%",
                ),
```

### `.env.example`

Currently a placeholder that states LucidPM reads no env vars.

---

## The Fix

### Step 1 — `state.py`: imports + `.env` loader + config constants

**Current** (lines 1–13):

```python
"""
Shared DB helpers, constants, and base state.
Import this from any page or component.
"""

import reflex as rx
import pyodbc
import datetime
from cryptography.fernet import Fernet

SQL_SERVER = "localhost\\SQLEXPRESS"
PROD_DB_NAME = "TenantCRM"
TEST_DB_NAME = "TenantCRM_Test"
```

**Replace with:**

```python
"""
Shared DB helpers, constants, and base state.
Import this from any page or component.
"""

import os
import datetime
from pathlib import Path

import reflex as rx
import pyodbc
from cryptography.fernet import Fernet


def _load_local_env() -> None:
    """Best-effort loader for a `.env` file at the repo root (dev convenience).

    Lets the Azure-SQL connection settings live in an untracked `.env` file
    instead of shell exports when running the app locally against a remote DB.
    Never overrides a variable already set in the real environment, so a
    container/host that injects real env vars is unaffected (and ships no
    `.env`, making this a no-op there). Deliberately dependency-free — do not
    swap in python-dotenv here.
    """
    try:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_local_env()

# --- Connection config: env-driven, with today's local values as defaults -----
SQL_SERVER = os.getenv("LUCIDPM_SQL_SERVER", "localhost\\SQLEXPRESS")
PROD_DB_NAME = os.getenv("LUCIDPM_PROD_DB", "TenantCRM")
TEST_DB_NAME = os.getenv("LUCIDPM_TEST_DB", "TenantCRM_Test")

# Optional single-database lock. When set to a database name, EVERY connection
# goes to it (ignoring the db= argument) and the Test/Prod toggle is hidden.
# Leave unset for local dev and for cloud dev where you still want the toggle
# (both Azure DBs are reachable). Set it only for a locked-down deployment.
SINGLE_DB_NAME = os.getenv("LUCIDPM_SINGLE_DB") or None

# Deployment environment marker. Unset (or "local") for local dev; "cloud" when
# running inside Azure Container Apps. Nothing branches on this yet — it is the
# single source of truth that Stage 5.3 (Entra ID auth) will gate the
# X-MS-CLIENT-PRINCIPAL-NAME header-trust on. Kept separate from
# LUCIDPM_SINGLE_DB deliberately: "which database(s)" and "am I in the cloud"
# are orthogonal (per the PM cloud-migration knowledge share).
LUCIDPM_ENV = (os.getenv("LUCIDPM_ENV", "local").strip().lower() or "local")

_SQL_AUTH = os.getenv("LUCIDPM_SQL_AUTH", "windows").strip().lower()   # "windows" | "sql"
_SQL_USER = os.getenv("LUCIDPM_SQL_USER", "")
_SQL_PASSWORD = os.getenv("LUCIDPM_SQL_PASSWORD", "")
_SQL_ENCRYPT = os.getenv("LUCIDPM_SQL_ENCRYPT", "yes").strip().lower()
_SQL_TRUST_CERT = os.getenv("LUCIDPM_SQL_TRUST_CERT", "yes").strip().lower()
try:
    _SQL_LOGIN_TIMEOUT = int(os.getenv("LUCIDPM_SQL_LOGIN_TIMEOUT", "30"))
except ValueError:
    _SQL_LOGIN_TIMEOUT = 30
```

Notes:
- `import os` / `import datetime` / `from pathlib import Path` move to the top;
  `send_email` already does a local `import os` — that shadowing stays harmless,
  leave it.
- Defaults reproduce the current hardcoded values exactly, so a plain
  `reflex run` with no `.env` and no exported vars behaves identically.

### Step 2 — `state.py`: `get_conn` with a SQL-auth branch

**Current** (lines 26–35):

```python
def get_conn(db: str) -> pyodbc.Connection:
    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={db};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)
```

**Replace with:**

```python
def _odbc_brace(value: str) -> str:
    """Wrap an ODBC connection-string value in braces, escaping any '}'.

    SQL passwords routinely contain ';' '=' '{' '}' — all of which break a bare
    key=value ODBC segment. Braces are the ODBC-defined escape for this.
    """
    return "{" + value.replace("}", "}}") + "}"


def get_conn(db: str) -> pyodbc.Connection:
    # Single-DB lock (if set) overrides the requested name; otherwise the app
    # connects to exactly the database it asked for (local Test/Prod, or the
    # matching Azure DB — all reachable by the configured login).
    target_db = SINGLE_DB_NAME or db

    parts = [
        "DRIVER={ODBC Driver 18 for SQL Server}",
        f"SERVER={SQL_SERVER}",
        f"DATABASE={target_db}",
        f"Encrypt={_SQL_ENCRYPT}",
        f"TrustServerCertificate={_SQL_TRUST_CERT}",
    ]
    if _SQL_AUTH == "sql":
        parts.append(f"UID={_odbc_brace(_SQL_USER)}")
        parts.append(f"PWD={_odbc_brace(_SQL_PASSWORD)}")
    else:
        parts.append("Trusted_Connection=yes")

    conn_str = ";".join(parts) + ";"
    return pyodbc.connect(conn_str, timeout=_SQL_LOGIN_TIMEOUT)
```

For the default local case this produces the same driver, server, database,
`Encrypt=yes`, `TrustServerCertificate=yes`, and `Trusted_Connection=yes`
(segment order is irrelevant to ODBC). `timeout=` is the **login** timeout;
`pyodbc`'s default is 0/none, so adding 30 s only changes behaviour when the
server is unreachable — harmless locally, useful against a paused Azure DB.

### Step 3 — `state.py`: `AppState` (toggle stays; single-DB lock hides it)

**Current** (lines 374–392, through the top of `toggle_db`):

```python
    use_test_db: bool = True
    # Increments each time the DB is toggled — child states watch this to reload
    db_version: int = 0

    @rx.var
    def db(self) -> str:
        return TEST_DB_NAME if self.use_test_db else PROD_DB_NAME

    @rx.var
    def db_label(self) -> str:
        return "TEST" if self.use_test_db else "PRODUCTION"

    @rx.var
    def db_toggle_label(self) -> str:
        return "Switch to Production" if self.use_test_db else "Switch to Test"

    def toggle_db(self):
        self.use_test_db = not self.use_test_db
        self.db_version += 1
```

**Replace with:**

```python
    use_test_db: bool = True
    # Increments each time the DB is toggled — child states watch this to reload
    db_version: int = 0

    @rx.var
    def is_single_db(self) -> bool:
        return SINGLE_DB_NAME is not None

    @rx.var
    def db(self) -> str:
        if SINGLE_DB_NAME is not None:
            return SINGLE_DB_NAME
        return TEST_DB_NAME if self.use_test_db else PROD_DB_NAME

    @rx.var
    def db_label(self) -> str:
        if SINGLE_DB_NAME is not None:
            return "PRODUCTION"
        return "TEST" if self.use_test_db else "PRODUCTION"

    @rx.var
    def db_toggle_label(self) -> str:
        return "Switch to Production" if self.use_test_db else "Switch to Test"

    def toggle_db(self):
        if SINGLE_DB_NAME is not None:
            return   # locked to one database — nothing to toggle
        self.use_test_db = not self.use_test_db
        self.db_version += 1
```

Leave the rest of `toggle_db` (the `from ... import` block and every
`yield ....reload_on_db_change`) exactly as is.

**In normal cloud dev (no `LUCIDPM_SINGLE_DB`), the toggle behaves exactly as
it does locally** — `use_test_db` flips, `db` returns the Test or Prod name,
`get_conn` connects to that Azure database, the reload cascade fires.

### Step 4 — `sidebar.py`: hide the Switch button only when locked

**Current** (lines ~318–329):

```python
                    rx.spacer(),
                    rx.button(
                        "Switch",
                        on_click=AppState.toggle_db,
                        size="1",
                        variant="ghost",
                        class_name="sidebar-label",
                        style={"color": "rgba(255,255,255,0.70)", "font_size": "11px"},
                    ),
                    align="center",
                    width="100%",
                ),
```

**Replace the `rx.button(...)` with a guarded version:**

```python
                    rx.spacer(),
                    rx.cond(
                        ~AppState.is_single_db,
                        rx.button(
                            "Switch",
                            on_click=AppState.toggle_db,
                            size="1",
                            variant="ghost",
                            class_name="sidebar-label",
                            style={"color": "rgba(255,255,255,0.70)", "font_size": "11px"},
                        ),
                    ),
                    align="center",
                    width="100%",
                ),
```

The status dot and `AppState.db_label` above it already render from Vars and
need no change. Do not add a new banner.

**Known cosmetic nit, deliberately left:** the status dot at `sidebar.py:307`
binds to `AppState.use_test_db` directly, which defaults `True`, so in
single-DB-lock mode the pill shows a **green dot next to "PRODUCTION"**. This is
harmless — single-DB lock is an optional, not-yet-used deployment mode and is
not exercised in Cycle 2.2. **Do not "fix" it** by rewiring the dot or adding a
Var; if it ever matters it is a one-line `rx.cond` in a later touch.

### Step 5 — `.env.example`

**Replace the entire file contents with:**

```
# LucidPM reads these at startup (LucidPM/state.py). Copy to `.env` and edit for
# local development; leave `.env` absent to use the built-in local defaults
# shown below. `.env` is gitignored. A host that injects real environment
# variables (e.g. a container) overrides anything here.

# --- Database connection ----------------------------------------------------
# SQL Server instance / host. Local default:
#LUCIDPM_SQL_SERVER=localhost\SQLEXPRESS
# Azure example:
#LUCIDPM_SQL_SERVER=lucidpm-sql-24899.database.windows.net

# Auth mode: "windows" (integrated, local only) or "sql" (username/password).
# For "sql": Cycle 2.2 smoke test may use the lucidadmin server login. The
# cloud build (Stage 3+) MUST use a dedicated contained, non-admin user
# (provisioned in BOTH databases if the Test/Prod toggle is kept) — see the
# PM cloud-migration knowledge share.
#LUCIDPM_SQL_AUTH=windows
#LUCIDPM_SQL_USER=lucidadmin
#LUCIDPM_SQL_PASSWORD=

# Deployment marker: unset / "local" for local dev, "cloud" inside Azure
# Container Apps. Not read by anything yet — reserved for Stage 5.3 Entra auth.
#LUCIDPM_ENV=local

# ODBC encryption. Local default yes/yes works for SQL Express with a self-
# signed cert. For Azure use yes / no (real managed certificate).
#LUCIDPM_SQL_ENCRYPT=yes
#LUCIDPM_SQL_TRUST_CERT=yes

# Login timeout in seconds (raise for a serverless Azure DB resuming from pause)
#LUCIDPM_SQL_LOGIN_TIMEOUT=30

# --- Database selection ----------------------------------------------------
# The two databases the Test/Prod toggle switches between.
#LUCIDPM_PROD_DB=TenantCRM
#LUCIDPM_TEST_DB=TenantCRM_Test

# Optional: lock the app to ONE database and hide the Test/Prod toggle. Leave
# unset for local and for cloud dev (you still want the toggle). Set it only
# for a locked-down deployment.
#LUCIDPM_SINGLE_DB=TenantCRM

# --- Example: local app against the Azure SQL databases (Cycle 2.2) -------
# Keeps the Test/Prod toggle; both Azure DBs are reachable by lucidadmin.
#LUCIDPM_SQL_SERVER=lucidpm-sql-24899.database.windows.net
#LUCIDPM_SQL_AUTH=sql
#LUCIDPM_SQL_USER=lucidadmin
#LUCIDPM_SQL_PASSWORD=<the SQL admin password>
#LUCIDPM_SQL_TRUST_CERT=no
#LUCIDPM_SQL_LOGIN_TIMEOUT=60
#LUCIDPM_PROD_DB=TenantCRM
#LUCIDPM_TEST_DB=TenantCRM_Test
```

---

## Do Not Touch

| What | Why |
|---|---|
| `run_query`, `run_exec` and their `db=` defaults | The `db` value still flows through; `get_conn` decides what it means |
| Any `pages/*.py` or `LucidPM.py` call site passing `db=...` | Works unchanged in multi-DB mode; the single-DB lock (if ever set) is handled centrally in `get_conn` |
| `get_fernet`, `encrypt_value`, `decrypt_value` | Fernet-key relocation is Cycle 0.4, a separate handoff |
| `send_email` and its local `import os` | Unrelated; the shadow is harmless |
| `toggle_db`'s state-import block and every `yield ...reload_on_db_change` | Only the two-line lock guard is added at the top |
| The status dot / `db_label` text in the sidebar | `db_label` already updates via the Step 3 Var change; the dot color binding stays as-is (green-in-single-DB-mode is an accepted cosmetic nit, see Step 4) — no new Var, no `rx.cond` on the dot |
| `rxconfig.py` | No `env_file` wiring needed — `state.py` loads `.env` itself |
| `LUCIDPM_ENV` — read it, branch on it, or wire it to anything | It is defined as an inert marker for **Stage 5.3** (Entra header-trust). This handoff only *declares* it in the config block + `.env.example`. Nothing reads it yet — leave it that way |
| Any SQL, schema, or DB object | Connection-string change only |

---

## Validation Checklist

**Local, no `.env`, nothing exported (must be identical to today):**

- [ ] `reflex run` starts; Dashboard, Rent Roll, Tenants, Lease Documents all
      load data.
- [ ] Sidebar shows the DB pill with a green dot + `TEST` and the **Switch**
      button.
- [ ] Click **Switch** → pill goes red / `PRODUCTION`, pages reload with prod
      data (the `db_version` reload path still fires). Switch back works.
- [ ] Generate a lease PDF (exercises the `?db=` standalone endpoint in
      `LucidPM.py`) — still works.

**Local with a `.env` pointing at Azure SQL (Cycle 2.2 dry run — toggle kept):**

- [ ] Create `.env` from the "local app against Azure" example block, real
      password. `git status` shows `.env` as **untracked/ignored**, not staged.
- [ ] `reflex run` connects (first query may take up to ~60 s if the Azure DB
      was auto-paused; subsequent ones are fast).
- [ ] **Cold-resume measurement (Gate 2 / next-cycle input).** With the Azure
      DB confirmed auto-paused (idle > 60 min, or check the portal), start the
      app and time the first data-bearing page to usable. Record the number and
      whether a wrong/timeout error was shown mid-wait. This is the evidence for
      whether the retry-on-resume wrapper is needed immediately.
- [ ] Sidebar still shows `TEST` + the **Switch** button.
- [ ] Tenant list, lease list, rent roll, property financials, analytics all
      render the Azure **Test** data (row counts match Cycle 2.1's verify:
      Tenants 62, Leases 75, LeasePackageSections 1545, …).
- [ ] Click **Switch** → pill goes `PRODUCTION`, pages reload against Azure
      `TenantCRM` (Tenants 46, Leases 93, LeaseGeneratedDocuments 144, …).
      Switch back to Test works.
- [ ] A write works end-to-end against Azure — e.g. add a Communication or edit
      a Work Item on the Test DB, reload, confirm it persisted (then undo).
- [ ] Wrong password → a clear connection error at startup, not a silent hang
      (login timeout caps it).

**Optional single-DB lock:**

- [ ] Add `LUCIDPM_SINGLE_DB=TenantCRM` to `.env`, restart → **Switch button is
      gone**, pill reads `PRODUCTION`, every page hits `TenantCRM` regardless of
      the `?db=` param on the PDF endpoints.

**Regression:**

- [ ] `grep -rn "Trusted_Connection" LucidPM/` shows it only in `state.py`
      `get_conn` (the `windows` branch).
- [ ] No new entry in `requirements`/imports for `dotenv`.

---

## How to Deliver This

Per `CLAUDE.md`: edit the live files in place, no `_vN` copies.

1. Apply Steps 1–5.
2. Verify the **local, no-`.env`** checklist first (the "did we break the
   working app" gate).
3. Then the Azure `.env` checklist — this is effectively Cycle 2.2's smoke test;
   capture any pyodbc/Azure incompatibility or latency surprise for the Gate 2
   write-up.
4. Commit (e.g. `Env-driven SQL connection + SQL-auth branch (Azure Stage 0.3)`).
5. Move this doc to `Completed Handoffs/`.
6. `state.py` has `_vN` siblings (`state_1.py` … `state_v9.py`) still in
   `LucidPM/`. Per the incremental-cleanup rule, once this change is verified,
   move `LucidPM/state_*.py` into `Archived Versions/` and commit that
   separately.

### Also (housekeeping, not blocking)

- **`.gitignore` — already done** (commit `1de81d2`): `/db/TenantCRM*.sql`
  covers the Cycle 2.1 PII dumps (`TenantCRM_full.sql`, `TenantCRM_Test_*.sql`,
  `*_verify.sql`, the future `TenantCRM_azure.sql`). `db/history/*.sql` stays
  tracked. No further `.gitignore` change needed here.
- **`.dockerignore` — forward reference, Cycle 3.1.** The repo has no
  `.dockerignore` yet. When one is added for the container build it must exclude
  the same things this handoff keeps out of git — `.env` / `.env.*`, `*.key` /
  `*.pem` / `*.pfx`, `/db/TenantCRM*.sql`, `.web/`, `.venv/`, tests, and
  `Undelivered Handoffs/` / `Completed Handoffs/` — so tenant PII and secrets
  never land in an image layer (per the PM cloud-migration knowledge share's
  build-artifact exclusion list).

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\state.py                    ← Steps 1–3 (primary)
  LucidPM\components\sidebar.py       ← Step 4
  .env.example                        ← Step 5
  .env                                ← operator-created, gitignored, never committed

Dev app (this handoff): http://localhost:3002   (backend :8002)
Live app:               http://localhost:3000   (backend :8000)
Test DB: green banner | Prod DB: red banner | single-DB lock: "PRODUCTION", no Switch button

Azure SQL (Cycle 2.1, both DBs already loaded + verified):
  server    lucidpm-sql-24899.database.windows.net
  databases TenantCRM, TenantCRM_Test  (serverless, free-limit, auto-pause)
  admin     lucidadmin  (password in Mark's password manager)
  firewall  Mark's client IP must be present (added during Cycle 2.1)
```

---

*One env loader, one config block, one `get_conn` rewrite (same output when
unconfigured), one optional single-DB lock, one `rx.cond` in the sidebar, one
doc file. No new dependency. The Test/Prod toggle works locally and against
Azure. No call site outside `state.py` changes.*
