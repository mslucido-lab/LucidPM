# LucidoPM — ChatGPT Handoff 61
*Project scaffolding: direct-dependency manifest, dev-deps split, Python pin, doc reconciliation*
*Prepared: 2026-09-08 · revised 2026-09-08 (pre-impl review, 4 points, all accepted: `.python-version` → exact patch `3.12.10`; dev extra mirrors `requirements-dev.txt` including `pyee`; app-import check uses `import LucidPM.LucidPM` not the empty package init; checklist D scoped to `requirements.txt` + `docs/` so it doesn't self-match this handoff's own quotes)*
*Azure Migration — Stage 0, Cycle 0.1. No Azure resource required; local behaviour unchanged.*

---

## What This Is

Roadmap **Cycle 0.1** (`Undelivered Handoffs/Azure Migration Roadmap.md`,
lines 153–158): *"a fresh clone → install → `reflex run` works with no tribal
knowledge."*

Most of this already exists from the 2026-08-16 stand-up (Handoff 49):
`requirements.txt` is a fully-pinned `pip freeze` with the load-bearing pins
documented, `rxconfig.py` is tracked, `LucidPM/__init__.py` exists, and
`docs/DeveloperSetup.md` walks the clean-machine path. This handoff closes the
remaining gaps:

1. **No `pyproject.toml`.** The 79-line frozen `requirements.txt` pins every
   transitive dependency but records nowhere *which 8 packages are the app's
   actual direct dependencies*. The Cycle 3.1 Dockerfile and any future
   dependency bump both need that list.
2. **No place for dev/validation-only dependencies.** `playwright` (used by the
   headless-Chromium checks in `docs/H58-validation.md` and `H59-validation.md`)
   is installed in the working `.venv` but is deliberately *not* in
   `requirements.txt` — and there is no `requirements-dev.txt` either, so a
   fresh clone can't reproduce the validation environment and the omission
   looks like drift.
3. **The `requirements.txt` header comment is stale and self-contradictory.**
   It says *"`reflex run` does NOT fully boot yet — see
   `…Handoff_49_UploadHandlerCompat.md`"*. That file does not exist (the real
   handoff is `_49_StandUpOnNewLaptop.md`), and the boot *was* fixed there —
   `docs/DeveloperSetup.md` line 32 says so, and Handoffs 50–60 were every one
   of them verified in the running app. This is exactly the conflicting tribal
   knowledge Cycle 0.1 is meant to delete.
4. **The Python version is prose-only.** `docs/DeveloperSetup.md` says "3.12";
   nothing machine-readable pins the exact interpreter the known-good freeze was
   validated against (3.12.10), and Cycle 3.1 picks the
   `python:3.12-slim-bookworm` base image off the loose assumption.

**Files that change:** new `pyproject.toml`, new `requirements-dev.txt`, new
`.python-version`; edits to `requirements.txt` (comment header only — **no pin
changes**) and `docs/DeveloperSetup.md`. No application code. No Azure.

### Scope constraint

**Manifest and documentation only.** This handoff does **not**:

- Change any pinned version in `requirements.txt`. The `reflex==0.8.9` /
  `pydantic==2.10.6` / `sqlmodel==0.0.24` set is load-bearing (see that file's
  header) and every other pin is a known-good `pip freeze` — they are copied
  into `pyproject.toml` verbatim, not re-resolved.
- Make the repo a `pip install`-able package. `pyproject.toml` here is a
  **metadata + direct-dependency manifest**; `requirements.txt` stays the
  install target and the lockfile. No `[build-system]` table.
- Touch `/api/pick-files` in `LucidPM.py` (the PowerShell file picker) or the
  `fastapi` route wiring — that is **Cycle 0.2**, Handoff TBD. This handoff only
  *records* `fastapi` as a direct dependency because `LucidPM.py:13` imports it
  at module level.
- Archive any `_vN` / `LucidPM_Reflex_*.py` sibling files.
- Add tests, CI, `pytest`, or `pip-tools`.
- Add or change any runtime env var, `.env` handling, or `rxconfig.py`.

---

## The Current State

### `requirements.txt` (tracked, 79 lines, last regenerated 2026-08-29)

A full `pip freeze`. Header comment documents the `reflex` / `pydantic` /
`sqlmodel` cross-constraint. Ends with the stale block (lines 15–18):

