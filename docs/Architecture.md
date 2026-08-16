# Architecture

## Framework

LucidPM is a [Reflex](https://reflex.dev) app: pure-Python UI code compiles to a React/Next.js frontend, backed by a FastAPI backend that Reflex generates and manages.

## Entry point

`LucidPM/LucidPM.py` is the app's entry point. It:

1. Imports every page module and its associated state class.
2. Creates a raw `FastAPI()` instance (`api`) and defines custom routes directly on it with `@api.get(...)` — these sit alongside Reflex's own generated routes for things Reflex doesn't natively do: a native file picker (`/api/pick-files`), and PDF generation/download endpoints (rent roll, proforma, property financials, bank package, communications, leases-expiring, generated lease documents, application reports).
3. Builds `app = rx.App(theme=..., api_transformer=api)` — the `api_transformer` mount is how the custom FastAPI routes get merged into Reflex's own backend.
4. Registers every page with `app.add_page(page_fn, route=..., on_load=State.on_load)`.

## Pages and state

Each route in `LucidPM/pages/` is a `(page_function, StateClass)` pair — e.g. `dashboard.py` exports `dashboard_page` and `DashboardState`. Reflex's state model means each page's state class holds the reactive vars and event handlers for that page; `on_load` handlers run when the route is navigated to (typically to (re)fetch data).

`LucidPM/state.py` is the shared base: DB connection helpers (`get_conn`, `run_query`, `run_exec`), brand color constants, and `AppState` (base state other pages' states inherit from — notably `use_test_db`, the test/production DB toggle referenced throughout the app).

## Shared UI

`LucidPM/components/sidebar.py` provides the page shell / navigation sidebar wrapping every page.

## PDF generation

Two libraries: `reportlab` for building PDFs from scratch (rent roll, proforma, property financials, etc.), `pypdf` for merging/reading/writing existing PDFs (e.g. the Bank Package export, which merges Proforma + Property Financials Trend + Rent Roll into one document — see `Completed Handoffs/LucidoPM_ChatGPT_Handoff_46_BankPackagePdf.md`).

## Lease document generation

`LucidPM/lease_merge.py` is the token-replacement/merge engine for lease documents; `lease_render_styles.py` holds the associated PDF styling. The domain architecture behind this subsystem (Section Library, ContentSnapshot, versioned regeneration) is documented separately in `LucidoPM_ProjectContext_v2_1.md` at the TenantCRM root — that doc is scoped to lease generation specifically, not the whole app.

## Database access pattern

There's no ORM. `run_query`/`run_exec` in `state.py` take raw SQL + params and a `db` argument (defaults to the test DB name) — every call site explicitly threads through which database it's targeting, driven by `AppState.use_test_db`. See `docs/Database.md`.
