# Coding Standards

The authoritative conventions live in `CLAUDE.md` at the repo root — this file is a pointer, not a fork, so the rules only need updating in one place.

Summary (see `CLAUDE.md` for the full, current wording):

- **Edit live files in place.** No new `_vN.py` duplicate files for anything under active development — git history is the version history now (as of baseline commit `18cb2f3`).
- **Old `_vN` duplicates are archived, not bulk-deleted**, and only when the file they shadow is next touched for a real change — see `docs/RepositoryLayout.md` for the mechanics and `Archived Versions/` destination.
- **No speculative abstraction or unrequested cleanup.** Changes are scoped to what's asked; a bug fix doesn't pull in a refactor.
- Changes are reviewed as a diff and committed with a descriptive message.

If `CLAUDE.md`'s conventions and this file ever seem to disagree, `CLAUDE.md` wins — update this file to match.
