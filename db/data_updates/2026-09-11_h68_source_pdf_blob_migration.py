"""Migrate Test source PDFs and split sections from local paths to Azure Blob.

Run from the repository root (or any directory):

    .\\.venv\\Scripts\\python.exe db/data_updates/2026-09-11_h68_source_pdf_blob_migration.py
    .\\.venv\\Scripts\\python.exe db/data_updates/2026-09-11_h68_source_pdf_blob_migration.py --commit

The default is a dry run: it reads TenantCRM_Test and checks every local PDF,
but writes neither Blob objects nor SQL rows. ``--commit`` creates a durable,
ignored JSON manifest before each Blob upload, updates one Test row at a time,
and writes a rollback SQL script for review. Production is rejected by a
``DB_NAME()`` guard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from LucidPM.document_storage import (  # noqa: E402
    SOURCE_BLOB_PREFIX,
    AzureBlobStorage,
)
from LucidPM.pages.lease_documents_pdf import safe_pdf_filename, slugify  # noqa: E402
from LucidPM.state import TEST_DB_NAME, get_conn  # noqa: E402


DEFAULT_MANIFEST = Path(__file__).with_name("h68_source_pdf_blob_manifest.json")
FALLBACK_PROPERTY = "Unlinked"
FALLBACK_CATEGORY = "Legacy"
GENERAL_PROPERTY = "General / All Properties"


def _rows(cursor, query: str) -> list[dict[str, Any]]:
    cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _load_candidates(cursor) -> list[dict[str, Any]]:
    source_rows = _rows(
        cursor,
        """
        SELECT 'LeaseSourceDocuments' AS table_name,
               s.LeaseSourceDocumentID AS row_id,
               s.StoredFilePath, s.RelativePath, s.StorageRoot, s.PropertyID,
               p.PropertyName, s.DocumentCategory
        FROM dbo.LeaseSourceDocuments AS s
        LEFT JOIN dbo.Properties AS p ON p.PropertyID = s.PropertyID
        WHERE s.StoredFilePath IS NOT NULL
        """,
    )
    section_rows = _rows(
        cursor,
        """
        SELECT 'LeaseDocumentSections' AS table_name,
               d.LeaseDocumentSectionID AS row_id,
               d.StoredFilePath, d.RelativePath, d.StorageRoot, s.PropertyID,
               p.PropertyName, s.DocumentCategory
        FROM dbo.LeaseDocumentSections AS d
        LEFT JOIN dbo.LeaseSourceDocuments AS s
               ON s.LeaseSourceDocumentID = d.LeaseSourceDocumentID
        LEFT JOIN dbo.Properties AS p ON p.PropertyID = s.PropertyID
        WHERE d.StoredFilePath IS NOT NULL
        """,
    )
    return source_rows + section_rows


def _metadata(row: dict[str, Any]) -> tuple[str, str, bool]:
    property_name = str(row.get("PropertyName") or "").strip()
    category = str(row.get("DocumentCategory") or "").strip()
    if row.get("PropertyID") is None:
        property_name = GENERAL_PROPERTY
    if not property_name or not category:
        return FALLBACK_PROPERTY, FALLBACK_CATEGORY, True
    return property_name, category, False


def _kind(row: dict[str, Any]) -> str:
    return "template" if row["table_name"] == "LeaseSourceDocuments" else "section"


def _filename(path: str, row: dict[str, Any]) -> str:
    fallback = f"{_kind(row)}_{row['row_id']}.pdf"
    return safe_pdf_filename(os.path.basename(path), fallback)


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.entries = {entry["entry_id"]: entry for entry in data.get("entries", [])}

    @staticmethod
    def entry_id(row: dict[str, Any]) -> str:
        return f"{row['table_name']}:{row['row_id']}"

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": list(self.entries.values())}
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=self.path.parent, suffix=".tmp"
        ) as temp:
            json.dump(payload, temp, indent=2)
            temp.write("\n")
            temp_path = Path(temp.name)
        os.replace(temp_path, self.path)

    def record(self, entry: dict[str, Any]) -> None:
        self.entries[entry["entry_id"]] = entry
        self.save()


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    return "N'" + str(value).replace("'", "''") + "'"


def _write_rollback(manifest: Manifest, output: Path) -> None:
    statements = [
        "-- H68 rollback: review before running. TenantCRM_Test only.",
        "BEGIN TRANSACTION;",
    ]
    for entry in manifest.entries.values():
        if entry.get("status") != "migrated":
            continue
        table = entry["table_name"]
        id_column = "LeaseSourceDocumentID" if table == "LeaseSourceDocuments" else "LeaseDocumentSectionID"
        statements.append(
            f"UPDATE dbo.{table} SET "
            f"StoredFilePath = {_sql_literal(entry['old_stored_file_path'])}, "
            f"RelativePath = {_sql_literal(entry['old_relative_path'])}, "
            f"StorageRoot = {_sql_literal(entry['old_storage_root'])} "
            f"WHERE {id_column} = {int(entry['row_id'])};"
        )
    statements += ["-- Inspect the row count before choosing COMMIT.", "-- COMMIT TRANSACTION;", "-- ROLLBACK TRANSACTION;"]
    output.write_text("\n".join(statements) + "\n", encoding="utf-8")


def _validate_test_database(cursor) -> None:
    cursor.execute("SELECT DB_NAME()")
    actual = str(cursor.fetchone()[0])
    if actual != TEST_DB_NAME:
        raise RuntimeError(f"Refusing to migrate {actual!r}; H68 is Test-only ({TEST_DB_NAME!r}).")


def _require_blob_writer() -> tuple[AzureBlobStorage, str]:
    connection_string = os.getenv("LUCIDPM_BLOB_CONNECTION_STRING", "").strip()
    container = os.getenv("LUCIDPM_BLOB_CONTAINER", "").strip()
    if not connection_string or not container:
        raise RuntimeError(
            "H68 migration requires both LUCIDPM_BLOB_CONNECTION_STRING and "
            "LUCIDPM_BLOB_CONTAINER; it never uses LUCIDPM_STORAGE_BACKEND."
        )
    return AzureBlobStorage(connection_string, container), container


def main(commit: bool, manifest_path: Path, rollback_path: Path) -> None:
    with get_conn(TEST_DB_NAME) as conn:
        cursor = conn.cursor()
        _validate_test_database(cursor)
        rows = _load_candidates(cursor)

        local_rows = [
            row for row in rows
            if not str(row["StoredFilePath"] or "").startswith(SOURCE_BLOB_PREFIX)
        ]
        missing = [
            row for row in local_rows
            if not os.path.isfile(str(row["StoredFilePath"] or ""))
        ]
        if missing:
            ids = ", ".join(f"{row['table_name']}:{row['row_id']}" for row in missing)
            raise RuntimeError(
                "Refusing to migrate while local source files are unreadable: " + ids
            )

        fallbacks = sum(_metadata(row)[2] for row in local_rows)
        already_blob = len(rows) - len(local_rows)
        print(
            f"{TEST_DB_NAME}: {len(local_rows)} local rows ready, {already_blob} already Blob-backed, "
            f"{fallbacks} fallback bucket(s)."
        )
        for row in local_rows:
            property_name, category, fallback_used = _metadata(row)
            section = "/Sections" if _kind(row) == "section" else ""
            planned = (
                f"{SOURCE_BLOB_PREFIX}Sources/{slugify(property_name)}/{slugify(category)}{section}/"
                f"<uuid>_{_filename(str(row['StoredFilePath']), row)}"
            )
            print(
                f"DRY {'fallback ' if fallback_used else ''}{row['table_name']}:{row['row_id']} "
                f"-> {planned}"
            )

        if not commit:
            print("DRY RUN -- no Blob objects, manifest, or SQL rows were written.")
            return

        blob, container = _require_blob_writer()
        manifest = Manifest(manifest_path)
        for row in local_rows:
            entry_id = Manifest.entry_id(row)
            previous = manifest.entries.get(entry_id)
            if previous and previous.get("status") == "migrated":
                continue

            old_path = str(row["StoredFilePath"])
            property_name, category, fallback_used = _metadata(row)
            kind = _kind(row)
            filename = _filename(old_path, row)
            data = Path(old_path).read_bytes()
            identifier = blob.source_identifier(property_name, category, filename, kind=kind)
            entry = {
                "entry_id": entry_id,
                "table_name": row["table_name"],
                "row_id": int(row["row_id"]),
                "old_stored_file_path": old_path,
                "old_relative_path": row.get("RelativePath"),
                "old_storage_root": row.get("StorageRoot"),
                "new_identifier": identifier,
                "sha256": hashlib.sha256(data).hexdigest(),
                "fallback_used": fallback_used,
                "status": "uploaded_pending_update",
            }
            manifest.record(entry)
            try:
                blob.save_source(
                    property_name, category, filename, data, kind=kind, identifier=identifier
                )
                id_column = "LeaseSourceDocumentID" if kind == "template" else "LeaseDocumentSectionID"
                cursor.execute(
                    f"UPDATE dbo.{row['table_name']} SET StoredFilePath=?, RelativePath=?, StorageRoot=? "
                    f"WHERE {id_column}=? AND StoredFilePath=?",
                    (
                        identifier,
                        identifier.removeprefix(SOURCE_BLOB_PREFIX),
                        container,
                        int(row["row_id"]),
                        old_path,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(f"Expected one row update; got {cursor.rowcount}")
                conn.commit()
                entry["status"] = "migrated"
                manifest.record(entry)
            except Exception as exc:
                conn.rollback()
                entry["status"] = "failed"
                entry["error"] = str(exc)
                manifest.record(entry)
                raise

        _write_rollback(manifest, rollback_path)
        print(f"Migrated {len(local_rows)} Test rows. Manifest: {manifest_path}")
        print(f"Rollback script (review only): {rollback_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Upload and update TenantCRM_Test rows.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--rollback-out", type=Path)
    args = parser.parse_args()
    rollback = args.rollback_out or args.manifest.with_suffix(".rollback.sql")
    main(args.commit, args.manifest, rollback)
