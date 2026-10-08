"""
Lease Templates admin page.

MVP scope:
  1. Upload a source PDF into an admin-level template library.
  2. Select the import path before saving the source PDF.
  3. Split the source PDF into reusable base lease, exhibit, and addendum pieces.

This version stores files on disk and keeps metadata in SQL Server.
"""

from __future__ import annotations

import datetime
import os
from typing import Optional

import reflex as rx

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.pages.lease_documents_pdf import (
    DEFAULT_DOCUMENT_ROOT,
    copy_existing_pdf,
    page_count,
    relative_to_root,
    save_uploaded_pdf,
    slugify,
    split_pdf_pages,
    template_folder,
)

DOCUMENT_CATEGORIES = ["Base Lease", "Exhibit", "Addendum", "Rules", "Guaranty", "Other"]
PIECE_TYPES = ["Base Lease", "Exhibit", "Addendum", "Rules", "Guaranty", "Other"]
PROPERTY_GENERAL = "General / All Properties"


class SourceDocumentRow(rx.Base):
    source_document_id: int = 0
    template_name: str = ""
    property_name: str = ""
    category: str = ""
    version: str = ""
    file_name: str = ""
    page_count: str = ""
    saved_path: str = ""
    uploaded_on: str = ""
    active: str = ""


class PieceRow(rx.Base):
    piece_id: int = 0
    piece_type: str = ""
    piece_name: str = ""
    exhibit_code: str = ""
    pages: str = ""
    sort_order: int = 0
    reusable: str = ""
    active: str = ""


