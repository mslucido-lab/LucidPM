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

### Active thread — Merge-token catalog

Making merge tokens data-driven so adding a simple one is a table row, not a code change across two files. Grounded analysis + agreed design in the `project_token_catalog_idea` memory; full backlog entry below. **Decisions locked (2026-08-29):** whitelisted source-objects (no SQL from data), standalone `/admin/merge-tokens` page, ship P1 (resolver + picker, no admin UI) → verify against a real package generation → then P2 (admin page). Next step: write the P1 handoff (55).

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

### Recently shipped (all committed + pushed, in `Completed Handoffs/`)

- **Handoff 52 — dynamic clause numbering.** `{{ClauseNumber}}` / `{{ClauseNumber:Anchor}}` / `{{ClauseRef:Anchor}}` tokens resolved document-wide by `lease_merge.apply_clause_numbering` before normal token rendering. Authoring rule: put `{{ClauseNumber}}` **inside a `bulletText` attribute**, not as bare leading text (bare `{{ClauseNumber}}. Body` → the renderer bolds the whole line). Prod `TenantCRM` Section Library rows 46/47/49/50 migrated via `db/data_updates/`. **Do not activate the inactive Option section (row 41)** — still on legacy `{{SectionNumber}}` with an independent counter; it would misnumber until migrated to `{{ClauseNumber:Option}}`. Regeneration is snapshot-based and does not renumber (generate a fresh package). Cross-reference only anchors guaranteed to be in the package — an excluded/undefined anchor hard-blocks generation.
- Renderer fix: a single fully-wrapped `<para>` with an internal `<br/>` now renders as one Paragraph (was splitting and re-applying `bulletText` → duplicate clause numbers).
- Work Items "Mark done" fix: the confirm/feedback message was only rendered in the edit form, so a blocked close silently reverted; moved to the detail panel.

### Standing backlog (not started; Mark to say when)

- **TOP PRIORITY — stale `StoredFilePath` in `dbo.LeaseDocumentSections`, both DBs.** Every PDF-only section's absolute path still points at the old laptop root `C:\Dell Inspirion\...`; ~4 active rows in Prod, ~16 in Test, blocking package generation for any document that includes one. Files aren't lost — the prefix maps cleanly to `C:\Users\msluc\OneDrive\Inspirion Backup`. Two fixes: (1) `mklink /J "C:\Dell Inspirion" "C:\Users\msluc\OneDrive\Inspirion Backup"` (junction, zero DB change, immediate); (2) one-time bulk `UPDATE ... SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Dell Inspirion', 'C:\Users\msluc\OneDrive\Inspirion Backup')` across both DBs (permanent). Mark is unblocking locally by recreating the old path.
- **Merge-token catalog — planned & scoped 2026-08-29 (now the active thread; see above + `project_token_catalog_idea` memory).** `dbo.MergeTokenCatalog` table both DBs (TokenName, DisplayName, GroupName, Description, Kind `field`|`computed`, SourceObject, SourceColumn, Format, SortOrder, IsActive, ExampleValue). `field` tokens resolve generically in `lease_merge.py`: `SourceObject` from a fixed whitelist of already-loaded row-dicts (`lease`/`tenant`/`property`/`suite`/`parent_lease`), `SourceColumn` + a fixed `Format` enum — **no SQL stored in data**. Adding a token on an already-selected column = 1 INSERT; a genuinely new DB column = 1-line Python edit to the base SELECT. Computed tokens (`AsAmendedPhrase`, `OriginalOptionRent`, `PaymentScheduleBlock`, …) keep their logic in `get_lease_merge_context()` forever but get a catalog row flagged `computed` (metadata-only editable) so the picker stays complete. `_available_token_buttons_panel` (`lease_documents.py`, the only picker — currently 86 hardcoded strings vs 121 resolver keys, already drifted) reads the catalog instead. Migration: `db/history/013_…` schema script + a `db/data_updates/` seed that reproduces today's picker exactly. **P1** = table + seed + resolver + picker, no admin UI. **P2** = `/admin/merge-tokens` list/detail page w/ live preview. **P3 (opt)** = package builder flags unknown tokens vs catalog.
- **DDL trigger to auto-populate `dbo.SchemaChangeLog`** on both DBs — captures executed T-SQL via `EVENTDATA()`. Would close the gap the `db/history/` reorg had to work around. Needs documenting in `docs/Database.md` + a decision on the now-redundant manual `INSERT INTO SchemaChangeLog` lines in `db/history/` scripts.
- **Handoff 45** — narrow `_standalone_state()` in `LucidPM.py` to the required ancestor chain. Written, in `Undelivered Handoffs/`, never implemented.
- **Property Financials Analytics DB-toggle chart bug** — switching tabs after toggling to Production shows chart data that looks like Test data (sidebar banner stays correct). Unreproduced / uninstrumented; no handoff yet.
- **Handoff 54 Phase 3 — deferred follow-ups (from Claude's review).**
  1. **Manual verification** — the F3 batch-split "advance range, split again" happy path could not be exercised locally: every source PDF path hits the stale `C:\Dell Inspirion\...` root (the TOP-PRIORITY item above), so `split_pdf_pages` throws `[Errno 2]`. The *failure* branch is verified correct (form stays put, range does not advance). Click through one real batch split in the app once the local path/junction is restored.
  2. **Dead-code nits** — `SECTION_CREATION_MODES` (constant, `lease_documents.py` ~line 252) and `set_p_creation_mode` (setter, ~line 2859) are orphaned after `_tab_parse` deletion (zero live refs); several header/inline comments still name the Parse tab (~lines 38-43, 85, 90, 161, 188-191, 364, 1327). Comment-only + safe deletes; fold into a later touch of the file.
  3. **F3 end-of-document UX wart** — when a batch split consumes the last page, F3 sets the next range to `N`-`N` and still shows "next range ready"; the next "Split & create" then fails with a page-overlap error. Follow-up: when no free pages remain, show "Source fully split" and navigate away like text mode.
- **`_vN` archive cleanup — `lease_documents.py` only.** Its `pages/lease_documents_v*.py` siblings + `pages/LeaseDocuments History/` (~150 files) → `Archived Versions/`. Held until Handoff 54 Phase 3 lands (mid-refactor); Phase 3 is now committed, so this is the next housekeeping step. `lease_documents_pdf`, `work_items`, and the `lease_merge` stragglers were archived 2026-08-29 (`9ed280c`); `lease_package_builder` earlier (`d186d83`).
- Automated tests, CI, VS Code workspace config.
- **Azure POC** — paused: CLI installed, no subscription yet. Next: Mark creates a subscription in the portal, then resume at POC-A (`az login`, create `Lucido-Apps-RG`). Full plan in `Undelivered Handoffs/Azure Planning`.

### Watch-fors

- `except Exception:` that swallows an `ImportError` into a silent degraded fallback — the exact bug behind `lease_documents_pdf.py`'s wrong `LEASE_STYLES` import path (fixed). Worth grepping if styling/behaviour ever looks subtly off.
- `rx.callout.text(rx.hstack(...))` and similar — block content inside a `<p>` → React hydration errors. Two were fixed in the H53 pass; the pattern may recur.
- `select_source_document` (`lease_documents.py`) silently resets the `p_*` form — don't call it from anywhere that has half-entered form state.
