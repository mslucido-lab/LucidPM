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
- `Undelivered Handoffs/Azure Planning` — Azure hosting plan + architect gap analysis for eventually moving this app (and a sibling app, Portfolio Manager) to Azure.
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

**As of 2026-08-29.**

### Active thread — Lease Template admin redesign ("Studio")

Reworking the `/admin/lease-templates` page (four tabs: Load / Parse & Section / Section Library / Package Templates) so the two heavily-used modules (Package Templates + Section Library) stop forcing constant tab-hopping. Origin doc: `Undelivered Handoffs/Refining Lease Template process.md`. A written proposal + a clickable prototype were delivered as private Artifacts (links in the `project_lease_template_studio` memory).

- **Handoff 53 — done, committed `3c3f096`, verified.** Tab order is now Package Templates · Section Library · Parse & Section · Load; lands on Package Templates. Section Library rebuilt from a wide filter-table into the standard left scrollable list / right detail: pick a section on the left (internal name + group badge), view it read-only on the right with a header bar (type/tag/group badges, Active/Reusable toggles, source/pages/updated meta) + Edit / Delete / Close; Edit swaps in the existing form (article/label/tag inputs + content textarea + scrollable token panel). Existing handlers + the save column set unchanged.
- **Handoff 54 — written, in `Undelivered Handoffs/`, being started by Codex.** Three phases, one file (`lease_documents.py`), one commit each:
  1. Library edit form gains Section name / type / exhibit code; `save_section_content` writes the full column set (name required; Base-Lease-clears-exhibit; per-source exhibit-code uniqueness — mirrored from `create_section`).
  2. `+ New section` in the Library right panel — modes text / from-PDF / bulk-paste-split — **reusing** `create_section` (made INSERT-only), `_save_text_clause_section`, `parse_pasted_clauses`, and every `_find_clause_markers` / `_parse_clause_header` / `_clean_clause_label` heuristic verbatim.
  3. Delete `_tab_parse`; Load-tab "Split" buttons → Library `+ New section`; strip dead vars. End state = 3 tabs (Package Templates / Section Library / Load).
- **Deferred (out of 54, decided):** editing a PDF section's page range (delete + recreate; a "re-cut" action can come later), Sort order in the editor, further Load-tab changes.
- **After 54:** the merge-token catalog (see backlog) is the natural next step — the prototype shows the intended `MergeTokenSources` shape.

### Recently shipped (all committed + pushed, in `Completed Handoffs/`)

- **Handoff 52 — dynamic clause numbering.** `{{ClauseNumber}}` / `{{ClauseNumber:Anchor}}` / `{{ClauseRef:Anchor}}` tokens resolved document-wide by `lease_merge.apply_clause_numbering` before normal token rendering. Authoring rule: put `{{ClauseNumber}}` **inside a `bulletText` attribute**, not as bare leading text (bare `{{ClauseNumber}}. Body` → the renderer bolds the whole line). Prod `TenantCRM` Section Library rows 46/47/49/50 migrated via `db/data_updates/`. **Do not activate the inactive Option section (row 41)** — still on legacy `{{SectionNumber}}` with an independent counter; it would misnumber until migrated to `{{ClauseNumber:Option}}`. Regeneration is snapshot-based and does not renumber (generate a fresh package). Cross-reference only anchors guaranteed to be in the package — an excluded/undefined anchor hard-blocks generation.
- Renderer fix: a single fully-wrapped `<para>` with an internal `<br/>` now renders as one Paragraph (was splitting and re-applying `bulletText` → duplicate clause numbers).
- Work Items "Mark done" fix: the confirm/feedback message was only rendered in the edit form, so a blocked close silently reverted; moved to the detail panel.

### Standing backlog (not started; Mark to say when)

- **TOP PRIORITY — stale `StoredFilePath` in `dbo.LeaseDocumentSections`, both DBs.** Every PDF-only section's absolute path still points at the old laptop root `C:\Dell Inspirion\...`; ~4 active rows in Prod, ~16 in Test, blocking package generation for any document that includes one. Files aren't lost — the prefix maps cleanly to `C:\Users\msluc\OneDrive\Inspirion Backup`. Two fixes: (1) `mklink /J "C:\Dell Inspirion" "C:\Users\msluc\OneDrive\Inspirion Backup"` (junction, zero DB change, immediate); (2) one-time bulk `UPDATE ... SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Dell Inspirion', 'C:\Users\msluc\OneDrive\Inspirion Backup')` across both DBs (permanent). Mark is unblocking locally by recreating the old path.
- **Merge-token catalog** (`MergeTokenSources` table: TokenName, SourceTable, SourceColumn, Description, kind). Picker reads it; the resolver resolves simple `field` tokens generically so adding one is a table row, no code. Computed tokens (`AsAmendedPhrase`, `OriginalOptionRent`, `PaymentScheduleBlock`, …) stay in `get_lease_merge_context()` but are still listed, flagged computed. Prototype's "token catalog" section documents the intended shape.
- **DDL trigger to auto-populate `dbo.SchemaChangeLog`** on both DBs — captures executed T-SQL via `EVENTDATA()`. Would close the gap the `db/history/` reorg had to work around. Needs documenting in `docs/Database.md` + a decision on the now-redundant manual `INSERT INTO SchemaChangeLog` lines in `db/history/` scripts.
- **Handoff 45** — narrow `_standalone_state()` in `LucidPM.py` to the required ancestor chain. Written, in `Undelivered Handoffs/`, never implemented.
- **Property Financials Analytics DB-toggle chart bug** — switching tabs after toggling to Production shows chart data that looks like Test data (sidebar banner stays correct). Unreproduced / uninstrumented; no handoff yet.
- **`_vN` archive cleanup for the lease-template files** — `lease_documents_v*.py`, `lease_documents_pdf_v*.py`, `pages/LeaseDocuments History/` → `Archived Versions/`. Owed since Handoff 53 (incremental per the File Versioning policy — do it once 54 lands).
- Automated tests, CI, VS Code workspace config.
- **Azure POC** — paused: CLI installed, no subscription yet. Next: Mark creates a subscription in the portal, then resume at POC-A (`az login`, create `Lucido-Apps-RG`). Full plan in `Undelivered Handoffs/Azure Planning`.

### Watch-fors

- `except Exception:` that swallows an `ImportError` into a silent degraded fallback — the exact bug behind `lease_documents_pdf.py`'s wrong `LEASE_STYLES` import path (fixed). Worth grepping if styling/behaviour ever looks subtly off.
- `rx.callout.text(rx.hstack(...))` and similar — block content inside a `<p>` → React hydration errors. Two were fixed in the H53 pass; the pattern may recur.
- `select_source_document` (`lease_documents.py`) silently resets the `p_*` form — don't call it from anywhere that has half-entered form state.