class LeaseDocumentState(AppState):
    property_names: list[str] = [PROPERTY_GENERAL]
    property_ids: list[int] = [0]

    source_documents: list[SourceDocumentRow] = []
    selected_source_document_id: int = 0
    selected_source_page_count: int = 0
    selected_source_path: str = ""

    pieces: list[PieceRow] = []

    # Step 1. Template context and source file upload.
    f_template_name: str = ""
    f_property: str = PROPERTY_GENERAL
    f_document_category: str = "Base Lease"
    f_template_version: str = "1.0"
    f_notes: str = ""
    f_is_active: bool = True

    # Step 2. Import path.
    storage_root: str = DEFAULT_DOCUMENT_ROOT
    local_pdf_path: str = ""

    # Step 3. Split piece form.
    p_piece_type: str = "Base Lease"
    p_piece_name: str = ""
    p_exhibit_code: str = ""
    p_start_page: str = "1"
    p_end_page: str = "1"
    p_sort_order: str = "10"
    p_is_reusable: bool = True
    p_is_active: bool = True

    form_error: str = ""
    form_success: str = ""

    @rx.var
    def destination_preview(self) -> str:
        return template_folder(self.storage_root, self.f_property, self.f_document_category)

    @rx.var
    def selected_source_summary(self) -> str:
        if not self.selected_source_document_id:
            return "No source document selected."
        return f"Source #{self.selected_source_document_id} · {self.selected_source_page_count} pages"

    @rx.var
    def has_source_document(self) -> bool:
        return self.selected_source_document_id > 0

    def on_load(self):
        self._ensure_schema()
        self._load_properties()
        self._load_source_documents()

    def reload_on_db_change(self):
        self.source_documents = []
        self.pieces = []
        self.selected_source_document_id = 0
        self.selected_source_page_count = 0
        self.selected_source_path = ""
        self._ensure_schema()
        self._load_properties()
        self._load_source_documents()

    def _ensure_schema(self):
        statements = [
            """
            IF OBJECT_ID('dbo.LeaseSourceDocuments', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseSourceDocuments (
                    LeaseSourceDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseID INT NULL,
                    PropertyID INT NULL,
                    TemplateName NVARCHAR(255) NULL,
                    DocumentScope NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentScope DEFAULT ('AdminTemplate'),
                    DocumentCategory NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentCategory DEFAULT ('Base Lease'),
                    TemplateVersion NVARCHAR(50) NULL,
                    StorageRoot NVARCHAR(1000) NULL,
                    RelativePath NVARCHAR(1000) NULL,
                    SourceFileType NVARCHAR(20) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_SourceFileType DEFAULT ('PDF'),
                    IsTemplate BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsTemplate DEFAULT (1),
                    IsActive BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsActive DEFAULT (1),
                    OriginalFileName NVARCHAR(255) NOT NULL,
                    StoredFilePath NVARCHAR(1000) NOT NULL,
                    PageCount INT NULL,
                    DocumentStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_Status DEFAULT ('Uploaded'),
                    UploadedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseSourceDocuments_UploadedOn DEFAULT (SYSDATETIME()),
                    Notes NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeaseDocumentPieces', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseDocumentPieces (
                    LeaseDocumentPieceID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseSourceDocumentID INT NOT NULL,
                    LeaseID INT NULL,
                    PieceType NVARCHAR(50) NOT NULL,
                    PieceName NVARCHAR(255) NOT NULL,
                    ExhibitCode NVARCHAR(50) NULL,
                    StartPage INT NOT NULL,
                    EndPage INT NOT NULL,
                    StoredFilePath NVARCHAR(1000) NOT NULL,
                    StorageRoot NVARCHAR(1000) NULL,
                    RelativePath NVARCHAR(1000) NULL,
                    SortOrder INT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_SortOrder DEFAULT (0),
                    IsReusable BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsReusable DEFAULT (1),
                    IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsActive DEFAULT (1),
                    CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseDocumentPieces_CreatedOn DEFAULT (SYSDATETIME()),
                    Notes NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeaseGeneratedDocuments', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseGeneratedDocuments (
                    LeaseGeneratedDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseID INT NULL,
                    GeneratedFileName NVARCHAR(255) NOT NULL,
                    StoredFilePath NVARCHAR(1000) NOT NULL,
                    GeneratedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseGeneratedDocuments_GeneratedOn DEFAULT (SYSDATETIME()),
                    PackageNotes NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'PropertyID') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD PropertyID INT NULL;
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'TemplateName') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD TemplateName NVARCHAR(255) NULL;
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'DocumentScope') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD DocumentScope NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentScope2 DEFAULT ('AdminTemplate');
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'DocumentCategory') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD DocumentCategory NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentCategory2 DEFAULT ('Base Lease');
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'TemplateVersion') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD TemplateVersion NVARCHAR(50) NULL;
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'StorageRoot') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD StorageRoot NVARCHAR(1000) NULL;
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'RelativePath') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD RelativePath NVARCHAR(1000) NULL;
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'SourceFileType') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD SourceFileType NVARCHAR(20) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_SourceFileType2 DEFAULT ('PDF');
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'IsTemplate') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD IsTemplate BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsTemplate2 DEFAULT (1);
            IF COL_LENGTH('dbo.LeaseSourceDocuments', 'IsActive') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsActive2 DEFAULT (1);
            """,
            """
            IF COL_LENGTH('dbo.LeaseDocumentPieces', 'StorageRoot') IS NULL ALTER TABLE dbo.LeaseDocumentPieces ADD StorageRoot NVARCHAR(1000) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentPieces', 'RelativePath') IS NULL ALTER TABLE dbo.LeaseDocumentPieces ADD RelativePath NVARCHAR(1000) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentPieces', 'IsActive') IS NULL ALTER TABLE dbo.LeaseDocumentPieces ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsActive2 DEFAULT (1);
            """,
        ]
        for sql in statements:
            run_exec(sql, db=self.db)
        try:
            run_exec("ALTER TABLE dbo.LeaseSourceDocuments ALTER COLUMN LeaseID INT NULL", db=self.db)
        except Exception:
            pass
        try:
            run_exec("ALTER TABLE dbo.LeaseDocumentPieces ALTER COLUMN LeaseID INT NULL", db=self.db)
        except Exception:
            pass

    def _fmt_date(self, val) -> str:
        if val is None:
            return ""
        if isinstance(val, datetime.datetime):
            return val.strftime("%m/%d/%Y %H:%M")
        if isinstance(val, datetime.date):
            return val.strftime("%m/%d/%Y")
        return str(val)

    def _load_properties(self):
        rows = run_query("SELECT PropertyID, PropertyName FROM Properties ORDER BY PropertyName", db=self.db)
        self.property_names = [PROPERTY_GENERAL] + [str(r["PropertyName"]) for r in rows]
        self.property_ids = [0] + [int(r["PropertyID"]) for r in rows]
        if self.f_property not in self.property_names:
            self.f_property = PROPERTY_GENERAL

    def _selected_property_id(self) -> Optional[int]:
        if self.f_property in self.property_names:
            pid = self.property_ids[self.property_names.index(self.f_property)]
            return int(pid) if pid else None
        return None

    def _property_name_for_id(self, property_id) -> str:
        try:
            pid = int(property_id or 0)
        except Exception:
            return PROPERTY_GENERAL
        if pid in self.property_ids:
            return self.property_names[self.property_ids.index(pid)]
        return PROPERTY_GENERAL

    def _load_source_documents(self):
        rows = run_query(
            "SELECT s.LeaseSourceDocumentID, s.TemplateName, s.PropertyID, s.DocumentCategory, "
            "s.TemplateVersion, s.OriginalFileName, s.PageCount, s.StorageRoot, s.RelativePath, "
            "s.StoredFilePath, s.UploadedOn, s.IsActive "
            "FROM LeaseSourceDocuments s "
            "WHERE ISNULL(s.DocumentScope, 'AdminTemplate') = 'AdminTemplate' "
            "ORDER BY s.UploadedOn DESC, s.LeaseSourceDocumentID DESC",
            db=self.db,
        )
        self.source_documents = [
            SourceDocumentRow(
                source_document_id=int(r["LeaseSourceDocumentID"]),
                template_name=str(r.get("TemplateName") or ""),
                property_name=self._property_name_for_id(r.get("PropertyID")),
                category=str(r.get("DocumentCategory") or ""),
                version=str(r.get("TemplateVersion") or ""),
                file_name=str(r.get("OriginalFileName") or ""),
                page_count=str(r.get("PageCount") or ""),
                saved_path=str(r.get("RelativePath") or r.get("StoredFilePath") or ""),
                uploaded_on=self._fmt_date(r.get("UploadedOn")),
                active="Yes" if r.get("IsActive") else "No",
            )
            for r in rows
        ]
        if self.source_documents and not self.selected_source_document_id:
            self.select_source_document(self.source_documents[0].source_document_id)
        elif self.selected_source_document_id:
            self._load_pieces()

    def select_source_document(self, source_document_id: int):
        self.selected_source_document_id = int(source_document_id)
        self.form_error = ""
        self.form_success = ""
        rows = run_query(
            "SELECT TemplateName, PropertyID, DocumentCategory, TemplateVersion, StorageRoot, "
            "StoredFilePath, PageCount, Notes, IsActive FROM LeaseSourceDocuments "
            "WHERE LeaseSourceDocumentID = ?",
            (self.selected_source_document_id,), db=self.db,
        )
        if not rows:
            return
        r = rows[0]
        self.f_template_name = str(r.get("TemplateName") or "")
        self.f_property = self._property_name_for_id(r.get("PropertyID"))
        self.f_document_category = str(r.get("DocumentCategory") or "Base Lease")
        self.f_template_version = str(r.get("TemplateVersion") or "1.0")
        self.storage_root = str(r.get("StorageRoot") or self.storage_root or DEFAULT_DOCUMENT_ROOT)
        self.f_notes = str(r.get("Notes") or "")
        self.f_is_active = bool(r.get("IsActive"))
        self.selected_source_path = str(r.get("StoredFilePath") or "")
        try:
            self.selected_source_page_count = int(r.get("PageCount") or 0)
        except Exception:
            self.selected_source_page_count = 0
        self.p_start_page = "1"
        self.p_end_page = str(max(self.selected_source_page_count, 1))
        self._load_pieces()

    def _load_pieces(self):
        if not self.selected_source_document_id:
            self.pieces = []
            return
        rows = run_query(
            "SELECT LeaseDocumentPieceID, PieceType, PieceName, ExhibitCode, StartPage, EndPage, "
            "SortOrder, IsReusable, IsActive FROM LeaseDocumentPieces "
            "WHERE LeaseSourceDocumentID = ? ORDER BY SortOrder, LeaseDocumentPieceID",
            (self.selected_source_document_id,), db=self.db,
        )
        self.pieces = [
            PieceRow(
                piece_id=int(r["LeaseDocumentPieceID"]),
                piece_type=str(r.get("PieceType") or ""),
                piece_name=str(r.get("PieceName") or ""),
                exhibit_code=str(r.get("ExhibitCode") or ""),
                pages=f"{int(r.get('StartPage') or 0)}-{int(r.get('EndPage') or 0)}",
                sort_order=int(r.get("SortOrder") or 0),
                reusable="Yes" if r.get("IsReusable") else "No",
                active="Yes" if r.get("IsActive") else "No",
            )
            for r in rows
        ]

    def _next_exhibit_code(self) -> str:
        rows = run_query(
            "SELECT ExhibitCode FROM LeaseDocumentPieces WHERE LeaseSourceDocumentID = ? AND PieceType = 'Exhibit'",
            (self.selected_source_document_id,), db=self.db,
        ) if self.selected_source_document_id else []
        used = {str(r.get("ExhibitCode") or "").replace("Exhibit", "").strip().upper() for r in rows}
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if letter not in used:
                return letter
        return ""

    def _next_sort_order(self) -> int:
        rows = run_query(
            "SELECT ISNULL(MAX(SortOrder), 0) AS MaxSort FROM LeaseDocumentPieces WHERE LeaseSourceDocumentID = ?",
            (self.selected_source_document_id,), db=self.db,
        ) if self.selected_source_document_id else []
        try:
            return int(rows[0].get("MaxSort") or 0) + 10
        except Exception:
            return 10

    async def handle_upload(self, files: list[rx.UploadFile]):
        self.form_error = ""
        self.form_success = ""
        if not self.f_template_name.strip():
            self.form_error = "Template name is required before upload."
            return
        if not files:
            self.form_error = "Choose a PDF file to upload."
            return
        file = files[0]
        if not str(file.filename or "").lower().endswith(".pdf"):
            self.form_error = "PDF upload is supported first. Word upload will come later."
            return
        try:
            data = await file.read()
            stored_path = save_uploaded_pdf(
                data,
                file.filename,
                self.storage_root,
                self.f_property,
                self.f_document_category,
                self.f_template_name,
            )
            pc = page_count(stored_path)
            root = self.storage_root.strip() or DEFAULT_DOCUMENT_ROOT
            rel = relative_to_root(stored_path, root)
            run_exec(
                "INSERT INTO LeaseSourceDocuments "
                "(LeaseID, PropertyID, TemplateName, DocumentScope, DocumentCategory, TemplateVersion, "
                "StorageRoot, RelativePath, SourceFileType, IsTemplate, IsActive, OriginalFileName, "
                "StoredFilePath, PageCount, DocumentStatus, Notes) "
                "VALUES (NULL, ?, ?, 'AdminTemplate', ?, ?, ?, ?, 'PDF', 1, ?, ?, ?, ?, 'Uploaded', ?)",
                (
                    self._selected_property_id(), self.f_template_name.strip(), self.f_document_category,
                    self.f_template_version.strip(), root, rel, 1 if self.f_is_active else 0,
                    file.filename, stored_path, pc, self.f_notes,
                ), db=self.db,
            )
            new_id = run_query(
                "SELECT TOP 1 LeaseSourceDocumentID FROM LeaseSourceDocuments ORDER BY LeaseSourceDocumentID DESC",
                db=self.db,
            )[0]["LeaseSourceDocumentID"]
            self.selected_source_document_id = int(new_id)
            self.selected_source_page_count = int(pc)
            self.selected_source_path = stored_path
            self.p_start_page = "1"
            self.p_end_page = str(pc)
            self.form_success = f"Uploaded source PDF with {pc} pages."
            self._load_source_documents()
            self._load_pieces()
        except Exception as ex:
            self.form_error = f"Upload failed: {ex}"

    def import_local_pdf_for_testing(self):
        self.form_error = ""
        self.form_success = ""
        if not self.f_template_name.strip():
            self.form_error = "Template name is required before import."
            return
        if not self.local_pdf_path.strip() or not os.path.isfile(self.local_pdf_path.strip()):
            self.form_error = "Enter a valid local PDF path."
            return
        try:
            source_path = self.local_pdf_path.strip()
            stored_path = copy_existing_pdf(
                source_path,
                os.path.basename(source_path),
                self.storage_root,
                self.f_property,
                self.f_document_category,
                self.f_template_name,
            )
            pc = page_count(stored_path)
            root = self.storage_root.strip() or DEFAULT_DOCUMENT_ROOT
            rel = relative_to_root(stored_path, root)
            run_exec(
                "INSERT INTO LeaseSourceDocuments "
                "(LeaseID, PropertyID, TemplateName, DocumentScope, DocumentCategory, TemplateVersion, "
                "StorageRoot, RelativePath, SourceFileType, IsTemplate, IsActive, OriginalFileName, "
                "StoredFilePath, PageCount, DocumentStatus, Notes) "
                "VALUES (NULL, ?, ?, 'AdminTemplate', ?, ?, ?, ?, 'PDF', 1, ?, ?, ?, ?, 'Uploaded', ?)",
                (
                    self._selected_property_id(), self.f_template_name.strip(), self.f_document_category,
                    self.f_template_version.strip(), root, rel, 1 if self.f_is_active else 0,
                    os.path.basename(source_path), stored_path, pc, self.f_notes,
                ), db=self.db,
            )
            new_id = run_query(
                "SELECT TOP 1 LeaseSourceDocumentID FROM LeaseSourceDocuments ORDER BY LeaseSourceDocumentID DESC",
                db=self.db,
            )[0]["LeaseSourceDocumentID"]
            self.selected_source_document_id = int(new_id)
            self.selected_source_page_count = int(pc)
            self.selected_source_path = stored_path
            self.local_pdf_path = ""
            self.p_start_page = "1"
            self.p_end_page = str(pc)
            self.form_success = f"Imported source PDF with {pc} pages."
            self._load_source_documents()
            self._load_pieces()
        except Exception as ex:
            self.form_error = f"Import failed: {ex}"

    def _validate_piece_range(self, start: int, end: int) -> bool:
        if start < 1 or end < start or end > self.selected_source_page_count:
            self.form_error = f"Page range must be between 1 and {self.selected_source_page_count}."
            return False
        rows = run_query(
            "SELECT StartPage, EndPage, PieceName FROM LeaseDocumentPieces WHERE LeaseSourceDocumentID = ?",
            (self.selected_source_document_id,), db=self.db,
        )
        for r in rows:
            existing_start = int(r.get("StartPage") or 0)
            existing_end = int(r.get("EndPage") or 0)
            if start <= existing_end and end >= existing_start:
                self.form_error = f"Page range overlaps existing piece: {r.get('PieceName')}."
                return False
        return True

    def create_piece(self):
        self.form_error = ""
        self.form_success = ""
        if not self.selected_source_document_id:
            self.form_error = "Upload or select a source PDF first."
            return
        if not self.p_piece_name.strip():
            self.form_error = "Piece name is required."
            return
        try:
            start = int(self.p_start_page)
            end = int(self.p_end_page)
            sort_order = int(self.p_sort_order or 0)
        except ValueError:
            self.form_error = "Start page, end page, and sort order must be numbers."
            return
        if not self._validate_piece_range(start, end):
            return
        code = self.p_exhibit_code.strip()
        if self.p_piece_type == "Exhibit" and code:
            dup = run_query(
                "SELECT TOP 1 LeaseDocumentPieceID FROM LeaseDocumentPieces "
                "WHERE LeaseSourceDocumentID = ? AND PieceType = 'Exhibit' AND UPPER(ISNULL(ExhibitCode,'')) = UPPER(?)",
                (self.selected_source_document_id, code), db=self.db,
            )
            if dup:
                self.form_error = "This exhibit code already exists for the selected source document."
                return
        try:
            if not code and self.p_piece_type == "Exhibit":
                code = self._next_exhibit_code()
            output_name = (
                f"source_{self.selected_source_document_id}_"
                f"{slugify(code) + '_' if code else ''}"
                f"{slugify(self.p_piece_name)}_p{start}_{end}.pdf"
            )
            piece_path = split_pdf_pages(
                self.selected_source_path,
                start,
                end,
                output_name,
                self.storage_root,
                self.f_property,
                self.f_document_category,
            )
            root = self.storage_root.strip() or DEFAULT_DOCUMENT_ROOT
            rel = relative_to_root(piece_path, root)
            run_exec(
                "INSERT INTO LeaseDocumentPieces "
                "(LeaseSourceDocumentID, LeaseID, PieceType, PieceName, ExhibitCode, StartPage, EndPage, "
                "StoredFilePath, StorageRoot, RelativePath, SortOrder, IsReusable, IsActive) "
                "VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.selected_source_document_id,
                    self.p_piece_type,
                    self.p_piece_name.strip(),
                    code or None,
                    start,
                    end,
                    piece_path,
                    root,
                    rel,
                    sort_order,
                    1 if self.p_is_reusable else 0,
                    1 if self.p_is_active else 0,
                ), db=self.db,
            )
            self.form_success = "Piece saved."
            next_page = end + 1
            self.p_start_page = str(next_page) if next_page <= self.selected_source_page_count else str(end)
            self.p_end_page = str(next_page) if next_page <= self.selected_source_page_count else str(end)
            self.p_sort_order = str(self._next_sort_order())
            self.p_piece_name = ""
            self.p_exhibit_code = ""
            self._load_pieces()
        except Exception as ex:
            self.form_error = f"Could not create piece: {ex}"

    def set_f_template_name(self, v: str): self.f_template_name = v
    def set_f_property(self, v: str): self.f_property = v
    def set_f_document_category(self, v: str): self.f_document_category = v
    def set_f_template_version(self, v: str): self.f_template_version = v
    def set_f_notes(self, v: str): self.f_notes = v
    def set_f_is_active(self, v: bool): self.f_is_active = v
    def set_storage_root(self, v: str): self.storage_root = v
    def set_local_pdf_path(self, v: str): self.local_pdf_path = v
    def set_p_piece_name(self, v: str): self.p_piece_name = v
    def set_p_exhibit_code(self, v: str): self.p_exhibit_code = v
    def set_p_start_page(self, v: str): self.p_start_page = v
    def set_p_end_page(self, v: str): self.p_end_page = v
    def set_p_sort_order(self, v: str): self.p_sort_order = v
    def set_p_is_reusable(self, v: bool): self.p_is_reusable = v
    def set_p_is_active(self, v: bool): self.p_is_active = v

    def set_p_piece_type(self, v: str):
        self.p_piece_type = v
        if v == "Exhibit" and not self.p_exhibit_code.strip():
            self.p_exhibit_code = self._next_exhibit_code()
        if not self.p_piece_name.strip():
            if v == "Base Lease":
                self.p_piece_name = "Base Lease"
            elif v == "Exhibit" and self.p_exhibit_code:
                self.p_piece_name = f"Exhibit {self.p_exhibit_code}"


