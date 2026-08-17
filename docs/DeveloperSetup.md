# Developer Setup

Steps to get from a clean checkout to a running app. Written from the 2026-08-16 foundation session that first made this possible on a clean machine.

## 1. Prerequisites

- **Python 3.12** — the project targets 3.12 specifically (not whatever else may be on the machine). On Windows with the `py` launcher: `py install 3.12`.
- **Node.js** — required by Reflex to compile its generated Next.js frontend. Not hand-pinned in this repo; install current LTS.
- **SQL Server Express**, instance named `SQLEXPRESS` (i.e. `localhost\SQLEXPRESS`) — see `docs/Database.md`.
- **ODBC Driver 18 for SQL Server** — a system-level install, not a pip package. Required by `pyodbc` to connect. Install separately from Microsoft.

## 2. Virtual environment

From the repo root:

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. Verify the app imports and boots

```
python -c "import LucidPM"
reflex run
```

At this point, expect the app to boot and the frontend to compile. Pages that hit the database will fail until the local `TenantCRM_Test` / `TenantCRM` databases exist and are reachable — that's a separate step, not a sign anything above is broken. See `docs/Database.md`.

**Verified working (2026-08-16):** `reflex run` boots cleanly, all 17 registered pages compile, and the app renders correctly in a browser (dashboard, tenants, and communications pages confirmed via screenshot, zero page errors). Getting there required three fixes — a real crash (outdated `on_drop=` upload-handler binding in `tenants`/`communications`) and two cosmetic machine-specific issues (a logo-lookup fallback path broken by the restructure, and a hardcoded old-machine file-picker default directory) — all implemented and verified; see `Completed Handoffs/LucidoPM_ChatGPT_Handoff_49_StandUpOnNewLaptop.md`.

### Why `requirements.txt` pins exact versions, not ranges

`reflex`, `pydantic`, and `sqlmodel` are pinned to specific versions that are known to work together, not just "latest." The app code uses `rx.Base`, which Reflex removed in 0.9.0, and the pydantic/sqlmodel versions have their own cross-compatibility constraint on top of that. See the comment header in `requirements.txt` for the full explanation — do not casually bump these without re-running the boot check above.

## 4. Document storage

`LucidPM/pages/tenants.py` hardcodes a default attachment folder: `C:\Dell Inspirion\TenantCRM\LeaseDocuments\Generated`. On a new machine this path won't exist. Either create it, or (as a future improvement) make it configurable — currently it is not.

## 5. Secrets

No environment variables are required to start the app (see `.env.example`). SMTP credentials and the Anthropic API key are configured from within the running app itself (Admin Settings) and stored encrypted in the database — there's no separate secrets step during setup.
