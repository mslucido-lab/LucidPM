"""
Tenant Lease Package Builder page.

Purpose:
  - Select an existing tenant lease
  - Select reusable lease sections from Admin > Lease Templates
  - Merge selected sections into a final tenant lease package PDF
  - Save generated package metadata back to the selected LeaseID
"""

# v3.0.5d - verified token validation blocks on missing tokens only; blank optional tokens remain non-blocking.
# v3.0.5c - corrected lease_merge import back to root module path.
# v3.0.5 - code review cleanup: removed dead ReportLab imports and fixed lease_merge import path.
# v3.0.1 - Supports standalone clauses with nullable LeaseSourceDocumentID.
# - Converts package-builder section queries from INNER JOIN to LEFT JOIN where source documents are optional.
# - Labels standalone clauses as "Standalone" when no source document exists.
# v3.0.1 - Pagination engine wiring: consecutive tokenized clauses render into one flowing PDF before merge.
# v3.0.4 - Prepends ArticleNumber/DisplayLabel metadata into rendered text so legal headings appear in generated PDFs.
# v3.0.3 - Uses v1.4 style-aware legal renderer for flowing text clauses.
# v3.0.2 - Uses pagination engine for consecutive text-backed clauses.
# v3.0.0 - Phase 5 baseline for clause-level lease package building.
# - Advances package builder version for Phase 5.
# - Simplifies selected-section dropdown labels to: Section Name (Source Document Template).
# - Keeps SectionID as the select value so duplicate display labels still resolve correctly.
# v2.8.12 - Adds generated package history/review polish with file status, section count, and package detail review.
# v2.8.11 - Adds pre-generation summary, clearer actionable errors, preview checks, and final output integrity validation.
# v2.8.10 - Package builder polish: template-driven UX cleanup, optional-row auto-include, and stronger generation validation.
# v2.8.13 - Review polish: display generated section audit flag as Status (Original/Revised) instead of Dirty.
# v2.8.14 - Adds first-pass generated lease section edit workflow and regenerate selected package.
# v2.8.21 - Combines Preview and Summary into a single Review Package tabbed section.
# v2.8.15 - Fixes regenerate to INSERT a new generated package/version and rebuild LeasePackageSections instead of updating the original record.
# v2.8.16 - Adds generated package version labels and Latest badge in package history.
# v2.8.17 - Removes full file path from generated package history and keeps path in the review panel only.
# v2.8.18 - Adds package-level revision status, stale PDF warning, and cleaner history table spacing.
# v2.8.19 - Collapses section library reference by default and adds regenerate preview before creating a new version.
# v2.8.21 - Reorders workflow so preview comes before summary and generate, with a soft missing-token warning near generate.
# v2.8.22 - Cleans selected generated package panel layout: badges, actions, and path details are separated to prevent header crowding.
# v2.8.23 - Final polish bundle: clean regenerate filenames, clearer regenerate preview, audit collapse, and history version column polish.

from __future__ import annotations

import datetime
import os
import tempfile
from xml.sax.saxutils import escape

import reflex as rx


from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.pages.lease_documents_pdf import (
    DEFAULT_DOCUMENT_ROOT,
    merge_pdf_files,
    normalize_storage_root,
    page_count,
    relative_to_root,
    render_text_to_pdf,
    render_text_sections_to_pdf,
)
from LucidPM_Reflex.lease_merge import (
    get_lease_merge_context,
    render_text_template,
    validate_template_tokens,
)


class LeasePackageSection(rx.Base):
    template_section_id: int = 0
    template_section_label: str = ""
    section_id: int = 0
    section_name: str = ""
    section_type: str = ""
    exhibit_code: str = ""
    article_number: str = ""
    display_label: str = ""
    property_name: str = ""
    source_template: str = ""
    sort_order: int = 0
    file_path: str = ""
    content: str = ""
    selected: bool = False


class LeasePackageTemplateRow(rx.Base):
    template_id: int = 0
    template_name: str = ""
    property_name: str = ""
    description: str = ""


class LeasePackageTemplateSectionRow(rx.Base):
    template_section_id: int = 0
    sort_order: int = 0
    section_label: str = ""
    section_type: str = ""
    is_optional: bool = False
    is_required: bool = False
    default_section_id: int = 0
    selected_section_id: int = 0
    selected_section_label: str = ""
    included: bool = True


class SectionOption(rx.Base):
    value: str = ""
    label: str = ""


class GeneratedPackageRow(rx.Base):
    generated_id: int = 0
    version_label: str = ""
    is_latest: bool = False
    generated_on: str = ""
    file_name: str = ""
    file_path: str = ""
    file_status: str = ""
    revision_status: str = ""
    is_stale: bool = False
    section_count: int = 0
    package_notes: str = ""
    download_url: str = ""


class GeneratedPackageSectionRow(rx.Base):
    package_section_id: int = 0
    sort_order: int = 0
    section_label: str = ""
    section_name: str = ""
    section_type: str = ""
    source_template: str = ""
    content_status: str = ""
    included: str = ""
    revision_status: str = ""
    editable: bool = False




def _format_actionable_errors(title: str, errors: list[str], limit: int = 8) -> str:
    """Return a short, readable validation message for Reflex callouts."""
    clean = [str(e or "").strip() for e in errors if str(e or "").strip()]
    if not clean:
        return title
    shown = clean[:limit]
    msg = title + "\n- " + "\n- ".join(shown)
    remaining = len(clean) - len(shown)
    if remaining > 0:
        msg += f"\n- ...and {remaining} more."
    return msg

def render_text_section_to_pdf_file(section_text: str, output_path: str) -> str:
    """Backward-compatible wrapper around the shared PDF renderer."""
    return render_text_to_pdf(section_text, output_path)


