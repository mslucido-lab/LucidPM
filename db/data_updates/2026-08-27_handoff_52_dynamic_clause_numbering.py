"""Apply Handoff 52's clause-token data update to Production TenantCRM.

Swaps the hardcoded top-level ``bulletText`` clause numbers in Amendment
Template 2's active clause rows (LeaseDocumentSections 46, 47, 49, 50) for the
dynamic ``{{ClauseNumber}}`` token. Row 41 (the inactive "Option" clause) is
deliberately left untouched.

STATUS: already applied to Production TenantCRM (2026-08-27). Re-running now
fails the ``count(old) == 1`` guard (fail-closed). Kept as the record of the
change. To revert, reverse the replacements below on rows 46/47/49/50:
    row 46: bulletText="{{ClauseNumber}}."  ->  bulletText="1."
    row 47: bulletText="{{ClauseNumber}}."  ->  bulletText="2."
    row 49: bulletText="{{ClauseNumber}}."  ->  bulletText="3."
    row 50: the three bulletText="{{ClauseNumber}}."  ->  "4." / "5." / "6." in order
Everything else in each row's Content is unchanged.

Usage (from anywhere; the filename's leading date makes ``python -m`` impossible):
    python db/data_updates/2026-08-27_handoff_52_dynamic_clause_numbering.py           # dry run
    python db/data_updates/2026-08-27_handoff_52_dynamic_clause_numbering.py --commit  # apply

The dry run prints every current ("recovery copy") and proposed value and runs
all guards, but writes nothing. --commit performs the writes in a single
transaction. Re-running after a successful apply fails the ``count(old) == 1``
guard (fail-closed) rather than double-applying.
"""

import os
import sys

# Repo root (three levels up: db/data_updates/<file>) so ``import LucidPM`` works
# when this is run as a plain script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from LucidPM.state import PROD_DB_NAME, get_conn  # noqa: E402


REPLACEMENTS = {
    46: [('bulletText="1."', 'bulletText="{{ClauseNumber}}."')],
    47: [('bulletText="2."', 'bulletText="{{ClauseNumber}}."')],
    49: [('bulletText="3."', 'bulletText="{{ClauseNumber}}."')],
    50: [
        ('bulletText="4."', 'bulletText="{{ClauseNumber}}."'),
        ('bulletText="5."', 'bulletText="{{ClauseNumber}}."'),
        ('bulletText="6."', 'bulletText="{{ClauseNumber}}."'),
    ],
}

_SELECT = (
    "SELECT LeaseDocumentSectionID, ArticleNumber, DisplayLabel, Content "
    "FROM dbo.LeaseDocumentSections "
    "WHERE LeaseDocumentSectionID IN (41, 46, 47, 49, 50)"
)


def _fetch(cursor) -> dict[int, tuple]:
    cursor.execute(_SELECT)
    return {int(r[0]): (r[1], r[2], str(r[3] or "")) for r in cursor.fetchall()}


def main(commit: bool) -> None:
    with get_conn(PROD_DB_NAME) as conn:
        cursor = conn.cursor()

        before = _fetch(cursor)
        if set(before) != {41, 46, 47, 49, 50}:
            raise RuntimeError(f"Expected rows 41/46/47/49/50; found {sorted(before)}")

        # Recovery copy -- printed BEFORE any write so it is captured even if a
        # later step fails.
        print(f"=== {PROD_DB_NAME}: pre-update Content (recovery copy) ===")
        for section_id in sorted(before):
            print(f"[{section_id}] {before[section_id][2]!r}")
        print()

        updated: dict[int, str] = {}
        for section_id, replacements in REPLACEMENTS.items():
            text = before[section_id][2]
            for old, new in replacements:
                if text.count(old) != 1:
                    raise RuntimeError(
                        f"Row {section_id}: expected exactly one {old!r}; "
                        f"found {text.count(old)}"
                    )
                text = text.replace(old, new)
            updated[section_id] = text

        print("=== proposed new Content ===")
        for section_id in sorted(updated):
            print(f"[{section_id}] {updated[section_id]!r}")
        print()

        if not commit:
            print("DRY RUN -- no rows written. Re-run with --commit to apply.")
            return

        for section_id, text in updated.items():
            cursor.execute(
                "UPDATE dbo.LeaseDocumentSections SET Content = ? "
                "WHERE LeaseDocumentSectionID = ?",
                (text, section_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Row {section_id}: expected one updated row")
        conn.commit()

        after = _fetch(cursor)
        assert after[41] == before[41], "Row 41 (inactive Option) must be unchanged"
        assert all(after[sid][2] == text for sid, text in updated.items())
        assert after[49][2].count("Section 3 of the Lease") == 1
        assert after[50][2].count("{{ClauseNumber}}") == 3

        print(f"Committed {PROD_DB_NAME} rows: {sorted(REPLACEMENTS)}")
        print("Verified row 41 unchanged: True")
        print(
            "ClauseNumber counts:",
            {sid: after[sid][2].count("{{ClauseNumber}}") for sid in REPLACEMENTS},
        )


if __name__ == "__main__":
    main(commit="--commit" in sys.argv[1:])
