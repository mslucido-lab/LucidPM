"""
Lease Documents page.
MVP scope:
  - upload a completed lease PDF and link it to an existing LeaseID
  - split the source PDF into reusable pieces by manual page range
  - select saved pieces and merge them into a final lease PDF package

This version stores files on disk and keeps only metadata in SQL Server.
"""

from __future__ import annotations

import datetime
import os
from typing import Optional

import reflex as rx

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.pages.lease_documents_pdf import (
    save_uploaded_pdf,
    page_count,
    split_pdf_pages,
    merge_pdf_files,
    slugify,
)

PIECE_TYPES = ["Base Lease", "Exhibit", "Addendum", "Guaranty", "Rules", "Other"]


class LeaseOption(rx.Base):
    lease_id: int = 0
    label: str = ""
    tenant_name: str = ""
    property_name: str = ""
    suite_label: str = ""


class SourceDocumentRow(rx.Base):
    source_document_id: int = 0
    file_name: str = ""
    page_count: str = ""
    uploaded_on: str = ""
    status: str = ""


class PieceRow(rx.Base):
    piece_id: int = 0
    piece_type: str = ""
    piece_name: str = ""
    exhibit_code: str = ""
    pages: str = ""
    sort_order: int = 0
    reusable: str = ""
    is_selected: bool = False


class GeneratedDocumentRow(rx.Base):
    generated_id: int = 0
    file_name: str = ""
    generated_on: str = ""