def render_text_sections_to_pdf_file(section_texts: list[str], output_path: str) -> str:
    """Render consecutive tokenized clauses as one flowing PDF segment."""
    return render_text_sections_to_pdf(section_texts, output_path)


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

    # Sections / manual selection
    available_sections: list[LeasePackageSection] = []
    selected_section_ids: list[int] = []
    show_section_library_reference: bool = False

    # Package template selection
    package_templates: list[LeasePackageTemplateRow] = []
    package_template_labels: list[str] = []
    package_template_ids: list[int] = []
    selected_package_template_label: str = ""
    selected_package_template_id: int = 0
    template_sections: list[LeasePackageTemplateSectionRow] = []
    section_option_labels: list[str] = []
    section_option_ids: list[int] = []
    section_options: list[SectionOption] = []

    # Results
    generated_packages: list[GeneratedPackageRow] = []
    selected_generated_id: int = 0
    selected_generated_on: str = ""
    selected_generated_file_name: str = ""
    selected_generated_path: str = ""
    selected_generated_status: str = ""
    selected_generated_revision_status: str = ""
    selected_generated_is_stale: bool = False
    selected_generated_version_label: str = ""
    selected_generated_is_latest: bool = False
    show_selected_generated_path: bool = False
    selected_generated_notes: str = ""
    generated_package_sections: list[GeneratedPackageSectionRow] = []
    show_section_audit: bool = False

    # Generated lease section edit workflow
    editing_package_section_id: int = 0
    editing_package_section_label: str = ""
    editing_package_section_content: str = ""
    edit_section_error: str = ""
    edit_section_success: str = ""

    last_generated_document_id: int = 0
    last_generated_path: str = ""
    form_error: str = ""
    form_success: str = ""

    # Merge preview results. This does not affect the existing PDF package flow.
    merge_preview: str = ""
    merge_error: str = ""
    merge_missing_tokens: list[str] = []
    merge_known_tokens: list[str] = []

    # Regenerate preview results. Regeneration still creates a new immutable version.
    regenerate_preview_open: bool = False
    regenerate_preview_ready: bool = False
    regenerate_preview_text: str = ""
    regenerate_preview_error: str = ""

    @rx.var
    def selected_count(self) -> int:
        return len(self.selected_section_ids)

    @rx.var
    def package_summary_lines(self) -> list[str]:
        """Human-readable pre-generation summary for the selected package template."""
        if self.selected_package_template_id <= 0 or not self.template_sections:
            return ["Select a package template to see the package summary."]

        by_id = {int(p.section_id): p for p in self.available_sections}
        included_rows = [
            section for section in sorted(
                self.template_sections,
                key=lambda s: (int(s.sort_order or 0), int(s.template_section_id or 0)),
            )
            if section.included
        ]
        optional_skipped = [section for section in self.template_sections if section.is_optional and not section.included]

        content_count = 0
        pdf_count = 0
        unresolved_count = 0
        lines = [f"Included sections: {len(included_rows)}"]

        for section in included_rows:
            sid = int(section.selected_section_id or 0)
            section_data = by_id.get(sid)
            label = section.section_label or f"Template section {section.template_section_id}"
            if sid <= 0:
                unresolved_count += 1
                lines.append(f"{section.sort_order}. {label} - missing selected section")
                continue
            if section_data and str(section_data.content or "").strip():
                content_count += 1
                kind = "Content"
            else:
                pdf_count += 1
                kind = "PDF"
            selected_label = section.selected_section_label or (section_data.section_name if section_data else f"Section ID {sid}")
            lines.append(f"{section.sort_order}. {label} - {kind} - {selected_label}")

        lines.insert(1, f"Content-based: {content_count}")
        lines.insert(2, f"PDF-based: {pdf_count}")
        lines.insert(3, f"Optional sections skipped: {len(optional_skipped)}")
        if unresolved_count:
            lines.insert(4, f"Warnings: {unresolved_count} included row(s) need a selected section")
        return lines

    @rx.var
    def package_summary_warning(self) -> str:
        if self.selected_package_template_id <= 0:
            return "Select a package template before generating."
        missing = [
            (section.section_label or f"Template section {section.template_section_id}")
            for section in self.template_sections
            if section.included and int(section.selected_section_id or 0) <= 0
        ]
        if missing:
            return "Included rows need selected sections: " + ", ".join(missing[:5])
        skipped = [section.section_label for section in self.template_sections if section.is_optional and not section.included]
        if skipped:
            return "Optional sections not included: " + ", ".join([s for s in skipped[:5] if s])
        return ""

    @rx.var
    def generated_download_url(self) -> str:
        if self.last_generated_document_id <= 0:
            return ""
        return f"http://localhost:8000/api/lease-generated-pdf?generated_id={self.last_generated_document_id}&db={self.db}"

    @rx.var
    def selected_generated_download_url(self) -> str:
        if self.selected_generated_id <= 0:
            return ""
        return f"http://localhost:8000/api/lease-generated-pdf?generated_id={self.selected_generated_id}&db={self.db}"

    @rx.var
    def selected_generated_summary(self) -> str:
        if self.selected_generated_id <= 0:
            return "Select a generated package to review what was created."
        version = f"{self.selected_generated_version_label} - " if self.selected_generated_version_label else ""
        return f"{version}{self.selected_generated_file_name} - {self.selected_generated_status}"

    def _reset_generated_review(self):
        self.selected_generated_id = 0
        self.selected_generated_on = ""
        self.selected_generated_file_name = ""
        self.selected_generated_path = ""
        self.selected_generated_status = ""
        self.selected_generated_revision_status = ""
        self.selected_generated_is_stale = False
        self.selected_generated_version_label = ""
        self.selected_generated_is_latest = False
        self.show_selected_generated_path = False
        self.selected_generated_notes = ""
        self.generated_package_sections = []
        self.show_section_audit = False
        self._reset_section_editor()
        self._reset_regenerate_preview()

    def _reset_section_editor(self):
        self.editing_package_section_id = 0
        self.editing_package_section_label = ""
        self.editing_package_section_content = ""
        self.edit_section_error = ""
        self.edit_section_success = ""

    def _reset_regenerate_preview(self):
        self.regenerate_preview_open = False
        self.regenerate_preview_ready = False
        self.regenerate_preview_text = ""
        self.regenerate_preview_error = ""

    def toggle_section_library_reference(self):
        self.show_section_library_reference = not self.show_section_library_reference

    def toggle_selected_generated_path(self):
        self.show_selected_generated_path = not self.show_selected_generated_path

    def toggle_section_audit(self):
        self.show_section_audit = not self.show_section_audit

    def _safe_filename_token(self, value: str, fallback: str = "Tenant") -> str:
        token = "".join(ch if ch.isalnum() else "_" for ch in str(value or "")).strip("_")
        while "__" in token:
            token = token.replace("__", "_")
        return token or fallback

    def _next_generated_version_number(self, lease_id: int) -> int:
        rows = run_query(
            "SELECT COUNT(*) AS n FROM LeaseGeneratedDocuments WHERE LeaseID = ?",
            (int(lease_id),),
            db=self.db,
        )
        try:
            return int(rows[0].get("n") or 0) + 1
        except Exception:
            return 1

    def _build_versioned_package_filename(self, version_number: int) -> str:
        tenant_token = self._safe_filename_token(self.lease_tenant_name, "Tenant")
        return f"{tenant_token}_Lease_Package_v{int(version_number)}.pdf"

    def _load_storage_root_setting(self):
        """Load lease document storage root from AppSettings, with safe fallback."""
        try:
            rows = run_query(
                "SELECT TOP 1 SettingValue FROM AppSettings WHERE SettingKey = ?",
                ("LeaseDocumentStorageRoot",),
                db=self.db,
            )
            value = str(rows[0].get("SettingValue") or "").strip() if rows else ""
            self.output_storage_root = value or DEFAULT_DOCUMENT_ROOT
        except Exception:
            self.output_storage_root = DEFAULT_DOCUMENT_ROOT

    def on_load(self):
        self._load_storage_root_setting()
        self._load_tenants()
        if self.tenant_labels:
            self.selected_tenant_label = self.tenant_labels[0]
            self._load_leases_for_selected_tenant()

    def reload_on_db_change(self):
        self.form_error = ""
        self.form_success = ""
        self.merge_preview = ""
        self.merge_error = ""
        self.merge_missing_tokens = []
        self.merge_known_tokens = []
        self.last_generated_document_id = 0
        self.last_generated_path = ""
        self._reset_generated_review()
        self.available_sections = []
        self.selected_section_ids = []
        self.package_templates = []
        self.package_template_labels = []
        self.package_template_ids = []
        self.selected_package_template_label = ""
        self.selected_package_template_id = 0
        self.template_sections = []
        self.section_option_labels = []
        self.section_option_ids = []
        self.section_options = []
        self._load_storage_root_setting()
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
        self.available_sections = []
        self.selected_section_ids = []
        self.package_templates = []
        self.package_template_labels = []
        self.package_template_ids = []
        self.selected_package_template_label = ""
        self.selected_package_template_id = 0
        self.template_sections = []
        self.section_option_labels = []
        self.section_option_ids = []
        self.section_options = []
        self.generated_packages = []
        self.last_generated_document_id = 0
        self._reset_generated_review()
        self.form_error = ""
        self.form_success = ""
        self.merge_preview = ""
        self.merge_error = ""
        self.merge_missing_tokens = []
        self.merge_known_tokens = []
        self._load_leases_for_selected_tenant()

    def _load_leases_for_selected_tenant(self):
        tenant_id = self._selected_tenant_id()
        if tenant_id <= 0:
            self.lease_labels = []
            self.lease_ids = []
            self.selected_lease_label = ""
            self.selected_lease_id = 0
            self._clear_lease_context()
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
            self.load_available_sections()
            self.load_package_templates()
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
        self.selected_section_ids = []
        self.last_generated_document_id = 0
        self._reset_generated_review()
        self.form_error = ""
        self.form_success = ""
        self.merge_preview = ""
        self.merge_error = ""
        self.merge_missing_tokens = []
        self.merge_known_tokens = []
        self._load_selected_lease_context()
        if self.selected_lease_id <= 0:
            self._clear_lease_context()
            return
        self.load_available_sections()
        self.load_package_templates()
        self.load_generated_packages()

    def _clear_lease_context(self):
        self.lease_tenant_name = ""
        self.lease_property_name = ""
        self.lease_suite_label = ""
        self.lease_start = ""
        self.lease_end = ""
        self.lease_rent = ""
        self.package_name = ""
        self.available_sections = []
        self.selected_section_ids = []
        self.package_templates = []
        self.package_template_labels = []
        self.package_template_ids = []
        self.selected_package_template_label = ""
        self.selected_package_template_id = 0
        self.template_sections = []
        self.section_option_labels = []
        self.section_option_ids = []
        self.section_options = []
        self.generated_packages = []
        self.last_generated_document_id = 0
        self.last_generated_path = ""
        self._reset_generated_review()
        self.merge_preview = ""
        self.merge_error = ""
        self.merge_missing_tokens = []
        self.merge_known_tokens = []

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

    def _lease_section_table(self) -> str:
        return "LeaseDocumentSections"

    def _lease_section_id_col(self) -> str:
        return "LeaseDocumentSectionID"

    def _lease_section_name_col(self) -> str:
        return "SectionName"

    def _lease_section_type_col(self) -> str:
        return "SectionType"

    def _template_default_section_col(self) -> str:
        return "DefaultSectionID"

    def _package_section_ref_col(self) -> str:
        return "SectionID"

    def _generated_section_audit_target(self) -> tuple[str, str]:
        return "LeaseGeneratedDocumentSections", "LeaseDocumentSectionID"

    def load_available_sections(self):
        if self.selected_lease_id <= 0:
            self.available_sections = []
            return

        section_table = self._lease_section_table()
        section_id_col = self._lease_section_id_col()
        section_name_col = self._lease_section_name_col()
        section_type_col = self._lease_section_type_col()

        rows = run_query(
            f"SELECT p.[{section_id_col}] AS SectionID, "
            f"p.[{section_name_col}] AS SectionName, "
            f"p.[{section_type_col}] AS SectionType, "
            "ISNULL(p.ExhibitCode,'') AS ExhibitCode, "
            "ISNULL(p.ArticleNumber, '') AS ArticleNumber, ISNULL(p.DisplayLabel, '') AS DisplayLabel, "
            "p.StoredFilePath, ISNULL(p.Content, '') AS Content, p.SortOrder, "
            "ISNULL(pr.PropertyName,'') AS PropertyName, "
            "COALESCE(NULLIF(s.TemplateName, ''), 'Standalone') AS TemplateName "
            f"FROM {section_table} p "
            "LEFT JOIN LeaseSourceDocuments s ON p.LeaseSourceDocumentID = s.LeaseSourceDocumentID "
            "LEFT JOIN Properties pr ON s.PropertyID = pr.PropertyID "
            "WHERE ISNULL(p.IsReusable, 1) = 1 "
            "AND ISNULL(p.IsActive, 1) = 1 "
            "AND (s.LeaseSourceDocumentID IS NULL OR ISNULL(s.IsActive, 1) = 1) "
            "AND (s.LeaseSourceDocumentID IS NULL OR s.PropertyID IS NULL OR pr.PropertyName = ? OR ? = '') "
            f"ORDER BY CASE WHEN p.[{section_type_col}] = 'Base Lease' THEN 0 "
            f"WHEN p.[{section_type_col}] = 'Base' THEN 0 "
            f"WHEN p.[{section_type_col}] = 'Exhibit' THEN 1 "
            f"WHEN p.[{section_type_col}] = 'Addendum' THEN 2 ELSE 3 END, "
            f"p.SortOrder, p.[{section_name_col}]",
            (self.lease_property_name, self.lease_property_name),
            db=self.db,
        )
        self.available_sections = [
            LeasePackageSection(
                section_id=int(r["SectionID"]),
                section_name=str(r.get("SectionName") or ""),
                section_type=str(r.get("SectionType") or ""),
                exhibit_code=str(r.get("ExhibitCode") or ""),
                article_number=str(r.get("ArticleNumber") or ""),
                display_label=str(r.get("DisplayLabel") or ""),
                property_name=str(r.get("PropertyName") or ""),
                source_template=str(r.get("TemplateName") or "Standalone"),
                sort_order=int(r.get("SortOrder") or 0),
                file_path=str(r.get("StoredFilePath") or ""),
                content=str(r.get("Content") or ""),
                selected=int(r["SectionID"]) in self.selected_section_ids,
            )
            for r in rows
        ]
        self._refresh_section_options()

    def _section_label(self, section_id: int) -> str:
        if section_id <= 0:
            return "(No section)"
        for idx, pid in enumerate(self.section_option_ids):
            if int(pid) == int(section_id):
                return self.section_option_labels[idx]
        for p in self.available_sections:
            if int(p.section_id) == int(section_id):
                parts = [p.section_type, p.section_name]
                if p.exhibit_code:
                    parts.append(f"Exhibit {p.exhibit_code}")
                return " | ".join(x for x in parts if x)
        return "(No section)"

    def _section_id_for_label(self, label: str) -> int:
        try:
            idx = self.section_option_labels.index(label)
            return int(self.section_option_ids[idx])
        except Exception:
            return 0

    def _refresh_section_options(self):
        labels = ["(No section)"]
        ids = [0]
        seen_labels: dict[str, int] = {}

        for p in self.available_sections:
            section_name = str(p.section_name or "").strip() or f"Section {int(p.section_id)}"
            source_template = str(p.source_template or "").strip()

            # User-facing label: Section Name (Source Document Template).
            # The select value remains the SectionID, so duplicate display names
            # still resolve correctly without exposing IDs in the dropdown.
            label = f"{section_name} ({source_template})" if source_template else section_name

            # If the same label appears more than once, add a small disambiguator
            # but keep the normal case clean.
            if label in seen_labels:
                seen_labels[label] += 1
                label = f"{label} #{seen_labels[label]}"
            else:
                seen_labels[label] = 1

            labels.append(label)
            ids.append(int(p.section_id))

        self.section_option_labels = labels
        self.section_option_ids = ids
        self.section_options = [
            SectionOption(value=str(pid), label=label)
            for pid, label in zip(ids, labels)
        ]

    def load_package_templates(self):
        self.package_templates = []
        self.package_template_labels = []
        self.package_template_ids = []
        self.selected_package_template_label = ""
        self.selected_package_template_id = 0
        self.template_sections = []
        if self.selected_lease_id <= 0:
            return
        try:
            rows = run_query(
                "SELECT lt.LeaseTemplateID, lt.TemplateName, lt.Description, "
                "ISNULL(p.PropertyName, '') AS PropertyName "
                "FROM LeaseTemplates lt "
                "LEFT JOIN Properties p ON lt.PropertyID = p.PropertyID "
                "WHERE ISNULL(lt.IsActive, 1) = 1 "
                "AND (lt.PropertyID IS NULL OR p.PropertyName = ? OR ? = '') "
                "ORDER BY CASE WHEN lt.PropertyID IS NULL THEN 1 ELSE 0 END, lt.TemplateName",
                (self.lease_property_name, self.lease_property_name),
                db=self.db,
            )
        except Exception:
            rows = []
        self.package_templates = [
            LeasePackageTemplateRow(
                template_id=int(r["LeaseTemplateID"]),
                template_name=str(r.get("TemplateName") or ""),
                property_name=str(r.get("PropertyName") or "General / All Properties"),
                description=str(r.get("Description") or ""),
            )
            for r in rows
        ]
        self.package_template_labels = [
            f"{t.template_name} — {t.property_name}" if t.property_name else t.template_name
            for t in self.package_templates
        ]
        self.package_template_ids = [int(t.template_id) for t in self.package_templates]

    def set_selected_package_template(self, label: str):
        self.selected_package_template_label = label
        try:
            idx = self.package_template_labels.index(label)
            self.selected_package_template_id = int(self.package_template_ids[idx])
        except Exception:
            self.selected_package_template_id = 0
        self.form_error = ""
        self.form_success = ""
        self.merge_preview = ""
        self.merge_error = ""
        self.merge_missing_tokens = []
        self.merge_known_tokens = []
        self.load_template_sections()

    def load_template_sections(self):
        self.template_sections = []
        self.selected_section_ids = []
        self._refresh_section_options()
        if self.selected_package_template_id <= 0:
            self.load_available_sections()
            return
        default_col = self._template_default_section_col()
        rows = run_query(
            "SELECT lts.LeaseTemplateSectionID, lts.SortOrder, lts.SectionLabel, "
            "ISNULL(lts.SectionType, '') AS SectionType, "
            f"lts.[{default_col}] AS DefaultSectionID, "
            "ISNULL(lts.IsOptional, 0) AS IsOptional, ISNULL(lts.IsRequired, 0) AS IsRequired "
            "FROM LeaseTemplateSections lts "
            "WHERE lts.LeaseTemplateID = ? AND ISNULL(lts.IsActive, 1) = 1 "
            "ORDER BY lts.SortOrder, lts.LeaseTemplateSectionID",
            (self.selected_package_template_id,),
            db=self.db,
        )
        out = []
        selected_ids = []
        valid_ids = set(int(x) for x in self.section_option_ids)
        for r in rows:
            default_section_id = int(r.get("DefaultSectionID") or 0)
            selected_section_id = default_section_id if default_section_id in valid_ids else 0
            included = bool(selected_section_id > 0 or r.get("IsRequired"))
            if included and selected_section_id > 0:
                selected_ids.append(selected_section_id)
            out.append(LeasePackageTemplateSectionRow(
                template_section_id=int(r["LeaseTemplateSectionID"]),
                sort_order=int(r.get("SortOrder") or 0),
                section_label=str(r.get("SectionLabel") or ""),
                section_type=str(r.get("SectionType") or ""),
                is_optional=bool(r.get("IsOptional")),
                is_required=bool(r.get("IsRequired")),
                default_section_id=default_section_id,
                selected_section_id=selected_section_id,
                selected_section_label=self._section_label(selected_section_id),
                included=included,
            ))
        self.template_sections = out
        self.selected_section_ids = selected_ids
        self.load_available_sections()

    def set_template_section_selected_section(self, template_section_id: int, value: str):
        sid = int(template_section_id)
        try:
            section_id = int(value or 0)
        except Exception:
            section_id = 0
        valid_ids = set(int(pid) for pid in self.section_option_ids)
        if section_id not in valid_ids:
            section_id = 0
        updated = []
        for section in self.template_sections:
            if int(section.template_section_id) == sid:
                # If the user chooses a concrete section from the dropdown, include
                # that template row automatically. If they clear it back to No section,
                # required rows remain included so validation can block generation, while
                # optional rows are excluded.
                updated.append(LeasePackageTemplateSectionRow(
                    template_section_id=section.template_section_id,
                    sort_order=section.sort_order,
                    section_label=section.section_label,
                    section_type=section.section_type,
                    is_optional=section.is_optional,
                    is_required=section.is_required,
                    default_section_id=section.default_section_id,
                    selected_section_id=section_id,
                    selected_section_label=self._section_label(section_id),
                    included=True if (section.is_required or section_id > 0) else False,
                ))
            else:
                updated.append(section)
        self.template_sections = updated
        self._sync_selected_section_ids_from_template()

    def toggle_template_section_included(self, template_section_id: int):
        sid = int(template_section_id)
        updated = []
        for section in self.template_sections:
            included = section.included
            if int(section.template_section_id) == sid:
                included = True if section.is_required else not included
            updated.append(LeasePackageTemplateSectionRow(
                template_section_id=section.template_section_id,
                sort_order=section.sort_order,
                section_label=section.section_label,
                section_type=section.section_type,
                is_optional=section.is_optional,
                is_required=section.is_required,
                default_section_id=section.default_section_id,
                selected_section_id=section.selected_section_id,
                selected_section_label=section.selected_section_label,
                included=included,
            ))
        self.template_sections = updated
        self._sync_selected_section_ids_from_template()

    def _sync_selected_section_ids_from_template(self):
        if self.selected_package_template_id <= 0:
            return
        self.selected_section_ids = [
            int(section.selected_section_id)
            for section in self.template_sections
            if section.included and int(section.selected_section_id or 0) > 0
        ]
        self.load_available_sections()

    def _selected_sections_for_generation(self) -> list[LeasePackageSection]:
        """Resolve included template sections into concrete section content.

        Generation uses one row per included template section. The package
        template is the source of truth. Manual, template-less generation is
        intentionally blocked in generate_package() so validation remains
        consistent.
        """
        if self.selected_package_template_id <= 0 or not self.template_sections:
            return []

        ordered: list[LeasePackageSection] = []

        selected_rows = [
            section for section in sorted(
                self.template_sections,
                key=lambda s: (int(s.sort_order or 0), int(s.template_section_id or 0)),
            )
            if section.included and int(section.selected_section_id or 0) > 0
        ]
        if not selected_rows:
            return []

        selected_section_ids = [int(section.selected_section_id) for section in selected_rows]
        placeholders = ",".join("?" for _ in selected_section_ids)

        section_table = self._lease_section_table()
        section_id_col = self._lease_section_id_col()
        section_name_col = self._lease_section_name_col()
        section_type_col = self._lease_section_type_col()

        rows = run_query(
            f"SELECT p.[{section_id_col}] AS SectionID, "
            f"p.[{section_name_col}] AS SectionName, "
            f"p.[{section_type_col}] AS SectionType, "
            "ISNULL(p.ExhibitCode,'') AS ExhibitCode, "
            "ISNULL(p.ArticleNumber, '') AS ArticleNumber, ISNULL(p.DisplayLabel, '') AS DisplayLabel, "
            "p.StoredFilePath, ISNULL(p.Content, '') AS Content, p.SortOrder, "
            "ISNULL(pr.PropertyName,'') AS PropertyName, "
            "COALESCE(NULLIF(s.TemplateName, ''), 'Standalone') AS TemplateName "
            f"FROM {section_table} p "
            "LEFT JOIN LeaseSourceDocuments s ON p.LeaseSourceDocumentID = s.LeaseSourceDocumentID "
            "LEFT JOIN Properties pr ON s.PropertyID = pr.PropertyID "
            f"WHERE p.[{section_id_col}] IN ({placeholders})",
            tuple(selected_section_ids),
            db=self.db,
        )
        section_by_id = {int(r["SectionID"]): r for r in rows}

        for section in selected_rows:
            sid = int(section.selected_section_id or 0)
            r = section_by_id.get(sid)
            if not r:
                continue
            ordered.append(LeasePackageSection(
                template_section_id=int(section.template_section_id or 0),
                template_section_label=str(section.section_label or ""),
                section_id=int(r["SectionID"]),
                section_name=str(r.get("SectionName") or section.section_label or "Section"),
                section_type=str(r.get("SectionType") or section.section_type or ""),
                exhibit_code=str(r.get("ExhibitCode") or ""),
                article_number=str(r.get("ArticleNumber") or ""),
                display_label=str(r.get("DisplayLabel") or ""),
                property_name=str(r.get("PropertyName") or ""),
                source_template=str(r.get("TemplateName") or "Standalone"),
                sort_order=int(section.sort_order or r.get("SortOrder") or 0),
                file_path=str(r.get("StoredFilePath") or ""),
                content=str(r.get("Content") or ""),
                selected=True,
            ))

        return ordered

    def _expected_included_template_section_count(self) -> int:
        """Count included template rows that should resolve to concrete sections."""
        return sum(
            1
            for section in self.template_sections
            if section.included and int(section.selected_section_id or 0) > 0
        )

    def _validate_duplicate_template_section_ids(self) -> list[str]:
        """Detect repeated selected Section IDs at the template-row level."""
        seen: dict[int, str] = {}
        errors: list[str] = []
        for section in self.template_sections:
            if not section.included:
                continue
            sid = int(section.selected_section_id or 0)
            if sid <= 0:
                continue
            label = section.section_label or f"Template section {section.template_section_id}"
            if sid in seen:
                errors.append(f"{seen[sid]} and {label} both point to section ID {sid}.")
            else:
                seen[sid] = label
        return errors

    def _validate_duplicate_dynamic_template_sections(self, selected: list[LeasePackageSection]) -> list[str]:
        """Stop silent repeated pages when multiple template rows point to the same dynamic section."""
        seen: dict[int, LeasePackageSection] = {}
        errors: list[str] = []
        for section in selected:
            if not str(section.content or "").strip():
                continue
            pid = int(section.section_id or 0)
            if pid <= 0:
                continue
            if pid in seen:
                first = seen[pid]
                first_label = first.template_section_label or first.section_name or f"Template section {first.template_section_id}"
                second_label = section.template_section_label or section.section_name or f"Template section {section.template_section_id}"
                errors.append(
                    f"{first_label} and {second_label} both point to the same tokenized section ID {pid} ({section.section_name})."
                )
            else:
                seen[pid] = section
        return errors

    def toggle_section(self, section_id: int):
        pid = int(section_id)
        if pid in self.selected_section_ids:
            self.selected_section_ids = [x for x in self.selected_section_ids if x != pid]
        else:
            self.selected_section_ids = self.selected_section_ids + [pid]
        self.available_sections = [
            LeasePackageSection(
                section_id=p.section_id,
                section_name=p.section_name,
                section_type=p.section_type,
                exhibit_code=p.exhibit_code,
                article_number=p.article_number,
                display_label=p.display_label,
                property_name=p.property_name,
                source_template=p.source_template,
                sort_order=p.sort_order,
                file_path=p.file_path,
                content=p.content,
                selected=p.section_id in self.selected_section_ids,
            )
            for p in self.available_sections
        ]

    def select_base_and_exhibits(self):
        ids = []
        for p in self.available_sections:
            ptype = (p.section_type or "").strip().lower()
            if ptype in ("base", "base lease", "exhibit", "addendum"):
                ids.append(p.section_id)
        self.selected_section_ids = ids
        self.load_available_sections()

    def clear_selected_sections(self):
        self.selected_section_ids = []
        self.load_available_sections()

    def set_package_name(self, v: str): self.package_name = v
    def set_output_storage_root(self, v: str): self.output_storage_root = v
    def set_package_notes(self, v: str): self.package_notes = v


    def _compose_section_render_text(self, section: LeasePackageSection, rendered_text: str) -> str:
        """Prepend clause metadata as a legal heading when the content does not already include it."""
        body = str(rendered_text or "").strip()
        article = str(getattr(section, "article_number", "") or "").strip()
        label = str(getattr(section, "display_label", "") or "").strip()

        if not body:
            return body
        if not article and not label:
            return body

        body_lower = body.lower()
        if article and body_lower.startswith(article.lower()):
            return body
        if label and body_lower.startswith(label.lower()):
            return body

        if article and label:
            if article.upper().startswith("ARTICLE"):
                heading = f"{article} - {label}"
            elif article.endswith(".") or article.endswith(")") or "." in article:
                heading = f"{article} {label}"
            else:
                heading = f"{article}. {label}"
        else:
            heading = article or label

        return f"{heading}\n\n{body}"

    def _validate_template_section_selections(self) -> list[str]:
        """Return visible errors for included template sections without selected content/PDF."""
        if self.selected_package_template_id <= 0 or not self.template_sections:
            return []
        errors: list[str] = []
        for section in self.template_sections:
            if not section.included:
                continue
            if int(section.selected_section_id or 0) <= 0:
                label = section.section_label or f"Template section {section.template_section_id}"
                errors.append(f"{label}: no selected section")
        return errors

    def _validate_tokens_before_generation(self, selected: list[LeasePackageSection], context: dict) -> list[str]:
        """Validate every tokenized section before any PDF is rendered."""
        errors: list[str] = []
        for p in selected:
            content = str(p.content or "").strip()
            if not content:
                continue
            validation = validate_template_tokens(content, context)
            unresolved = validation.get("missing", []) or []
            if unresolved:
                label = p.template_section_label or p.section_name
                errors.append(f"{label}: " + ", ".join(sorted(set(unresolved))[:10]))
        return errors

    def generate_package(self):
        self.form_error = ""
        self.form_success = ""
        self.last_generated_document_id = 0
        self.last_generated_path = ""

        if self.selected_lease_id <= 0:
            self.form_error = "Select a lease first."
            return
        if not self.package_name.strip():
            self.form_error = "Package file name is required."
            return
        if self.selected_package_template_id <= 0:
            self.form_error = "Select a package template first."
            return

        selection_errors = self._validate_template_section_selections()
        if selection_errors:
            self.form_error = _format_actionable_errors("Fix these sections before generating:", selection_errors)
            return

        duplicate_template_errors = self._validate_duplicate_template_section_ids()
        if duplicate_template_errors:
            self.form_error = _format_actionable_errors("Choose a different section for each duplicate template row:", duplicate_template_errors)
            return

        selected = self._selected_sections_for_generation()
        if not selected:
            self.form_error = "Select at least one lease section."
            return

        expected_count = self._expected_included_template_section_count()
        if len(selected) != expected_count:
            self.form_error = (
                f"Cannot generate. Expected {expected_count} included template sections, "
                f"but only {len(selected)} resolved to active section records. "
                "Refresh the page and reselect the package template."
            )
            return

        duplicate_dynamic_errors = self._validate_duplicate_dynamic_template_sections(selected)
        if duplicate_dynamic_errors:
            self.form_error = _format_actionable_errors("Fix duplicate tokenized sections before generating:", duplicate_dynamic_errors)
            return

        missing_sources = [
            p.section_name for p in selected
            if not str(p.content or "").strip() and not os.path.isfile(p.file_path)
        ]
        if missing_sources:
            self.form_error = _format_actionable_errors("Missing PDF files for these PDF-only sections:", missing_sources)
            return

        temp_pdf_paths: list[str] = []

        try:
            root = normalize_storage_root(self.output_storage_root)
            tenant_id = self._selected_tenant_id()
            context = get_lease_merge_context(tenant_id=tenant_id, lease_id=self.selected_lease_id, db=self.db)

            token_errors = self._validate_tokens_before_generation(selected, context)
            if token_errors:
                self.form_error = _format_actionable_errors("Fix these missing tokens before generating:", token_errors)
                return

            pdf_paths_to_merge: list[str] = []
            rendered_content_by_template_section_id: dict[int, str] = {}
            rendered_content_by_section_id: dict[int, str] = {}

            pending_text_sections: list[str] = []

            def flush_pending_text_sections():
                if not pending_text_sections:
                    return
                temp_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_path = temp_handle.name
                temp_handle.close()
                render_text_sections_to_pdf_file(pending_text_sections.copy(), temp_path)
                temp_pdf_paths.append(temp_path)
                pdf_paths_to_merge.append(temp_path)
                pending_text_sections.clear()

            for idx, p in enumerate(selected, start=1):
                content = str(p.content or "").strip()
                if content:
                    rendered_text, unresolved = render_text_template(content, context)
                    if unresolved:
                        label = p.template_section_label or p.section_name
                        self.form_error = _format_actionable_errors(
                            "Fix these unresolved tokens before generating:",
                            [f"{label}: " + ", ".join(sorted(set(unresolved))[:10])],
                        )
                        return

                    rendered_text = self._compose_section_render_text(p, rendered_text)
                    pending_text_sections.append(rendered_text)
                    if int(p.template_section_id or 0) > 0:
                        rendered_content_by_template_section_id[int(p.template_section_id)] = rendered_text
                    rendered_content_by_section_id[int(p.section_id)] = rendered_text
                else:
                    flush_pending_text_sections()
                    pdf_paths_to_merge.append(p.file_path)

            flush_pending_text_sections()

            if not pdf_paths_to_merge:
                self.form_error = "No valid sections to merge."
                return

            output_path = merge_pdf_files(pdf_paths_to_merge, self.package_name.strip(), root)
            if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError(f"Merged PDF was not created or is empty: {output_path}")
            try:
                merged_page_count = page_count(output_path)
            except Exception as page_ex:
                raise RuntimeError(f"Merged PDF could not be opened for validation: {page_ex}")
            if merged_page_count <= 0:
                raise RuntimeError(f"Merged PDF has no pages: {output_path}")

            filename = os.path.basename(output_path)
            now = datetime.datetime.now()
            notes = self.package_notes.strip()

            run_exec(
                "INSERT INTO LeaseGeneratedDocuments (LeaseID, TenantID, GeneratedFileName, StoredFilePath, GeneratedOn, PackageNotes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.selected_lease_id, tenant_id if tenant_id > 0 else None, filename, output_path, now, notes),
                db=self.db,
            )
            id_rows = run_query(
                "SELECT TOP 1 LeaseGeneratedDocumentID FROM LeaseGeneratedDocuments "
                "WHERE LeaseID = ? AND StoredFilePath = ? ORDER BY LeaseGeneratedDocumentID DESC",
                (self.selected_lease_id, output_path),
                db=self.db,
            )
            generated_id = int(id_rows[0]["LeaseGeneratedDocumentID"]) if id_rows else 0
            if generated_id <= 0:
                raise RuntimeError("Generated document was written to disk, but the database record could not be confirmed.")

            audit_warnings: list[str] = []
            if generated_id:
                audit_table, audit_col = self._generated_section_audit_target()
                for idx, p in enumerate(selected, start=1):
                    if not audit_table or not audit_col:
                        continue
                    try:
                        run_exec(
                            f"INSERT INTO {audit_table} "
                            f"(LeaseGeneratedDocumentID, {audit_col}, SortOrder) VALUES (?, ?, ?)",
                            (generated_id, p.section_id, idx),
                            db=self.db,
                        )
                    except Exception as audit_ex:
                        # LeasePackageSections is the current audit path. Surface audit issues instead of swallowing them.
                        audit_warnings.append(str(audit_ex))

                if self.selected_package_template_id > 0 and self.template_sections:
                    for section in self.template_sections:
                        if not section.included:
                            continue
                        rendered_snapshot = rendered_content_by_template_section_id.get(int(section.template_section_id or 0), "")
                        if not rendered_snapshot:
                            rendered_snapshot = rendered_content_by_section_id.get(int(section.selected_section_id or 0), "")
                        package_ref_col = self._package_section_ref_col()
                        run_exec(
                            "INSERT INTO LeasePackageSections "
                            f"(LeaseGeneratedDocumentID, LeaseTemplateSectionID, SortOrder, IsIncluded, {package_ref_col}, Content, IsDirty, ContentSnapshot) "
                            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                            (
                                generated_id,
                                section.template_section_id,
                                section.sort_order,
                                1 if section.included else 0,
                                section.selected_section_id if section.selected_section_id > 0 else None,
                                rendered_snapshot if rendered_snapshot else None,
                                rendered_snapshot if rendered_snapshot else None,
                            ),
                            db=self.db,
                        )

            self.last_generated_document_id = generated_id
            self.last_generated_path = output_path
            self.form_success = f"Lease package generated: {filename} ({merged_page_count} page(s))"
            if audit_warnings:
                self.form_success += " Audit warning: " + " | ".join(audit_warnings[:3])
            self.load_generated_packages()
        except Exception as ex:
            self.form_error = f"Package generation failed: {ex}"
        finally:
            for temp_path in temp_pdf_paths:
                try:
                    if temp_path and os.path.isfile(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass

    def generate_merge_preview(self):
        """
        Preview the ordered package and token replacement before generating.
        This does not write PDFs or database records.
        """
        self.merge_preview = ""
        self.merge_error = ""
        self.merge_missing_tokens = []
        self.merge_known_tokens = []

        if self.selected_lease_id <= 0:
            self.merge_error = "Select a lease first."
            return
        if self.selected_package_template_id <= 0:
            self.merge_error = "Select a package template first."
            return

        selection_errors = self._validate_template_section_selections()
        if selection_errors:
            self.merge_error = _format_actionable_errors("Preview blocked. Fix these included sections first:", selection_errors)
            return

        selected = self._selected_sections_for_generation()
        if not selected:
            self.merge_error = "Select at least one lease section."
            return

        try:
            tenant_id = self._selected_tenant_id()
            context = get_lease_merge_context(tenant_id=tenant_id, lease_id=self.selected_lease_id, db=self.db)

            preview_sections = []
            all_unresolved: list[str] = []
            all_known_tokens = set()

            for idx, section in enumerate(selected, start=1):
                label = section.template_section_label or section.section_name or f"Section {idx}"
                content = str(section.content or "").strip()
                header = f"--- {idx}. {label} [{section.section_type or 'Section'}] ---"

                if content:
                    rendered_text, unresolved = render_text_template(content, context)
                    validation = validate_template_tokens(content, context)
                    for token in validation.get("tokens", []):
                        all_known_tokens.add(token)
                    all_unresolved.extend(unresolved)
                    rendered_text = self._compose_section_render_text(section, rendered_text)
                    preview_sections.append(header + "\n" + rendered_text)
                else:
                    status = "PDF-only section"
                    if not os.path.isfile(section.file_path):
                        status += " - MISSING FILE"
                        all_unresolved.append(f"{label}: missing PDF file")
                    else:
                        status += f" - {section.file_path}"
                    preview_sections.append(header + "\n" + status)

            self.merge_preview = "\n\n".join(preview_sections)
            self.merge_missing_tokens = sorted(set(all_unresolved))
            self.merge_known_tokens = sorted(all_known_tokens)

            if self.merge_missing_tokens:
                self.merge_error = _format_actionable_errors("Preview found issues:", self.merge_missing_tokens)
            elif not all_known_tokens:
                self.merge_error = "Preview generated. Selected sections are PDF-only, so no merge tokens were found."
        except Exception as ex:
            self.merge_error = f"Merge preview failed: {ex}"

    def load_generated_packages(self):
        if self.selected_lease_id <= 0:
            self.generated_packages = []
            self._reset_generated_review()
            return

        # Load all packages for this lease so version labels stay stable even if
        # the visible history is capped to the latest 10 rows.
        rows = run_query(
            "SELECT d.LeaseGeneratedDocumentID, d.GeneratedFileName, d.StoredFilePath, "
            "d.GeneratedOn, ISNULL(d.PackageNotes, '') AS PackageNotes, "
            "(SELECT COUNT(*) FROM LeasePackageSections lps "
            " WHERE lps.LeaseGeneratedDocumentID = d.LeaseGeneratedDocumentID) AS SectionCount, "
            "(SELECT COUNT(*) FROM LeasePackageSections lps "
            " WHERE lps.LeaseGeneratedDocumentID = d.LeaseGeneratedDocumentID "
            " AND ISNULL(lps.IsDirty, 0) = 1) AS RevisedSectionCount "
            "FROM LeaseGeneratedDocuments d "
            "WHERE d.LeaseID = ? ORDER BY d.GeneratedOn ASC, d.LeaseGeneratedDocumentID ASC",
            (self.selected_lease_id,),
            db=self.db,
        )

        def fmt_dt(v):
            if v is None:
                return ""
            if hasattr(v, "strftime"):
                return v.strftime("%m/%d/%Y %I:%M %p")
            return str(v)

        version_by_id: dict[int, str] = {}
        for idx, r in enumerate(rows, start=1):
            version_by_id[int(r["LeaseGeneratedDocumentID"])] = f"v{idx}"

        latest_id = int(rows[-1]["LeaseGeneratedDocumentID"]) if rows else 0
        display_rows = sorted(
            rows,
            key=lambda r: (r.get("GeneratedOn") or datetime.datetime.min, int(r["LeaseGeneratedDocumentID"])),
            reverse=True,
        )[:10]

        package_rows: list[GeneratedPackageRow] = []
        for r in display_rows:
            generated_id = int(r["LeaseGeneratedDocumentID"])
            file_path = str(r.get("StoredFilePath") or "")
            status = "File OK" if file_path and os.path.isfile(file_path) else "Missing file"
            revised_count = int(r.get("RevisedSectionCount") or 0)
            package_rows.append(GeneratedPackageRow(
                generated_id=generated_id,
                version_label=version_by_id.get(generated_id, ""),
                is_latest=(generated_id == latest_id),
                generated_on=fmt_dt(r.get("GeneratedOn")),
                file_name=str(r.get("GeneratedFileName") or ""),
                file_path=file_path,
                file_status=status,
                revision_status="Contains Revisions" if revised_count > 0 else "Original",
                is_stale=(revised_count > 0),
                section_count=int(r.get("SectionCount") or 0),
                package_notes=str(r.get("PackageNotes") or ""),
                download_url=f"http://localhost:8000/api/lease-generated-pdf?generated_id={generated_id}&db={self.db}",
            ))
        self.generated_packages = package_rows

        current_ids = [int(g.generated_id) for g in package_rows]
        if self.selected_generated_id in current_ids:
            self.select_generated_package(self.selected_generated_id)
        elif package_rows:
            self.select_generated_package(package_rows[0].generated_id)
        else:
            self._reset_generated_review()

    def select_generated_package(self, generated_id: int):
        """Load the saved generated package and its frozen section audit rows."""
        gid = int(generated_id or 0)
        self._reset_generated_review()
        if gid <= 0:
            return

        rows = run_query(
            "SELECT LeaseGeneratedDocumentID, GeneratedFileName, StoredFilePath, GeneratedOn, "
            "ISNULL(PackageNotes, '') AS PackageNotes "
            "FROM LeaseGeneratedDocuments WHERE LeaseGeneratedDocumentID = ?",
            (gid,),
            db=self.db,
        )
        if not rows:
            return

        def fmt_dt(v):
            if v is None:
                return ""
            if hasattr(v, "strftime"):
                return v.strftime("%m/%d/%Y %I:%M %p")
            return str(v)

        r = rows[0]
        path = str(r.get("StoredFilePath") or "")
        self.selected_generated_id = gid
        self.selected_generated_on = fmt_dt(r.get("GeneratedOn"))
        self.selected_generated_file_name = str(r.get("GeneratedFileName") or "")
        self.selected_generated_path = path
        self.selected_generated_status = "File OK" if path and os.path.isfile(path) else "Missing file"
        self.selected_generated_revision_status = ""
        self.selected_generated_is_stale = False
        self.selected_generated_notes = str(r.get("PackageNotes") or "")
        self.selected_generated_version_label = ""
        self.selected_generated_is_latest = False
        for package in self.generated_packages:
            if int(package.generated_id) == gid:
                self.selected_generated_version_label = package.version_label
                self.selected_generated_is_latest = bool(package.is_latest)
                self.selected_generated_revision_status = package.revision_status
                self.selected_generated_is_stale = bool(package.is_stale)
                break

        package_ref_col = self._package_section_ref_col()
        try:
            detail_rows = run_query(
                "SELECT lps.LeasePackageSectionID, lps.SortOrder, ISNULL(lts.SectionLabel, '') AS SectionLabel, "
                "ISNULL(lds.SectionName, '') AS SectionName, ISNULL(lds.SectionType, '') AS SectionType, "
                "COALESCE(NULLIF(sd.TemplateName, ''), 'Standalone') AS SourceTemplate, ISNULL(lps.IsIncluded, 1) AS IsIncluded, "
                "ISNULL(lps.IsDirty, 0) AS IsDirty, "
                "CASE WHEN NULLIF(LTRIM(RTRIM(ISNULL(lps.ContentSnapshot,''))), '') IS NULL "
                "THEN 'PDF/static' ELSE 'ContentSnapshot' END AS ContentStatus, "
                "CASE WHEN NULLIF(LTRIM(RTRIM(ISNULL(lps.Content,''))), '') IS NULL "
                "AND NULLIF(LTRIM(RTRIM(ISNULL(lps.ContentSnapshot,''))), '') IS NULL "
                "THEN 0 ELSE 1 END AS IsEditable "
                "FROM LeasePackageSections lps "
                "LEFT JOIN LeaseTemplateSections lts ON lps.LeaseTemplateSectionID = lts.LeaseTemplateSectionID "
                f"LEFT JOIN LeaseDocumentSections lds ON lps.[{package_ref_col}] = lds.LeaseDocumentSectionID "
                "LEFT JOIN LeaseSourceDocuments sd ON lds.LeaseSourceDocumentID = sd.LeaseSourceDocumentID "
                "WHERE lps.LeaseGeneratedDocumentID = ? "
                "ORDER BY lps.SortOrder, lps.LeasePackageSectionID",
                (gid,),
                db=self.db,
            )
        except Exception as ex:
            self.generated_package_sections = [
                GeneratedPackageSectionRow(
                    package_section_id=0,
                    sort_order=0,
                    section_label="Could not load package sections",
                    section_name=str(ex),
                    section_type="",
                    source_template="",
                    content_status="",
                    included="",
                    revision_status="",
                    editable=False,
                )
            ]
            return

        self.generated_package_sections = [
            GeneratedPackageSectionRow(
                package_section_id=int(row.get("LeasePackageSectionID") or 0),
                sort_order=int(row.get("SortOrder") or 0),
                section_label=str(row.get("SectionLabel") or ""),
                section_name=str(row.get("SectionName") or ""),
                section_type=str(row.get("SectionType") or ""),
                source_template=str(row.get("SourceTemplate") or "Standalone"),
                content_status=str(row.get("ContentStatus") or ""),
                included="Yes" if row.get("IsIncluded") else "No",
                revision_status="Revised" if row.get("IsDirty") else "Original",
                editable=bool(row.get("IsEditable")),
            )
            for row in detail_rows
        ]


    def start_edit_generated_section(self, package_section_id: int):
        """Open the generated section editor for a Content-based section."""
        self.edit_section_error = ""
        self.edit_section_success = ""
        psid = int(package_section_id or 0)
        if psid <= 0:
            self.edit_section_error = "Select a generated section first."
            return
        rows = run_query(
            "SELECT lps.LeasePackageSectionID, ISNULL(lts.SectionLabel, '') AS SectionLabel, "
            "ISNULL(lds.SectionName, '') AS SectionName, "
            "ISNULL(lps.Content, '') AS Content, ISNULL(lps.ContentSnapshot, '') AS ContentSnapshot "
            "FROM LeasePackageSections lps "
            "LEFT JOIN LeaseTemplateSections lts ON lps.LeaseTemplateSectionID = lts.LeaseTemplateSectionID "
            f"LEFT JOIN LeaseDocumentSections lds ON lps.[{self._package_section_ref_col()}] = lds.LeaseDocumentSectionID "
            "WHERE lps.LeasePackageSectionID = ? AND lps.LeaseGeneratedDocumentID = ?",
            (psid, int(self.selected_generated_id or 0)),
            db=self.db,
        )
        if not rows:
            self.edit_section_error = "Generated section not found for the selected package."
            return
        r = rows[0]
        current_content = str(r.get("Content") or "").strip()
        snapshot = str(r.get("ContentSnapshot") or "").strip()
        if not current_content and not snapshot:
            self.edit_section_error = "PDF/static sections cannot be edited here. Edit the source document or package template instead."
            return
        self.editing_package_section_id = psid
        self.editing_package_section_label = str(r.get("SectionLabel") or r.get("SectionName") or f"Section {psid}")
        self.editing_package_section_content = current_content or snapshot

    def cancel_edit_generated_section(self):
        self._reset_section_editor()

    def set_editing_package_section_content(self, v: str):
        self.editing_package_section_content = v

    def save_generated_section_revision(self):
        """Save edited generated content without overwriting ContentSnapshot."""
        self.edit_section_error = ""
        self.edit_section_success = ""
        psid = int(self.editing_package_section_id or 0)
        if psid <= 0:
            self.edit_section_error = "Select a generated section to edit first."
            return
        if not str(self.editing_package_section_content or "").strip():
            self.edit_section_error = "Section content cannot be blank."
            return
        try:
            run_exec(
                "UPDATE LeasePackageSections SET Content = ?, IsDirty = 1 "
                "WHERE LeasePackageSectionID = ? AND LeaseGeneratedDocumentID = ?",
                (self.editing_package_section_content, psid, int(self.selected_generated_id or 0)),
                db=self.db,
            )
            self.edit_section_success = "Section saved as Revised. Regenerate the selected package to update the PDF."
            self._reset_regenerate_preview()
            current_gid = int(self.selected_generated_id or 0)
            if current_gid > 0:
                self.select_generated_package(current_gid)
                self.editing_package_section_id = psid
        except Exception as ex:
            self.edit_section_error = f"Could not save section revision: {ex}"

    def preview_regenerate_selected_generated_package(self):
        """Validate the selected generated package and show what regeneration will use."""
        self.form_error = ""
        self.form_success = ""
        self.regenerate_preview_open = True
        self.regenerate_preview_ready = False
        self.regenerate_preview_text = ""
        self.regenerate_preview_error = ""

        source_generated_id = int(self.selected_generated_id or 0)
        if source_generated_id <= 0:
            self.regenerate_preview_error = "Select a generated package to preview."
            return
        if self.selected_lease_id <= 0:
            self.regenerate_preview_error = "Select a lease first."
            return

        try:
            tenant_id = self._selected_tenant_id()
            context = get_lease_merge_context(tenant_id=tenant_id, lease_id=self.selected_lease_id, db=self.db)
            package_ref_col = self._package_section_ref_col()

            source_rows = run_query(
                "SELECT LeaseGeneratedDocumentID, GeneratedFileName, GeneratedOn "
                "FROM LeaseGeneratedDocuments WHERE LeaseGeneratedDocumentID = ?",
                (source_generated_id,),
                db=self.db,
            )
            if not source_rows:
                self.regenerate_preview_error = "Selected generated package was not found."
                return

            rows = run_query(
                "SELECT lps.LeasePackageSectionID, lps.LeaseTemplateSectionID, lps.SortOrder, "
                "ISNULL(lts.SectionLabel, '') AS SectionLabel, "
                "ISNULL(lps.Content, '') AS Content, ISNULL(lps.ContentSnapshot, '') AS ContentSnapshot, "
                "ISNULL(lps.IsDirty, 0) AS IsDirty, "
                "ISNULL(lds.StoredFilePath, '') AS StoredFilePath, ISNULL(lds.SectionName, '') AS SectionName, "
                "ISNULL(lds.ArticleNumber, '') AS ArticleNumber, ISNULL(lds.DisplayLabel, '') AS DisplayLabel, "
                f"lps.[{package_ref_col}] AS SectionID "
                "FROM LeasePackageSections lps "
                "LEFT JOIN LeaseTemplateSections lts ON lps.LeaseTemplateSectionID = lts.LeaseTemplateSectionID "
                f"LEFT JOIN LeaseDocumentSections lds ON lps.[{package_ref_col}] = lds.LeaseDocumentSectionID "
                "WHERE lps.LeaseGeneratedDocumentID = ? AND ISNULL(lps.IsIncluded, 1) = 1 "
                "ORDER BY lps.SortOrder, lps.LeasePackageSectionID",
                (source_generated_id,),
                db=self.db,
            )
            if not rows:
                self.regenerate_preview_error = "No included package sections were found for the selected generated package."
                return

            errors: list[str] = []
            lines: list[str] = []
            revised_count = 0
            content_count = 0
            static_count = 0

            lines.append(f"Source package: {self.selected_generated_version_label or 'selected version'}")
            lines.append(f"Source file: {self.selected_generated_file_name}")
            lines.append(f"New version will be created. The selected version will not be modified.")
            lines.append("")
            lines.append("Sections to regenerate:")

            for idx, row in enumerate(rows, start=1):
                label = str(row.get("SectionLabel") or row.get("SectionName") or f"Section {idx}")
                content = str(row.get("Content") or "").strip()
                snapshot = str(row.get("ContentSnapshot") or "").strip()
                text_to_render = content or snapshot
                is_revised = bool(row.get("IsDirty"))

                if is_revised:
                    revised_count += 1

                if text_to_render:
                    content_count += 1
                    validation = validate_template_tokens(text_to_render, context)
                    unresolved = validation.get("missing", []) or []
                    if unresolved:
                        errors.append(f"{label}: " + ", ".join(sorted(set(unresolved))[:10]))
                    source_label = "edited Content" if content else "ContentSnapshot"
                    status = "Revised" if is_revised else "Original"
                    lines.append(f"{idx}. {label} - Content - {source_label} - {status}")
                else:
                    static_count += 1
                    file_path = str(row.get("StoredFilePath") or "")
                    if not file_path or not os.path.isfile(file_path):
                        errors.append(f"{label}: missing PDF file")
                    lines.append(f"{idx}. {label} - Static PDF")

            lines.insert(4, f"Included sections: {len(rows)}")
            lines.insert(5, f"Content sections: {content_count}")
            lines.insert(6, f"Static PDF sections: {static_count}")
            lines.insert(7, f"Revised sections: {revised_count}")

            self.regenerate_preview_text = "\n".join(lines)
            if errors:
                self.regenerate_preview_error = _format_actionable_errors("Preview found issues. Regeneration is blocked:", errors)
                return
            self.regenerate_preview_ready = True
        except Exception as ex:
            self.regenerate_preview_error = f"Regenerate preview failed: {ex}"

    def cancel_regenerate_preview(self):
        self._reset_regenerate_preview()

    def regenerate_selected_generated_package(self):
        """Rebuild the selected generated PDF from saved package section rows.

        Regeneration creates a new LeaseGeneratedDocuments row and new
        LeasePackageSections rows. The previously generated record is left
        untouched so version history and ContentSnapshot audit records remain
        intact.
        """
        self.form_error = ""
        self.form_success = ""

        source_generated_id = int(self.selected_generated_id or 0)
        if source_generated_id <= 0:
            self.form_error = "Select a generated package to regenerate."
            return
        if self.selected_lease_id <= 0:
            self.form_error = "Select a lease first."
            return

        temp_pdf_paths: list[str] = []

        try:
            tenant_id = self._selected_tenant_id()
            context = get_lease_merge_context(tenant_id=tenant_id, lease_id=self.selected_lease_id, db=self.db)
            package_ref_col = self._package_section_ref_col()

            # Load source generated package metadata so the new version can carry
            # forward the same LeaseID, TenantID, and PackageNotes.
            source_rows = run_query(
                "SELECT LeaseGeneratedDocumentID, LeaseID, TenantID, GeneratedFileName, "
                "StoredFilePath, GeneratedOn, ISNULL(PackageNotes, '') AS PackageNotes "
                "FROM LeaseGeneratedDocuments WHERE LeaseGeneratedDocumentID = ?",
                (source_generated_id,),
                db=self.db,
            )
            if not source_rows:
                self.form_error = "Selected generated package was not found."
                return
            source_doc = source_rows[0]
            source_lease_id = int(source_doc.get("LeaseID") or self.selected_lease_id)
            source_tenant_id = source_doc.get("TenantID")
            source_notes = str(source_doc.get("PackageNotes") or "")

            rows = run_query(
                "SELECT lps.LeasePackageSectionID, lps.LeaseTemplateSectionID, lps.SortOrder, "
                "ISNULL(lts.SectionLabel, '') AS SectionLabel, "
                "ISNULL(lps.Content, '') AS Content, ISNULL(lps.ContentSnapshot, '') AS ContentSnapshot, "
                "ISNULL(lds.StoredFilePath, '') AS StoredFilePath, ISNULL(lds.SectionName, '') AS SectionName, "
                "ISNULL(lds.ArticleNumber, '') AS ArticleNumber, ISNULL(lds.DisplayLabel, '') AS DisplayLabel, "
                f"lps.[{package_ref_col}] AS SectionID "
                "FROM LeasePackageSections lps "
                "LEFT JOIN LeaseTemplateSections lts ON lps.LeaseTemplateSectionID = lts.LeaseTemplateSectionID "
                f"LEFT JOIN LeaseDocumentSections lds ON lps.[{package_ref_col}] = lds.LeaseDocumentSectionID "
                "WHERE lps.LeaseGeneratedDocumentID = ? AND ISNULL(lps.IsIncluded, 1) = 1 "
                "ORDER BY lps.SortOrder, lps.LeasePackageSectionID",
                (source_generated_id,),
                db=self.db,
            )
            if not rows:
                self.form_error = "No included package sections were found for the selected generated package."
                return

            pdf_paths_to_merge: list[str] = []
            errors: list[str] = []
            new_section_rows: list[dict] = []

            pending_text_sections: list[str] = []

            def flush_pending_text_sections():
                if not pending_text_sections:
                    return
                temp_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_path = temp_handle.name
                temp_handle.close()
                render_text_sections_to_pdf_file(pending_text_sections.copy(), temp_path)
                temp_pdf_paths.append(temp_path)
                pdf_paths_to_merge.append(temp_path)
                pending_text_sections.clear()

            for idx, row in enumerate(rows, start=1):
                label = str(row.get("SectionLabel") or row.get("SectionName") or f"Section {idx}")
                content = str(row.get("Content") or "").strip()
                snapshot = str(row.get("ContentSnapshot") or "").strip()
                text_to_render = content or snapshot
                rendered_text = ""

                if text_to_render:
                    validation = validate_template_tokens(text_to_render, context)
                    unresolved = validation.get("missing", []) or []
                    if unresolved:
                        errors.append(f"{label}: " + ", ".join(sorted(set(unresolved))[:10]))
                        continue

                    rendered_text, unresolved_after_render = render_text_template(text_to_render, context)
                    temp_section_meta = LeasePackageSection(
                        article_number=str(row.get("ArticleNumber") or ""),
                        display_label=str(row.get("DisplayLabel") or ""),
                    )
                    rendered_text = self._compose_section_render_text(temp_section_meta, rendered_text)
                    if unresolved_after_render:
                        errors.append(f"{label}: " + ", ".join(sorted(set(unresolved_after_render))[:10]))
                        continue

                    pending_text_sections.append(rendered_text)
                else:
                    flush_pending_text_sections()
                    file_path = str(row.get("StoredFilePath") or "")
                    if not file_path or not os.path.isfile(file_path):
                        errors.append(f"{label}: missing PDF file")
                    else:
                        pdf_paths_to_merge.append(file_path)

                new_section_rows.append({
                    "lease_template_section_id": row.get("LeaseTemplateSectionID"),
                    "sort_order": row.get("SortOrder"),
                    "section_id": row.get("SectionID"),
                    "rendered_text": rendered_text if rendered_text else None,
                })

            flush_pending_text_sections()

            if errors:
                self.form_error = _format_actionable_errors("Cannot regenerate. Fix these sections first:", errors)
                return
            if not pdf_paths_to_merge:
                self.form_error = "No valid sections to regenerate."
                return

            root = normalize_storage_root(self.output_storage_root)
            next_version_number = self._next_generated_version_number(source_lease_id)
            regen_name = self._build_versioned_package_filename(next_version_number)
            output_path = merge_pdf_files(pdf_paths_to_merge, regen_name, root)

            if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError(f"Regenerated PDF was not created or is empty: {output_path}")
            merged_page_count = page_count(output_path)
            if merged_page_count <= 0:
                raise RuntimeError(f"Regenerated PDF has no pages: {output_path}")

            filename = os.path.basename(output_path)
            now = datetime.datetime.now()

            # Create a new generated package record. Do not update the selected
            # source record.
            run_exec(
                "INSERT INTO LeaseGeneratedDocuments "
                "(LeaseID, TenantID, GeneratedFileName, StoredFilePath, GeneratedOn, PackageNotes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    source_lease_id,
                    source_tenant_id if source_tenant_id is not None else (tenant_id if tenant_id > 0 else None),
                    filename,
                    output_path,
                    now,
                    source_notes,
                ),
                db=self.db,
            )
            id_rows = run_query(
                "SELECT TOP 1 LeaseGeneratedDocumentID FROM LeaseGeneratedDocuments "
                "WHERE LeaseID = ? AND StoredFilePath = ? ORDER BY LeaseGeneratedDocumentID DESC",
                (source_lease_id, output_path),
                db=self.db,
            )
            new_generated_id = int(id_rows[0]["LeaseGeneratedDocumentID"]) if id_rows else 0
            if new_generated_id <= 0:
                raise RuntimeError("Regenerated document was written to disk, but the database record could not be confirmed.")

            # Rebuild package-section audit rows under the new generated ID.
            for section_row in new_section_rows:
                rendered_text = section_row.get("rendered_text")
                run_exec(
                    "INSERT INTO LeasePackageSections "
                    f"(LeaseGeneratedDocumentID, LeaseTemplateSectionID, SortOrder, IsIncluded, {package_ref_col}, Content, IsDirty, ContentSnapshot) "
                    "VALUES (?, ?, ?, 1, ?, ?, 0, ?)",
                    (
                        new_generated_id,
                        section_row.get("lease_template_section_id"),
                        section_row.get("sort_order"),
                        section_row.get("section_id"),
                        rendered_text,
                        rendered_text,
                    ),
                    db=self.db,
                )

            self.last_generated_document_id = new_generated_id
            self.last_generated_path = output_path
            self.form_success = f"New lease package version created: {filename} ({merged_page_count} page(s))"
            self._reset_regenerate_preview()
            self.load_generated_packages()
            self.select_generated_package(new_generated_id)
        except Exception as ex:
            self.form_error = f"Regenerate failed: {ex}"
        finally:
            for temp_path in temp_pdf_paths:
                try:
                    if temp_path and os.path.isfile(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass

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


def section_row(p: LeasePackageSection) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.cond(
                p.selected,
                rx.badge("Selected", color_scheme="green", variant="soft"),
                rx.badge("Available", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(rx.text(p.section_name, size="2", weight="bold")),
        rx.table.cell(rx.text(p.section_type, size="2")),
        rx.table.cell(rx.text(p.exhibit_code, size="2")),
        rx.table.cell(rx.text(p.source_template, size="2", color="#555")),
        rx.table.cell(rx.text(p.property_name, size="2", color="#555")),
        rx.table.cell(rx.text(p.sort_order.to_string(), size="2")),
        rx.table.cell(
            rx.cond(
                p.selected,
                rx.badge("Used by template", color_scheme="green", variant="soft"),
                rx.badge("Reference", color_scheme="gray", variant="soft"),
            )
        ),
        style=rx.cond(p.selected, {"background": "#f0fff4"}, {"background": "white"}),
    )


def section_option_item(option: SectionOption) -> rx.Component:
    return rx.select.item(option.label, value=option.value)


def template_section_row(s: LeasePackageTemplateSectionRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.button(
                rx.cond(s.included, "Yes", "No"),
                on_click=LeasePackageBuilderState.toggle_template_section_included(s.template_section_id),
                size="1",
                variant="soft",
                color_scheme=rx.cond(s.included, "green", "gray"),
                is_disabled=s.is_required,
            )
        ),
        rx.table.cell(rx.text(s.sort_order.to_string(), size="2")),
        rx.table.cell(rx.text(s.section_label, size="2", weight="bold")),
        rx.table.cell(rx.text(s.section_type, size="2")),
        rx.table.cell(
            rx.cond(
                s.is_required,
                rx.badge("Required", color_scheme="blue", variant="soft"),
                rx.badge("Optional", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(
            rx.select.root(
                rx.select.trigger(placeholder="Select section"),
                rx.select.content(
                    rx.foreach(LeasePackageBuilderState.section_options, section_option_item),
                    position="popper",
                ),
                value=s.selected_section_id.to_string(),
                on_change=lambda value: LeasePackageBuilderState.set_template_section_selected_section(s.template_section_id, value),
                size="1",
                width="100%",
            )
        ),
        style=rx.cond(s.included, {"background": "#f0fff4"}, {"background": "white"}),
    )


def generated_row(g: GeneratedPackageRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.badge(g.version_label, color_scheme="blue", variant="soft"),
                rx.cond(
                    g.is_latest,
                    rx.badge("Latest", color_scheme="green", variant="soft"),
                    rx.fragment(),
                ),
                spacing="2",
                align="center",
            )
        ),
        rx.table.cell(rx.text(g.generated_on, size="2")),
        rx.table.cell(rx.text(g.file_name, size="2", weight="bold")),
        rx.table.cell(rx.text(g.section_count.to_string(), size="2")),
        rx.table.cell(
            rx.badge(
                g.file_status,
                color_scheme=rx.cond(g.file_status == "File OK", "green", "red"),
                variant="soft",
            )
        ),
        rx.table.cell(
            rx.vstack(
                rx.badge(
                    g.revision_status,
                    color_scheme=rx.cond(g.revision_status == "Contains Revisions", "orange", "green"),
                    variant="soft",
                ),
                rx.cond(
                    g.is_stale,
                    rx.badge("PDF may be stale", color_scheme="orange", variant="soft"),
                    rx.fragment(),
                ),
                spacing="1",
                align_items="start",
            )
        ),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    "Review",
                    size="1",
                    variant="soft",
                    color_scheme="purple",
                    on_click=LeasePackageBuilderState.select_generated_package(g.generated_id),
                ),
                rx.link(
                    rx.button("Download", size="1", variant="soft", color_scheme="blue"),
                    href=g.download_url,
                    is_external=True,
                ),
                spacing="2",
            )
        ),
        style=rx.cond(
            LeasePackageBuilderState.selected_generated_id == g.generated_id,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
    )

