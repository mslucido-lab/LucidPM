"""
Tenant Lease Package Builder page.

Purpose:
  - Select an existing tenant lease
  - Select reusable PDF pieces from Admin > Lease Templates
  - Merge selected pieces into a final tenant lease package PDF
  - Save generated package metadata back to the selected LeaseID
"""

from __future__ import annotations

import datetime
import os

import reflex as rx

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.pages.lease_documents_pdf import (
    DEFAULT_DOCUMENT_ROOT,
    merge_pdf_files,
    normalize_storage_root,
    relative_to_root,
)


class LeasePackagePiece(rx.Base):
    piece_id: int = 0
    piece_name: str = ""
    piece_type: str = ""
    exhibit_code: str = ""
    property_name: str = ""
    source_template: str = ""
    sort_order: int = 0
    file_path: str = ""
    selected: bool = False


class GeneratedPackageRow(rx.Base):
    generated_id: int = 0
    generated_on: str = ""
    file_name: str = ""
    file_path: str = ""


class LeasePackageBuilderState(AppState):
    # Tenant and lease selectors
    tenant_labels: list[str] = []
    tenant_ids: list[int] = []
    selected_tenant_label: str = ""

    lease_labels: list[str] = []
    lease_ids: list[int] = []
    selected_lease_label: str = ""
    selected_lease_id: int = 0

    # Context display
    lease_tenant_name: str = ""
    lease_property_name: str = ""
    lease_suite_label: str = ""
    lease_start: str = ""
    lease_end: str = ""
    lease_rent: str = ""

    # Package inputs
    package_name: str = ""
    output_storage_root: str = DEFAULT_DOCUMENT_ROOT
    package_notes: str = ""

    # Pieces
    available_pieces: list[LeasePackagePiece] = []
    selected_piece_ids: list[int] = []

    # Results
    generated_packages: list[GeneratedPackageRow] = []
    last_generated_document_id: int = 0
    last_generated_path: str = ""
    form_error: str = ""
    form_success: str = ""

    @rx.var
    def selected_count(self) -> int:
        return len(self.selected_piece_ids)

    @rx.var
    def generated_download_url(self) -> str:
        if self.last_generated_document_id <= 0:
            return ""
        return f"http://localhost:8000/api/lease-generated-pdf?id={self.last_generated_document_id}&db={self.db}"

    def on_load(self):
        self.output_storage_root = DEFAULT_DOCUMENT_ROOT
        self._load_tenants()
        if self.tenant_labels:
            self.selected_tenant_label = self.tenant_labels[0]
            self._load_leases_for_selected_tenant()

    def reload_on_db_change(self):
        self.form_error = ""
        self.form_success = ""
        self.last_generated_document_id = 0
        self.last_generated_path = ""
        self.available_pieces = []
        self.selected_piece_ids = []
        self._load_tenants()
        if self.tenant_labels:
            self.selected_tenant_label = self.tenant_labels[0]
            self._load_leases_for_selected_tenant()

    def _load_tenants(self):
        rows = run_query(
            "SELECT t.TenantID, t.TenantName, ISNULL(p.PropertyName,'') AS PropertyName, "
            "ISNULL(ps.SuiteLabel, ISNULL(t.Suite,'')) AS SuiteLabel "
            "FROM Tenants t "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            "LEFT JOIN PropertySuites ps ON t.SuiteID = ps.SuiteID "
            "ORDER BY t.TenantName",
            db=self.db,
        )
        self.tenant_labels = [
            f"{str(r.get('TenantName') or '').strip()}"
            + (f" — {str(r.get('PropertyName') or '').strip()}" if str(r.get('PropertyName') or '').strip() else "")
            + (f" / {str(r.get('SuiteLabel') or '').strip()}" if str(r.get('SuiteLabel') or '').strip() else "")
            + f" (ID={int(r['TenantID'])})"
            for r in rows
        ]
        self.tenant_ids = [int(r["TenantID"]) for r in rows]

    def _selected_tenant_id(self) -> int:
        try:
            idx = self.tenant_labels.index(self.selected_tenant_label)
            return int(self.tenant_ids[idx])
        except Exception:
            return 0

    def set_selected_tenant(self, label: str):
        self.selected_tenant_label = label
        self.selected_lease_id = 0
        self.selected_lease_label = ""
        self.available_pieces = []
        self.selected_piece_ids = []
        self.last_generated_document_id = 0
        self.form_error = ""
        self.form_success = ""
        self._load_leases_for_selected_tenant()

    def _load_leases_for_selected_tenant(self):
        tenant_id = self._selected_tenant_id()
        if tenant_id <= 0:
            self.lease_labels = []
            self.lease_ids = []
            return

        rows = run_query(
            "SELECT l.LeaseID, ISNULL(p.PropertyName,'') AS PropertyName, "
            "ISNULL(ps.SuiteLabel, '') AS SuiteLabel, l.LeaseStart, l.LeaseEnd, l.RentAmount, "
            "ISNULL(lt.LeaseTypeName,'') AS LeaseTypeName, ISNULL(ltt.LeaseTermTypeName,'') AS LeaseTermTypeName "
            "FROM Leases l "
            "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
            "LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID "
            "LEFT JOIN LeaseTypes lt ON l.LeaseTypeID = lt.LeaseTypeID "
            "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
            "WHERE l.TenantID = ? "
            "ORDER BY l.LeaseStart DESC, l.LeaseID DESC",
            (tenant_id,),
            db=self.db,
        )

        def fmt_dt(v):
            if v is None:
                return ""
            d = v.date() if hasattr(v, "date") else v
            try:
                return d.strftime("%m/%d/%Y")
            except Exception:
                return str(v)

        def fmt_money(v):
            try:
                return f"${float(v):,.2f}"
            except Exception:
                return ""

        labels = []
        ids = []
        for r in rows:
            lid = int(r["LeaseID"])
            start = fmt_dt(r.get("LeaseStart"))
            end = fmt_dt(r.get("LeaseEnd"))
            prop = str(r.get("PropertyName") or "").strip()
            suite = str(r.get("SuiteLabel") or "").strip()
            rent = fmt_money(r.get("RentAmount"))
            labels.append(f"Lease #{lid} — {prop} {suite} — {start} to {end} — {rent}".strip())
            ids.append(lid)
        self.lease_labels = labels
        self.lease_ids = ids
        if labels:
            self.selected_lease_label = labels[0]
            self.selected_lease_id = ids[0]
            self._load_selected_lease_context()
            self.load_available_pieces()
            self.load_generated_packages()
        else:
            self.selected_lease_label = ""
            self.selected_lease_id = 0
            self._clear_lease_context()

    def set_selected_lease(self, label: str):
        self.selected_lease_label = label
        try:
            idx = self.lease_labels.index(label)
            self.selected_lease_id = int(self.lease_ids[idx])
        except Exception:
            self.selected_lease_id = 0
        self.selected_piece_ids = []
        self.last_generated_document_id = 0
        self.form_error = ""
        self.form_success = ""
        self._load_selected_lease_context()
        self.load_available_pieces()
        self.load_generated_packages()

    def _clear_lease_context(self):
        self.lease_tenant_name = ""
        self.lease_property_name = ""
        self.lease_suite_label = ""
        self.lease_start = ""
        self.lease_end = ""
        self.lease_rent = ""
        self.package_name = ""

    def _load_selected_lease_context(self):
        if self.selected_lease_id <= 0:
            self._clear_lease_context()
            return
        rows = run_query(
            "SELECT l.LeaseID, t.TenantName, ISNULL(p.PropertyName,'') AS PropertyName, "
            "ISNULL(ps.SuiteLabel, ISNULL(t.Suite,'')) AS SuiteLabel, "
            "l.LeaseStart, l.LeaseEnd, l.RentAmount "
            "FROM Leases l "
            "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
            "LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID "
            "WHERE l.LeaseID = ?",
            (self.selected_lease_id,),
            db=self.db,
        )
        if not rows:
            self._clear_lease_context()
            return
        r = rows[0]

        def fmt_dt(v):
            if v is None:
                return ""
            d = v.date() if hasattr(v, "date") else v
            try:
                return d.strftime("%m/%d/%Y")
            except Exception:
                return str(v)

        def fmt_money(v):
            try:
                return f"${float(v):,.2f}"
            except Exception:
                return ""

        self.lease_tenant_name = str(r.get("TenantName") or "")
        self.lease_property_name = str(r.get("PropertyName") or "")
        self.lease_suite_label = str(r.get("SuiteLabel") or "")
        self.lease_start = fmt_dt(r.get("LeaseStart"))
        self.lease_end = fmt_dt(r.get("LeaseEnd"))
        self.lease_rent = fmt_money(r.get("RentAmount"))
        today = datetime.date.today().strftime("%Y%m%d")
        safe_tenant = "".join(ch if ch.isalnum() else "_" for ch in self.lease_tenant_name).strip("_") or "Tenant"
        self.package_name = f"{safe_tenant}_Lease_Package_{today}.pdf"

    def load_available_pieces(self):
        if self.selected_lease_id <= 0:
            self.available_pieces = []
            return
        rows = run_query(
            "SELECT p.LeaseDocumentPieceID, p.PieceName, p.PieceType, ISNULL(p.ExhibitCode,'') AS ExhibitCode, "
            "p.StoredFilePath, p.SortOrder, ISNULL(pr.PropertyName,'') AS PropertyName, "
            "ISNULL(s.TemplateName, '') AS TemplateName "
            "FROM LeaseDocumentPieces p "
            "INNER JOIN LeaseSourceDocuments s ON p.LeaseSourceDocumentID = s.LeaseSourceDocumentID "
            "LEFT JOIN Properties pr ON s.PropertyID = pr.PropertyID "
            "WHERE ISNULL(p.IsReusable, 1) = 1 "
            "AND ISNULL(p.IsActive, 1) = 1 "
            "AND ISNULL(s.IsActive, 1) = 1 "
            "AND (s.PropertyID IS NULL OR pr.PropertyName = ? OR ? = '') "
            "ORDER BY CASE WHEN p.PieceType = 'Base Lease' THEN 0 "
            "WHEN p.PieceType = 'Base' THEN 0 "
            "WHEN p.PieceType = 'Exhibit' THEN 1 "
            "WHEN p.PieceType = 'Addendum' THEN 2 ELSE 3 END, "
            "p.SortOrder, p.PieceName",
            (self.lease_property_name, self.lease_property_name),
            db=self.db,
        )
        self.available_pieces = [
            LeasePackagePiece(
                piece_id=int(r["LeaseDocumentPieceID"]),
                piece_name=str(r.get("PieceName") or ""),
                piece_type=str(r.get("PieceType") or ""),
                exhibit_code=str(r.get("ExhibitCode") or ""),
                property_name=str(r.get("PropertyName") or ""),
                source_template=str(r.get("TemplateName") or ""),
                sort_order=int(r.get("SortOrder") or 0),
                file_path=str(r.get("StoredFilePath") or ""),
                selected=int(r["LeaseDocumentPieceID"]) in self.selected_piece_ids,
            )
            for r in rows
        ]

    def toggle_piece(self, piece_id: int):
        pid = int(piece_id)
        if pid in self.selected_piece_ids:
            self.selected_piece_ids = [x for x in self.selected_piece_ids if x != pid]
        else:
            self.selected_piece_ids = self.selected_piece_ids + [pid]
        self.available_pieces = [
            LeasePackagePiece(
                piece_id=p.piece_id,
                piece_name=p.piece_name,
                piece_type=p.piece_type,
                exhibit_code=p.exhibit_code,
                property_name=p.property_name,
                source_template=p.source_template,
                sort_order=p.sort_order,
                file_path=p.file_path,
                selected=p.piece_id in self.selected_piece_ids,
            )
            for p in self.available_pieces
        ]

    def select_base_and_exhibits(self):
        ids = []
        for p in self.available_pieces:
            ptype = (p.piece_type or "").strip().lower()
            if ptype in ("base", "base lease", "exhibit", "addendum"):
                ids.append(p.piece_id)
        self.selected_piece_ids = ids
        self.load_available_pieces()

    def clear_selected_pieces(self):
        self.selected_piece_ids = []
        self.load_available_pieces()

    def set_package_name(self, v: str): self.package_name = v
    def set_output_storage_root(self, v: str): self.output_storage_root = v
    def set_package_notes(self, v: str): self.package_notes = v

    def generate_package(self):
        self.form_error = ""
        self.form_success = ""
        self.last_generated_document_id = 0
        self.last_generated_path = ""
        if self.selected_lease_id <= 0:
            self.form_error = "Select a lease first."
            return
        if not self.selected_piece_ids:
            self.form_error = "Select at least one template piece."
            return
        if not self.package_name.strip():
            self.form_error = "Package file name is required."
            return

        selected = [p for p in self.available_pieces if p.piece_id in self.selected_piece_ids]
        selected.sort(key=lambda p: (p.sort_order, p.piece_type, p.piece_name))
        missing = [p.piece_name for p in selected if not os.path.isfile(p.file_path)]
        if missing:
            self.form_error = "Missing PDF files: " + ", ".join(missing[:3])
            return

        try:
            root = normalize_storage_root(self.output_storage_root)
            output_path = merge_pdf_files([p.file_path for p in selected], self.package_name.strip(), root)
            filename = os.path.basename(output_path)
            now = datetime.datetime.now()
            notes = self.package_notes.strip()
            run_exec(
                "INSERT INTO LeaseGeneratedDocuments (LeaseID, GeneratedFileName, StoredFilePath, GeneratedOn, PackageNotes) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.selected_lease_id, filename, output_path, now, notes),
                db=self.db,
            )
            id_rows = run_query(
                "SELECT TOP 1 LeaseGeneratedDocumentID FROM LeaseGeneratedDocuments "
                "WHERE LeaseID = ? AND StoredFilePath = ? ORDER BY LeaseGeneratedDocumentID DESC",
                (self.selected_lease_id, output_path),
                db=self.db,
            )
            generated_id = int(id_rows[0]["LeaseGeneratedDocumentID"]) if id_rows else 0
            if generated_id:
                for idx, p in enumerate(selected, start=1):
                    run_exec(
                        "INSERT INTO LeaseGeneratedDocumentPieces "
                        "(LeaseGeneratedDocumentID, LeaseDocumentPieceID, SortOrder) VALUES (?, ?, ?)",
                        (generated_id, p.piece_id, idx),
                        db=self.db,
                    )
            self.last_generated_document_id = generated_id
            self.last_generated_path = output_path
            self.form_success = f"Lease package generated: {filename}"
            self.load_generated_packages()
        except Exception as ex:
            self.form_error = f"Package generation failed: {ex}"

    def load_generated_packages(self):
        if self.selected_lease_id <= 0:
            self.generated_packages = []
            return
        rows = run_query(
            "SELECT TOP 10 LeaseGeneratedDocumentID, GeneratedFileName, StoredFilePath, GeneratedOn "
            "FROM LeaseGeneratedDocuments WHERE LeaseID = ? ORDER BY GeneratedOn DESC, LeaseGeneratedDocumentID DESC",
            (self.selected_lease_id,),
            db=self.db,
        )

        def fmt_dt(v):
            if v is None:
                return ""
            if hasattr(v, "strftime"):
                return v.strftime("%m/%d/%Y %I:%M %p")
            return str(v)

        self.generated_packages = [
            GeneratedPackageRow(
                generated_id=int(r["LeaseGeneratedDocumentID"]),
                generated_on=fmt_dt(r.get("GeneratedOn")),
                file_name=str(r.get("GeneratedFileName") or ""),
                file_path=str(r.get("StoredFilePath") or ""),
            )
            for r in rows
        ]


