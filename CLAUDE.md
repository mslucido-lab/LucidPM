# CLAUDE.md

Working agreement and conventions for LucidPM_Reflex. Read this at the start of every session in this repo.

---

## Project Overview

LucidPM (Lucid Property Manager) — a tenant CRM / property management app.

| Layer | Technology |
|---|---|
| App framework | Python / Reflex |
| Database | SQL Server Express (local), pyodbc |
| PDF generation | ReportLab, pypdf |

Related docs:
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

**As of 2026-08-09:**
- Handoff 44's two fixes (income-split rounding + y-axis clipping in `pages/property_financials_analytics.py`) are verified live in the file — both confirmed correct.
- Handoff 44's step 3 (archive `property_financials_analytics_v1.py`–`_v15.py` into `Archived Versions/`) has **not** happened yet — still 20 old versions sitting in `pages/`, folder doesn't exist yet. This will be the first use of that folder.
- Handoff 45 (narrow `_standalone_state()` in `LucidPM_Reflex.py` to build only the required ancestor chain instead of the whole app's state tree, plus document its unavoidable dependency on internal Reflex API) is written and in `Undelivered Handoffs/`, not yet implemented.
- Handoff 46 (Bank Package PDF — merges Proforma + Property Financials Trend + Rent Roll via pypdf, new Cap Rate input on the Proforma page) is implemented and live. A full multi-angle code review of it found 6 concrete correctness bugs (garbled button label, unguarded cap_rate crash, unsanitized filename, non-decimal-capable Cap Rate input, unencoded property name in the URL, silent wrong-property substitution on a name mismatch) plus several lower-urgency efficiency/architecture items (the already-tracked `_standalone_state` whole-tree cost now hit twice, a fully-blocking endpoint, duplicate Properties queries, hardcoded basis/mode, triplicated NOI-margin-% logic). The 6 correctness bugs are written up as Handoff 47, not yet implemented. The efficiency/architecture items are intentionally deferred, not yet handed off.
- Reported but unconfirmed bug: on the Property Financials Analytics page, switching tabs (Summary/Trend/Margins/Valuation/Compare) after toggling DB to Production makes chart data look like Test data — but the sidebar banner itself stays correctly on Production (so this is not a `toggle_db` wiring bug; that fan-out was checked and looks correct). The computed-var chain feeding the charts (`chart_data` ← `filtered_data` ← `selected_property_id` ← `financials_data`) was reviewed statically and looks structurally sound — no bug found by reading code alone. Mark is attempting to reproduce it live to narrow down exactly when it happens before a handoff gets written. Next step once reproduced: report back what's actually in `financials_data`/`self.db` at the moment it looks wrong (a diagnostic-instrumentation handoff was proposed but not written, pending better repro info).
- Azure POC: Azure CLI installed locally (v2.89.0). No Azure subscription created yet — next step is Mark creating one in the portal, then resuming at POC-A (`az login`, create `Lucido-Apps-RG`). Full plan in `Undelivered Handoffs/Azure Planning`.