def generated_section_row(row: GeneratedPackageSectionRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.sort_order.to_string(), size="2")),
        rx.table.cell(rx.text(row.section_label, size="2", weight="bold")),
        rx.table.cell(rx.text(row.section_name, size="2")),
        rx.table.cell(rx.text(row.section_type, size="2")),
        rx.table.cell(rx.text(row.source_template, size="2", color="#555")),
        rx.table.cell(rx.badge(row.content_status, color_scheme=rx.cond(row.content_status == "ContentSnapshot", "purple", "gray"), variant="soft")),
        rx.table.cell(rx.badge(row.included, color_scheme=rx.cond(row.included == "Yes", "green", "gray"), variant="soft")),
        rx.table.cell(rx.badge(row.revision_status, color_scheme=rx.cond(row.revision_status == "Revised", "orange", "green"), variant="soft")),
        rx.table.cell(
            rx.cond(
                row.editable,
                rx.button("Edit", size="1", variant="soft", color_scheme="blue", on_click=LeasePackageBuilderState.start_edit_generated_section(row.package_section_id)),
                rx.text("", size="1"),
            )
        ),
        style={"background": "white"},
    )



def regenerate_preview_panel() -> rx.Component:
    return rx.cond(
        LeasePackageBuilderState.regenerate_preview_open,
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Preview regenerated version", size="3", weight="bold", color=BRAND_DARK),
                    rx.spacer(),
                    rx.badge("Creates a new version", color_scheme="blue", variant="soft"),
                    width="100%",
                    align="center",
                ),
                rx.cond(
                    LeasePackageBuilderState.regenerate_preview_error != "",
                    rx.callout(LeasePackageBuilderState.regenerate_preview_error, color_scheme="orange", variant="soft"),
                    rx.fragment(),
                ),
                rx.text_area(
                    value=LeasePackageBuilderState.regenerate_preview_text,
                    width="100%",
                    height="220px",
                ),
                rx.cond(
                    LeasePackageBuilderState.regenerate_preview_ready,
                    rx.callout("Regeneration will create a new version. The selected package will not be overwritten.", color_scheme="blue", variant="soft"),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.cond(
                        LeasePackageBuilderState.regenerate_preview_ready,
                        rx.button("Confirm and create new version", size="2", color_scheme="green", on_click=LeasePackageBuilderState.regenerate_selected_generated_package),
                        rx.fragment(),
                    ),
                    rx.button("Cancel", size="2", variant="ghost", on_click=LeasePackageBuilderState.cancel_regenerate_preview),
                    spacing="3",
                ),
                spacing="3",
                width="100%",
                align_items="start",
            ),
            style={"background": "#f8faff", "border": "1px solid #d8e1f5", "border_left": f"4px solid {BRAND_PRIMARY}", "border_radius": "10px", "padding": "14px", "width": "100%"},
        ),
        rx.fragment(),
    )