def context_card() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Selected lease", size="3", weight="bold", color=BRAND_DARK),
            rx.grid(
                rx.vstack(rx.text("Tenant", size="1", color="#666"), rx.text(LeasePackageBuilderState.lease_tenant_name, size="2", weight="bold"), spacing="1"),
                rx.vstack(rx.text("Property", size="1", color="#666"), rx.text(LeasePackageBuilderState.lease_property_name, size="2"), spacing="1"),
                rx.vstack(rx.text("Suite", size="1", color="#666"), rx.text(LeasePackageBuilderState.lease_suite_label, size="2"), spacing="1"),
                rx.vstack(rx.text("Term", size="1", color="#666"), rx.text(LeasePackageBuilderState.lease_start + " to " + LeasePackageBuilderState.lease_end, size="2"), spacing="1"),
                rx.vstack(rx.text("Rent", size="1", color="#666"), rx.text(LeasePackageBuilderState.lease_rent, size="2", weight="bold"), spacing="1"),
                columns="5",
                spacing="4",
                width="100%",
            ),
            spacing="3",
            width="100%",
            align_items="start",
        ),
        style={
            "background": "#f8faff",
            "border": "1px solid #d8e1f5",
            "border_left": f"4px solid {BRAND_PRIMARY}",
            "border_radius": "10px",
            "padding": "14px",
            "width": "100%",
        },
    )


