# LucidoPM — ChatGPT Handoff 60
*Connection retry-on-resume for Azure SQL serverless auto-pause*
*Prepared: 2026-09-08 · Azure Migration — the expected follow-up after Handoff 58 / Cycle 2.2*

---

## What This Is

Azure SQL serverless with `AutoPause` (both `TenantCRM` and `TenantCRM_Test`
are configured this way, 60-minute idle) **pauses the database when idle**. The
first connection after a pause fails while the database spins back up — roughly
20–60 seconds — with a login-timeout or "database is not currently available"
error. Today that surfaces to the user as a broken page; they have to notice and
refresh.

This handoff adds a **bounded, transient-only retry loop around
`pyodbc.connect`** inside `state.get_conn()`. When a connection attempt fails
with a resume-shaped error, it waits briefly and retries; after N attempts it
re-raises the original error unchanged. Auth failures, "database does not exist",
and every other non-transient error still fail **immediately** — the loop never
masks a real problem.

**With a local SQL Express instance the first attempt always succeeds, so the
retry path is never entered and behaviour is byte-for-byte identical to today
(no added latency, no new log lines).** The retry only engages on an actual
connection exception.

This is the follow-up flagged in Handoff 58's scope constraint ("a
retry-on-resume wrapper is the expected next cycle") and the roadmap. Handoff 58
shipped only a longer `LUCIDPM_SQL_LOGIN_TIMEOUT` as an interim mitigation.

**Files that change:** `LucidPM/state.py` (retry loop + 2 config vars + validation)
and `.env.example` (document the 2 vars). No page, no call site, no SQL.

### Scope constraint

**Connection-level retry only.** This handoff does **not**:

- Retry at the `cursor.execute` level. A transient error *during* a query would
  mean re-running it — unsafe for `run_exec` writes without idempotency
  analysis. Out of scope; `run_query` / `run_exec` bodies are untouched.
- Add a circuit breaker, connection pool, health-check endpoint, or async
  variant.