```
# Even with these pins, `reflex run` does NOT fully boot yet -- see
# Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_49_UploadHandlerCompat.md for
# a separate, unrelated app-code issue (not a dependency problem) blocking the
# tenants and communications pages specifically.
```

### Direct dependencies — reconstructed from live-code imports

`grep`-ed across `LucidPM/**/*.py` excluding `*_v[0-9]*` and `LeaseDocuments
History/`. Third-party module-level or feature-critical imports:

| Package (requirements.txt pin) | Where | Notes |
|---|---|---|
| `reflex==0.8.9` | everywhere | Framework. Pin is load-bearing (`rx.Base`, removed in 0.9). |
| `pyodbc==5.3.0` | `state.py` | SQL Server driver. |
| `fastapi==0.141.1` | `LucidPM.py:13` (module level) | Custom `/api/*` routes. App won't import without it. |
| `pypdf==6.16.1` | `LucidPM.py:12` (module level), lease PDF code | |
| `reportlab==5.0.0` | PDF generation (`*_pdf.py`, `lease_merge`, …) | |
| `pandas==3.0.5` | `property_financials_analytics.py`, proforma | Pulls `numpy` transitively. |
| `cryptography==50.0.0` | `settings.py` / `admin_settings.py` | Fernet encryption of stored secrets. |
| `anthropic==0.122.0` | `admin_settings.py:422`, `communications.py:945`, `settings.py:448` (lazy `import` inside handlers) | AI content generation. App boots without it; the feature 500s without it. Runtime dep, not optional. |

Everything else in `requirements.txt` (`granian`, `uvicorn`, `starlette`,
`SQLAlchemy`, `alembic`, `redis`, `Mako`, …) is transitive via `reflex` /
`anthropic` / `pandas`.

### Dev-only, in `.venv` but not in `requirements.txt`

```
playwright==1.62.0
pyee==13.0.1          # playwright's dependency
```

Used only by the H58/H59 validation harnesses (headless Chromium). Correct to
keep out of the runtime set; needs its own file.

### Already correct — do not recreate

- `rxconfig.py` — tracked, minimal (`app_name="LucidPM"`). Cycle 0.1's "add
  `rxconfig.py` if genuinely missing" is already satisfied.
