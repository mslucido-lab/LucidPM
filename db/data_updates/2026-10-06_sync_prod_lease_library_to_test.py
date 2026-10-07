"""Synchronize the reusable Lease Documents library from Prod to Test.

Azure SQL Database does not permit three-part cross-database queries, so this
tool opens a read-only Production connection and a separate Test connection.
It never copies tenants, leases, rent schedules, or generated package history.

From the repository root:

    .\\.venv\\Scripts\\python.exe db\\data_updates\\2026-10-06_sync_prod_lease_library_to_test.py
    .\\.venv\\Scripts\\python.exe db\\data_updates\\2026-10-06_sync_prod_lease_library_to_test.py --commit

The first command is a dry run. ``--commit`` archives Test's current reusable
library and rebuilds it from Prod in one Test transaction. The document blobs
are not copied: this expects Test to be able to read the same Azure Blob paths
recorded by Production.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from LucidPM.state import PROD_DB_NAME, TEST_DB_NAME, get_conn  # noqa: E402


def _rows(cursor: Any, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _require_database(cursor: Any, expected: str) -> None:
    cursor.execute("SELECT DB_NAME()")
    actual = str(cursor.fetchone()[0])
    if actual != expected:
        raise RuntimeError(f"Expected {expected!r}, but this connection opened {actual!r}.")


def _load_prod_library(cursor: Any) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    source_documents = _rows(cursor, """
        SELECT s.LeaseSourceDocumentID AS ProdSourceDocumentID,
               s.PropertyID AS ProdPropertyID, p.PropertyName,
               s.OriginalFileName, s.StoredFilePath, s.PageCount,
               s.DocumentStatus, s.UploadedOn, s.Notes, s.TemplateName,
               s.DocumentScope, s.DocumentCategory, s.TemplateVersion,
               s.StorageRoot, s.RelativePath, s.SourceFileType,
               s.IsTemplate, s.IsActive
        FROM dbo.LeaseSourceDocuments AS s
        LEFT JOIN dbo.Properties AS p ON p.PropertyID = s.PropertyID
        WHERE s.LeaseID IS NULL
          AND (s.IsTemplate = 1 OR EXISTS (
              SELECT 1 FROM dbo.LeaseDocumentSections AS ds
              WHERE ds.LeaseSourceDocumentID = s.LeaseSourceDocumentID
                AND ds.LeaseID IS NULL AND ds.IsReusable = 1
          ))
        ORDER BY s.LeaseSourceDocumentID
    """)
    sections = _rows(cursor, """
        SELECT ds.LeaseDocumentSectionID AS ProdSectionID,
               ds.LeaseSourceDocumentID AS ProdSourceDocumentID,
               ds.SectionType, ds.SectionName, ds.ExhibitCode, ds.StartPage,
               ds.EndPage, ds.StoredFilePath, ds.SortOrder, ds.IsReusable,
               ds.CreatedOn, ds.Notes, ds.StorageRoot, ds.RelativePath,
               ds.IsActive, ds.Content, ds.ClauseTag, ds.ArticleNumber,
               ds.DisplayLabel, ds.UpdatedOn
        FROM dbo.LeaseDocumentSections AS ds
        WHERE ds.LeaseID IS NULL AND ds.IsReusable = 1
        ORDER BY ds.LeaseDocumentSectionID
    """)
    templates = _rows(cursor, """
        SELECT lt.LeaseTemplateID AS ProdTemplateID,
               lt.PropertyID AS ProdPropertyID, p.PropertyName,
               lt.TemplateName, lt.Description, lt.IsActive, lt.CreatedOn,
               lt.UpdatedOn, lt.TemplateVersion
        FROM dbo.LeaseTemplates AS lt
        LEFT JOIN dbo.Properties AS p ON p.PropertyID = lt.PropertyID
        ORDER BY lt.LeaseTemplateID
    """)
    template_sections = _rows(cursor, """
        SELECT lts.LeaseTemplateSectionID AS ProdTemplateSectionID,
               lts.LeaseTemplateID AS ProdTemplateID, lts.SortOrder,
               lts.SectionLabel, lts.DefaultSectionID AS ProdDefaultSectionID,
               lts.IsOptional, lts.IsRequired, lts.SectionType, lts.IsActive
        FROM dbo.LeaseTemplateSections AS lts
        ORDER BY lts.LeaseTemplateID, lts.SortOrder, lts.LeaseTemplateSectionID
    """)
    return source_documents, sections, templates, template_sections


def _test_property_map(cursor: Any) -> dict[str, int]:
    by_name: dict[str, list[int]] = {}
    for row in _rows(cursor, "SELECT PropertyID, PropertyName FROM dbo.Properties"):
        name = str(row.get("PropertyName") or "").strip()
        if name:
            by_name.setdefault(name.casefold(), []).append(int(row["PropertyID"]))
    duplicates = [name for name, ids in by_name.items() if len(ids) != 1]
    if duplicates:
        raise RuntimeError(f"Test has duplicate PropertyName values: {duplicates!r}.")
    return {name: ids[0] for name, ids in by_name.items()}


def _map_properties(rows: Iterable[dict], test_properties: dict[str, int]) -> None:
    missing: list[str] = []
    for row in rows:
        if row.get("ProdPropertyID") is None:
            row["TestPropertyID"] = None
            continue
        name = str(row.get("PropertyName") or "").strip()
        row["TestPropertyID"] = test_properties.get(name.casefold())
        if row["TestPropertyID"] is None:
            missing.append(name or f"Prod PropertyID {row['ProdPropertyID']}")
    if missing:
        raise RuntimeError("Test is missing Prod template properties: " + ", ".join(sorted(set(missing))))


def _validate_library(source_documents: list[dict], sections: list[dict],
                      templates: list[dict], template_sections: list[dict]) -> None:
    source_ids = {int(row["ProdSourceDocumentID"]) for row in source_documents}
    section_ids = {int(row["ProdSectionID"]) for row in sections}
    template_ids = {int(row["ProdTemplateID"]) for row in templates}
    dangling_sources = [row["ProdSectionID"] for row in sections if row.get("ProdSourceDocumentID") is not None and int(row["ProdSourceDocumentID"]) not in source_ids]
    dangling_sections = [row["ProdTemplateSectionID"] for row in template_sections if row.get("ProdDefaultSectionID") is not None and int(row["ProdDefaultSectionID"]) not in section_ids]
    dangling_templates = [row["ProdTemplateSectionID"] for row in template_sections if int(row["ProdTemplateID"]) not in template_ids]
    if dangling_sources or dangling_sections or dangling_templates:
        raise RuntimeError(
            "Prod library has references outside the reusable-library scope: "
            f"sections->sources={dangling_sources}, template slots->sections={dangling_sections}, "
            f"template slots->templates={dangling_templates}."
        )


def _insert_returning_id(cursor: Any, sql: str, params: tuple, id_column: str) -> int:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"Insert into {id_column} returned no identity value.")
    return int(row[0])


def _archive_test_library(cursor: Any) -> None:
    cursor.execute("UPDATE dbo.LeaseTemplateSections SET IsActive = 0")
    cursor.execute("UPDATE dbo.LeaseTemplates SET IsActive = 0")
    cursor.execute("UPDATE dbo.LeaseDocumentSections SET IsActive = 0 WHERE LeaseID IS NULL AND IsReusable = 1")
    cursor.execute("""
        UPDATE sd SET IsActive = 0
        FROM dbo.LeaseSourceDocuments AS sd
        WHERE sd.LeaseID IS NULL
          AND (sd.IsTemplate = 1 OR EXISTS (
              SELECT 1 FROM dbo.LeaseDocumentSections AS ds
              WHERE ds.LeaseSourceDocumentID = sd.LeaseSourceDocumentID
                AND ds.LeaseID IS NULL AND ds.IsReusable = 1
          ))
    """)


def _copy_library(cursor: Any, source_documents: list[dict], sections: list[dict],
                  templates: list[dict], template_sections: list[dict]) -> tuple[int, int, int, int]:
    source_map: dict[int, int] = {}
    for row in source_documents:
        source_map[int(row["ProdSourceDocumentID"])] = _insert_returning_id(cursor, """
            INSERT INTO dbo.LeaseSourceDocuments (
                LeaseID, OriginalFileName, StoredFilePath, PageCount, DocumentStatus, UploadedOn,
                Notes, PropertyID, TemplateName, DocumentScope, DocumentCategory, TemplateVersion,
                StorageRoot, RelativePath, SourceFileType, IsTemplate, IsActive
            ) OUTPUT INSERTED.LeaseSourceDocumentID
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (None, row["OriginalFileName"], row["StoredFilePath"], row["PageCount"], row["DocumentStatus"], row["UploadedOn"], row["Notes"], row["TestPropertyID"], row["TemplateName"], row["DocumentScope"], row["DocumentCategory"], row["TemplateVersion"], row["StorageRoot"], row["RelativePath"], row["SourceFileType"], row["IsTemplate"], row["IsActive"]), "LeaseSourceDocumentID")

    section_map: dict[int, int] = {}
    for row in sections:
        source_id = row.get("ProdSourceDocumentID")
        section_map[int(row["ProdSectionID"])] = _insert_returning_id(cursor, """
            INSERT INTO dbo.LeaseDocumentSections (
                LeaseSourceDocumentID, LeaseID, SectionType, SectionName, ExhibitCode, StartPage,
                EndPage, StoredFilePath, SortOrder, IsReusable, CreatedOn, Notes, StorageRoot,
                RelativePath, IsActive, Content, ClauseTag, ArticleNumber, DisplayLabel, UpdatedOn
            ) OUTPUT INSERTED.LeaseDocumentSectionID
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (source_map.get(int(source_id)) if source_id is not None else None, None, row["SectionType"], row["SectionName"], row["ExhibitCode"], row["StartPage"], row["EndPage"], row["StoredFilePath"], row["SortOrder"], row["IsReusable"], row["CreatedOn"], row["Notes"], row["StorageRoot"], row["RelativePath"], row["IsActive"], row["Content"], row["ClauseTag"], row["ArticleNumber"], row["DisplayLabel"], row["UpdatedOn"]), "LeaseDocumentSectionID")

    template_map: dict[int, int] = {}
    for row in templates:
        template_map[int(row["ProdTemplateID"])] = _insert_returning_id(cursor, """
            INSERT INTO dbo.LeaseTemplates (
                TemplateName, PropertyID, Description, IsActive, CreatedOn, UpdatedOn, TemplateVersion
            ) OUTPUT INSERTED.LeaseTemplateID
              VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (row["TemplateName"], row["TestPropertyID"], row["Description"], row["IsActive"], row["CreatedOn"], row["UpdatedOn"], row["TemplateVersion"]), "LeaseTemplateID")

    for row in template_sections:
        default_id = row.get("ProdDefaultSectionID")
        _insert_returning_id(cursor, """
            INSERT INTO dbo.LeaseTemplateSections (
                LeaseTemplateID, SortOrder, SectionLabel, DefaultSectionID, IsOptional,
                IsRequired, SectionType, IsActive
            ) OUTPUT INSERTED.LeaseTemplateSectionID
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (template_map[int(row["ProdTemplateID"])], row["SortOrder"], row["SectionLabel"], section_map.get(int(default_id)) if default_id is not None else None, row["IsOptional"], row["IsRequired"], row["SectionType"], row["IsActive"]), "LeaseTemplateSectionID")

    return len(source_map), len(section_map), len(template_map), len(template_sections)


def main(commit: bool) -> None:
    with get_conn(PROD_DB_NAME) as prod_connection, get_conn(TEST_DB_NAME) as test_connection:
        prod_cursor, test_cursor = prod_connection.cursor(), test_connection.cursor()
        _require_database(prod_cursor, PROD_DB_NAME)
        _require_database(test_cursor, TEST_DB_NAME)
        source_documents, sections, templates, template_sections = _load_prod_library(prod_cursor)
        _map_properties(source_documents + templates, _test_property_map(test_cursor))
        _validate_library(source_documents, sections, templates, template_sections)
        counts = Counter({"source documents": len(source_documents), "reusable sections": len(sections), "templates": len(templates), "template sections": len(template_sections)})
        print("Production library staged: " + ", ".join(f"{value} {name}" for name, value in counts.items()))
        if not commit:
            print("DRY RUN -- no Test rows were changed. Repeat with --commit to sync the library.")
            return
        try:
            _archive_test_library(test_cursor)
            copied = _copy_library(test_cursor, source_documents, sections, templates, template_sections)
            test_connection.commit()
        except Exception:
            test_connection.rollback()
            raise
    print(f"Sync completed: {copied[0]} source documents, {copied[1]} reusable sections, {copied[2]} templates, and {copied[3]} template sections.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Archive Test's library and copy Prod's library.")
    main(parser.parse_args().commit)