def piece_row(p: LeasePackagePiece) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.cond(
                p.selected,
                rx.badge("Selected", color_scheme="green", variant="soft"),
                rx.badge("Available", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(rx.text(p.piece_name, size="2", weight="bold")),
        rx.table.cell(rx.text(p.piece_type, size="2")),
        rx.table.cell(rx.text(p.exhibit_code, size="2")),
        rx.table.cell(rx.text(p.source_template, size="2", color="#555")),
        rx.table.cell(rx.text(p.property_name, size="2", color="#555")),
        rx.table.cell(rx.text(p.sort_order.to_string(), size="2")),
        rx.table.cell(
            rx.button(
                rx.cond(p.selected, "Remove", "Add"),
                on_click=LeasePackageBuilderState.toggle_piece(p.piece_id),
                size="1",
                variant="soft",
                color_scheme=rx.cond(p.selected, "red", "blue"),
            )
        ),
        style=rx.cond(p.selected, {"background": "#f0fff4"}, {"background": "white"}),
    )


def generated_row(g: GeneratedPackageRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(g.generated_on, size="2")),
        rx.table.cell(rx.text(g.file_name, size="2", weight="bold")),
        rx.table.cell(rx.text(g.file_path, size="1", color="#666")),
        rx.table.cell(
            rx.link(
                rx.button("Download", size="1", variant="soft", color_scheme="blue"),
                href="http://localhost:8000/api/lease-generated-pdf?id=" + g.generated_id.to_string(),
                is_external=True,
            )
        ),
    )


