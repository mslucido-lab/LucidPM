# AI Workflow

The working agreement lives in `CLAUDE.md` at the repo root — this file is a pointer, not a fork.

Summary (see `CLAUDE.md` for the full, current wording):

## Roles

- **Product Manager (Mark)** — sets priorities, makes product/design calls, verifies changes in the running app, approves anything touching shared state (git pushes, Azure resources, destructive operations).
- **Claude — Architect** — analyzes the codebase, makes design/architecture recommendations, writes handoff documents for Codex, reviews Codex's output, and directly implements smaller/lower-risk changes when asked.
- **Codex — Developer** — implements larger feature work from a handoff document written by Claude.

## Flow

1. Claude designs the change and writes a handoff doc in `Undelivered Handoffs/`.
2. Codex implements it.
3. Mark verifies it in the running app.
4. The change is committed to git.
5. The handoff doc moves to `Completed Handoffs/`.

## Handoff doc format

Naming: `LucidoPM_ChatGPT_Handoff_NN_ShortDescription.md`, continuing the existing numbering. Structure follows Handoffs 40/42/43: What This Is (with an explicit scope constraint), Current State (grounded in real file/line references), The Fix (exact current → replace code blocks), Do Not Touch, Validation Checklist, File Locations.

## Why this session (2026-08-16) matters for future AI sessions

Before this session, there was no `/docs` — every fresh Claude or Codex session had to re-derive the project's structure, dependencies, and conventions from scratch, or rely on `CLAUDE.md`'s "Where We Left Off" narrative alone. `/docs` is meant to be the stable reference material that both Claude and Codex start from now, so `CLAUDE.md` can stay focused on the working agreement and current session state rather than growing into a full engineering manual.
