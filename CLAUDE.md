# CLAUDE.md

Working agreement and conventions for LucidPM. Read this at the start of every session in this repo.

---

## Project Overview

LucidPM (Lucid Property Manager) — a tenant CRM / property management app.

| Layer | Technology |
|---|---|
| App framework | Python / Reflex |
| Database | SQL Server Express (local), pyodbc |
| PDF generation | ReportLab, pypdf |

Related docs:
- `docs/` — engineering reference (Architecture, Developer Setup, Database, Deployment, Coding Standards, AI Workflow, Repository Layout). Start here for anything that isn't session-specific state; this file stays focused on the working agreement and current session status.
- `Undelivered Handoffs/Azure Planning` — Azure hosting plan + architect gap analysis for eventually moving this app (and a sibling app, Portfolio Manager) to Azure. `Undelivered Handoffs/Azure Migration Roadmap.md` sequences it into cycle-sized work with go/no-go gates.
- `LucidoPM_ProjectContext_v2_1.md` (TenantCRM root) — domain architecture for the lease generation/template subsystem specifically (Section Library, ContentSnapshot, versioned regeneration). Scoped to that subsystem, not the whole app.

---

## Working Agreement

Three roles on this project:

- **Product Manager (Mark)** — sets priorities, makes product/design calls, verifies changes in the running app, approves anything that touches shared state (git pushes, Azure resources, destructive operations).
- **Claude — Architect** — analyzes the codebase, makes design/architecture recommendations, writes handoff documents for Codex, reviews Codex's output, and directly implements smaller/lower-risk changes (bug fixes, targeted edits) when asked.
- **Codex — Developer** — implements larger feature work from a handoff document written by Claude.

Typical flow: Claude designs the change and writes a handoff doc in `Undelivered Handoffs/` → Codex implements it → Mark verifies in the running app → the change is committed to git → the handoff doc moves to `Completed Handoffs/`.

---

## Project Conventions

### File versioning — git only, no more manual `_vN` files

**This supersedes the old convention.** Historically, every change produced a new duplicate file (e.g. `pages/foo_v3.py`), manually copied over the live file to "deploy" it. Hundreds of these duplicates still exist throughout the repo. That convention is retired now that the repo is under git version control (baseline commit `18cb2f3`).

Going forward:
- Codex and Claude edit the **live file in place** (e.g. `pages/foo.py`). No new `_vN.py` files are created for any file under active development.
- Changes are reviewed as a diff and committed to git with a descriptive commit message. Git commit history is the version history now — it replaces what the `_vN` files used to do.
- Handoff documents describe edits to the live file directly — there is no "File to Produce: `foo_vN.py`" step anymore.

### Cleaning up old `_vN` files — incremental, file-by-file

The existing duplicate files are not being bulk-deleted. Cleanup happens **only when a file is next touched** for a real change:

1. Implement and verify the change to the live file (e.g. `pages/foo.py`).
2. Once verified working, move that file's old versioned siblings (`foo_v1.py` ... `foo_vN.py`, including any lettered variants like `foo_v14b.py`) into `Archived Versions/` at the repo root.
3. Commit the move.

Old versions are **archived, not deleted** — kept browsable in `Archived Versions/` rather than requiring git archaeology to recover, since everything is already safely preserved in the baseline commit regardless. Do not run a bulk cleanup pass across untouched files.

### Handoff documents

- Location: `Undelivered Handoffs/` for anything not yet sent to Codex or not yet completed. Move to `Completed Handoffs/` once implemented and verified.
- Naming: `LucidoPM_ChatGPT_Handoff_NN_ShortDescription.md`, continuing the existing numbering (last delivered: 42).
- Format: follow the structure established in Handoffs 40/42/43 — What This Is (with an explicit scope constraint), Current State (grounded in real file/line references), The Fix (exact current → replace code blocks), Do Not Touch, Validation Checklist, File Locations. No "File to Produce" versioned-file step — see File Versioning above.

---

## Where We Left Off

*(Updated in place each session — not appended to. For deeper history, use `git log` or browse `Completed Handoffs/`.)*

**As of 2026-09-07.**

### Queued — handoffs written as docs, not implemented, Mark to sequence

