# Database

## Server

SQL Server Express, local instance `localhost\SQLEXPRESS` — hardcoded as `SQL_SERVER` in `LucidPM/state.py`, not configurable via environment variable today.

## Databases

Two databases, both expected to exist on the same instance:

- `TenantCRM` — production (`PROD_DB_NAME` in `state.py`)
- `TenantCRM_Test` — test (`TEST_DB_NAME` in `state.py`)

The app toggles between them at runtime via `AppState.use_test_db`; nearly every query call site passes `db=` explicitly rather than relying on a single global connection.

## Connection

`get_conn(db)` in `state.py` connects via `pyodbc` using:

- **ODBC Driver 18 for SQL Server** (system-level install, not a pip package)
- Windows trusted connection (`Trusted_Connection=yes`)
- `Encrypt=yes`, `TrustServerCertificate=yes`

## Schema

There is no formal migrations folder. Schema history exists as loose, unordered SQL scripts under `LucidPM/pages/TEST/`:

- `Executed/*.sql` — scripts believed to have already been run
- `SKIP/*.sql` — scripts intentionally not run
- Assorted top-level `.txt`/loose files (`Prod sql update 2.0.txt`, etc.) with no consistent naming or ordering

This is a real gap: a clean database cannot currently be built from a deterministic, ordered script set. Consolidating this into an authoritative migration baseline is flagged as follow-up work (see CODEX Repository Analysis, item 8), not attempted as part of the 2026-08-16 foundation session — it requires live DB inspection to determine which scripts actually reflect the current schema.

## Secrets

No environment variables are used. All secrets live encrypted in the database itself:

- **Fernet encryption key**: `get_fernet()` in `state.py` reads `AppSettings.LocalEncryptionKey`; if absent, it generates one and persists it back to `AppSettings` on first use. There's no external key to configure — the key lives entirely in whichever database (`TenantCRM` or `TenantCRM_Test`) is active at the time.
- **SMTP credentials, Anthropic API key**: stored encrypted (via that Fernet key) in `EmailConfig` / `AppSettings`, configured from the running app's Admin Settings page.

One consequence worth knowing: because the Fernet key is per-database and auto-generated, a value encrypted under `TenantCRM_Test`'s key cannot be decrypted using `TenantCRM`'s key, and vice versa. Restoring/copying data between the two databases needs to account for this.