- `LucidPM/__init__.py` — exists (empty). `python -c "import LucidPM"` only
  proves the package *layout* (it doesn't touch any page module). The real
  app-import check is `python -c "import LucidPM.LucidPM"` — the entry module
  that imports every page; it exits 0 here today (Reflex prints its existing
  sitemap-plugin warning, which is not a failure).
- `.gitignore` — already covers `.venv/`, `.web/`, `__pycache__/`, `.env` /
  `.env.*` (with `!.env.example`).
- `docs/DeveloperSetup.md` — accurate except the cross-references noted below.

---

## The Fix

### Step 1 — new file `pyproject.toml` (repo root)

Metadata + direct-dependency manifest. **No `[build-system]` table** — this is
not a package to build; `requirements.txt` remains the install target. Versions
are copied verbatim from `requirements.txt` (do not re-resolve).

```toml
# Direct-dependency manifest for LucidPM. This is documentation + a single
# place tools (Dependabot, uv, IDEs) can read the real dependency set.
#
# It is NOT an install target and NOT a buildable package: install with
#   pip install -r requirements.txt          (runtime — the pinned lockfile)
#   pip install -r requirements-dev.txt      (+ validation-harness extras)
# and see docs/DeveloperSetup.md.
#
# When a version here changes, change it in requirements.txt too (re-freeze
# from a clean, boot-tested .venv) — requirements.txt is authoritative.

[project]
name = "lucidpm"
version = "0.0.0"
description = "Lucid Property Manager — tenant CRM / property management app (Reflex)."
requires-python = ">=3.12,<3.13"

# Direct runtime dependencies only. Pins match requirements.txt exactly.
# reflex / (pydantic) / (sqlmodel) are a load-bearing set — see the
# requirements.txt header before touching them.
dependencies = [
    "reflex==0.8.9",
    "pyodbc==5.3.0",
    "fastapi==0.141.1",
    "pypdf==6.16.1",
    "reportlab==5.0.0",
    "pandas==3.0.5",
    "cryptography==50.0.0",
    "anthropic==0.122.0",
]

[project.optional-dependencies]
# Validation / local-tooling only — never installed in the container image.
# Same pinned set as requirements-dev.txt (pyee is playwright's dep, pinned
# for reproducibility).
dev = [
    "playwright==1.62.0",
    "pyee==13.0.1",
]
```

### Step 2 — new file `requirements-dev.txt` (repo root)

```
# Dev / validation-only dependencies. NOT installed in production or the
# Cycle 3.1 container image. The runtime set is requirements.txt.
#
# Regenerate the pins from a clean .venv that has both files installed:
#   pip install -r requirements.txt -r requirements-dev.txt
#   pip freeze  # then copy the playwright / pyee lines here

-r requirements.txt

playwright==1.62.0
pyee==13.0.1
```

### Step 3 — new file `.python-version` (repo root)

```
3.12.10
```

Single line, no trailing content. The exact interpreter the known-good freeze
was validated on (2026-08-16) — pyenv / asdf / mise resolve a bare `3.12`
inconsistently, so pin the patch. `pyproject.toml`'s
`requires-python = ">=3.12,<3.13"` stays a range (any 3.12.x is fine to *run*
on), and the Cycle 3.1 Docker base stays `python:3.12-slim-bookworm`.

### Step 4 — `requirements.txt`: replace the stale header block

**Current** (lines 15–18):

```
# Even with these pins, `reflex run` does NOT fully boot yet -- see
# Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_49_UploadHandlerCompat.md for
# a separate, unrelated app-code issue (not a dependency problem) blocking the
# tenants and communications pages specifically.
```

**Replace with:**

```
# `reflex run` boots cleanly from these pins: verified on a clean machine
# 2026-08-16 (Handoff 49 "StandUpOnNewLaptop") and continuously since — every
# Handoff 50-60 change was verified in the running app.
#
# Direct dependencies are listed in pyproject.toml. Dev / validation-only
# packages (playwright) are in requirements-dev.txt, not here — keep this file
# to the app's runtime set so it maps 1:1 to the container image.
```

**Also** add one line as the last comment before the first package entry
(`alembic==1.19.1`):

```
# When you re-freeze, keep pyproject.toml's [project.dependencies] pins in sync.
```

### Step 5 — `docs/DeveloperSetup.md`: reconcile

**5a** — Section **2. Virtual environment**, after the fenced install block, add
this paragraph:

> Contributors who run the validation harnesses (headless-browser checks) also
> need `pip install -r requirements-dev.txt` followed by
> `python -m playwright install chromium`.

**5b** — Section **3. Verify the app imports and boots**. Replace the lone
`python -c "import LucidPM"` line with both checks and a note:

```
python -c "import LucidPM"            # package layout only
python -c "import LucidPM.LucidPM"    # real app-import: every page module
reflex run
```

> `import LucidPM` touches only the (empty) package initializer.
> `import LucidPM.LucidPM` imports the entry module and, through it, every
> registered page — exit code 0 is the pass criterion. Reflex prints an
> existing sitemap-plugin warning on this import; that is not a failure. Both
> are fast pre-checks before the slower `reflex run` frontend compile.

**5c** — add a short subsection after "Why `requirements.txt` pins exact
versions":

```
### `pyproject.toml` vs `requirements.txt`

`requirements.txt` is the authoritative, fully-pinned lockfile and the install
target — it maps 1:1 to what ships in the container image. `pyproject.toml`
lists only the ~8 *direct* dependencies (same pins), as a readable manifest for
tooling and for anyone deciding whether a bump is safe. `requirements-dev.txt`
adds validation-only packages (`playwright`, `pyee`). When you change a pin,
change it in both `requirements.txt` and `pyproject.toml`, and re-run the boot
check.
```

**5d** — no change to Section 4 (document storage) or Section 5 (secrets); the
`/api/pick-files` path work is Cycle 0.2.

---

## Do Not Touch

| What | Why |
|---|---|
| Any `==` pin in `requirements.txt` | Load-bearing / known-good freeze; `pyproject.toml` copies them, doesn't re-resolve |
| `rxconfig.py` | Already correct and tracked; Stage 3.1 handles `REFLEX_API_URL` |
| `LucidPM/__init__.py` | Already exists (empty); leave it empty — the app-import check uses `import LucidPM.LucidPM`, not the package init |
| `LucidPM.py` `/api/pick-files`, `fastapi` routes | Cycle 0.2 |
| `.gitignore` | Already covers `.venv` / `.web` / `.env` |
| Any `_vN.py` / `LucidPM_Reflex_*.py` sibling | Not a scaffolding concern; separate housekeeping |
| `.env.example`, `state.py`, env handling | Handoffs 58–60; untouched |
| Application / page code | This handoff is manifest + docs only |

---

## Validation Checklist

All local, no Azure. Run from a **scratch directory**, not the working `.venv`.

### A — clean runtime install from the lockfile

- [ ] `py -3.12 -m venv /tmp/h61 && /tmp/h61/Scripts/pip install -r requirements.txt`
      resolves with **no dependency conflicts** and no errors.
- [ ] `/tmp/h61/Scripts/python -c "import LucidPM"` → exits 0 (package layout).
- [ ] `/tmp/h61/Scripts/python -c "import LucidPM.LucidPM"` → **exits 0** (the
      real app-import: pulls in every page module). The sitemap-plugin warning
      on stderr is pre-existing and fine; a non-zero exit is not.
- [ ] `reflex run` (in that env, from the repo root) → frontend compiles, all
      registered pages load, no page errors. (Same bar as `docs/DeveloperSetup.md`
      line 32. DB pages may error if the local SQL DBs aren't up — that's
      expected and not a regression.)

### B — dev install

- [ ] `/tmp/h61/Scripts/pip install -r requirements-dev.txt` resolves cleanly
      (pulls `playwright==1.62.0`, `pyee==13.0.1`, nothing else new).
- [ ] `pip freeze` in that env differs from `requirements.txt` by **exactly**
      `playwright` + `pyee`.

### C — pyproject.toml is well-formed and consistent

- [ ] `python -c "import tomllib,sys; d=tomllib.load(open('pyproject.toml','rb')); print(d['project']['dependencies'])"`
      parses.
- [ ] Every version in `[project.dependencies]` and `[project.optional-dependencies].dev`
      **string-matches** the corresponding line in `requirements.txt` /
      `requirements-dev.txt`.
- [ ] `requires-python` is `>=3.12,<3.13`; `.python-version` is `3.12.10`
      (exact patch — the freeze's validated interpreter).

### D — no stale cross-references remain

Scope the search to the files this handoff owns — **`requirements.txt` and
`docs/`**. Do *not* grep the repo root: this handoff and its future
`Completed Handoffs/` copy both quote the stale phrases verbatim in their
"Current State" section, and that is correct.

- [ ] `grep -rn "UploadHandlerCompat\|does NOT fully boot\|not fully boot" requirements.txt docs/`
      → no hits (was: `requirements.txt` line 15).
- [ ] `grep -rn "Handoff_49\|Handoff 49" requirements.txt docs/` → every hit
      names `StandUpOnNewLaptop`, none name a non-existent file.

### E — repo hygiene

- [ ] `git status` shows only: new `pyproject.toml`, `requirements-dev.txt`,
      `.python-version`; modified `requirements.txt`, `docs/DeveloperSetup.md`.
- [ ] `.venv/`, `.web/`, `__pycache__/` still untracked/ignored.

---

## How to Deliver This

Per `CLAUDE.md`: create the new files and edit the live ones in place.

1. Apply Steps 1–5.
2. Run checklist **A–E**. This is the acceptance gate — none of it needs Azure.
3. Commit — e.g. `Project scaffolding: pyproject.toml + dev-deps split + Python pin (H61, Cycle 0.1)`.
4. Move this doc to `Completed Handoffs/`.
5. Update the roadmap progress log: Cycle 0.1 done.

No `_vN` sibling cleanup (scaffolding files have none).

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  pyproject.toml           ← Step 1 (new)
  requirements-dev.txt     ← Step 2 (new)
  .python-version          ← Step 3 (new)
  requirements.txt         ← Step 4 (header comment only — no pin changes)
  docs\DeveloperSetup.md   ← Step 5

  Undelivered Handoffs\Azure Migration Roadmap.md   ← Cycle 0.1 (lines 153–158); progress log update on delivery
```

---

*Three new files, two comment/doc edits, zero pin changes, zero app code. Turns
"the real dependency list lives in a 79-line freeze and one contradictory
comment" into "8 direct deps in `pyproject.toml`, dev extras in their own file,
Python version pinned, docs agree with each other." Unblocks the Cycle 3.1
Dockerfile.*
