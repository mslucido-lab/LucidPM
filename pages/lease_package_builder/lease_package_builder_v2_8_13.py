"""
Tenant Lease Package Builder page.

Purpose:
  - Select an existing tenant lease
  - Select reusable lease sections from Admin > Lease Templates
  - Merge selected sections into a final tenant lease package PDF
  - Save generated package metadata back to the selected LeaseID
"""

# v2.8.12 - Adds generated package history/review polish with file status, section count, and package detail review.
# v2.8.11 - Adds pre-generation summary, clearer actionable errors, preview checks, and final output integrity validation.
# v2.8.10 - Package builder polish: template-driven UX cleanup, optional-row auto-include, and stronger generation validation.
# v2.8.13 - Review polish: display generated section audit flag as Status (Original/Revised) instead of Dirty.

from __future__ import annotations

import datetime
import os
import tempfile
from xml.sax.saxutils import escape

import reflex as rx

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.pages.lease_documents_pdf import (
    DEFAULT_DOCUMENT_ROOT,
    merge_pdf_files,
    normalize_storage_root,
    page_count,
    relative_to_root,
    render_text_to_pdf,
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
    generated_on: str = ""
    file_name: str = ""
    file_path: str = ""
    file_status: str = ""
    section_count: int = 0
    package_notes: str = ""
    download_url: str = ""


class GeneratedPackageSectionRow(rx.Base):
    sort_order: int = 0
    section_label: str = ""
    section_name: str = ""
    section_type: str = ""
    source_template: str = ""
    content_status: str = ""
    included: str = ""
    revision_status: str = ""




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
    selected_generated_notes: str = ""
    generated_package_sections: list[GeneratedPackageSectionRow] = []
    last_generated_document_id: int = 0
    last_generated_path: str = ""
    form_error: str = ""
    form_success: str = ""

    # Merge preview results. This does not affect the existing PDF package flow.
    merge_preview: str = ""
    merge_error: str = ""
    merge_missing_tokens: list[str] = []
    merge_known_tokens: list[str] = []

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
        return f"{self.selected_generated_file_name} - {self.selected_generated_status}"

    def _reset_generated_review(self):
        self.selected_generated_id = 0
        self.selected_generated_on = ""
        self.selected_generated_file_name = ""
        self.selected_generated_path = ""
        self.selected_generated_status = ""
        self.selected_generated_notes = ""
        self.generated_package_sections = []

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
            "p.StoredFilePath, ISNULL(p.Content, '') AS Content, p.SortOrder, "
            "ISNULL(pr.PropertyName,'') AS PropertyName, "
            "ISNULL(s.TemplateName, '') AS TemplateName "
            f"FROM {section_table} p "
            "INNER JOIN LeaseSourceDocuments s ON p.LeaseSourceDocumentID = s.LeaseSourceDocumentID "
            "LEFT JOIN Properties pr ON s.PropertyID = pr.PropertyID "
            "WHERE ISNULL(p.IsReusable, 1) = 1 "
            "AND ISNULL(p.IsActive, 1) = 1 "
            "AND ISNULL(s.IsActive, 1) = 1 "
            "AND (s.PropertyID IS NULL OR pr.PropertyName = ? OR ? = '') "
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
                property_name=str(r.get("PropertyName") or ""),
                source_template=str(r.get("TemplateName") or ""),
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
        for p in self.available_sections:
            suffix = []
            if p.exhibit_code:
                suffix.append(f"Exhibit {p.exhibit_code}")
            if p.source_template:
                suffix.append(p.source_template)
            if p.property_name:
                suffix.append(p.property_name)
            # Include the physical Section ID in the visible label. Without this, two
            # sections with the same type/name/source can produce identical labels, and
            # Reflex select changes can resolve back to the first matching label.
            suffix.append(f"ID={int(p.section_id)}")
            extra = f" ({' / '.join(suffix)})" if suffix else ""
            labels.append(f"{p.section_type} | {p.section_name}{extra}")
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
            "p.StoredFilePath, ISNULL(p.Content, '') AS Content, p.SortOrder, "
            "ISNULL(pr.PropertyName,'') AS PropertyName, "
            "ISNULL(s.TemplateName, '') AS TemplateName "
            f"FROM {section_table} p "
            "INNER JOIN LeaseSourceDocuments s ON p.LeaseSourceDocumentID = s.LeaseSourceDocumentID "
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
                property_name=str(r.get("PropertyName") or ""),
                source_template=str(r.get("TemplateName") or ""),
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

                    temp_handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    temp_path = temp_handle.name
                    temp_handle.close()

                    render_text_section_to_pdf_file(rendered_text, temp_path)
                    temp_pdf_paths.append(temp_path)
                    pdf_paths_to_merge.append(temp_path)
                    if int(p.template_section_id or 0) > 0:
                        rendered_content_by_template_section_id[int(p.template_section_id)] = rendered_text
                    rendered_content_by_section_id[int(p.section_id)] = rendered_text
                else:
                    pdf_paths_to_merge.append(p.file_path)

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
        rows = run_query(
            "SELECT TOP 10 d.LeaseGeneratedDocumentID, d.GeneratedFileName, d.StoredFilePath, "
            "d.GeneratedOn, ISNULL(d.PackageNotes, '') AS PackageNotes, "
            "(SELECT COUNT(*) FROM LeasePackageSections lps "
            " WHERE lps.LeaseGeneratedDocumentID = d.LeaseGeneratedDocumentID) AS SectionCount "
            "FROM LeaseGeneratedDocuments d "
            "WHERE d.LeaseID = ? ORDER BY d.GeneratedOn DESC, d.LeaseGeneratedDocumentID DESC",
            (self.selected_lease_id,),
            db=self.db,
        )

        def fmt_dt(v):
            if v is None:
                return ""
            if hasattr(v, "strftime"):
                return v.strftime("%m/%d/%Y %I:%M %p")
            return str(v)

        package_rows: list[GeneratedPackageRow] = []
        for r in rows:
            file_path = str(r.get("StoredFilePath") or "")
            status = "File OK" if file_path and os.path.isfile(file_path) else "Missing file"
            package_rows.append(GeneratedPackageRow(
                generated_id=int(r["LeaseGeneratedDocumentID"]),
                generated_on=fmt_dt(r.get("GeneratedOn")),
                file_name=str(r.get("GeneratedFileName") or ""),
                file_path=file_path,
                file_status=status,
                section_count=int(r.get("SectionCount") or 0),
                package_notes=str(r.get("PackageNotes") or ""),
                download_url=f"http://localhost:8000/api/lease-generated-pdf?generated_id={int(r['LeaseGeneratedDocumentID'])}&db={self.db}",
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
        self.selected_generated_notes = str(r.get("PackageNotes") or "")

        package_ref_col = self._package_section_ref_col()
        try:
            detail_rows = run_query(
                "SELECT lps.SortOrder, ISNULL(lts.SectionLabel, '') AS SectionLabel, "
                "ISNULL(lds.SectionName, '') AS SectionName, ISNULL(lds.SectionType, '') AS SectionType, "
                "ISNULL(sd.TemplateName, '') AS SourceTemplate, ISNULL(lps.IsIncluded, 1) AS IsIncluded, "
                "ISNULL(lps.IsDirty, 0) AS IsDirty, "
                "CASE WHEN NULLIF(LTRIM(RTRIM(ISNULL(lps.ContentSnapshot,''))), '') IS NULL "
                "THEN 'PDF/static' ELSE 'ContentSnapshot' END AS ContentStatus "
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
                    sort_order=0,
                    section_label="Could not load package sections",
                    section_name=str(ex),
                    section_type="",
                    source_template="",
                    content_status="",
                    included="",
                    revision_status="",
                )
            ]
            return

        self.generated_package_sections = [
            GeneratedPackageSectionRow(
                sort_order=int(row.get("SortOrder") or 0),
                section_label=str(row.get("SectionLabel") or ""),
                section_name=str(row.get("SectionName") or ""),
                section_type=str(row.get("SectionType") or ""),
                source_template=str(row.get("SourceTemplate") or ""),
                content_status=str(row.get("ContentStatus") or ""),
                included="Yes" if row.get("IsIncluded") else "No",
                revision_status="Revised" if row.get("IsDirty") else "Original",
            )
            for row in detail_rows
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
        rx.table.cell(rx.text(g.file_path, size="1", color="#666")),
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
        style={"background": "white"},
    )


def generated_package_review_panel() -> rx.Component:
    return rx.cond(
        LeasePackageBuilderState.selected_generated_id > 0,
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("Selected generated package", size="3", weight="bold", color=BRAND_DARK),
                    rx.spacer(),
                    rx.badge(LeasePackageBuilderState.selected_generated_status, color_scheme=rx.cond(LeasePackageBuilderState.selected_generated_status == "File OK", "green", "red"), variant="soft"),
                    rx.link(
                        rx.button("Download selected PDF", size="1", variant="soft", color_scheme="blue"),
                        href=LeasePackageBuilderState.selected_generated_download_url,
                        is_external=True,
                    ),
                    width="100%",
                    align="center",
                ),
                rx.grid(
                    rx.vstack(rx.text("Generated", size="1", color="#666"), rx.text(LeasePackageBuilderState.selected_generated_on, size="2"), spacing="1"),
                    rx.vstack(rx.text("File", size="1", color="#666"), rx.text(LeasePackageBuilderState.selected_generated_file_name, size="2", weight="bold"), spacing="1"),
                    rx.vstack(rx.text("Path", size="1", color="#666"), rx.text(LeasePackageBuilderState.selected_generated_path, size="1", color="#555"), spacing="1"),
                    columns="3",
                    spacing="4",
                    width="100%",
                ),
                rx.cond(
                    LeasePackageBuilderState.selected_generated_notes != "",
                    rx.box(
                        rx.text("Notes", size="1", color="#666"),
                        rx.text(LeasePackageBuilderState.selected_generated_notes, size="2"),
                        style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                    ),
                    rx.fragment(),
                ),
                rx.text("Frozen section audit", size="3", weight="bold", color=BRAND_DARK),
                rx.cond(
                    LeasePackageBuilderState.generated_package_sections.length() > 0,
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
                            )
                        ),
                        rx.table.body(rx.foreach(LeasePackageBuilderState.generated_package_sections, generated_section_row)),
                        width="100%",
                        variant="surface",
                    ),
                    rx.callout("No LeasePackageSections audit rows found for this generated package.", color_scheme="orange", variant="soft"),
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
                rx.text("3. Review available sections", size="4", weight="bold", color=BRAND_DARK),
                rx.text("Generation is package-template driven. Use the table above to include, exclude, or replace sections. This list is reference-only.", size="2", color="#555"),
                rx.hstack(
                    rx.badge("Template-selected: " + LeasePackageBuilderState.selected_count.to_string(), color_scheme="green", variant="soft"),
                    spacing="3",
                    align="center",
                ),
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
                spacing="4",
                width="100%",
                align_items="start",
            ),
            style={"background": "white", "border": "1px solid #e5e7eb", "border_radius": "10px", "padding": "16px", "width": "100%"},
        ),

        rx.box(
            rx.vstack(
                rx.text("4. Pre-generation summary", size="4", weight="bold", color=BRAND_DARK),
                rx.text("Review the package before generating. This is the ordered list the generator will use.", size="2", color="#555"),
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
                rx.text("6. Preview package", size="4", weight="bold", color=BRAND_DARK),
                rx.text(
                    "Preview the ordered package and rendered text sections before generating. PDF-only sections show their file path.",
                    size="2",
                    color="#555",
                ),
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
                                rx.table.column_header_cell("Sections"),
                                rx.table.column_header_cell("Status"),
                                rx.table.column_header_cell("Path"),
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
