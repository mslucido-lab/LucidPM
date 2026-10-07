"""Sync document-facing PropertySuite metadata from Prod into Test.

This updates matching Test suites by PropertyName + SuiteLabel. It does not add,
delete, activate, or rename suites. It copies the fields used by lease documents:
SquareFeet, SuiteUseType, UnderwritingRent, SuitePremisesDescription,
SuiteLegalDescription, and SuiteAddressOverride.

Run from the repository root. The first command is a dry run:

    .\\.venv\\Scripts\\python.exe db\\data_updates\\2026-10-06_sync_prod_suite_document_metadata_to_test.py
    .\\.venv\\Scripts\\python.exe db\\data_updates\\2026-10-06_sync_prod_suite_document_metadata_to_test.py --commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from LucidPM.state import PROD_DB_NAME, TEST_DB_NAME, get_conn  # noqa: E402


FIELDS = (
    "SquareFeet",
    "SuiteUseType",
    "UnderwritingRent",
    "SuitePremisesDescription",
    "SuiteLegalDescription",
    "SuiteAddressOverride",
)


def _rows(cursor: Any, sql: str) -> list[dict[str, Any]]:
    cursor.execute(sql)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _require_database(cursor: Any, expected: str) -> None:
    cursor.execute("SELECT DB_NAME()")
    actual = str(cursor.fetchone()[0])
    if actual != expected:
        raise RuntimeError(f"Expected {expected!r}, but this connection opened {actual!r}.")


def _load_suites(cursor: Any) -> list[dict[str, Any]]:
    return _rows(cursor, """
        SELECT ps.SuiteID, p.PropertyName, ps.SuiteLabel,
               ps.SquareFeet, ps.SuiteUseType, ps.UnderwritingRent,
               ps.SuitePremisesDescription, ps.SuiteLegalDescription,
               ps.SuiteAddressOverride
        FROM dbo.PropertySuites AS ps
        INNER JOIN dbo.Properties AS p ON p.PropertyID = ps.PropertyID
        ORDER BY p.PropertyName, ps.SortOrder, ps.SuiteLabel, ps.SuiteID
    """)


def _key(row: dict) -> tuple[str, str]:
    return (
        str(row.get("PropertyName") or "").strip().casefold(),
        str(row.get("SuiteLabel") or "").strip().casefold(),
    )


def _index(rows: list[dict], database: str) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    duplicates: list[tuple[str, str]] = []
    for row in rows:
        key = _key(row)
        if not all(key):
            raise RuntimeError(f"{database} has a suite without a property name or suite label: {row!r}")
        if key in result:
            duplicates.append(key)
        result[key] = row
    if duplicates:
        raise RuntimeError(f"{database} has duplicate PropertyName/SuiteLabel keys: {duplicates!r}")
    return result


def _same(left: Any, right: Any) -> bool:
    return ("" if left is None else str(left).strip()) == ("" if right is None else str(right).strip())


def main(commit: bool) -> None:
    with get_conn(PROD_DB_NAME) as prod_connection, get_conn(TEST_DB_NAME) as test_connection:
        prod_cursor, test_cursor = prod_connection.cursor(), test_connection.cursor()
        _require_database(prod_cursor, PROD_DB_NAME)
        _require_database(test_cursor, TEST_DB_NAME)
        prod = _index(_load_suites(prod_cursor), PROD_DB_NAME)
        test = _index(_load_suites(test_cursor), TEST_DB_NAME)

        missing = sorted(key for key in prod if key not in test)
        changes: list[tuple[dict, dict, list[str]]] = []
        for key, prod_row in prod.items():
            test_row = test.get(key)
            if test_row is None:
                continue
            changed = [field for field in FIELDS if not _same(prod_row[field], test_row[field])]
            if changed:
                changes.append((prod_row, test_row, changed))

        print(f"Prod suites: {len(prod)}; matching Test suites: {len(prod) - len(missing)}; metadata updates: {len(changes)}.")
        if missing:
            print("Prod suites absent from Test (not created):")
            for property_name, suite_label in missing:
                print(f"  {property_name} / {suite_label}")
        for prod_row, _, changed in changes:
            print(f"  {prod_row['PropertyName']} / {prod_row['SuiteLabel']}: {', '.join(changed)}")

        if not commit:
            print("DRY RUN -- no Test suite metadata changed. Repeat with --commit to apply.")
            return

        try:
            for prod_row, test_row, _ in changes:
                test_cursor.execute(
                    """
                    UPDATE dbo.PropertySuites
                    SET SquareFeet=?, SuiteUseType=?, UnderwritingRent=?,
                        SuitePremisesDescription=?, SuiteLegalDescription=?,
                        SuiteAddressOverride=?
                    WHERE SuiteID=?
                    """,
                    tuple(prod_row[field] for field in FIELDS) + (test_row["SuiteID"],),
                )
            test_connection.commit()
        except Exception:
            test_connection.rollback()
            raise

    print(f"Updated document-facing metadata on {len(changes)} Test suites.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Copy Prod suite metadata into Test.")
    main(parser.parse_args().commit)