- **Handoff 59 — Env-aware API base URL** (`Undelivered Handoffs/`, this session, Codex pre-impl reviewed, not started). Retire the hardcoded `http://localhost:8000` in 8 live page modules' PDF/report download `@rx.var`s → `state.api_base_url()` (reads Reflex `api_url`; default unchanged). Stage 3 prerequisite, no Azure dependency, parallel with Cycle 2.2. Folds in H58 review finding 2 (`tenants.py:703` literal); archives the dead orphan `communications_report.py`. See the standing-backlog entry below.
- **Handoff 57 — Suite Rent PSF tab** (`Undelivered Handoffs/`, committed `1257263`). New "Suite Rent" tab on Property Financials Analytics: per-suite in-place annual rent PSF vs the suite's underwriting rent PSF, with the property's SquareFeet-weighted avg as a benchmark line, plus a numbers table. Metric = `monthly rent × 12 ÷ SquareFeet` (both `Leases.RentAmount` and `PropertySuites.UnderwritingRent` are monthly — mirrors `rent_roll.py`). One file (`property_financials_analytics.py`), read-only, no schema. Reuses the `rent_roll.find_lease` suite→lease matching cascade. Design + write-up this session.
- **Handoff 55 — Merge-token catalog P1** (`Undelivered Handoffs/`, committed `0756799`). Data-driven merge tokens: `dbo.MergeTokenCatalog` table, `field` tokens resolve generically from a whitelisted source-object + fixed format enum (no SQL from data), `computed` tokens stay Python but get catalogued, the picker reads the table. P1 = table + seed reproducing today's ~121 tokens + resolver + picker, no admin UI; verify a package generation is byte-identical. P2 = `/admin/merge-tokens` page. Decisions locked 2026-08-29 (see `project_token_catalog_idea` memory + backlog below).
- **Handoff 56 — Retire the Load tab** (`Undelivered Handoffs/`, committed `4d34fe5`). End state two tabs (Package Templates · Section Library). Source PDFs become a switchable view inside the Library (list / upload / metadata / coverage). The frequent path — one formatted page (signature block etc.) → one section — collapses to upload-name-split in the From-PDF create mode; revising it is a "Replace PDF" button on the section. 3 phases, one file (`lease_documents.py`), one commit each. Design discussion with Mark 2026-08-30 (see `project_load_tab_retire` memory).

### Prior thread (shipped) — Lease Template admin redesign ("Studio")

Reworked the `/admin/lease-templates` page so the two heavily-used modules (Package Templates + Section Library) stop forcing constant tab-hopping. Origin doc: `Undelivered Handoffs/Refining Lease Template process.md`. A written proposal + a clickable prototype were delivered as private Artifacts (links in the `project_lease_template_studio` memory). Handoffs 53 + 54 done, committed, Claude-reviewed, both in `Completed Handoffs/`.

- **Handoff 53 — done, committed `3c3f096`, verified.** Tab order → Package Templates · Section Library · Parse & Section · Load; lands on Package Templates. Section Library rebuilt from a wide filter-table into the standard left scrollable list / right detail (list = internal name + group badge; right = read-only view with header bar of badges/toggles/meta + Edit / Delete / Close; Edit swaps in the existing form).
- **Handoff 54 — all three phases done + Claude-reviewed. Phase 3 committed `18eb32b`.** One file (`lease_documents.py`), one commit per phase:
  1. `d09cc1c` — Library edit form gains Section name / type / exhibit code; `save_section_content` writes the full column set (name required; Base-Lease-clears-exhibit; per-source exhibit-code uniqueness).
  2. `bdbc01c` — `+ New section` in the Library right panel: modes text / from-PDF / bulk-paste-split, reusing `create_section` (now INSERT-only), `_save_text_clause_section`, `parse_pasted_clauses`, and the clause-marker heuristics verbatim.
  3. `18eb32b` — `_tab_parse` deleted (~265 lines); Load-tab "Split / Add Section" + card "Split ->" + `source_document_row` → `start_new_section_from_source`; Load section-row Edit → `open_section_in_library`; dead code stripped (`go_to_parse_tab`, `new_standalone_clause`, `detach_current_clause_from_source`, `_is_metadata_only_section_update`, 7 `parse_*` computed vars). **End state = 3 tabs (Package Templates / Section Library / Load).** F3: a successful PDF split keeps From-PDF mode open with the page range advanced (`next_start = end+1`); text/bulk still navigate to the new section. F4: `save_loaded_draft_as_section` navigates to the new section like every other create path.
- **Post-54 polish (Codex + Mark, `1956f7b`).** Section Library left list → three-column grid (Section / Group / Tag) with a header row + ellipsis/hover; Sort-by dropdown gains "Section Name" and "Group". Not part of any handoff.
- **Deferred out of 54 (decided earlier):** editing a PDF section's page range (delete + recreate; a "re-cut" action later), Sort order in the editor, further Load-tab changes.
- **Deferred from Phase 3 review (see backlog):** manual in-app check of the F3 batch-split advance path; two trivial dead-code nits; one F3 end-of-document UX wart.