def lease_package_builder_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Build Lease Package", size="6", color=BRAND_DARK),
        rx.text(
            "Create a tenant lease PDF by selecting reusable pieces from Admin > Lease Templates.",
            size="2",
            color="#555",
        ),

        rx.box(
            rx.vstack(
                rx.text("1. Select tenant lease", size="4", weight="bold", color=BRAND_DARK),
                rx.grid(
                    rx.vstack(
                        rx.text("Tenant", size="1", color="#666"),
                        rx.cond(
                            LeasePackageBuilderState.tenant_labels.length() > 0,
                            rx.select(
                                LeasePackageBuilderState.tenant_labels,
                                value=LeasePackageBuilderState.selected_tenant_label,
                                on_change=LeasePackageBuilderState.set_selected_tenant,
                                size="2",
                                width="100%",
                            ),
                            rx.text("No tenants found.", size="2", color="#888"),
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Lease", size="1", color="#666"),
                        rx.cond(
                            LeasePackageBuilderState.lease_labels.length() > 0,
                            rx.select(
                                LeasePackageBuilderState.lease_labels,
                                value=LeasePackageBuilderState.selected_lease_label,
                                on_change=LeasePackageBuilderState.set_selected_lease,
                                size="2",
                                width="100%",
                            ),
                            rx.text("No leases found for selected tenant.", size="2", color="#888"),
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    columns="2",
                    spacing="4",
                    width="100%",
                ),
                rx.cond(LeasePackageBuilderState.selected_lease_id > 0, context_card(), rx.fragment()),
                spacing="4",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        rx.box(
            rx.vstack(
                rx.text("2. Select lease pieces", size="4", weight="bold", color=BRAND_DARK),
                rx.hstack(
                    rx.button("Select base, exhibits, addendums", on_click=LeasePackageBuilderState.select_base_and_exhibits, size="2", variant="soft", color_scheme="blue"),
                    rx.button("Clear selected", on_click=LeasePackageBuilderState.clear_selected_pieces, size="2", variant="ghost"),
                    rx.badge("Selected: " + LeasePackageBuilderState.selected_count.to_string(), color_scheme="green", variant="soft"),
                    spacing="3",
                    align="center",
                ),
                rx.cond(
                    LeasePackageBuilderState.available_pieces.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell("Piece"),
                                rx.table.column_header_cell("Type"),
                                rx.table.column_header_cell("Exhibit"),
                                rx.table.column_header_cell("Template"),
                                rx.table.column_header_cell("Property"),
                                rx.table.column_header_cell("Sort"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(rx.foreach(LeasePackageBuilderState.available_pieces, piece_row)),
                        width="100%",
                        variant="surface",
                    ),
                    rx.callout("No reusable template pieces found. Go to Admin > Lease Templates and split a PDF into reusable pieces first.", color_scheme="gray", variant="soft"),
                ),
                spacing="4",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        rx.box(
            rx.vstack(
                rx.text("3. Generate package", size="4", weight="bold", color=BRAND_DARK),
                rx.grid(
                    rx.vstack(
                        rx.text("Package file name", size="1", color="#666"),
                        rx.input(value=LeasePackageBuilderState.package_name, on_change=LeasePackageBuilderState.set_package_name, size="2", width="100%"),
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("Output storage root", size="1", color="#666"),
                        rx.input(value=LeasePackageBuilderState.output_storage_root, on_change=LeasePackageBuilderState.set_output_storage_root, size="2", width="100%"),
                        spacing="1",
                        width="100%",
                    ),
                    columns="2",
                    spacing="4",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("Package notes", size="1", color="#666"),
                    rx.text_area(value=LeasePackageBuilderState.package_notes, on_change=LeasePackageBuilderState.set_package_notes, width="100%", height="80px"),
                    spacing="1",
                    width="100%",
                ),
                rx.cond(LeasePackageBuilderState.form_error != "", rx.callout(LeasePackageBuilderState.form_error, color_scheme="red", variant="soft"), rx.fragment()),
                rx.cond(LeasePackageBuilderState.form_success != "", rx.callout(LeasePackageBuilderState.form_success, color_scheme="green", variant="soft"), rx.fragment()),
                rx.hstack(
                    rx.button("Generate lease package PDF", on_click=LeasePackageBuilderState.generate_package, color_scheme="blue", size="2"),
                    rx.cond(
                        LeasePackageBuilderState.last_generated_document_id > 0,
                        rx.link(rx.button("Download last generated PDF", size="2", variant="soft", color_scheme="green"), href=LeasePackageBuilderState.generated_download_url, is_external=True),
                        rx.fragment(),
                    ),
                    spacing="3",
                    align="center",
                ),
                spacing="4",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        rx.box(
            rx.vstack(
                rx.text("Generated packages for this lease", size="4", weight="bold", color=BRAND_DARK),
                rx.cond(
                    LeasePackageBuilderState.generated_packages.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Generated"),
                                rx.table.column_header_cell("File"),
                                rx.table.column_header_cell("Path"),
                                rx.table.column_header_cell(""),
                            )
                        ),
                        rx.table.body(rx.foreach(LeasePackageBuilderState.generated_packages, generated_row)),
                        width="100%",
                        variant="surface",
                    ),
                    rx.text("No packages generated for this lease yet.", size="2", color="#888"),
                ),
                spacing="3",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        spacing="5",
        width="100%",
        align_items="start",
        padding="24px",
    )


def lease_package_builder_page() -> rx.Component:
    return page_shell(lease_package_builder_content(), current_path="/lease-package-builder")