def generated_package_review_panel() -> rx.Component:
    return rx.cond(
        LeasePackageBuilderState.selected_generated_id > 0,
        rx.box(
            rx.vstack(
                rx.vstack(
                    rx.hstack(
                        rx.text("Selected generated package", size="3", weight="bold", color=BRAND_DARK),
                        rx.spacer(),
                        width="100%",
                        align="center",
                    ),
                    rx.hstack(
                        rx.cond(
                            LeasePackageBuilderState.selected_generated_version_label != "",
                            rx.badge(LeasePackageBuilderState.selected_generated_version_label, color_scheme="blue", variant="soft"),
                            rx.fragment(),
                        ),
                        rx.cond(
                            LeasePackageBuilderState.selected_generated_is_latest,
                            rx.badge("Latest", color_scheme="green", variant="soft"),
                            rx.fragment(),
                        ),
                        rx.badge(
                            LeasePackageBuilderState.selected_generated_status,
                            color_scheme=rx.cond(LeasePackageBuilderState.selected_generated_status == "File OK", "green", "red"),
                            variant="soft",
                        ),
                        rx.cond(
                            LeasePackageBuilderState.selected_generated_revision_status != "",
                            rx.badge(
                                LeasePackageBuilderState.selected_generated_revision_status,
                                color_scheme=rx.cond(LeasePackageBuilderState.selected_generated_revision_status == "Contains Revisions", "orange", "green"),
                                variant="soft",
                            ),
                            rx.fragment(),
                        ),
                        spacing="2",
                        wrap="wrap",
                        width="100%",
                    ),
                    spacing="2",
                    width="100%",
                    align_items="start",
                ),
                rx.grid(
                    rx.vstack(
                        rx.text("Generated", size="1", color="#666"),
                        rx.text(LeasePackageBuilderState.selected_generated_on, size="2"),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("File", size="1", color="#666"),
                        rx.text(
                            LeasePackageBuilderState.selected_generated_file_name,
                            size="2",
                            weight="bold",
                            style={"white_space": "normal", "overflow_wrap": "anywhere"},
                        ),
                        spacing="1",
                    ),
                    columns="2",
                    spacing="4",
                    width="100%",
                ),
                rx.hstack(
                    rx.link(
                        rx.button("Download selected PDF", size="1", variant="soft", color_scheme="blue"),
                        href=LeasePackageBuilderState.selected_generated_download_url,
                        is_external=True,
                    ),
                    rx.button(
                        "Preview regenerated version",
                        size="1",
                        variant="soft",
                        color_scheme="green",
                        on_click=LeasePackageBuilderState.preview_regenerate_selected_generated_package,
                    ),
                    rx.button(
                        rx.cond(LeasePackageBuilderState.show_selected_generated_path, "Hide path", "Show path"),
                        size="1",
                        variant="ghost",
                        color_scheme="gray",
                        on_click=LeasePackageBuilderState.toggle_selected_generated_path,
                    ),
                    spacing="2",
                    wrap="wrap",
                    width="100%",
                    align="center",
                ),
                rx.cond(
                    LeasePackageBuilderState.show_selected_generated_path,
                    rx.box(
                        rx.text("Stored path", size="1", color="#666"),
                        rx.text(
                            LeasePackageBuilderState.selected_generated_path,
                            size="1",
                            color="#555",
                            style={"white_space": "normal", "word_break": "break-all", "overflow_wrap": "anywhere"},
                        ),
                        style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    LeasePackageBuilderState.selected_generated_is_stale,
                    rx.callout("PDF may be stale because this generated package contains revised sections. Regenerate to create a clean new version.", color_scheme="orange", variant="soft"),
                    rx.fragment(),
                ),
                regenerate_preview_panel(),
                rx.cond(
                    LeasePackageBuilderState.selected_generated_notes != "",
                    rx.box(
                        rx.text("Notes", size="1", color="#666"),
                        rx.text(LeasePackageBuilderState.selected_generated_notes, size="2"),
                        style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                    ),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.text("Frozen section audit", size="3", weight="bold", color=BRAND_DARK),
                    rx.spacer(),
                    rx.button(
                        rx.cond(LeasePackageBuilderState.show_section_audit, "Hide section audit", "View section audit"),
                        size="1",
                        variant="soft",
                        color_scheme="gray",
                        on_click=LeasePackageBuilderState.toggle_section_audit,
                    ),
                    width="100%",
                    align="center",
                ),
                rx.cond(
                    LeasePackageBuilderState.show_section_audit,
                    rx.cond(
                        LeasePackageBuilderState.generated_package_sections.length() > 0,
                        rx.box(
                            rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("Sort"),
                                    rx.table.column_header_cell("Template Section"),
                                    rx.table.column_header_cell("Section"),
                                    rx.table.column_header_cell("Type"),
                                    rx.table.column_header_cell("Source"),
                                    rx.table.column_header_cell("Content"),
                                    rx.table.column_header_cell("Included"),
                                    rx.table.column_header_cell("Status"),
                                    rx.table.column_header_cell("Action"),
                                )
                            ),
                            rx.table.body(rx.foreach(LeasePackageBuilderState.generated_package_sections, generated_section_row)),
                            width="100%",
                            variant="surface",
                        ),
                            style={"width": "100%", "overflow_x": "auto"},
                        ),
                        rx.callout("No LeasePackageSections audit rows found for this generated package.", color_scheme="orange", variant="soft"),
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    LeasePackageBuilderState.editing_package_section_id > 0,
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("Edit generated section", size="3", weight="bold", color=BRAND_DARK),
                                rx.spacer(),
                                rx.badge("Revised on save", color_scheme="orange", variant="soft"),
                                width="100%",
                                align="center",
                            ),
                            rx.text(LeasePackageBuilderState.editing_package_section_label, size="2", weight="bold"),
                            rx.cond(LeasePackageBuilderState.edit_section_error != "", rx.callout.root(rx.callout.text(LeasePackageBuilderState.edit_section_error), color_scheme="red", width="100%"), rx.fragment()),
                            rx.cond(LeasePackageBuilderState.edit_section_success != "", rx.callout.root(rx.callout.text(LeasePackageBuilderState.edit_section_success), color_scheme="green", width="100%"), rx.fragment()),
                            rx.text_area(value=LeasePackageBuilderState.editing_package_section_content, on_change=LeasePackageBuilderState.set_editing_package_section_content, width="100%", height="240px"),
                            rx.hstack(
                                rx.button("Save revision", size="2", color_scheme="green", on_click=LeasePackageBuilderState.save_generated_section_revision),
                                rx.button("Cancel", size="2", variant="ghost", on_click=LeasePackageBuilderState.cancel_edit_generated_section),
                                spacing="3",
                            ),
                            rx.text("Saving marks this section as Revised. It does not overwrite the original ContentSnapshot. Use Regenerate selected PDF to update the PDF file.", size="1", color="#666"),
                            spacing="3",
                            width="100%",
                            align_items="start",
                        ),
                        style={"background": "#fffaf0", "border": "1px solid #f2d28b", "border_left": "4px solid #f59e0b", "border_radius": "10px", "padding": "14px", "width": "100%"},
                    ),
                    rx.fragment(),
                ),
                spacing="3",
                width="100%",
                align_items="start",
            ),
            style={"background": "#f8faff", "border": "1px solid #d8e1f5", "border_left": f"4px solid {BRAND_PRIMARY}", "border_radius": "10px", "padding": "14px", "width": "100%"},
        ),
        rx.callout("Select a generated package to review its saved audit details.", color_scheme="gray", variant="soft"),
    )

