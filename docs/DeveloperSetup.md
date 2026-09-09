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

Contributors who run the validation harnesses (headless-browser checks) also
need `pip install -r requirements-dev.txt` followed by
`python -m playwright install chromium`.

## 3. Verify the app imports and boots

```
python -c "import LucidPM"            # package layout only
python -c "import LucidPM.LucidPM"    # real app-import: every page module
reflex run
```

`import LucidPM` touches only the empty package initializer.
`import LucidPM.LucidPM` imports the entry module and, through it, every
registered page; exit code 0 is the pass criterion. Reflex prints an existing
sitemap-plugin warning on this import; that is not a failure. Both are fast
pre-checks before the slower `reflex run` frontend compile.

At this point, expect the app to boot and the frontend to compile. Pages that hit the database will fail until the local `TenantCRM_Test` / `TenantCRM` databases exist and are reachable — that's a separate step, not a sign anything above is broken. See `docs/Database.md`.

**Verified working (2026-08-16):** `reflex run` boots cleanly, all 17 registered pages compile, and the app renders correctly in a browser (dashboard, tenants, and communications pages confirmed via screenshot, zero page errors). Getting there required three fixes — a real crash (outdated `on_drop=` upload-handler binding in `tenants`/`communications`) and two cosmetic machine-specific issues (a logo-lookup fallback path broken by the restructure, and a hardcoded old-machine file-picker default directory) — all implemented and verified; see `Completed Handoffs/LucidoPM_ChatGPT_Handoff_49_StandUpOnNewLaptop.md`.

### Why `requirements.txt` pins exact versions, not ranges

`reflex`, `pydantic`, and `sqlmodel` are pinned to specific versions that are known to work together, not just "latest." The app code uses `rx.Base`, which Reflex removed in 0.9.0, and the pydantic/sqlmodel versions have their own cross-compatibility constraint on top of that. See the comment header in `requirements.txt` for the full explanation — do not casually bump these without re-running the boot check above.

### `pyproject.toml` vs `requirements.txt`

`requirements.txt` is the authoritative, fully-pinned lockfile and the install
target — it maps 1:1 to what ships in the container image. `pyproject.toml`
lists only the eight direct dependencies (same pins), as a readable manifest
for tooling and for anyone deciding whether a bump is safe.
`requirements-dev.txt` adds validation-only packages (`playwright`, `pyee`).
When you change a pin, change it in both `requirements.txt` and
`pyproject.toml`, and re-run the boot check.

## 4. Document storage

Attachment and source-PDF uploads use Reflex's `rx.upload` browser file input — no native/OS file dialog and no server-side path assumptions. `tenants.py` still defines a `DEFAULT_ATTACHMENT_FOLDER` constant with the old `C:\Dell Inspirion\TenantCRM\LeaseDocuments\Generated` path, but it is dead code and never referenced. Making the lease-document storage root (a separate concern from uploads — see `admin_settings.py` and the seeded value in `lease_documents.py`) properly configurable for cloud remains open in Azure roadmap Stage 5.1.

## 5. Secrets

No environment variables are required to start the app (see `.env.example`). SMTP credentials and the Anthropic API key are configured from within the running app itself (Admin Settings) and stored encrypted in the database — there's no separate secrets step during setup.