class LeaseDocumentState(AppState):
    lease_options: list[LeaseOption] = []
    lease_labels: list[str] = []
    selected_lease_label: str = ""
    selected_lease_id: int = 0

    source_documents: list[SourceDocumentRow] = []
    selected_source_document_id: int = 0
    selected_source_page_count: int = 0

    pieces: list[PieceRow] = []
    generated_documents: list[GeneratedDocumentRow] = []
    selected_piece_ids: list[int] = []

    # Split form
    p_piece_type: str = "Base Lease"
    p_piece_name: str = ""
    p_exhibit_code: str = ""
    p_start_page: str = "1"
    p_end_page: str = "1"
    p_sort_order: str = "10"
    p_is_reusable: bool = False

    # Upload helper for local testing when Reflex upload is not used
    local_pdf_path: str = ""

    form_error: str = ""
    form_success: str = ""

    @rx.var
    def selected_lease_summary(self) -> str:
        if not self.selected_lease_id:
            return "No lease selected"
        return f"Lease #{self.selected_lease_id}"

    @rx.var
    def has_source_document(self) -> bool:
        return self.selected_source_document_id > 0

    @rx.var
    def generated_download_url(self) -> str:
        if not self.generated_documents:
            return "#"
        gid = self.generated_documents[0].generated_id
        return f"http://localhost:8000/api/lease-generated-pdf?generated_id={gid}&db={self.db}"

    def on_load(self):
        self._ensure_schema()
        self._load_leases()
        if self.lease_options:
            self.select_lease(self.lease_options[0].label)

    def reload_on_db_change(self):
        self.lease_options = []
        self.lease_labels = []
        self.selected_lease_label = ""
        self.selected_lease_id = 0
        self.source_documents = []
        self.pieces = []
        self.generated_documents = []
        self.selected_piece_ids = []
        self._ensure_schema()
        self._load_leases()
        if self.lease_options:
            self.select_lease(self.lease_options[0].label)

    def _ensure_schema(self):
        statements = [
            """
            IF OBJECT_ID('dbo.LeaseSourceDocuments', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseSourceDocuments (
                    LeaseSourceDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseID INT NOT NULL,
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
                    LeaseID INT NOT NULL,
                    PieceType NVARCHAR(50) NOT NULL,
                    PieceName NVARCHAR(255) NOT NULL,
                    ExhibitCode NVARCHAR(50) NULL,
                    StartPage INT NOT NULL,
                    EndPage INT NOT NULL,
                    StoredFilePath NVARCHAR(1000) NOT NULL,
                    SortOrder INT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_SortOrder DEFAULT (0),
                    IsReusable BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsReusable DEFAULT (0),
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
                    LeaseID INT NOT NULL,
                    GeneratedFileName NVARCHAR(255) NOT NULL,
                    StoredFilePath NVARCHAR(1000) NOT NULL,
                    GeneratedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseGeneratedDocuments_GeneratedOn DEFAULT (SYSDATETIME()),
                    PackageNotes NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeaseGeneratedDocumentPieces', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseGeneratedDocumentPieces (
                    LeaseGeneratedDocumentPieceID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseGeneratedDocumentID INT NOT NULL,
                    LeaseDocumentPieceID INT NOT NULL,
                    SortOrder INT NOT NULL
                )
            END
            """,
        ]
        for sql in statements:
            run_exec(sql, db=self.db)

    def _fmt_date(self, val) -> str:
        if val is None:
            return ""
        if isinstance(val, datetime.datetime):
            return val.strftime("%m/%d/%Y %H:%M")
        if isinstance(val, datetime.date):
            return val.strftime("%m/%d/%Y")
        return str(val)

    def _load_leases(self):
        rows = run_query(
            "SELECT l.LeaseID, t.TenantName, p.PropertyName, ps.SuiteLabel, "
            "l.LeaseStart, l.LeaseEnd "
            "FROM Leases l "
            "LEFT JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
            "LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID "
            "ORDER BY t.TenantName, l.LeaseStart DESC, l.LeaseID DESC",
            db=self.db,
        )
        out = []
        for r in rows:
            lease_id = int(r["LeaseID"])
            tenant = str(r.get("TenantName") or f"Lease {lease_id}").strip()
            prop = str(r.get("PropertyName") or "").strip()
            suite = str(r.get("SuiteLabel") or "").strip()
            start = self._fmt_date(r.get("LeaseStart"))
            end = self._fmt_date(r.get("LeaseEnd"))
            label_parts = [tenant]
            loc = " · ".join(x for x in [prop, suite] if x)
            if loc:
                label_parts.append(loc)
            dates = " - ".join(x for x in [start, end] if x)
            if dates:
                label_parts.append(dates)
            label_parts.append(f"ID={lease_id}")
            label = " | ".join(label_parts)
            out.append(LeaseOption(
                lease_id=lease_id,
                label=label,
                tenant_name=tenant,
                property_name=prop,
                suite_label=suite,
            ))
        self.lease_options = out
        self.lease_labels = [x.label for x in out]

    def select_lease(self, label: str):
        self.selected_lease_label = label
        self.form_error = ""
        self.form_success = ""
        self.selected_piece_ids = []
        match = next((x for x in self.lease_options if x.label == label), None)
        self.selected_lease_id = match.lease_id if match else 0
        self._load_documents_for_lease()

    def _load_documents_for_lease(self):
        if not self.selected_lease_id:
            self.source_documents = []
            self.pieces = []
            self.generated_documents = []
            return
        src_rows = run_query(
            "SELECT LeaseSourceDocumentID, OriginalFileName, PageCount, DocumentStatus, UploadedOn "
            "FROM LeaseSourceDocuments WHERE LeaseID = ? ORDER BY UploadedOn DESC, LeaseSourceDocumentID DESC",
            (self.selected_lease_id,), db=self.db,
        )
        self.source_documents = [
            SourceDocumentRow(
                source_document_id=int(r["LeaseSourceDocumentID"]),
                file_name=str(r.get("OriginalFileName") or ""),
                page_count=str(r.get("PageCount") or ""),
                uploaded_on=self._fmt_date(r.get("UploadedOn")),
                status=str(r.get("DocumentStatus") or ""),
            )
            for r in src_rows
        ]
        if self.source_documents and self.selected_source_document_id == 0:
            self.select_source_document(self.source_documents[0].source_document_id)
        else:
            self._load_pieces()
        self._load_generated_documents()

    def select_source_document(self, source_document_id: int):
        self.selected_source_document_id = int(source_document_id)
        rows = run_query(
            "SELECT PageCount FROM LeaseSourceDocuments WHERE LeaseSourceDocumentID = ?",
            (self.selected_source_document_id,), db=self.db,
        )
        try:
            self.selected_source_page_count = int(rows[0].get("PageCount") or 0)
            self.p_end_page = str(max(self.selected_source_page_count, 1))
        except Exception:
            self.selected_source_page_count = 0
        self._load_pieces()

    def _load_pieces(self):
        if not self.selected_lease_id:
            self.pieces = []
            return
        rows = run_query(
            "SELECT LeaseDocumentPieceID, PieceType, PieceName, ExhibitCode, StartPage, EndPage, "
            "SortOrder, IsReusable FROM LeaseDocumentPieces "
            "WHERE LeaseID = ? ORDER BY SortOrder, LeaseDocumentPieceID",
            (self.selected_lease_id,), db=self.db,
        )
        selected = set(self.selected_piece_ids)
        self.pieces = [
            PieceRow(
                piece_id=int(r["LeaseDocumentPieceID"]),
                piece_type=str(r.get("PieceType") or ""),
                piece_name=str(r.get("PieceName") or ""),
                exhibit_code=str(r.get("ExhibitCode") or ""),
                pages=f"{int(r.get('StartPage') or 0)}-{int(r.get('EndPage') or 0)}",
                sort_order=int(r.get("SortOrder") or 0),
                reusable="Yes" if r.get("IsReusable") else "No",
                is_selected=int(r["LeaseDocumentPieceID"]) in selected,
            )
            for r in rows
        ]

    def _load_generated_documents(self):
        rows = run_query(
            "SELECT LeaseGeneratedDocumentID, GeneratedFileName, GeneratedOn "
            "FROM LeaseGeneratedDocuments WHERE LeaseID = ? ORDER BY GeneratedOn DESC, LeaseGeneratedDocumentID DESC",
            (self.selected_lease_id,), db=self.db,
        )
        self.generated_documents = [
            GeneratedDocumentRow(
                generated_id=int(r["LeaseGeneratedDocumentID"]),
                file_name=str(r.get("GeneratedFileName") or ""),
                generated_on=self._fmt_date(r.get("GeneratedOn")),
            )
            for r in rows
        ]

    async def handle_upload(self, files: list[rx.UploadFile]):
        self.form_error = ""
        self.form_success = ""
        if not self.selected_lease_id:
            self.form_error = "Select a lease first."
            return
        if not files:
            self.form_error = "Choose a PDF file to upload."
            return
        file = files[0]
        try:
            data = await file.read()
            stored_path = save_uploaded_pdf(data, file.filename, self.selected_lease_id)
            pc = page_count(stored_path)
            run_exec(
                "INSERT INTO LeaseSourceDocuments (LeaseID, OriginalFileName, StoredFilePath, PageCount, DocumentStatus) "
                "VALUES (?, ?, ?, ?, 'Uploaded')",
                (self.selected_lease_id, file.filename, stored_path, pc), db=self.db,
            )
            new_id = run_query(
                "SELECT TOP 1 LeaseSourceDocumentID FROM LeaseSourceDocuments "
                "WHERE LeaseID = ? ORDER BY LeaseSourceDocumentID DESC",
                (self.selected_lease_id,), db=self.db,
            )[0]["LeaseSourceDocumentID"]
            self.selected_source_document_id = int(new_id)
            self.selected_source_page_count = int(pc)
            self.p_start_page = "1"
            self.p_end_page = str(pc)
            self.form_success = f"Uploaded PDF with {pc} pages."
            self._load_documents_for_lease()
        except Exception as ex:
            self.form_error = f"Upload failed: {ex}"

    def import_local_pdf_for_testing(self):
        """Optional helper for local development when testing without the Reflex upload widget."""
        self.form_error = ""
        self.form_success = ""
        if not self.selected_lease_id:
            self.form_error = "Select a lease first."
            return
        if not self.local_pdf_path.strip() or not os.path.isfile(self.local_pdf_path.strip()):
            self.form_error = "Enter a valid local PDF path."
            return
        try:
            from LucidPM_Reflex.pages.lease_documents_pdf import copy_existing_pdf
            source_path = self.local_pdf_path.strip()
            stored_path = copy_existing_pdf(source_path, os.path.basename(source_path), self.selected_lease_id)
            pc = page_count(stored_path)
            run_exec(
                "INSERT INTO LeaseSourceDocuments (LeaseID, OriginalFileName, StoredFilePath, PageCount, DocumentStatus) "
                "VALUES (?, ?, ?, ?, 'Uploaded')",
                (self.selected_lease_id, os.path.basename(source_path), stored_path, pc), db=self.db,
            )
            self.form_success = f"Imported local PDF with {pc} pages."
            self.local_pdf_path = ""
            self._load_documents_for_lease()
        except Exception as ex:
            self.form_error = f"Import failed: {ex}"

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
        try:
            src = run_query(
                "SELECT StoredFilePath, PageCount FROM LeaseSourceDocuments WHERE LeaseSourceDocumentID = ?",
                (self.selected_source_document_id,), db=self.db,
            )
            if not src:
                self.form_error = "Source document not found."
                return
            source_path = str(src[0].get("StoredFilePath") or "")
            pc = int(src[0].get("PageCount") or 0)
            if start < 1 or end < start or end > pc:
                self.form_error = f"Page range must be between 1 and {pc}."
                return
            output_name = (
                f"lease_{self.selected_lease_id}_"
                f"{slugify(self.p_exhibit_code) + '_' if self.p_exhibit_code.strip() else ''}"
                f"{slugify(self.p_piece_name)}_p{start}_{end}.pdf"
            )
            piece_path = split_pdf_pages(source_path, start, end, output_name)
            run_exec(
                "INSERT INTO LeaseDocumentPieces "
                "(LeaseSourceDocumentID, LeaseID, PieceType, PieceName, ExhibitCode, StartPage, EndPage, "
                "StoredFilePath, SortOrder, IsReusable) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.selected_source_document_id,
                    self.selected_lease_id,
                    self.p_piece_type,
                    self.p_piece_name.strip(),
                    self.p_exhibit_code.strip() or None,
                    start,
                    end,
                    piece_path,
                    sort_order,
                    1 if self.p_is_reusable else 0,
                ),
                db=self.db,
            )
            self.form_success = "Piece saved."
            self._load_pieces()
        except Exception as ex:
            self.form_error = f"Could not create piece: {ex}"

    def toggle_piece(self, piece_id: int, checked: bool):
        ids = set(self.selected_piece_ids)
        pid = int(piece_id)
        if checked:
            ids.add(pid)
        else:
            ids.discard(pid)
        self.selected_piece_ids = sorted(ids)
        self._load_pieces()

    def select_all_pieces(self):
        self.selected_piece_ids = [p.piece_id for p in self.pieces]
        self._load_pieces()

    def clear_selected_pieces(self):
        self.selected_piece_ids = []
        self._load_pieces()

    def generate_package(self):
        self.form_error = ""
        self.form_success = ""
        if not self.selected_lease_id:
            self.form_error = "Select a lease first."
            return
        if not self.selected_piece_ids:
            self.form_error = "Select at least one piece."
            return
        try:
            placeholders = ",".join("?" for _ in self.selected_piece_ids)
            rows = run_query(
                "SELECT LeaseDocumentPieceID, PieceName, StoredFilePath, SortOrder "
                f"FROM LeaseDocumentPieces WHERE LeaseDocumentPieceID IN ({placeholders}) "
                "ORDER BY SortOrder, LeaseDocumentPieceID",
                tuple(self.selected_piece_ids), db=self.db,
            )
            if not rows:
                self.form_error = "Selected pieces were not found."
                return
            paths = [str(r.get("StoredFilePath") or "") for r in rows]
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"lease_{self.selected_lease_id}_package_{stamp}.pdf"
            generated_path = merge_pdf_files(paths, output_name)
            run_exec(
                "INSERT INTO LeaseGeneratedDocuments (LeaseID, GeneratedFileName, StoredFilePath) VALUES (?, ?, ?)",
                (self.selected_lease_id, os.path.basename(generated_path), generated_path), db=self.db,
            )
            gid = int(run_query(
                "SELECT TOP 1 LeaseGeneratedDocumentID FROM LeaseGeneratedDocuments "
                "WHERE LeaseID = ? ORDER BY LeaseGeneratedDocumentID DESC",
                (self.selected_lease_id,), db=self.db,
            )[0]["LeaseGeneratedDocumentID"])
            for idx, r in enumerate(rows, start=1):
                run_exec(
                    "INSERT INTO LeaseGeneratedDocumentPieces "
                    "(LeaseGeneratedDocumentID, LeaseDocumentPieceID, SortOrder) VALUES (?, ?, ?)",
                    (gid, int(r["LeaseDocumentPieceID"]), idx), db=self.db,
                )
            self.form_success = "Lease PDF package generated."
            self._load_generated_documents()
        except Exception as ex:
            self.form_error = f"Could not generate package: {ex}"

    def set_p_piece_type(self, v: str): self.p_piece_type = v
    def set_p_piece_name(self, v: str): self.p_piece_name = v
    def set_p_exhibit_code(self, v: str): self.p_exhibit_code = v
    def set_p_start_page(self, v: str): self.p_start_page = v
    def set_p_end_page(self, v: str): self.p_end_page = v
    def set_p_sort_order(self, v: str): self.p_sort_order = v
    def set_p_is_reusable(self, v: bool): self.p_is_reusable = v
    def set_local_pdf_path(self, v: str): self.local_pdf_path = v


