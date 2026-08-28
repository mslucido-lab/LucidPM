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

**As of 2026-08-27 (Handoff 52 — dynamic clause numbering):**
- Dynamic amendment-clause numbering is implemented with document-wide
  `{{ClauseNumber}}`, `{{ClauseNumber:Anchor}}`, and `{{ClauseRef:Anchor}}`
  tokens (`lease_merge.apply_clause_numbering`). Number assignment and named
  cross-reference resolution run in two passes over included text sections
  before normal lease-token rendering; PDF-only sections do not consume
  numbers, and undefined anchors block preview/generation with an actionable
  error.
- **Author `{{ClauseNumber}}` inside a `bulletText` attribute** (`<para
  bulletText="{{ClauseNumber}}.">`), not as bare leading text — a bare
  `{{ClauseNumber}}. Body` resolves to `3. Body`, which the PDF renderer
  promotes to a bold whole-line heading.
- Production `TenantCRM` Section Library rows 46, 47, 49, and 50 now use
  `{{ClauseNumber}}` in their top-level `bulletText` values (data-update
  script under `db/data_updates/` — run against Production by Mark). The
  inactive Option row 41 is deliberately unchanged; its `{{SectionNumber}}`
  mechanism is retained for backward compatibility but is legacy and
  superseded. **Do not activate the Option section** until it is migrated to
  `{{ClauseNumber:Option}}` — its counter is independent and it would
  misnumber.
- Regeneration is snapshot-based and does **not** renumber: `apply_clause_numbering`
  is not re-run on frozen `LeasePackageSections` rows. Generate a fresh package
  to pick up inserted/reordered clauses. Manual edits in the generated-section
  editor should use a literal number, not the token.
- Only cross-reference an anchor guaranteed to be included whenever the
  referencing clause is; a reference to an excluded/undefined anchor
  intentionally hard-blocks generation.