### Recently shipped (committed; not pushed unless noted)

- **Handoff 58 — Env-driven SQL connection + SQL-auth branch (Azure Stage 0.3).** Implemented + Claude-reviewed + committed `b47b6f8` (impl), `d18a256` (archived 19 `state_*.py`), `67b7e91` (review follow-ups); doc in `Completed Handoffs/`. `state.get_conn()` reads server/db/auth from env (defaults = today's hardcoded values → Windows-auth path byte-equivalent, order-independent); `sql` auth branch with `UID={}`/`PWD={}` brace-escaping; fail-fast `ConfigError` on bad auth mode / missing creds / bad encrypt-trust / non-int-or-negative timeout; dependency-free `.env` loader (full-line comments only, single quote-pair strip). `LUCIDPM_SINGLE_DB=<name>` locks to one DB + hides the Switch button; `LUCIDPM_ENV` is an inert marker reserved for Stage 5.3 Entra. `LucidPM.py` — two `"TenantCRM"` string literals → `PROD_DB_NAME`. **The `sql`-auth string is not yet tested against a live server — first test is Cycle 2.2** (if login fails, suspect the brace-escaping). `pyodbc 5.3.0` `connect(timeout=)` confirmed to be the *login* timeout, no query-timeout regression. Deferred review findings live in the Standing backlog (`localhost:8000` URLs, `tenants.py:703` stale literal).
- **Income Split chart rework (`6cc1c6f`, this session, Mark-verified on dev).** `income_split_chart()` in `property_financials_analytics.py` now reads as a composition chart: left axis "Opex % of Revenue" (0–100, builds up), right axis "NOI % of Revenue" reversed (reads down from 100%), one dashed line at the shared 40%-Opex / 60%-NOI mark (replaced the old meaningless `y=60` line). A hidden `_scale` bar bound to the right axis + `include_hidden=True` is what makes the right-axis ticks and the reference line render (a right YAxis with no series draws nothing). Axis domain reverted from `dataMin-5/dataMax+5` to `[0, 100]`. Then `ce1ca75` archived the 20 `property_financials_analytics_v*.py` siblings.

### Older shipped (all committed + pushed, in `Completed Handoffs/`)

- **Handoff 52 — dynamic clause numbering.** `{{ClauseNumber}}` / `{{ClauseNumber:Anchor}}` / `{{ClauseRef:Anchor}}` tokens resolved document-wide by `lease_merge.apply_clause_numbering` before normal token rendering. Authoring rule: put `{{ClauseNumber}}` **inside a `bulletText` attribute**, not as bare leading text (bare `{{ClauseNumber}}. Body` → the renderer bolds the whole line). Prod `TenantCRM` Section Library rows 46/47/49/50 migrated via `db/data_updates/`. **Do not activate the inactive Option section (row 41)** — still on legacy `{{SectionNumber}}` with an independent counter; it would misnumber until migrated to `{{ClauseNumber:Option}}`. Regeneration is snapshot-based and does not renumber (generate a fresh package). Cross-reference only anchors guaranteed to be in the package — an excluded/undefined anchor hard-blocks generation.
- Renderer fix: a single fully-wrapped `<para>` with an internal `<br/>` now renders as one Paragraph (was splitting and re-applying `bulletText` → duplicate clause numbers).
- Work Items "Mark done" fix: the confirm/feedback message was only rendered in the edit form, so a blocked close silently reverted; moved to the detail panel.

### Standing backlog (not started; Mark to say when)

- **TOP PRIORITY — stale `StoredFilePath` in `dbo.LeaseDocumentSections`, both DBs.** Every PDF-only section's absolute path still points at the old laptop root `C:\Dell Inspirion\...`; ~4 active rows in Prod, ~16 in Test, blocking package generation for any document that includes one. Files aren't lost — the prefix maps cleanly to `C:\Users\msluc\OneDrive\Inspirion Backup`. Two fixes: (1) `mklink /J "C:\Dell Inspirion" "C:\Users\msluc\OneDrive\Inspirion Backup"` (junction, zero DB change, immediate); (2) one-time bulk `UPDATE ... SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Dell Inspirion', 'C:\Users\msluc\OneDrive\Inspirion Backup')` across both DBs (permanent). Mark is unblocking locally by recreating the old path.
- **Merge-token catalog — planned & scoped 2026-08-29 (now the active thread; see above + `project_token_catalog_idea` memory).** `dbo.MergeTokenCatalog` table both DBs (TokenName, DisplayName, GroupName, Description, Kind `field`|`computed`, SourceObject, SourceColumn, Format, SortOrder, IsActive, ExampleValue). `field` tokens resolve generically in `lease_merge.py`: `SourceObject` from a fixed whitelist of already-loaded row-dicts (`lease`/`tenant`/`property`/`suite`/`parent_lease`), `SourceColumn` + a fixed `Format` enum — **no SQL stored in data**. Adding a token on an already-selected column = 1 INSERT; a genuinely new DB column = 1-line Python edit to the base SELECT. Computed tokens (`AsAmendedPhrase`, `OriginalOptionRent`, `PaymentScheduleBlock`, …) keep their logic in `get_lease_merge_context()` forever but get a catalog row flagged `computed` (metadata-only editable) so the picker stays complete. `_available_token_buttons_panel` (`lease_documents.py`, the only picker — currently 86 hardcoded strings vs 121 resolver keys, already drifted) reads the catalog instead. Migration: `db/history/013_…` schema script + a `db/data_updates/` seed that reproduces today's picker exactly. **P1** = table + seed + resolver + picker, no admin UI. **P2** = `/admin/merge-tokens` list/detail page w/ live preview. **P3 (opt)** = package builder flags unknown tokens vs catalog.
- **DDL trigger to auto-populate `dbo.SchemaChangeLog`** on both DBs — captures executed T-SQL via `EVENTDATA()`. Would close the gap the `db/history/` reorg had to work around. Needs documenting in `docs/Database.md` + a decision on the now-redundant manual `INSERT INTO SchemaChangeLog` lines in `db/history/` scripts.
- **Handoff 45** — narrow `_standalone_state()` in `LucidPM.py` to the required ancestor chain. Written, in `Undelivered Handoffs/`, never implemented.
- **Hardcoded `http://localhost:8000` in PDF/report URLs — cloud-blocker, fix before Stage 3** (H58 review finding 4). **Handoff 59 written 2026-09-07, Codex-reviewed** (`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_59_ApiBaseUrl.md`, not started): 8 live page modules (`communications`, `leases_expiring`, `lease_package_builder` ×3, `proforma` ×2, `property_financials`, `rent_roll`, `tenants`) hardcode `http://localhost:8000` in download-link `@rx.var`s → every link 404s on any non-default port or in a container. Fix = new `state.api_base_url()` reading Reflex's `api_url` config (default = `http://localhost:8000`, so local behaviour byte-identical); folds in H58 finding 2 (`tenants.py:703` `self.db or "TenantCRM"` → `PROD_DB_NAME`). No Azure dependency; parallel with Cycle 2.2. `pages/communications_report.py` (same literal) is a **dead orphan** — not imported/routed; NOT edited, archived in the housekeeping step along with the 8 files' `_vN` siblings. Checklist splits isolated `api_base_url()` subprocess checks (the `REFLEX_API_URL` override also redirects the websocket, so it can't be browser-tested) from browser checks on real ports.
- **Property Financials Analytics DB-toggle chart bug** — switching tabs after toggling to Production shows chart data that looks like Test data (sidebar banner stays correct). Unreproduced / uninstrumented; no handoff yet.
- **Handoff 54 Phase 3 — deferred follow-ups (from Claude's review).**
  1. **Manual verification** — the F3 batch-split "advance range, split again" happy path could not be exercised locally: every source PDF path hits the stale `C:\Dell Inspirion\...` root (the TOP-PRIORITY item above), so `split_pdf_pages` throws `[Errno 2]`. The *failure* branch is verified correct (form stays put, range does not advance). Click through one real batch split in the app once the local path/junction is restored.
  2. **Dead-code nits** — `SECTION_CREATION_MODES` (constant, `lease_documents.py` ~line 252) and `set_p_creation_mode` (setter, ~line 2859) are orphaned after `_tab_parse` deletion (zero live refs); several header/inline comments still name the Parse tab (~lines 38-43, 85, 90, 161, 188-191, 364, 1327). Comment-only + safe deletes; fold into a later touch of the file.
  3. **F3 end-of-document UX wart** — when a batch split consumes the last page, F3 sets the next range to `N`-`N` and still shows "next range ready"; the next "Split & create" then fails with a page-overlap error. Follow-up: when no free pages remain, show "Source fully split" and navigate away like text mode.
- **`_vN` archive cleanup — `lease_documents.py` only.** Its `pages/lease_documents_v*.py` siblings + `pages/LeaseDocuments History/` (~150 files) → `Archived Versions/`. Held until Handoff 54 Phase 3 lands (mid-refactor); Phase 3 is now committed, so this is the next housekeeping step. `lease_documents_pdf`, `work_items`, and the `lease_merge` stragglers were archived 2026-08-29 (`9ed280c`); `lease_package_builder` earlier (`d186d83`).
- Automated tests, CI, VS Code workspace config.
- **Azure POC — Stage 1 + Gate 1 PASSED (2026-09-06); Cycle 2.1 done, both DBs (2026-09-06); Handoff 58 / Stage 0.3 implemented + reviewed + committed `b47b6f8` (2026-09-07).** Plan: `Undelivered Handoffs/Azure Planning`; sequenced with a progress log in `Undelivered Handoffs/Azure Migration Roadmap.md` (read that for detail). ~11–15 cycles to POC complete, ~25–35 for both apps. Live resources (subscription `Lucido-Apps` / `76290cf4-215e-4da5-b9ae-572e0fad7052`, personal tenant, $1 budget alert): RG `Lucido-Apps-RG`; SQL server `lucidpm-sql-24899` in **westus3** (project region — East US regions were throttled for the new sub); admin `lucidadmin`; **DBs `TenantCRM` + `TenantCRM_Test`** both serverless free-offer (`useFreeLimit: true`; `AutoPause`; allowance is **per-database** — own 100k vCore-sec + 32 GB/mo each — up to 10 free DBs/subscription; region westus3 now locked for all free DBs), each **now holds a full verified copy of the matching local DB** (schema + data via SSMS Generate Scripts; row counts / FKs / CHECKs / indexes identical, only `sysdiagrams` left behind). BACPAC route abandoned (import recreates the DB → loses the free tier). `az` not installed locally — using Cloud Shell for now. Generated `.sql` copies under `C:\Inspirion\Dev\TenantCRM\Database\` + `db\` (repo copies have tenant PII — `.gitignore` now covers `/db/TenantCRM*.sql`, committed `1de81d2`). **PM precedent (2026-09-07):** `Undelivered Handoffs/lucidpm-cloud-migration-knowledge-share.md` (untracked) — Portfolio Manager already runs as a public Azure Container App in this same subscription. Reusable: shared Container Apps env `lucido-apps-env` + Log Analytics `lucido-apps-logs` (westus3, don't recreate), private GHCR + read-only pull-token pattern, `python:3.12-slim-bookworm` + ODBC 18 + non-root, Container Apps `secretref:` secrets, explicit schema bootstrap, Entra single-tenant built-in auth recipe, scale-to-zero. Residual Reflex-only risk: FE/BE split in one container + websocket through ingress. Handoff 58 revised 2026-09-07 to reconcile with it, then implemented + Claude-reviewed + committed `b47b6f8` (`state.get_conn` env-driven + `sql`-auth branch + fail-fast `ConfigError` validation + dependency-free `.env` loader; `LUCIDPM_SINGLE_DB` lock; `LUCIDPM_ENV` inert marker for Stage 5.3; `LucidPM.py` two `"TenantCRM"` literals → `PROD_DB_NAME`; toggle stays). `state_*.py` archived `d18a256`, doc in `Completed Handoffs/`. Windows-auth default path verified byte-equivalent; **the SQL-auth string is not yet tested against a live server — that's Cycle 2.2** (if login fails, suspect the `UID={}`/`PWD={}` brace-escaping). Contained non-admin SQL user for cloud still needed in *both* DBs if the toggle stays (Stage 3+). **Next:** Cycle 2.2 / Gate 2 = run H58's Part B checklist against Azure SQL (process env vars in one shell, not a persistent `.env`); capture cold-resume-from-auto-pause latency as the retry-wrapper input. Stage 0 code prep 0.1 (scaffolding), 0.2 (browser file input), 0.4 (Fernet key out of DB) have no Azure dependency and can run in parallel.

### Watch-fors

- `except Exception:` that swallows an `ImportError` into a silent degraded fallback — the exact bug behind `lease_documents_pdf.py`'s wrong `LEASE_STYLES` import path (fixed). Worth grepping if styling/behaviour ever looks subtly off.
- `rx.callout.text(rx.hstack(...))` and similar — block content inside a `<p>` → React hydration errors. Two were fixed in the H53 pass; the pattern may recur.
- `select_source_document` (`lease_documents.py`) silently resets the `p_*` form — don't call it from anywhere that has half-entered form state.