- Change `get_conn`'s signature, the connection string, auth handling, or
  anything Handoff 58 / 59 added (`_odbc_brace`, `api_base_url`, `ConfigError`,
  the `.env` loader, `_validate_sql_config`'s existing checks).
- Add a package dependency. `time` and `sys` are stdlib.
- Change behaviour when the database is reachable on the first try.

---

## The Current State

### `LucidPM/state.py`

**Config validation (lines 78–114)** — `_validate_sql_config()` parses and
range-checks the SQL env vars, returning the login timeout; the module binds it
with:

```python
_SQL_LOGIN_TIMEOUT = _validate_sql_config()
```

**`get_conn` (lines 136–156)** — builds the connection string and connects once:

```python
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

`run_query` (line 171) and `run_exec` (line 179) are the only callers, both via
`with get_conn(db) as conn:`. Dozens of `pages/*.py` and `LucidPM.py` call
sites reach them indirectly. **None change.**

### Verified facts (checked 2026-09-08, `pyodbc 5.3.0`)

- `pyodbc.OperationalError` ⊂ `pyodbc.DatabaseError` ⊂ `pyodbc.Error` ⊂ `Exception`.
- A failed `pyodbc.connect` raises `pyodbc.Error` (usually `OperationalError`)
  with `exc.args[0]` = the SQLSTATE string, e.g. `'08001'` / `'HYT00'`.
- The native error number appears in `str(exc)`, e.g. `... (40613) ...`.
- `timeout=N` on `connect` is honoured as the login timeout (a bad host with
  `timeout=3` returns in ~3 s).

Resume-from-pause presents as SQLSTATE `HYT00` (login timeout while the gateway
holds the connection) or `08001` / `08S01` (TCP-level timeout), and if the
resume is slow, native `40613` ("Database '…' … is not currently available").
An auth failure is SQLSTATE `28000` (native `18456`); a missing/ungranted
database is `42000` (native `4060`) — **neither is retried.**

---

## The Fix

### Step 1 — `state.py`: imports

**Current** (lines 6–12):

```python
import os
import datetime
from pathlib import Path

import reflex as rx
import pyodbc
from cryptography.fernet import Fernet
```

**Replace with:**

```python
import os
import sys
import time
import datetime
from pathlib import Path

import reflex as rx
import pyodbc
from cryptography.fernet import Fernet
```

### Step 2 — `state.py`: two new config vars, validated in `_validate_sql_config`

**Current** — the end of `_validate_sql_config` and its bind (lines 102–114):

```python
    raw_timeout = os.getenv("LUCIDPM_SQL_LOGIN_TIMEOUT", "30").strip()
    try:
        timeout = int(raw_timeout)
    except ValueError:
        raise ConfigError(
            f"LUCIDPM_SQL_LOGIN_TIMEOUT={raw_timeout!r} is not an integer."
        ) from None
    if timeout < 0:
        raise ConfigError("LUCIDPM_SQL_LOGIN_TIMEOUT must not be negative.")
    return timeout


_SQL_LOGIN_TIMEOUT = _validate_sql_config()
```

**Replace with:**

```python
    raw_timeout = os.getenv("LUCIDPM_SQL_LOGIN_TIMEOUT", "30").strip()
    try:
        timeout = int(raw_timeout)
    except ValueError:
        raise ConfigError(
            f"LUCIDPM_SQL_LOGIN_TIMEOUT={raw_timeout!r} is not an integer."
        ) from None
    if timeout < 0:
        raise ConfigError("LUCIDPM_SQL_LOGIN_TIMEOUT must not be negative.")

    retries = _non_negative_int_env("LUCIDPM_SQL_CONNECT_RETRIES", "2")
    backoff = _non_negative_int_env("LUCIDPM_SQL_RETRY_BACKOFF", "3")
    return timeout, retries, backoff


def _non_negative_int_env(name: str, default: str) -> int:
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not an integer.") from None
    if value < 0:
        raise ConfigError(f"{name} must not be negative.")
    return value


# LUCIDPM_SQL_CONNECT_RETRIES  — extra connect attempts after the first when the
#   failure looks like an Azure serverless resume (default 2 -> 3 total; 0
#   disables retry entirely and restores the pre-H60 single-attempt behaviour).
# LUCIDPM_SQL_RETRY_BACKOFF     — base seconds between attempts; attempt k waits
#   backoff * k (default 3 -> 3 s, then 6 s). The login timeout already provides
#   the long blocking wait, so this only needs to be short.
_SQL_LOGIN_TIMEOUT, _SQL_CONNECT_RETRIES, _SQL_RETRY_BACKOFF = _validate_sql_config()
```

Notes:
- `_validate_sql_config` now returns a 3-tuple. Its existing four checks are
  unchanged; only the two lines before `return` and the return value are new.
- `_non_negative_int_env` mirrors the existing timeout check exactly (same
  `ConfigError`, same `from None`), so a bad value still stops startup with a
  named error — no silent default.
- Defaults (`retries=2`, `backoff=3`) are inert locally: SQL Express connects
  first try, so the loop exits before any retry.

### Step 3 — `state.py`: the transient-error predicate + retry loop

**Current** `get_conn` (lines 136–156) ends with:

```python
    conn_str = ";".join(parts) + ";"
    return pyodbc.connect(conn_str, timeout=_SQL_LOGIN_TIMEOUT)
```

**Replace that final line with:**

```python
    conn_str = ";".join(parts) + ";"
    return _connect_with_resume_retry(conn_str, target_db)
```

**And add these two module-level helpers immediately above `get_conn`** (after
`_odbc_brace`):

```python
# SQLSTATE classes and native error numbers that indicate a transient /
# resume-in-progress condition worth retrying. Deliberately excludes 28000
# (auth failure / 18456) and 42000 (4060, database not grantable).
_TRANSIENT_SQLSTATE_PREFIXES = ("08", "HYT")
_TRANSIENT_NATIVE_CODES = (
    "40613",  # database is not currently available (still resuming)
    "40197", "40501", "49918", "49919", "49920",  # service busy / throttling
    "10928", "10929", "10053", "10054", "10060", "4221",
)


def _is_transient_connect_error(exc: pyodbc.Error) -> bool:
    sqlstate = (exc.args[0] if exc.args else "") or ""
    if sqlstate.startswith(_TRANSIENT_SQLSTATE_PREFIXES):
        return True
    text = str(exc)
    return any(f"({code})" in text for code in _TRANSIENT_NATIVE_CODES)


def _connect_with_resume_retry(conn_str: str, target_db: str) -> pyodbc.Connection:
    """pyodbc.connect, retrying only transient/resume-shaped failures.

    An Azure serverless database that has auto-paused takes ~20-60 s to resume;
    the first connect fails with a login timeout or 'not currently available'.
    Non-transient errors (bad password, missing database, …) are re-raised on
    the first attempt. With LUCIDPM_SQL_CONNECT_RETRIES=0 this is a plain
    single-attempt connect.
    """
    attempts = _SQL_CONNECT_RETRIES + 1
    for attempt in range(1, attempts + 1):
        try:
            return pyodbc.connect(conn_str, timeout=_SQL_LOGIN_TIMEOUT)
        except pyodbc.Error as exc:
            if attempt >= attempts or not _is_transient_connect_error(exc):
                raise
            wait = _SQL_RETRY_BACKOFF * attempt
            print(
                f"[state.get_conn] transient DB connect error for {target_db!r} "
                f"({(exc.args[0] if exc.args else '?')}); attempt {attempt}/{attempts}, "
                f"retrying in {wait}s — Azure serverless DB is probably resuming.",
                file=sys.stderr,
            )
            time.sleep(wait)
    # unreachable — the loop either returns or raises
    raise RuntimeError("unreachable")
```

Notes:
- The `print(..., file=sys.stderr)` line is intentional: Cycle 2.2 needs to
  *see* the resume happening to record its duration. Dependency-free.
- `target_db` is passed in only for that log line.
- Worst case with defaults + `LUCIDPM_SQL_LOGIN_TIMEOUT=60`:
  3 attempts × ~60 s + (3 s + 6 s) ≈ 189 s. That is a once-per-idle-period
  cost and still far better than a hard failure. Mark can lower
  `LUCIDPM_SQL_CONNECT_RETRIES` or the timeout if it feels long in practice —
  Cycle 2.2's measurement is what tunes these.

### Step 4 — `.env.example`

**4a** — after the two `LUCIDPM_SQL_LOGIN_TIMEOUT` lines:

```
# Login timeout in seconds (raise for a serverless Azure DB resuming from pause)
#LUCIDPM_SQL_LOGIN_TIMEOUT=30
```

→ append:

```
# Login timeout in seconds (raise for a serverless Azure DB resuming from pause)
#LUCIDPM_SQL_LOGIN_TIMEOUT=30

# Connect-retry for Azure serverless auto-pause (a paused DB takes ~20-60s to
# resume; the first connect fails with a timeout / "not available"). Extra
# attempts after the first; 0 restores single-attempt behaviour.
#LUCIDPM_SQL_CONNECT_RETRIES=2
# Base seconds between attempts (attempt k waits backoff * k).
#LUCIDPM_SQL_RETRY_BACKOFF=3
```

**4b** — in the PowerShell process-env recipe, after the
`$env:LUCIDPM_SQL_TRUST_CERT = 'no'; $env:LUCIDPM_SQL_LOGIN_TIMEOUT = '60'`
line, add:

```
#   $env:LUCIDPM_SQL_CONNECT_RETRIES = '3'
```

**4c** — in the trailing commented `#LUCIDPM_SQL_*` block of that same example,
after `#LUCIDPM_SQL_LOGIN_TIMEOUT=60`, add:

```
#LUCIDPM_SQL_CONNECT_RETRIES=3
```

---

## Do Not Touch

| What | Why |
|---|---|
| `run_query`, `run_exec` bodies | Retry is connect-only; execute-level retry would re-run writes |
| Any `pages/*.py` / `LucidPM.py` call site | They call `run_query`/`run_exec` → `get_conn`; nothing changes for them |
| The connection-string build, `_odbc_brace`, `_SQL_AUTH` handling | Handoff 58; untouched |
| `api_base_url` | Handoff 59; untouched |
| `_validate_sql_config`'s four existing checks | Only the return value + two new lines are added |
| `ConfigError` | Reused as-is for the two new vars |
| `LUCIDPM_SQL_LOGIN_TIMEOUT` semantics | Unchanged — the retry loop wraps it, doesn't replace it |
| `rxconfig.py`, schema, any SQL | Out of scope |

---

## Validation Checklist

### A — local, no config (must be identical to today)

- [ ] `reflex run` starts; Dashboard / Rent Roll / Tenants / Lease Documents
      load. No `[state.get_conn]` line ever printed (first attempt succeeds).
- [ ] Time a page load — no measurable change vs. before (the loop body runs
      once, no `sleep`).
- [ ] `LUCIDPM_SQL_CONNECT_RETRIES=abc` → startup stops with a named
      `ConfigError`. `=-1` → same. Then unset.

### B — transient path, simulated (no Azure needed)

- [ ] Point at an unroutable host to force a fast timeout, e.g.
      `LUCIDPM_SQL_SERVER=10.255.255.1,14330`, `LUCIDPM_SQL_AUTH=sql`,
      `LUCIDPM_SQL_USER=x`, `LUCIDPM_SQL_PASSWORD=y`,
      `LUCIDPM_SQL_LOGIN_TIMEOUT=3`, `LUCIDPM_SQL_CONNECT_RETRIES=2`,
      `LUCIDPM_SQL_RETRY_BACKOFF=1`.
      → three `[state.get_conn] transient DB connect error …` lines (attempts
      1/3, 2/3), ~1 s then ~2 s apart, then the **original** `pyodbc` error is
      raised (not swallowed, not wrapped).
- [ ] Same but `LUCIDPM_SQL_CONNECT_RETRIES=0` → one attempt, immediate raise,
      no retry line (pre-H60 behaviour).

### C — non-transient path fails fast (no Azure needed)

- [ ] Reachable server (local `localhost\SQLEXPRESS`), `LUCIDPM_SQL_AUTH=sql`
      with a **wrong password** → fails on the first attempt, **no retry
      line**, error raised promptly (SQLSTATE `28000` is not transient).

### D — real resume (Cycle 2.2, against Azure SQL — records the number)

- [ ] With the Azure Test DB confirmed auto-paused (idle > 60 min), start the
      app pointed at Azure (`LUCIDPM_SQL_CONNECT_RETRIES=3`,
      `LUCIDPM_SQL_LOGIN_TIMEOUT=60`). Load a data page.
      → one or more `[state.get_conn]` retry lines, then the page loads
      successfully **without a manual refresh**.
- [ ] **Record** in the Cycle 2.2 / Gate 2 notes: total wall-clock to first
      usable page, how many attempts it took, which SQLSTATE(s) appeared. Feed
      that back into the roadmap and, if needed, tune the two defaults.

### Regression

- [ ] `grep -rn "pyodbc.connect" LucidPM/` — one call, inside
      `_connect_with_resume_retry` in `state.py`.
- [ ] No new import of any non-stdlib module.

---

## How to Deliver This

Per `CLAUDE.md`: edit the live file in place.

1. Apply Steps 1–4.
2. Run checklist **A**, **B**, **C** — none need Azure. This is the acceptance
   gate for H60.
3. Commit — e.g. `SQL connect retry-on-resume for Azure serverless auto-pause (H60)`.
4. Move this doc to `Completed Handoffs/`.
5. **D is Cycle 2.2 work** — run it when the app is next pointed at Azure SQL
   and record the resume timing. It does not block the H60 commit.

`state.py`'s `_vN` siblings were already archived under Handoff 58 (`d18a256`),
so there is no sibling cleanup this time.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\state.py     ← Steps 1–3 (imports, config vars, retry loop)
  .env.example         ← Step 4

Local: localhost\SQLEXPRESS, Windows auth — connects first try, retry never engages.
Azure (Cycle 2.2): lucidpm-sql-24899.database.windows.net, serverless auto-pause —
  this is what the retry loop is for.
```

---

*Two stdlib imports, two validated config vars, one transient-error predicate,
one retry loop around the single `pyodbc.connect` call. Zero behaviour change
when the database answers on the first attempt. Auth and "no such database"
errors still fail immediately. Turns the post-idle "broken page, refresh
yourself" into a slow-but-successful first load.*
