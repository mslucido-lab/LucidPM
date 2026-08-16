# Repository Layout

## Top level (Reflex project root)

```
LucidPM/                      <- git repo root, also the Reflex project root
  rxconfig.py                 <- Reflex config (app_name="LucidPM")
  requirements.txt
  .env.example
  assets/                     <- static files served by Reflex (currently empty)
  docs/                       <- this folder
  CLAUDE.md                   <- working agreement + session log ("Where We Left Off")
  Claude.txt                  <- old directory listing kept for historical reference
  Undelivered Handoffs/       <- handoff docs not yet implemented/verified
  Completed Handoffs/         <- handoff docs implemented and verified in the app
  Archived Versions/          <- retired _vN files, moved here incrementally (see below)
  LucidPM/                    <- the actual app package (see below) -- yes, same name as the repo root, see note below
  .venv/                      <- local virtualenv (gitignored)
  .web/                       <- Reflex-generated Next.js build output (gitignored)
```

**Note on the repeated `LucidPM` name:** the outer `LucidPM/` above is the git repo root / checkout folder (named that deliberately by Mark for a clean top-level directory on this machine). The inner `LucidPM/` is the Reflex app package, required by Reflex convention to share its name with `rxconfig.py`'s `app_name`. These are two different directories that happen to share a name — Reflex doesn't care what the outer checkout folder is called, only that a subfolder matching `app_name` exists inside it. This mirrors the original pre-git layout recorded in `Claude.txt` (`...\LucidPM_Reflex\LucidPM_Reflex\`), just renamed. The app was originally named `LucidPM_Reflex`; renamed to `LucidPM` on 2026-08-16, same session as the restructure.

## `LucidPM/` (inner) — the app package

This is what the code imports as `LucidPM.*` (e.g. `from LucidPM.state import AppState`). It was flat at the repo root until the 2026-08-16 restructure moved it into this subdirectory to match the layout Reflex expects (project root with `rxconfig.py` + a same-named app package underneath).

```
LucidPM/
  __init__.py
  LucidPM.py                  <- entry point: registers all pages, FastAPI mount, rx.App()
  state.py                    <- shared DB helpers (get_conn, run_query, run_exec), AppState, encryption helpers
  lease_merge.py               <- lease document token-replacement / merge engine
  lease_render_styles.py       <- PDF rendering styles for lease documents
  pages/                       <- one file per route (dashboard.py, tenants.py, rent_roll.py, ...)
  components/                  <- shared UI pieces (sidebar.py, etc.)
```

The many `LucidPM_Reflex_*.py` / `*_vN.py` files still sitting alongside these live files are the old versioned duplicates (see below) — their filenames still say `LucidPM_Reflex` since they're inert history, not imported by anything; they weren't renamed as part of the app-name change.

## The `_vN` legacy files

Historically, every change to a file produced a new duplicate (e.g. `tenants_32_v2_7_9.py`) that was manually copied over the live file to "deploy" it — there was no version control. That convention is retired as of baseline commit `18cb2f3` (see `CLAUDE.md` → File Versioning). Going forward, live files are edited in place and git history is the version history.

The old duplicates are **not bulk-deleted**. `LucidPM/`, `LucidPM/pages/`, and `LucidPM/components/` still contain hundreds of them. They're cleaned up **incrementally, only when the live file they shadow is next touched for a real change** — at that point the old versions move to `Archived Versions/` at the repo root (which doesn't exist yet; it's created the first time this happens). See `CLAUDE.md` for the exact procedure.

## Handoff docs

- `Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_NN_ShortDescription.md` — written by Claude, implemented by Codex.
- Moves to `Completed Handoffs/` once implemented and verified live by Mark.
- See `docs/AIWorkflow.md` for the full process.