def source_document_row(row: SourceDocumentRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.template_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.property_name, size="2")),
        rx.table.cell(rx.text(row.category, size="2")),
        rx.table.cell(rx.text(row.version, size="2")),
        rx.table.cell(rx.text(row.page_count, size="2")),
        rx.table.cell(rx.text(row.uploaded_on, size="2")),
        rx.table.cell(rx.badge(row.active, color_scheme="green", variant="soft")),
        rx.table.cell(
            rx.button(
                "Use",
                size="1",
                variant="soft",
                color_scheme="blue",
                on_click=LeaseDocumentState.select_source_document(row.source_document_id),
            )
        ),
        style=rx.cond(
            LeaseDocumentState.selected_source_document_id == row.source_document_id,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
    )


def piece_row(row: PieceRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.sort_order, size="2")),
        rx.table.cell(rx.text(row.piece_type, size="2")),
        rx.table.cell(rx.text(row.exhibit_code, size="2")),
        rx.table.cell(rx.text(row.piece_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.pages, size="2")),
        rx.table.cell(rx.text(row.reusable, size="2")),
        rx.table.cell(rx.text(row.active, size="2")),
    )


def lease_documents_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Lease Templates", size="6", color=BRAND_DARK),
        rx.text(
            "Admin library for base lease templates, core exhibits, and addendums. Tenant packages come later from these saved pieces.",
            size="2",
            color="#555",
        ),

        rx.cond(
            LeaseDocumentState.form_error != "",
            rx.callout.root(rx.callout.text(LeaseDocumentState.form_error), color_scheme="red", width="100%"),
        ),
        rx.cond(
            LeaseDocumentState.form_success != "",
            rx.callout.root(rx.callout.text(LeaseDocumentState.form_success), color_scheme="green", width="100%"),
        ),

        rx.card(
            rx.vstack(
                rx.text("1. Upload source PDF", size="4", weight="bold", color=BRAND_DARK),
                rx.grid(
                    rx.vstack(rx.text("Template name", size="1", color="#666"), rx.input(value=LeaseDocumentState.f_template_name, on_change=LeaseDocumentState.set_f_template_name, placeholder="Broadway Standard Lease", width="100%"), spacing="1"),
                    rx.vstack(rx.text("Property", size="1", color="#666"), rx.select(LeaseDocumentState.property_names, value=LeaseDocumentState.f_property, on_change=LeaseDocumentState.set_f_property, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Document category", size="1", color="#666"), rx.select(DOCUMENT_CATEGORIES, value=LeaseDocumentState.f_document_category, on_change=LeaseDocumentState.set_f_document_category, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Version", size="1", color="#666"), rx.input(value=LeaseDocumentState.f_template_version, on_change=LeaseDocumentState.set_f_template_version, width="100%"), spacing="1"),
                    columns="4",
                    spacing="3",
                    width="100%",
                ),
                rx.vstack(rx.text("Notes", size="1", color="#666"), rx.text_area(value=LeaseDocumentState.f_notes, on_change=LeaseDocumentState.set_f_notes, width="100%"), spacing="1", width="100%"),
                rx.checkbox("Active template", checked=LeaseDocumentState.f_is_active, on_change=LeaseDocumentState.set_f_is_active),
                rx.upload(
                    rx.vstack(
                        rx.button("Choose PDF", color_scheme="blue", variant="soft"),
                        rx.text("Drop a source lease PDF here or click to choose.", size="2", color="#666"),
                        spacing="2",
                        align="center",
                    ),
                    id="lease_template_pdf_upload",
                    accept={"application/pdf": [".pdf"]},
                    max_files=1,
                    border=f"1px dashed {BRAND_PRIMARY}",
                    padding="18px",
                    border_radius="8px",
                    width="100%",
                ),
                rx.button(
                    "Upload Source PDF",
                    on_click=LeaseDocumentState.handle_upload(rx.upload_files(upload_id="lease_template_pdf_upload")),
                    color_scheme="blue",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),

        rx.card(
            rx.vstack(
                rx.text("2. Select import path", size="4", weight="bold", color=BRAND_DARK),
                rx.text("This is the root folder for the admin document library. Files are stored on disk, not as SQL blobs.", size="2", color="#666"),
                rx.input(
                    value=LeaseDocumentState.storage_root,
                    on_change=LeaseDocumentState.set_storage_root,
                    placeholder=r"C:\Dell Inspirion\TenantCRM\LeaseDocuments",
                    width="100%",
                ),
                rx.box(
                    rx.text("Destination preview", size="1", color="#666"),
                    rx.text(LeaseDocumentState.destination_preview, size="2", weight="bold", color=BRAND_DARK),
                    style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                ),
                rx.divider(),
                rx.text("Optional local test import", size="2", weight="bold", color="#555"),
                rx.hstack(
                    rx.input(value=LeaseDocumentState.local_pdf_path, on_change=LeaseDocumentState.set_local_pdf_path, placeholder=r"C:\path\to\lease.pdf", width="100%"),
                    rx.button("Import Path", on_click=LeaseDocumentState.import_local_pdf_for_testing, variant="soft"),
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),

        rx.card(
            rx.vstack(
                rx.text("Source documents", size="4", weight="bold", color=BRAND_DARK),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Template"),
                            rx.table.column_header_cell("Property"),
                            rx.table.column_header_cell("Category"),
                            rx.table.column_header_cell("Version"),
                            rx.table.column_header_cell("Pages"),
                            rx.table.column_header_cell("Uploaded"),
                            rx.table.column_header_cell("Active"),
                            rx.table.column_header_cell("Action"),
                        )
                    ),
                    rx.table.body(rx.foreach(LeaseDocumentState.source_documents, source_document_row)),
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),

        rx.card(
            rx.vstack(
                rx.text("3. Split PDF into pieces", size="4", weight="bold", color=BRAND_DARK),
                rx.text(LeaseDocumentState.selected_source_summary, size="2", color="#666"),
                rx.text("Use page ranges from the selected source PDF. Example: Base Lease pages 1-10, Exhibit A page 11, Exhibit B pages 12-13.", size="2", color="#666"),
                rx.grid(
                    rx.vstack(rx.text("Piece type", size="1", color="#666"), rx.select(PIECE_TYPES, value=LeaseDocumentState.p_piece_type, on_change=LeaseDocumentState.set_p_piece_type, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Piece name", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_piece_name, on_change=LeaseDocumentState.set_p_piece_name, placeholder="Base Lease or Special Terms", width="100%"), spacing="1"),
                    rx.vstack(rx.text("Exhibit code", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_exhibit_code, on_change=LeaseDocumentState.set_p_exhibit_code, placeholder="A", width="100%"), spacing="1"),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.grid(
                    rx.vstack(rx.text("Start page", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_start_page, on_change=LeaseDocumentState.set_p_start_page, width="100%"), spacing="1"),
                    rx.vstack(rx.text("End page", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_end_page, on_change=LeaseDocumentState.set_p_end_page, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Sort order", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_sort_order, on_change=LeaseDocumentState.set_p_sort_order, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Reusable", size="1", color="#666"), rx.checkbox("Show later in tenant builder", checked=LeaseDocumentState.p_is_reusable, on_change=LeaseDocumentState.set_p_is_reusable), spacing="1"),
                    rx.vstack(rx.text("Active", size="1", color="#666"), rx.checkbox("Active", checked=LeaseDocumentState.p_is_active, on_change=LeaseDocumentState.set_p_is_active), spacing="1"),
                    columns="5",
                    spacing="3",
                    width="100%",
                ),
                rx.button("Split and Save Piece", on_click=LeaseDocumentState.create_piece, color_scheme="blue"),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Sort"),
                            rx.table.column_header_cell("Type"),
                            rx.table.column_header_cell("Code"),
                            rx.table.column_header_cell("Name"),
                            rx.table.column_header_cell("Pages"),
                            rx.table.column_header_cell("Reusable"),
                            rx.table.column_header_cell("Active"),
                        )
                    ),
                    rx.table.body(rx.foreach(LeaseDocumentState.pieces, piece_row)),
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


def lease_documents_page() -> rx.Component:
    return page_shell(lease_documents_content(), current_path="/admin/lease-templates")