def source_document_row(row: SourceDocumentRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.file_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.page_count, size="2")),
        rx.table.cell(rx.text(row.uploaded_on, size="2")),
        rx.table.cell(rx.badge(row.status, color_scheme="blue", variant="soft")),
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
        rx.table.cell(
            rx.checkbox(
                checked=row.is_selected,
                on_change=lambda checked: LeaseDocumentState.toggle_piece(row.piece_id, checked),
            )
        ),
        rx.table.cell(rx.text(row.sort_order, size="2")),
        rx.table.cell(rx.text(row.piece_type, size="2")),
        rx.table.cell(rx.text(row.exhibit_code, size="2")),
        rx.table.cell(rx.text(row.piece_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.pages, size="2")),
        rx.table.cell(rx.text(row.reusable, size="2")),
    )


def generated_row(row: GeneratedDocumentRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.file_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.generated_on, size="2")),
        rx.table.cell(
            rx.link(
                rx.button("Download", size="1", variant="soft", color_scheme="blue"),
                href=f"http://localhost:8000/api/lease-generated-pdf?generated_id={row.generated_id}",
                is_external=True,
            )
        ),
    )


def lease_documents_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Lease Documents", size="6", color=BRAND_DARK),
        rx.text("Upload an executed lease PDF, split it into pieces, and assemble a final PDF package.", size="2", color="#555"),

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
                rx.text("1. Select lease", size="4", weight="bold", color=BRAND_DARK),
                rx.select(
                    LeaseDocumentState.lease_labels,
                    value=LeaseDocumentState.selected_lease_label,
                    on_change=LeaseDocumentState.select_lease,
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),

        rx.card(
            rx.vstack(
                rx.text("2. Upload source PDF", size="4", weight="bold", color=BRAND_DARK),
                rx.upload(
                    rx.vstack(
                        rx.button("Choose PDF", color_scheme="blue", variant="soft"),
                        rx.text("Drop one lease PDF here or click to choose.", size="2", color="#666"),
                        spacing="2",
                        align="center",
                    ),
                    id="lease_pdf_upload",
                    accept={"application/pdf": [".pdf"]},
                    max_files=1,
                    border=f"1px dashed {BRAND_PRIMARY}",
                    padding="18px",
                    border_radius="8px",
                    width="100%",
                ),
                rx.button(
                    "Upload PDF",
                    on_click=LeaseDocumentState.handle_upload(rx.upload_files(upload_id="lease_pdf_upload")),
                    color_scheme="blue",
                ),
                rx.divider(),
                rx.text("Optional local test import", size="2", weight="bold", color="#555"),
                rx.hstack(
                    rx.input(
                        value=LeaseDocumentState.local_pdf_path,
                        on_change=LeaseDocumentState.set_local_pdf_path,
                        placeholder=r"C:\path\to\lease.pdf",
                        width="100%",
                    ),
                    rx.button("Import Path", on_click=LeaseDocumentState.import_local_pdf_for_testing, variant="soft"),
                    width="100%",
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("File"),
                            rx.table.column_header_cell("Pages"),
                            rx.table.column_header_cell("Uploaded"),
                            rx.table.column_header_cell("Status"),
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
                rx.text("Use page ranges from the uploaded PDF. Example: Base Lease pages 1-10, Exhibit A pages 11-12.", size="2", color="#666"),
                rx.grid(
                    rx.vstack(rx.text("Piece type", size="1", color="#666"), rx.select(PIECE_TYPES, value=LeaseDocumentState.p_piece_type, on_change=LeaseDocumentState.set_p_piece_type, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Piece name", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_piece_name, on_change=LeaseDocumentState.set_p_piece_name, placeholder="Base Lease or Special Terms", width="100%"), spacing="1"),
                    rx.vstack(rx.text("Exhibit code", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_exhibit_code, on_change=LeaseDocumentState.set_p_exhibit_code, placeholder="Exhibit A", width="100%"), spacing="1"),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.grid(
                    rx.vstack(rx.text("Start page", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_start_page, on_change=LeaseDocumentState.set_p_start_page, width="100%"), spacing="1"),
                    rx.vstack(rx.text("End page", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_end_page, on_change=LeaseDocumentState.set_p_end_page, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Sort order", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_sort_order, on_change=LeaseDocumentState.set_p_sort_order, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Reusable", size="1", color="#666"), rx.checkbox("Add to reusable library later", checked=LeaseDocumentState.p_is_reusable, on_change=LeaseDocumentState.set_p_is_reusable), spacing="1"),
                    columns="4",
                    spacing="3",
                    width="100%",
                ),
                rx.button("Save Piece", on_click=LeaseDocumentState.create_piece, color_scheme="blue"),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),

        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.text("4. Select pieces and generate final lease PDF", size="4", weight="bold", color=BRAND_DARK),
                    rx.spacer(),
                    rx.button("Select All", size="2", variant="soft", on_click=LeaseDocumentState.select_all_pieces),
                    rx.button("Clear", size="2", variant="soft", on_click=LeaseDocumentState.clear_selected_pieces),
                    rx.button("Generate Package", size="2", color_scheme="blue", on_click=LeaseDocumentState.generate_package),
                    width="100%",
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Use"),
                            rx.table.column_header_cell("Sort"),
                            rx.table.column_header_cell("Type"),
                            rx.table.column_header_cell("Code"),
                            rx.table.column_header_cell("Name"),
                            rx.table.column_header_cell("Pages"),
                            rx.table.column_header_cell("Reusable"),
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

        rx.card(
            rx.vstack(
                rx.text("Generated lease PDFs", size="4", weight="bold", color=BRAND_DARK),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("File"),
                            rx.table.column_header_cell("Generated"),
                            rx.table.column_header_cell("Action"),
                        )
                    ),
                    rx.table.body(rx.foreach(LeaseDocumentState.generated_documents, generated_row)),
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
    return page_shell(lease_documents_content(), current_path="/lease-documents")