def lease_package_builder_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Build Lease Package", size="6", color=BRAND_DARK),
        rx.text(
            "Create a tenant lease PDF from reusable lease sections or a package template.",
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
                rx.text("2. Select package template", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Choose a package template to pre-load ordered lease sections. You can override sections before generating.",
                    size="2",
                    color="#555",
                ),
                rx.cond(
                    LeasePackageBuilderState.package_template_labels.length() > 0,
                    rx.select(
                        LeasePackageBuilderState.package_template_labels,
                        value=LeasePackageBuilderState.selected_package_template_label,
                        on_change=LeasePackageBuilderState.set_selected_package_template,
                        placeholder="Select package template",
                        size="2",
                        width="100%",
                    ),
                    rx.callout("No active package templates found for this lease property. Create or activate a package template in Admin > Lease Documents before generating.", color_scheme="gray", variant="soft"),
                ),
                rx.cond(
                    LeasePackageBuilderState.template_sections.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Include"),
                                rx.table.column_header_cell("Sort"),
                                rx.table.column_header_cell("Template Section"),
                                rx.table.column_header_cell("Type"),
                                rx.table.column_header_cell("Required"),
                                rx.table.column_header_cell("Selected Section"),
                            )
                        ),
                        rx.table.body(rx.foreach(LeasePackageBuilderState.template_sections, template_section_row)),
                        width="100%",
                        variant="surface",
                    ),
                    rx.fragment(),
                ),
                spacing="4",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text("3. Section library reference", size="4", weight="bold", color=BRAND_DARK),
                        rx.text("Hidden by default. Use this only as a read-only reference when you need to confirm which reusable sections are available.", size="2", color="#555"),
                        spacing="1",
                        align_items="start",
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.cond(LeasePackageBuilderState.show_section_library_reference, "Hide section library", "Show section library"),
                        on_click=LeasePackageBuilderState.toggle_section_library_reference,
                        size="2",
                        variant="soft",
                        color_scheme="gray",
                    ),
                    width="100%",
                    align="center",
                ),
                rx.hstack(
                    rx.badge("Template-selected: " + LeasePackageBuilderState.selected_count.to_string(), color_scheme="green", variant="soft"),
                    rx.badge("Available sections: " + LeasePackageBuilderState.available_sections.length().to_string(), color_scheme="blue", variant="soft"),
                    spacing="3",
                    align="center",
                ),
                rx.cond(
                    LeasePackageBuilderState.show_section_library_reference,
                    rx.cond(
                        LeasePackageBuilderState.available_sections.length() > 0,
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("Status"),
                                    rx.table.column_header_cell("Section"),
                                    rx.table.column_header_cell("Type"),
                                    rx.table.column_header_cell("Exhibit"),
                                    rx.table.column_header_cell("Template"),
                                    rx.table.column_header_cell("Property"),
                                    rx.table.column_header_cell("Sort"),
                                    rx.table.column_header_cell("Usage"),
                                )
                            ),
                            rx.table.body(rx.foreach(LeasePackageBuilderState.available_sections, section_row)),
                            width="100%",
                            variant="surface",
                        ),
                        rx.callout("No reusable sections found. Go to Admin > Lease Templates and split a source document into reusable sections first.", color_scheme="gray", variant="soft"),
                    ),
                    rx.text("Section library is hidden to keep the package workflow focused on the selected template.", size="2", color="#666"),
                ),
                spacing="4",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        rx.box(
            rx.vstack(
                rx.text("4. Review package", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Preview rendered content and confirm the ordered section summary before generating.",
                    size="2",
                    color="#555",
                ),
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("Preview", value="preview"),
                        rx.tabs.trigger("Summary", value="summary"),
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.hstack(
                                rx.button(
                                    "Preview package",
                                    on_click=LeasePackageBuilderState.generate_merge_preview,
                                    color_scheme="purple",
                                    size="2",
                                ),
                                rx.badge(
                                    "Known tokens: " + LeasePackageBuilderState.merge_known_tokens.length().to_string(),
                                    color_scheme="blue",
                                    variant="soft",
                                ),
                                rx.badge(
                                    "Missing tokens: " + LeasePackageBuilderState.merge_missing_tokens.length().to_string(),
                                    color_scheme="orange",
                                    variant="soft",
                                ),
                                spacing="3",
                                align="center",
                            ),
                            rx.cond(
                                LeasePackageBuilderState.merge_error != "",
                                rx.callout(LeasePackageBuilderState.merge_error, color_scheme="orange", variant="soft"),
                                rx.fragment(),
                            ),
                            rx.cond(
                                LeasePackageBuilderState.merge_missing_tokens.length() > 0,
                                rx.box(
                                    rx.text("Missing tokens", size="2", weight="bold", color="#9a3412"),
                                    rx.foreach(
                                        LeasePackageBuilderState.merge_missing_tokens,
                                        lambda token: rx.badge(token, color_scheme="orange", variant="soft"),
                                    ),
                                    style={
                                        "display": "flex",
                                        "gap": "8px",
                                        "flex_wrap": "wrap",
                                        "background": "#fff7ed",
                                        "border": "1px solid #fed7aa",
                                        "border_radius": "8px",
                                        "padding": "10px",
                                        "width": "100%",
                                    },
                                ),
                                rx.fragment(),
                            ),
                            rx.text_area(
                                value=LeasePackageBuilderState.merge_preview,
                                placeholder="Merged lease text will appear here if selected sections have tokenized text content.",
                                width="100%",
                                height="360px",
                            ),
                            spacing="4",
                            width="100%",
                            align_items="start",
                        ),
                        value="preview",
                        padding_top="16px",
                    ),
                    rx.tabs.content(
                        rx.vstack(
                            rx.text("Confirm the package structure before generating. This is the ordered list the generator will use.", size="2", color="#555"),
                            rx.cond(
                                LeasePackageBuilderState.package_summary_warning != "",
                                rx.callout(LeasePackageBuilderState.package_summary_warning, color_scheme="orange", variant="soft"),
                                rx.fragment(),
                            ),
                            rx.box(
                                rx.vstack(
                                    rx.foreach(
                                        LeasePackageBuilderState.package_summary_lines,
                                        lambda line: rx.text(line, size="2", color="#333"),
                                    ),
                                    spacing="1",
                                    align_items="start",
                                ),
                                style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "12px", "width": "100%"},
                            ),
                            spacing="3",
                            width="100%",
                            align_items="start",
                        ),
                        value="summary",
                        padding_top="16px",
                    ),
                    default_value="preview",
                    width="100%",
                ),
                spacing="4",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        rx.box(
            rx.vstack(
                rx.text("5. Generate package", size="4", weight="bold", color=BRAND_DARK),
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
                rx.cond(
                    LeasePackageBuilderState.merge_missing_tokens.length() > 0,
                    rx.callout("Preview still has missing tokens. Fix them before generating to avoid a failed package.", color_scheme="orange", variant="soft"),
                    rx.fragment(),
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
                                rx.table.column_header_cell("Version"),
                                rx.table.column_header_cell("Generated"),
                                rx.table.column_header_cell("File"),
                                rx.table.column_header_cell("Sections"),
                                rx.table.column_header_cell("File Status"),
                                rx.table.column_header_cell("Revision"),
                                rx.table.column_header_cell("Actions"),
                            )
                        ),
                        rx.table.body(rx.foreach(LeasePackageBuilderState.generated_packages, generated_row)),
                        width="100%",
                        variant="surface",
                    ),
                    rx.text("No packages generated for this lease yet.", size="2", color="#888"),
                ),
                generated_package_review_panel(),
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
