r"""Remove six identified POC package records from Azure Production.

The default dry run writes a complete, ignored JSON manifest and a reviewable
rollback SQL script but makes no database change.  Run from the repository root:

    $env:LUCIDPM_SINGLE_DB = "TenantCRM"
    try {
        & .\.venv\Scripts\python.exe db\data_updates\2026-09-12_h71_remove_prod_poc_test_packages.py
    } finally {
        Remove-Item Env:\LUCIDPM_SINGLE_DB -ErrorAction SilentlyContinue
    }

After reviewing the generated files, repeat with ``--commit`` in a separate
try/finally block.  The script refuses every database except TenantCRM.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from LucidPM.state import PROD_DB_NAME, get_conn  # noqa: E402


TARGET_IDS = (2111, 2112, 2113, 2114, 2115, 2116)
EXPECTED_PARENT_COUNT = len(TARGET_IDS)
EXPECTED_CHILD_COUNT = 24
DEFAULT_MANIFEST = Path(__file__).with_name("h71_prod_package_cleanup_manifest.json")

PARENT_COLUMNS = (
    "LeaseGeneratedDocumentID",
    "TenantID",
    "LeaseID",
    "GeneratedFileName",
    "StoredFilePath",
    "GeneratedOn",
    "PackageNotes",
)
CHILD_COLUMNS = (
    "LeasePackageSectionID",
    "LeaseGeneratedDocumentID",
    "LeaseTemplateSectionID",
    "SortOrder",
    "IsIncluded",
    "PieceID",
    "Content",
    "IsDirty",
    "ContentSnapshot",
    "SectionID",
)


def _rows(cursor: Any, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _validate_prod_database(cursor: Any) -> None:
    cursor.execute("SELECT DB_NAME()")
    actual = str(cursor.fetchone()[0])
    if actual != PROD_DB_NAME:
        raise RuntimeError(
            f"Refusing to clean up {actual!r}; this script is Production-only ({PROD_DB_NAME!r})."
        )


def _load_current_rows(cursor: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    placeholders = ", ".join("?" for _ in TARGET_IDS)
    parents = _rows(
        cursor,
        f"""
        SELECT {", ".join(PARENT_COLUMNS)}
        FROM dbo.LeaseGeneratedDocuments
        WHERE LeaseGeneratedDocumentID IN ({placeholders})
        ORDER BY LeaseGeneratedDocumentID
        """,
        TARGET_IDS,
    )
    children = _rows(
        cursor,
        f"""
        SELECT {", ".join(CHILD_COLUMNS)}
        FROM dbo.LeasePackageSections
        WHERE LeaseGeneratedDocumentID IN ({placeholders})
        ORDER BY LeaseGeneratedDocumentID, LeasePackageSectionID
        """,
        TARGET_IDS,
    )
    actual_ids = {int(row["LeaseGeneratedDocumentID"]) for row in parents}
    if actual_ids != set(TARGET_IDS):
        raise RuntimeError(
            "Refusing cleanup because the live parent IDs do not exactly match the approved set. "
            f"Expected {list(TARGET_IDS)}; found {sorted(actual_ids)}."
        )
    if len(children) != EXPECTED_CHILD_COUNT:
        raise RuntimeError(
            "Refusing cleanup because the live child count changed. "
            f"Expected {EXPECTED_CHILD_COUNT}; found {len(children)}."
        )
    return parents, children


def _json_value(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    return value


def _json_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in rows]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as temporary:
        json.dump(payload, temporary, indent=2, ensure_ascii=False)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return "N'" + value.isoformat(sep=" ") + "'"
    if isinstance(value, bytes):
        return "0x" + value.hex()
    return "N'" + str(value).replace("'", "''") + "'"


def _insert_statement(table: str, columns: tuple[str, ...], row: dict[str, Any]) -> str:
    names = ", ".join(f"[{column}]" for column in columns)
    values = ", ".join(_sql_literal(row[column]) for column in columns)
    return f"INSERT INTO dbo.[{table}] ({names}) VALUES ({values});"


def _write_rollback(
    path: Path, parents: list[dict[str, Any]], children: list[dict[str, Any]]
) -> None:
    statements = [
        "-- H71 rollback: review before running. Azure TenantCRM only.",
        "SET XACT_ABORT ON;",
        "BEGIN TRANSACTION;",
        "SET IDENTITY_INSERT dbo.LeaseGeneratedDocuments ON;",
        *(_insert_statement("LeaseGeneratedDocuments", PARENT_COLUMNS, row) for row in parents),
        "SET IDENTITY_INSERT dbo.LeaseGeneratedDocuments OFF;",
        "SET IDENTITY_INSERT dbo.LeasePackageSections ON;",
        *(_insert_statement("LeasePackageSections", CHILD_COLUMNS, row) for row in children),
        "SET IDENTITY_INSERT dbo.LeasePackageSections OFF;",
        "-- Inspect the inserted row counts before choosing COMMIT.",
        "-- COMMIT TRANSACTION;",
        "-- ROLLBACK TRANSACTION;",
    ]
    path.write_text("\n".join(statements) + "\n", encoding="utf-8")


def _table_counts(cursor: Any) -> tuple[int, int]:
    cursor.execute("SELECT COUNT(*) FROM dbo.LeaseGeneratedDocuments")
    parents = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM dbo.LeasePackageSections")
    children = int(cursor.fetchone()[0])
    return parents, children


def _print_rows(parents: list[dict[str, Any]], children: list[dict[str, Any]]) -> None:
    print("Approved parent rows:")
    print(json.dumps(_json_rows(parents), indent=2, ensure_ascii=False))
    print("Approved child rows:")
    print(json.dumps(_json_rows(children), indent=2, ensure_ascii=False))


def main(commit: bool, manifest_path: Path, rollback_path: Path) -> None:
    with get_conn(PROD_DB_NAME) as connection:
        cursor = connection.cursor()
        _validate_prod_database(cursor)
        parents, children = _load_current_rows(cursor)
        before_counts = _table_counts(cursor)
        _print_rows(parents, children)

        manifest = {
            "handoff": "H71",
            "database": PROD_DB_NAME,
            "target_ids": list(TARGET_IDS),
            "parents": _json_rows(parents),
            "children": _json_rows(children),
        }
        _write_json(manifest_path, manifest)
        _write_rollback(rollback_path, parents, children)
        print(f"Manifest: {manifest_path}")
        print(f"Rollback SQL: {rollback_path}")

        if not commit:
            print("DRY RUN -- no database rows were deleted.")
            return

        placeholders = ", ".join("?" for _ in TARGET_IDS)
        try:
            cursor.execute(
                f"DELETE FROM dbo.LeasePackageSections WHERE LeaseGeneratedDocumentID IN ({placeholders})",
                TARGET_IDS,
            )
            deleted_children = cursor.rowcount
            cursor.execute(
                f"DELETE FROM dbo.LeaseGeneratedDocuments WHERE LeaseGeneratedDocumentID IN ({placeholders})",
                TARGET_IDS,
            )
            deleted_parents = cursor.rowcount
            if deleted_children != len(children) or deleted_parents != len(parents):
                raise RuntimeError(
                    "Delete count changed during cleanup; rolling back. "
                    f"Expected children/parents {len(children)}/{len(parents)}, got "
                    f"{deleted_children}/{deleted_parents}."
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        after_counts = _table_counts(cursor)
        print(
            f"Deleted {deleted_children} LeasePackageSections rows and "
            f"{deleted_parents} LeaseGeneratedDocuments rows."
        )
        print(f"Table counts before: generated={before_counts[0]}, sections={before_counts[1]}")
        print(f"Table counts after:  generated={after_counts[0]}, sections={after_counts[1]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Delete the approved Production rows.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--rollback-out", type=Path)
    args = parser.parse_args()
    rollback = args.rollback_out or args.manifest.with_suffix(".rollback.sql")
    main(args.commit, args.manifest, rollback)