**As of 2026-08-16 (new laptop foundation session):**
- New laptop setup. Repo restructured to a standard Reflex project layout: the app package (`LucidPM.py`, `state.py`, `lease_merge.py`, `lease_render_styles.py`, `pages/`, `components/`, and all their `_vN` siblings) moved via `git mv` from the repo root into a new `LucidPM/` subdirectory. Repo root is now the true Reflex project root — no import statements changed, since they already assumed this layout. `pages/property_financials_analytics_v1.py`–`_v15.py` (the still-unarchived duplicates flagged back on 08-09) simply moved along with everything else to `LucidPM/pages/`; they remain unarchived. See `docs/RepositoryLayout.md`.
- Added the missing scaffold: `rxconfig.py` (`app_name="LucidPM"`), `requirements.txt` (pinned from a verified clean install), `.env.example` (documents that no env vars are actually used — all secrets are DB-stored), `assets/` placeholder, `.gitignore` updated for `.web/`.
- `/docs` created as the new source-of-truth engineering reference (Architecture, DeveloperSetup, Database, Deployment, CodingStandards, AIWorkflow, RepositoryLayout) — in response to Mark comparing the two independent repo-analysis handoffs (48 and the CODEX one) and having ChatGPT flag that neither addressed the lack of persistent engineering docs.
- **Python 3.12** is now the pinned target (not the 3.14 that ships on this machine) — installed via `py install 3.12`, chosen for package-compatibility maturity and alignment with the likely future Azure App Service runtime. `.venv` created and `pip install -r requirements.txt` verified clean. `python -c "import LucidPM"` succeeds.
- Dependency pinning turned out to be non-trivial: an unpinned `reflex` installs 0.9.8, which removed `rx.Base` (used across 14 live page files) — pinned to `reflex==0.8.9` instead. That surfaced a second conflict (0.8.9's pydantic-v1 compat shim breaks under pydantic ≥2.11, but recent `sqlmodel` requires pydantic ≥2.11) — resolved by pinning `pydantic<2.11` + `sqlmodel==0.0.24`. Full rationale is in `requirements.txt`'s header comment and `docs/DeveloperSetup.md`.
- With that pin set, `reflex run --backend-only` initially crashed compiling the `tenants`/`communications` pages: `EventHandlerArgTypeMismatchError` on their file-upload handlers. Root-caused (not a version problem — confirmed unchanged back to Reflex 0.7.0): those two files bound `on_drop=` directly to the handler, which Reflex's type-checker rejects; `waiting_list.py` already used the correct modern pattern (`on_drop=State.handler(rx.upload_files(...))`). Two more machine-specific issues turned up alongside it (a logo-lookup fallback broken by the restructure's extra directory level, and a hardcoded old-machine file-picker default directory) — both cosmetic, not crashes. All three bundled into **Handoff 49**, implemented (by Codex) and verified: all 17 registered pages compile cleanly, and the app was driven with a headless browser (Playwright) — dashboard, tenants, and communications pages all render correctly with live `TenantCRM_Test` data, zero page errors. Handoff 49 moved to `Completed Handoffs/`.
- **DB schema/migration baselining — done, later in this same session.** The loose scripts under the old `LucidPM/pages/TEST/` turned out to be reviewable against a much better source: the database already has its own `dbo.SchemaChangeLog` table, present in both `TenantCRM_Test` and `TenantCRM`, recording every real schema change (36 in Test, 35 in Prod) with timestamps and notes. Cross-referencing it against the 15 saved files found only 11 still have runnable SQL — the other 25 real changes have no surviving script, log-entry-only. Reorganized into a new `db/` folder at the repo root: `db/baseline_schema.sql` (a regeneratable, verified-correct live-schema snapshot — 43 tables, 51 FKs, 61 indexes, confirmed by actually building a throwaway scratch database from it and diffing counts against the source) plus `db/history/` (the 11 recovered scripts renumbered into real chronological order, a `skipped/` and `untracked/` subfolder for the edge cases, and `CHANGELOG.md` covering the full 36-entry timeline). See `docs/Database.md`. Also surfaced: `GeneratedLeaseDocuments` is confirmed dead code (already flagged in `lease_documents.py`'s own TODO comments, not fixed here) and Test/Prod are functionally in sync (one harmless Test-only legacy table, one log-entry gap that isn't a real schema difference).
- **Not done this session** (explicitly deferred, tracked as backlog, not overlooked): automated tests, CI, VS Code workspace config, and the bulk `_vN` archive cleanup (stays incremental per policy).
- **New backlog item: add a DDL trigger to auto-populate `dbo.SchemaChangeLog`.** `CREATE TRIGGER ... ON DATABASE FOR DDL_DATABASE_LEVEL_EVENTS` with `EVENTDATA().value('(/EVENT_INSTANCE/TSQLCommand/CommandText)[1]', 'nvarchar(max)')` captures the actual executed T-SQL text automatically, not just metadata — this would close the exact gap the `db/history/` reorganization above just had to work around (25 of 36 real changes had no surviving script because logging was a manual, easily-forgotten step in each script). Needs applying to both `TenantCRM_Test` and `TenantCRM`, documenting in `docs/Database.md` so it's not mystery automation, and a decision on whether to keep or drop the now-redundant manual `INSERT INTO SchemaChangeLog` statements already baked into the `db/history/` scripts. Not started — discussed and explicitly deferred, Mark to say when to pick it up.
- **New backlog item, TOP PRIORITY: stale post-migration `StoredFilePath` values across `dbo.LeaseDocumentSections` in both databases.** Every PDF-only section's stored absolute path still points to the old laptop's root (`C:\Dell Inspirion\...`), which doesn't exist on this machine — confirmed 4 active rows affected in `TenantCRM` (Production) and 16 active rows in `TenantCRM_Test`, all currently blocking package generation for any document that includes one of them (surfaced by the "Missing PDF files for these PDF-only sections" error while testing the Handoff 50 renewal-notice work). Good news: none of the files are actually lost — every single stale path was confirmed to resolve cleanly by swapping the `C:\Dell Inspirion` prefix for `C:\Users\msluc\OneDrive\Inspirion Backup` (7/7 in Prod, 17/17 in Test). Two fix options identified, neither applied yet: (1) a directory junction — `mklink /J "C:\Dell Inspirion" "C:\Users\msluc\OneDrive\Inspirion Backup"` — zero DB changes, unblocks immediately; (2) a one-time bulk `UPDATE LeaseDocumentSections SET StoredFilePath = REPLACE(StoredFilePath, 'C:\Dell Inspirion', 'C:\Users\msluc\OneDrive\Inspirion Backup')` across both DBs for a permanent fix. Deferred for now — Mark is unblocking himself locally in the meantime (recreating the old path). This is the same root cause Handoff 49 only partially patched (that one fixed a hardcoded file-picker *default directory*, cosmetic; this is stale paths baked into the DB itself, functional). Mark to say when to pick this up properly.
- **Fixed this session: `lease_documents_pdf.py` was silently running on a degraded fallback style set.** Its `LEASE_STYLES` import used the wrong module path (`LucidPM.pages.lease_render_styles`, which doesn't exist — the real module is `LucidPM.lease_render_styles`, one level up), always throwing `ImportError`, silently swallowed by a bare `except Exception:` that substitutes a hardcoded 10-style fallback dict missing `SIGNATURE_BLOCK` and `ARTICLE_CENTERED`. Predates Handoff 50 entirely (Codex's diff never touched these lines) — it surfaced now only because the renewal-notice document's authored signature-block text was the first content to actually exercise that code path, producing `Package generation failed: 'SIGNATURE_BLOCK'` (a `KeyError` swallowed down to just its message by the generic `except Exception as ex: self.form_error = f"Package generation failed: {ex}"` in `lease_package_builder.py`). Fixed with a one-line import path correction; confirmed the real 12-style `LEASE_STYLES` dict now loads. Given how long this silently degraded styling could have applied to other documents unnoticed, worth a broader look: `except Exception:` swallowing an `ImportError` into a silent fallback is a pattern worth grepping for elsewhere in the codebase.
- **New backlog item: a metadata-driven merge-token catalog, to stew on before designing.** `lease_merge.py`'s ~100+ merge tokens are all hardcoded in one large Python function, with a *separate* hardcoded list in `lease_documents.py` powering the Section Library's token picker — the two lists have already drifted apart multiple times this session (tokens existing in one but missing from the other). Idea floated with Mark: a `MergeTokenSources`-style DB table (TokenName, SourceTable, SourceColumn, Description) that the picker reads from directly, so **simple direct-field tokens** (e.g. a token that's just `Contacts.WorkPhone`) can be defined by picking a table/column and naming it — no code change, no handoff. Explicitly does NOT extend to **calculated/composed tokens** (anything with a condition, a join, a chain-walk — e.g. `OriginalOptionRent`, `AsAmendedPhrase`, both added this session) — those involve real procedural business logic that isn't a good fit for a data-driven formula system without inventing and safely sandboxing a mini expression language, which isn't judged worth the complexity for a two-person team already comfortable with code review. Likely shape: calculated tokens could still be *listed* in the same catalog table (flagged "computed in code") purely so the picker UI stays complete, even though only the simple half is actually data-driven. Not started — explicitly deferred at Mark's request to think it over further before scoping a handoff.
- **Also fixed this session: `_is_signature_block()` false-positive on ordinary prose.** Its heuristic (`lease_documents_pdf.py`) flagged any block containing "landlord"/"tenant"/etc. *plus either* `"____"` *or the word* `"signature"` as a signature footer — dumping it as raw escaped text instead of parsing it. The renewal-notice document's clause 7 ("Ratification...may be executed... by electronic signature") legitimately uses the word "signature" in prose, got misclassified, and printed its literal `<para bulletText="7."...>` tag in the generated PDF instead of rendering as a formatted numbered clause. Fixed by requiring `"____"` (every real signature block in both DBs has blank sign-here lines; confirmed via query that no active Section Library content relied on the word-only match). Verified: the false positive is gone and real signature blocks still detect correctly.
- Carried over, still open from before the laptop switch: Handoff 45 (narrow `_standalone_state()` in `LucidPM.py` to the required ancestor chain instead of the whole app's state tree) is written and sitting in `Undelivered Handoffs/`, not yet implemented — its file references were corrected this session (old flat `LucidPM_Reflex.py` path → `LucidPM/LucidPM.py`). (Handoff 47 — the 6 Bank Package PDF correctness bugs — was already completed prior to this session; it's in `Completed Handoffs/`. An earlier draft of this note incorrectly carried it forward as still-open; corrected here.) The Property Financials Analytics DB-toggle chart bug (switching tabs after toggling to Production makes chart data look like Test data, though the sidebar banner stays correct) is reported but still unreproduced/uninstrumented — no handoff written yet, pending better repro info. Azure POC is paused at: CLI installed, no subscription created yet — next step is Mark creating one in the portal, then resuming at POC-A (`az login`, create `Lucido-Apps-RG`); full plan in `Undelivered Handoffs/Azure Planning`.
