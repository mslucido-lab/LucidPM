"""
Lease Documents admin page.

Four-tab layout:
  1. Load        - Upload source PDFs, manage storage root, view ingested source documents.
  2. Parse       - Select a source document, define page ranges, split into sections.
  3. Library     - Edit section content, manage tokens, toggle reusable/active flags.
  4. Templates   - Build and manage lease package templates and their section slots.
"""

# VERSION: 3.0.18
# - v3.0.18: code review fixes: standalone clause flag true, removed stray inline import re.
# - Hotfix: source documents no longer auto-select on initial Lease Documents load.
# - Prevents standalone Text Clause creation from accidentally inheriting the newest source document.
# - Users must explicitly click a source row or Split -> when they want source-backed section creation.
#
# Previously in 3.0.14:
# - Added nullable source-document support for standalone clauses.
# - Added New Standalone Clause workflow and LEFT JOIN loading for standalone clauses.
#
# Previously in 3.0.11:
# - Cleanup: fixed selected-source sections grid header/body alignment after Phase 5 clause metadata additions.
# - Removed inherited Source/Property columns from the selected-source grid and restored correct mappings for Sort, Type, Code, Name, Article, Display Label, and Tag.
#
# Previously in 3.0.10:
# - Hotfix: paste-and-split now detects inline numeric clause headers inside messy PDF copy/paste text.
# - Splits on top-level markers like 9., 10., 11., 12. even when clauses share a page and no blank lines exist.
#
# Previously in 3.0.9:
# - Hardened paste-and-split clause parser for real PDF/Word paste text.
# - Supports repeated numeric clause headers on the same source page and header-only numbers.
# - Moved paste-and-split clause ingestion from Section Library to Parse & Section tab.
# - Section Library is now focused on search, management, and editing existing sections.
# - Parse & Section now owns all initial section creation workflows: PDF split, single Text Clause, and pasted multi-clause split.
#
# Previously in 3.0.7:
# - Added inline clause content editor to Parse tab when Creation mode = Text Clause.
# - Text Clause mode now lets users paste/type content before the section exists in the Library.
# - Preserves paste-and-split tool and overlapping page-reference behavior.
#
# Previously in 3.0.6:
# - Hotfix: restored paste-and-split clause tool event handlers that the v3.0.5 polish accidentally omitted.
# - Preserves Text Clause mode overlap fix from v3.0.5.
#
# Previously in 3.0.5:
# - Phase 5 T1-5 polish: added section creation mode so text clauses can share source pages without triggering PDF page-overlap validation.
# - Text Clause mode treats Start/End page as source-page references, requires Content, and does not split the PDF.
# - PDF Page Split mode preserves existing non-overlapping page extraction behavior.
#
# Previously in 3.0.4:
# - Phase 5 T1-5: added paste-and-split clause entry tool for drafting clause-level sections from pasted lease text.
# - Draft clauses can be loaded into the editor or saved directly as text-backed LeaseDocumentSections.
# - Existing PDF page split workflow is unchanged.
#
# Previously in 3.0.3:
# - Phase 5 T1-4: confirmed and promoted Load tab left-list / right-detail split-panel workflow.
# - Preserves source document selection, metadata save, upload, selected-source sections list, and Split -> navigation.
#
# Previously in 3.0.2:
# - Phase 5 T1-3: added Section Library search/filter/sort controls, grouping column, and metadata badges.
# - Added library row support for clause text search, snapshot usage, and last-updated display.
#
# Previously in 3.0.1:
# - Phase 5 T1-2: added clause-level section metadata fields: ClauseTag, ArticleNumber, DisplayLabel.
# - Added section content character count and Copy From Snapshot helper in the Section Library editor.
# - Phase 5 baseline versioning: advanced Lease Documents module from 2.8.x to 3.0.0.
# - T1-1 schema migration completed externally and is now also guarded in _ensure_schema.
# - Hardened section delete/archive so reference checks detect live column names across
#   LeaseGeneratedDocumentSections and LeasePackageSections instead of assuming one name.
# - Clarified cross-document Section Library behavior and package-template section selection.
# - Load tab bottom grid is selected-source only again and refreshes from self.sections.
# - Template default-section options are explicitly source-document agnostic and include source/property context in labels.
# - Selecting a source document resets parse/edit state to prevent stale section edits from targeting the wrong source.
#
# Previously in 2.8.3:
# - Fixed Package Templates slot edit/delete handlers so each row reliably passes its own LeaseTemplateSectionID.
# - Added explicit active package-template selector for slot editing so selected template state cannot drop to 0.
#   Section Library shows all active sections across all source documents (not scoped to
#   selected_source_document_id). Parse tab continues to use sections (scoped).
# - SectionRow gains source_doc field (sd.TemplateName) for Library tab grouping column.
# - _load_all_sections() called alongside _load_sections() in every mutation method.
#
# Previously in 2.8.0:
# - Refactored from linear scroll to 4-tab layout (Load / Parse & Section / Section Library / Package Templates).
# - Fixed IsOptional / IsRequired mutual-exclusion -> sec_inclusion_mode ("Required"|"Optional"|"Inactive").
# - Removed duplicate SECTION_TYPES assignment.
# - Active tab tracked in state (admin_lease_tab).

# ═══════════════════════════════════════════════════════════════════════════════
# HANDOFF NOTES FOR CHATGPT - READ BEFORE TOUCHING THIS FILE
# ═══════════════════════════════════════════════════════════════════════════════
#
# WHAT THIS FILE IS:
#   Admin page for the Lease Document module. Reflex frontend. 4-tab layout.
#   Part of LucidPM - a property management CRM for small commercial landlords.
#   Stack: Reflex (Python) + SQL Server (pyodbc). Local desktop deployment.
#
# CURRENT STATE (v2.8.1 - ready for cleanup):
#   ✅ Tab 1 Load        - upload source PDFs, manage storage root
#   ✅ Tab 2 Parse       - split source PDF into named sections by page range
#   ✅ Tab 3 Library     - all-sections view, content/token editor
#   ✅ Tab 4 Templates   - package template builder, section slot manager
#   ✅ IsOptional/IsRequired replaced by sec_inclusion_mode ("Required"|"Optional"|"Inactive")
#   ✅ all_sections / _load_all_sections() for cross-document Library tab
#
# PHASE 1 - CLEANUP (do this first, before any new features):
#   These issues were identified in code review. Fix in this order:
#
#   🔴 Issue 1 - lease_merge.py: Token validation must block generation on unresolved
#      tokens. Current behaviour silently passes through {{UnresolvedToken}} strings.
#      Fix: after token replacement pass, scan output for remaining {{...}} patterns.
#      If any found, raise a descriptive error - do NOT generate the PDF.
#
#   🔴 Issue 2 - lease_merge.py or lease_package_builder.py: Audit INSERT into
#      LeaseGeneratedDocumentSections. Verify the column name LeaseDocumentSectionID
#      exists in SSMS before assuming. Current code has `except Exception: pass`
#      swallowing failures silently. Replace with warning log at minimum.
#
#   🟡 Issue 3 - lease_merge.py: Delete save_generated_lease_snapshot(). Dead code.
#      References wrong table (GeneratedLeaseDocuments vs LeaseGeneratedDocuments).
#
#   🟡 Issue 4 - lease_package_builder.py: Delete _lease_section_text_column(). Dead
#      code with a live DB call that is never invoked. Remove entirely.
#
#   🟡 Issue 5 - lease_package_builder.py: Block generation when no template is
#      selected. Add guard at top of generate_package() - check selected_template_id
#      before doing any DB work.
#
#   🟢 Issue 6 - lease_merge.py: Misplaced docstring in _selected_sections_for_generation().
#      Move it to the top of the function, not inside the body.
#
#   🟢 Issue 7 - lease_documents_pdf.py: Rename pieces_folder() -> sections_folder().
#      "Piece" naming was retired - "Section" is the standard term project-wide.
#
#   🟢 Issue 8 - THIS FILE, _tab_templates(): Add a resizable vertical splitter between
#      the template list (left column) and the template detail + section slot editor
#      (right column). Currently a static rx.grid(columns="2"). Replace with a split
#      panel that lets the user drag the divider to resize.
#      Implementation approach in Reflex: use rx.hstack with a narrow drag handle div
#      between two rx.box containers. Track split position in state as
#      `template_tab_split_pct: int = 35` (percent for left panel, default 35%).
#      The drag handle should be ~6px wide, cursor "col-resize", with a visible
#      separator line. Left panel min-width ~200px, right panel takes the remainder.
#      Wire onMouseDown on the handle to a JS-driven drag - use rx.script or inline
#      JavaScript via rx.html - since Reflex state round-trips are too slow for smooth
#      drag. Store the final width in state only on mouseup so it persists across
#      re-renders. This is the same pattern used on the Tenants split panel.
#
#   🟢 Issue 9 - THIS FILE, _tab_load(): Refactor Load tab to left-list / right-detail
#      split panel layout - consistent with Tenants and Work Items patterns in the app.
#      LEFT PANEL: scrollable list of ingested source documents. Each row shows template
#      name, category, page count, active badge. Clicking a row selects it and loads
#      its metadata into the right panel. "New Source Document" button at top of list
#      clears the form for a fresh upload (new mode). "Split ->" button on each row
#      selects the document and jumps to the Parse tab (go_to_parse_tab already exists).
#      RIGHT PANEL: two stacked sections -
#        (1) Metadata form: template name, property, category, version, notes, active
#            checkbox, Save Metadata button. Shows selected doc metadata in edit mode,
#            blank fields in new mode.
#        (2) Upload zone: PDF upload component. In edit mode show a note that uploading
#            a new file will replace the existing source PDF. In new mode show the
#            standard upload prompt. Upload button only active when template name is set.
#      Use same resizable splitter pattern as Issue 8 (JS drag, state on mouseup).
#      State var for split: `load_tab_split_pct: int = 30` (left panel default 30%).
#
#   🟢 Issue 10 - Storage root: move out of Load tab into Admin Settings screen.
#      REASON: storage_root is a deployment-time setting, not a runtime decision.
#      Changing it mid-use is dangerous - existing LeaseDocumentSections rows have
#      StoredFilePath and StorageRoot baked in pointing at the old location. A mid-stream
#      change would split file references across two paths with no reconciliation.
#      LOAD TAB: replace the storage root input with a read-only display pill -
#        "Files stored in: C:\TenantCRM\LeaseDocuments  [Edit in Settings]"
#      ADMIN SETTINGS SCREEN: add storage_root as a named setting in AppSettings table
#        (SettingKey = 'LeaseDocumentStorageRoot'). Settings screen should also surface
#        EnableDeveloperTools (already in AppSettings). Add a migration warning banner
#        when the storage root is changed: "Changing this path does not move existing
#        files. Ensure all files are physically moved to the new location before saving."
#      _load_settings() already reads from AppSettings - extend it to also load
#        storage_root from the new key. Fall back to DEFAULT_DOCUMENT_ROOT if not set.
#
# PHASE 2 - PHASE 3 TEXT INGESTION (after cleanup is verified):
#   Add PDF text extraction UI to Tab 2 (Parse & Section).
#   The Parse tab (_tab_parse function, bottom of this file) should gain a side-by-side
#   panel: extracted PDF text on the left, the split form on the right.
#   Entry point: _tab_parse() component function - this is where new UI goes.
#   Text extraction: use pypdf (already in requirements). Extract per-page text from
#   self.selected_source_path. Store extracted text in a new state var
#   `extracted_page_text: str` - normalise to str, no datetime objects.
#   Trigger extraction when a source document is selected (select_source_document method).
#
# CRITICAL REFLEX GOTCHAS (this version is 0.8.15):
#   - Use rx.cond() not Python `if` inside component functions - Python if on a Var crashes.
#   - rx.select crashes if value="" on initial render. Guard with rx.cond(list.length() > 0, ...).
#   - list[dict] state vars with datetime objects cause "dispatch is not a function".
#     Normalise ALL values to str/None before storing in state.
#   - rx.Base is deprecated in 0.8.15 - current code still uses it and works but will
#     break in 0.9.0. Do not add new rx.Base usage; flag for future migration.
#   - Cannot use lambda with arguments in rx.foreach row components in all Reflex versions.
#     Use named event handlers where possible.
#   - PDF download URLs must target localhost:8000 explicitly (frontend on 3000, backend 8000).
#
# KEY FILES IN THIS MODULE (all need cleanup work):
#   lease_documents_v2_8_1.py   - this file (admin page)
#   lease_merge.py               - token replacement engine, Issues 1/2/3/6
#   lease_package_builder.py     - package generation pipeline, Issues 4/5
#   lease_documents_pdf.py       - PDF split/merge utilities, Issue 7
#
# DATABASE (SQL Server - TenantCRM / TenantCRM_Test):
#   LeaseSourceDocuments         - uploaded source PDFs
#   LeaseDocumentSections        - split sections (Content field holds tokenised text)
#   LeaseTemplates               - package template headers
#   LeaseTemplateSections        - ordered section slots within a template
#   LeasePackageSections         - per-tenant section instances (IsDirty, ContentSnapshot)
#   LeaseGeneratedDocuments      - generated package records
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import datetime
import os
import re
from typing import Optional

import reflex as rx

from LucidPM_Reflex.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
from LucidPM_Reflex.components.sidebar import page_shell
from LucidPM_Reflex.lease_merge import extract_tokens
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
SECTION_TYPES = ["Base Lease", "Exhibit", "Addendum", "Rules", "Guaranty", "Other"]

# Inclusion mode options for template sections - replaces the IsOptional/IsRequired bool pair.
INCLUSION_MODES = ["Required", "Optional", "Inactive"]
SECTION_CREATION_MODES = ["PDF Page Split", "Text Clause"]

PROPERTY_GENERAL = "General / All Properties"


def _safe_int(value, default: int = 0) -> int:
    """Convert DB/Reflex values to int without Decimal/float/string quirks."""
    try:
        if value is None:
            return int(default)
        text = str(value).strip()
        if not text:
            return int(default)
        return int(text.split(".")[0])
    except Exception:
        try:
            return int(default)
        except Exception:
            return 0


# ── Data transfer objects ─────────────────────────────────────────────────────

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


class SectionRow(rx.Base):
    section_id: int = 0
    source_doc: str = ""       # sd.TemplateName - shown in Library tab grouping column
    source_property: str = ""
    section_type: str = ""
    section_name: str = ""
    clause_tag: str = ""
    article_number: str = ""
    display_label: str = ""
    exhibit_code: str = ""
    pages: str = ""
    sort_order: int = 0
    reusable: str = ""
    active: str = ""
    content_status: str = ""
    content_text: str = ""
    updated_on: str = ""
    has_snapshot: str = ""


class LeaseTemplateRow(rx.Base):
    template_id: int = 0
    template_name: str = ""
    property_name: str = ""
    description: str = ""
    active: str = ""
    section_count: int = 0


class LeaseTemplateSectionRow(rx.Base):
    section_id: int = 0
    sort_order: int = 0
    section_label: str = ""
    section_type: str = ""
    default_section_label: str = ""
    inclusion_mode: str = ""   # "Required" | "Optional" | "Inactive"
    active: str = ""


class ReusableSectionOption(rx.Base):
    section_id: int = 0
    label: str = ""


class DraftClauseRow(rx.Base):
    draft_id: int = 0
    article_number: str = ""
    display_label: str = ""
    clause_tag: str = ""
    preview: str = ""
    content: str = ""


# ── State ─────────────────────────────────────────────────────────────────────

class LeaseDocumentState(AppState):

    # Active tab: "load" | "parse" | "library" | "templates"
    admin_lease_tab: str = "load"
    load_tab_split_pct: int = 30
    template_tab_split_pct: int = 35

    property_names: list[str] = [PROPERTY_GENERAL]
    property_ids: list[int] = [0]

    source_documents: list[SourceDocumentRow] = []
    selected_source_document_id: int = 0
    selected_source_page_count: int = 0
    selected_source_path: str = ""

    # Parse tab - scoped to selected_source_document_id
    sections: list[SectionRow] = []
    # Library tab - all active sections across all source documents
    all_sections: list[SectionRow] = []
    library_search: str = ""
    library_type_filter: str = "All"
    library_tag_filter: str = "All"
    library_status_filter: str = "All"
    library_group_by: str = "Clause Tag"
    library_sort_by: str = "Article Number"
    library_sort_desc: bool = False

    # Paste-and-split clause tool
    paste_clause_text: str = ""
    draft_clauses: list[DraftClauseRow] = []
    draft_clause_count: str = "0 draft clause(s)"

    # Package template manager
    lease_templates: list[LeaseTemplateRow] = []
    lease_template_labels: list[str] = []
    lease_template_ids: list[int] = []
    selected_template_label: str = ""
    selected_template_id: int = 0
    slot_template_id: int = 0
    lease_template_sections: list[LeaseTemplateSectionRow] = []

    lt_template_mode: str = "new"
    lt_template_name: str = ""
    lt_property: str = PROPERTY_GENERAL
    lt_description: str = ""
    lt_is_active: bool = True

    reusable_section_labels: list[str] = ["(No default section)"]
    reusable_section_ids: list[int] = [0]

    section_mode: str = "new"
    selected_section_id: int = 0
    sec_label: str = ""
    sec_sort_order: str = "10"
    sec_default_section_label: str = "(No default section)"
    sec_section_type: str = "Base Lease"
    # Replaces sec_is_optional + sec_is_required booleans.
    sec_inclusion_mode: str = "Required"
    sec_is_active: bool = True

    # Tab 1 - Load: source document upload form
    f_template_name: str = ""
    f_property: str = PROPERTY_GENERAL
    f_document_category: str = "Base Lease"
    f_template_version: str = "1.0"
    f_notes: str = ""
    f_is_active: bool = True

    # Tab 1 - storage root
    storage_root: str = DEFAULT_DOCUMENT_ROOT
    local_pdf_path: str = ""
    selected_upload_file_name: str = ""
    developer_tools_enabled: bool = False

    # Tab 2 - Parse: section split form
    p_creation_mode: str = "PDF Page Split"
    p_section_type: str = "Base Lease"
    p_section_name: str = ""
    p_exhibit_code: str = ""
    p_start_page: str = "1"
    p_end_page: str = "1"
    p_sort_order: str = "10"
    p_is_reusable: bool = True
    p_is_active: bool = True
    p_clause_tag: str = ""
    p_article_number: str = ""
    p_display_label: str = ""
    p_content: str = ""
    p_is_standalone_clause: bool = False
    editing_section_id: int = 0

    form_error: str = ""
    form_success: str = ""

    # ── Computed vars ──────────────────────────────────────────────────────────

    @rx.var
    def destination_preview(self) -> str:
        return template_folder(self.storage_root, self.f_property, self.f_document_category)

    @rx.var
    def selected_source_summary(self) -> str:
        if not self.selected_source_document_id:
            return "No source document selected."
        return f"Source #{self.selected_source_document_id} - {self.selected_source_page_count} pages"

    @rx.var
    def has_source_document(self) -> bool:
        return self.selected_source_document_id > 0

    @rx.var
    def is_text_clause_mode(self) -> bool:
        return self.p_creation_mode == "Text Clause"

    @rx.var
    def will_save_without_source_document(self) -> bool:
        return self.p_creation_mode == "Text Clause" and self.p_is_standalone_clause

    @rx.var
    def parse_mode_help_text(self) -> str:
        if self.p_creation_mode == "Text Clause":
            if self.p_is_standalone_clause:
                return "Create a standalone text-backed clause. No source document ID will be saved."
            return "Create a text-backed clause from the selected source document. Page numbers are references only, so multiple clauses may share the same page."
        return "Split a non-overlapping PDF page range from the selected source PDF and save it as a reusable section."

    @rx.var
    def parse_save_button_label(self) -> str:
        if self.editing_section_id > 0:
            return "Update Section"
        if self.p_creation_mode == "Text Clause":
            return "Save Text Clause"
        return "Split and Save Section"

    @rx.var
    def parse_page_label(self) -> str:
        return "Source page reference" if self.p_creation_mode == "Text Clause" else "Start page"

    @rx.var
    def parse_end_page_label(self) -> str:
        return "End page reference" if self.p_creation_mode == "Text Clause" else "End page"

    @rx.var
    def detected_section_tokens(self) -> str:
        tokens = extract_tokens(self.p_content)
        return ", ".join(tokens) if tokens else "None detected"

    @rx.var
    def section_content_character_count(self) -> str:
        return f"{len(self.p_content or ''):,} characters"

    @rx.var
    def section_display_heading(self) -> str:
        label = str(self.p_display_label or self.p_section_name or "").strip()
        article = str(self.p_article_number or "").strip()
        tag = str(self.p_clause_tag or "").strip()
        parts = []
        if article:
            parts.append(article)
        if label:
            parts.append(label)
        if tag:
            parts.append(f"Tag: {tag}")
        return " | ".join(parts) if parts else "Selected section"

    @rx.var
    def filtered_library_sections(self) -> list[SectionRow]:
        q = str(self.library_search or "").strip().lower()
        result: list[SectionRow] = []
        for row in self.all_sections:
            if self.library_type_filter != "All" and row.section_type != self.library_type_filter:
                continue
            if self.library_status_filter != "All" and row.active != self.library_status_filter:
                continue
            if self.library_tag_filter == "Tagged" and not str(row.clause_tag or "").strip():
                continue
            if self.library_tag_filter == "Untagged" and str(row.clause_tag or "").strip():
                continue
            haystack = " ".join([
                str(row.source_doc or ""), str(row.source_property or ""), str(row.section_type or ""),
                str(row.section_name or ""), str(row.display_label or ""), str(row.clause_tag or ""),
                str(row.article_number or ""), str(row.content_text or ""),
            ]).lower()
            if q and q not in haystack:
                continue
            result.append(row)

        def sort_key(row: SectionRow):
            if self.library_group_by == "Clause Tag":
                group = str(row.clause_tag or "(No tag)").lower()
            elif self.library_group_by == "Section Type":
                group = str(row.section_type or "").lower()
            elif self.library_group_by == "Active Status":
                group = str(row.active or "").lower()
            else:
                group = ""
            if self.library_sort_by == "Display Label":
                main = str(row.display_label or row.section_name or "").lower()
            elif self.library_sort_by == "Updated On":
                main = str(row.updated_on or "")
            elif self.library_sort_by == "Clause Tag":
                main = str(row.clause_tag or "").lower()
            elif self.library_sort_by == "Source Document":
                main = str(row.source_doc or "").lower()
            else:
                main = str(row.article_number or "").lower().zfill(8)
            return (group, main, int(row.sort_order or 0), int(row.section_id or 0))

        result.sort(key=sort_key, reverse=bool(self.library_sort_desc))
        return result

    @rx.var
    def library_result_count(self) -> str:
        return f"{len(self.filtered_library_sections):,} section(s) shown"

    @rx.var
    def paste_clause_character_count(self) -> str:
        return f"{len(self.paste_clause_text or ''):,} characters pasted"

    @rx.var
    def has_draft_clauses(self) -> bool:
        return len(self.draft_clauses) > 0

    @rx.var
    def active_template_select_value(self) -> str:
        """Always return a valid value for the package-template rx.select.

        Reflex 0.8.x can reset state when an rx.select renders with value=""
        while options exist. This computed value protects the select during
        rerenders before on_load or row selection has fully hydrated state.
        """
        label = str(self.selected_template_label or "").strip()
        if label and label in self.lease_template_labels:
            return label
        if self.lease_template_labels:
            return self.lease_template_labels[0]
        return ""

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_load(self):
        self.form_error = ""
        self.form_success = ""
        self._ensure_schema()
        self._load_properties()
        self._load_settings()
        self._load_source_documents()
        self._load_all_sections()
        self._load_reusable_section_options()
        self._load_lease_templates()

    def reload_on_db_change(self):
        self.source_documents = []
        self.sections = []
        self.all_sections = []
        self.selected_source_document_id = 0
        self.selected_source_page_count = 0
        self.selected_source_path = ""
        self.lease_templates = []
        self.lease_template_labels = []
        self.lease_template_ids = []
        self.selected_template_label = ""
        self.selected_template_id = 0
        self.slot_template_id = 0
        self.lease_template_sections = []
        self.form_error = ""
        self.form_success = ""
        self._ensure_schema()
        self._load_properties()
        self._load_settings()
        self._load_source_documents()
        self._load_all_sections()
        self._load_reusable_section_options()
        self._load_lease_templates()

    # ── Schema inspection helpers ──────────────────────────────────────────────

    def _table_columns(self, table_name: str) -> set[str]:
        try:
            rows = run_query(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?",
                (table_name,),
                db=self.db,
            )
            return {str(r.get("COLUMN_NAME") or "") for r in rows}
        except Exception:
            return set()

    def _first_existing_column(self, table_name: str, candidates: list[str]) -> str:
        cols = self._table_columns(table_name)
        for candidate in candidates:
            if candidate in cols:
                return candidate
        return ""

    # ── Tab navigation ─────────────────────────────────────────────────────────

    def set_tab(self, tab: str):
        self.admin_lease_tab = tab
        self.form_error = ""
        self.form_success = ""

    def go_to_parse_tab(self, source_document_id: int):
        """Select a source document and jump to the Parse tab."""
        self.select_source_document(source_document_id)
        self.admin_lease_tab = "parse"

    def new_source_document(self):
        """Clear the Load tab form for a new source document upload."""
        self.selected_source_document_id = 0
        self.selected_source_page_count = 0
        self.selected_source_path = ""
        self.sections = []
        self.editing_section_id = 0
        self.f_template_name = ""
        self.f_property = PROPERTY_GENERAL
        self.f_document_category = "Base Lease"
        self.f_template_version = "1.0"
        self.f_notes = ""
        self.f_is_active = True
        self.local_pdf_path = ""
        self.selected_upload_file_name = ""
        self.p_creation_mode = "PDF Page Split"
        self.p_start_page = "1"
        self.p_end_page = "1"
        self.p_sort_order = "10"
        self.p_section_name = ""
        self.p_exhibit_code = ""
        self.p_clause_tag = ""
        self.p_article_number = ""
        self.p_display_label = ""
        self.p_content = ""
        self.p_is_standalone_clause = False
        self.form_error = ""
        self.form_success = ""

    # ── Schema ─────────────────────────────────────────────────────────────────

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
                    StoredFilePath NVARCHAR(1000) NULL,
                    PageCount INT NULL,
                    DocumentStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_Status DEFAULT ('Uploaded'),
                    UploadedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseSourceDocuments_UploadedOn DEFAULT (SYSDATETIME()),
                    Notes NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeaseDocumentSections', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseDocumentSections (
                    LeaseDocumentSectionID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseSourceDocumentID INT NULL,
                    LeaseID INT NULL,
                    SectionType NVARCHAR(50) NOT NULL,
                    SectionName NVARCHAR(255) NOT NULL,
                    ExhibitCode NVARCHAR(50) NULL,
                    StartPage INT NULL,
                    EndPage INT NULL,
                    StoredFilePath NVARCHAR(1000) NOT NULL,
                    StorageRoot NVARCHAR(1000) NULL,
                    RelativePath NVARCHAR(1000) NULL,
                    SortOrder INT NOT NULL CONSTRAINT DF_LeaseDocumentSections_SortOrder DEFAULT (0),
                    IsReusable BIT NOT NULL CONSTRAINT DF_LeaseDocumentSections_IsReusable DEFAULT (1),
                    IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentSections_IsActive DEFAULT (1),
                    CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseDocumentSections_CreatedOn DEFAULT (SYSDATETIME()),
                    Content NVARCHAR(MAX) NULL,
                    Notes NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeaseGeneratedDocuments', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseGeneratedDocuments (
                    LeaseGeneratedDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    TenantID INT NULL,
                    LeaseID INT NULL,
                    GeneratedFileName NVARCHAR(255) NOT NULL,
                    StoredFilePath NVARCHAR(1000) NOT NULL,
                    GeneratedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseGeneratedDocuments_GeneratedOn DEFAULT (SYSDATETIME()),
                    PackageNotes NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeaseTemplates', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseTemplates (
                    LeaseTemplateID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    TemplateName NVARCHAR(255) NOT NULL,
                    PropertyID INT NULL,
                    Description NVARCHAR(MAX) NULL,
                    TemplateVersion INT NOT NULL CONSTRAINT DF_LeaseTemplates_TemplateVersion DEFAULT (1),
                    IsActive BIT NOT NULL CONSTRAINT DF_LeaseTemplates_IsActive DEFAULT (1),
                    CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseTemplates_CreatedOn DEFAULT (SYSDATETIME()),
                    UpdatedOn DATETIME2 NULL
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeaseTemplateSections', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeaseTemplateSections (
                    LeaseTemplateSectionID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseTemplateID INT NOT NULL,
                    SortOrder INT NOT NULL CONSTRAINT DF_LeaseTemplateSections_SortOrder DEFAULT (0),
                    SectionLabel NVARCHAR(255) NOT NULL,
                    DefaultSectionID INT NULL,
                    IsOptional BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsOptional DEFAULT (0),
                    IsRequired BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsRequired DEFAULT (0),
                    SectionType NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseTemplateSections_SectionType DEFAULT ('dynamic'),
                    IsActive BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsActive DEFAULT (1)
                )
            END
            """,
            """
            IF OBJECT_ID('dbo.LeasePackageSections', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.LeasePackageSections (
                    LeasePackageSectionID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    LeaseGeneratedDocumentID INT NOT NULL,
                    LeaseTemplateSectionID INT NOT NULL,
                    SortOrder INT NOT NULL CONSTRAINT DF_LeasePackageSections_SortOrder DEFAULT (0),
                    IsIncluded BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsIncluded DEFAULT (1),
                    SectionID INT NULL,
                    Content NVARCHAR(MAX) NULL,
                    IsDirty BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsDirty DEFAULT (0),
                    ContentSnapshot NVARCHAR(MAX) NULL
                )
            END
            """,
            """
            IF COL_LENGTH('dbo.LeaseGeneratedDocuments', 'TenantID') IS NULL ALTER TABLE dbo.LeaseGeneratedDocuments ADD TenantID INT NULL;

            IF COL_LENGTH('dbo.LeaseTemplates', 'PropertyID') IS NULL ALTER TABLE dbo.LeaseTemplates ADD PropertyID INT NULL;
            IF COL_LENGTH('dbo.LeaseTemplates', 'Description') IS NULL ALTER TABLE dbo.LeaseTemplates ADD Description NVARCHAR(MAX) NULL;
            IF COL_LENGTH('dbo.LeaseTemplates', 'TemplateVersion') IS NULL ALTER TABLE dbo.LeaseTemplates ADD TemplateVersion INT NOT NULL CONSTRAINT DF_LeaseTemplates_TemplateVersion2 DEFAULT (1);
            IF COL_LENGTH('dbo.LeaseTemplates', 'IsActive') IS NULL ALTER TABLE dbo.LeaseTemplates ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseTemplates_IsActive2 DEFAULT (1);
            IF COL_LENGTH('dbo.LeaseTemplates', 'CreatedOn') IS NULL ALTER TABLE dbo.LeaseTemplates ADD CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseTemplates_CreatedOn2 DEFAULT (SYSDATETIME());
            IF COL_LENGTH('dbo.LeaseTemplates', 'UpdatedOn') IS NULL ALTER TABLE dbo.LeaseTemplates ADD UpdatedOn DATETIME2 NULL;

            IF COL_LENGTH('dbo.LeaseTemplateSections', 'LeaseTemplateID') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD LeaseTemplateID INT NOT NULL CONSTRAINT DF_LeaseTemplateSections_LeaseTemplateID DEFAULT (0);
            IF COL_LENGTH('dbo.LeaseTemplateSections', 'SortOrder') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD SortOrder INT NOT NULL CONSTRAINT DF_LeaseTemplateSections_SortOrder2 DEFAULT (0);
            IF COL_LENGTH('dbo.LeaseTemplateSections', 'SectionLabel') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD SectionLabel NVARCHAR(255) NOT NULL CONSTRAINT DF_LeaseTemplateSections_SectionLabel DEFAULT ('Section');
            IF COL_LENGTH('dbo.LeaseTemplateSections', 'DefaultSectionID') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD DefaultSectionID INT NULL;
            IF COL_LENGTH('dbo.LeaseTemplateSections', 'IsOptional') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD IsOptional BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsOptional2 DEFAULT (0);
            IF COL_LENGTH('dbo.LeaseTemplateSections', 'IsRequired') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD IsRequired BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsRequired2 DEFAULT (0);
            IF COL_LENGTH('dbo.LeaseTemplateSections', 'SectionType') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD SectionType NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseTemplateSections_SectionType2 DEFAULT ('dynamic');
            IF COL_LENGTH('dbo.LeaseTemplateSections', 'IsActive') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsActive2 DEFAULT (1);

            IF COL_LENGTH('dbo.LeasePackageSections', 'LeaseGeneratedDocumentID') IS NULL ALTER TABLE dbo.LeasePackageSections ADD LeaseGeneratedDocumentID INT NOT NULL CONSTRAINT DF_LeasePackageSections_GeneratedDocumentID DEFAULT (0);
            IF COL_LENGTH('dbo.LeasePackageSections', 'LeaseTemplateSectionID') IS NULL ALTER TABLE dbo.LeasePackageSections ADD LeaseTemplateSectionID INT NOT NULL CONSTRAINT DF_LeasePackageSections_TemplateSectionID DEFAULT (0);
            IF COL_LENGTH('dbo.LeasePackageSections', 'SortOrder') IS NULL ALTER TABLE dbo.LeasePackageSections ADD SortOrder INT NOT NULL CONSTRAINT DF_LeasePackageSections_SortOrder2 DEFAULT (0);
            IF COL_LENGTH('dbo.LeasePackageSections', 'IsIncluded') IS NULL ALTER TABLE dbo.LeasePackageSections ADD IsIncluded BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsIncluded2 DEFAULT (1);
            IF COL_LENGTH('dbo.LeasePackageSections', 'SectionID') IS NULL ALTER TABLE dbo.LeasePackageSections ADD SectionID INT NULL;
            IF COL_LENGTH('dbo.LeasePackageSections', 'Content') IS NULL ALTER TABLE dbo.LeasePackageSections ADD Content NVARCHAR(MAX) NULL;
            IF COL_LENGTH('dbo.LeasePackageSections', 'IsDirty') IS NULL ALTER TABLE dbo.LeasePackageSections ADD IsDirty BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsDirty2 DEFAULT (0);
            IF COL_LENGTH('dbo.LeasePackageSections', 'ContentSnapshot') IS NULL ALTER TABLE dbo.LeasePackageSections ADD ContentSnapshot NVARCHAR(MAX) NULL;
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
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'StorageRoot') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD StorageRoot NVARCHAR(1000) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'RelativePath') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD RelativePath NVARCHAR(1000) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'IsActive') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentSections_IsActive2 DEFAULT (1);
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'Content') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD Content NVARCHAR(MAX) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'ClauseTag') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD ClauseTag NVARCHAR(100) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'ArticleNumber') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD ArticleNumber NVARCHAR(20) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'DisplayLabel') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD DisplayLabel NVARCHAR(255) NULL;
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'UpdatedOn') IS NULL ALTER TABLE dbo.LeaseDocumentSections ADD UpdatedOn DATETIME2 NULL;
            IF COL_LENGTH('dbo.LeaseDocumentSections', 'LeaseSourceDocumentID') IS NOT NULL
                AND COLUMNPROPERTY(OBJECT_ID('dbo.LeaseDocumentSections'), 'LeaseSourceDocumentID', 'AllowsNull') = 0
            BEGIN
                ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN LeaseSourceDocumentID INT NULL;
                ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN StartPage INT NULL;
                ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN EndPage INT NULL;
                ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN StoredFilePath NVARCHAR(1000) NULL;
            END
            IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM dbo.SchemaChangeLog WHERE ScriptName = 'phase5_sprint2_nullable_source_document.sql')
            BEGIN
                INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
                VALUES (
                    'phase5_sprint2_nullable_source_document.sql',
                    GETDATE(),
                    SUSER_SNAME(),
                    'Made LeaseSourceDocumentID, StartPage, EndPage, StoredFilePath nullable on LeaseDocumentSections to support standalone clauses not derived from a source PDF.'
                );
            END
            """,
        ]
        for sql in statements:
            run_exec(sql, db=self.db)
        run_exec("""
        IF OBJECT_ID('dbo.AppSettings', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.AppSettings (
                SettingKey NVARCHAR(100) NOT NULL PRIMARY KEY,
                SettingValue NVARCHAR(1000) NULL,
                UpdatedOn DATETIME2 NOT NULL CONSTRAINT DF_AppSettings_UpdatedOn DEFAULT (SYSDATETIME())
            );
        END
        """, db=self.db)
        run_exec("""
        IF NOT EXISTS (SELECT 1 FROM dbo.AppSettings WHERE SettingKey = 'EnableDeveloperTools')
        BEGIN
            INSERT INTO dbo.AppSettings (SettingKey, SettingValue, UpdatedOn)
            VALUES ('EnableDeveloperTools', '0', SYSDATETIME());
        END
        IF NOT EXISTS (SELECT 1 FROM dbo.AppSettings WHERE SettingKey = 'LeaseDocumentStorageRoot')
        BEGIN
            INSERT INTO dbo.AppSettings (SettingKey, SettingValue, UpdatedOn)
            VALUES ('LeaseDocumentStorageRoot', N'C:\\Dell Inspirion\\TenantCRM\\LeaseDocuments', SYSDATETIME());
        END
        """, db=self.db)
        try:
            run_exec("ALTER TABLE dbo.LeaseSourceDocuments ALTER COLUMN LeaseID INT NULL", db=self.db)
        except Exception:
            pass
        try:
            run_exec("ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN LeaseID INT NULL", db=self.db)
        except Exception:
            pass

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _fmt_date(self, val) -> str:
        if val is None:
            return ""
        if isinstance(val, datetime.datetime):
            return val.strftime("%m/%d/%Y %H:%M")
        if isinstance(val, datetime.date):
            return val.strftime("%m/%d/%Y")
        return str(val)

    def _load_settings(self):
        try:
            rows = run_query(
                "SELECT SettingKey, SettingValue FROM AppSettings "
                "WHERE SettingKey IN ('EnableDeveloperTools', 'LeaseDocumentStorageRoot')",
                db=self.db,
            )
            settings = {str(r.get("SettingKey") or ""): str(r.get("SettingValue") or "") for r in rows}
            self.developer_tools_enabled = settings.get("EnableDeveloperTools", "0").strip() in ("1", "true", "True", "yes", "Yes")
            self.storage_root = settings.get("LeaseDocumentStorageRoot", "").strip() or DEFAULT_DOCUMENT_ROOT
        except Exception:
            self.developer_tools_enabled = False
            self.storage_root = self.storage_root or DEFAULT_DOCUMENT_ROOT

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

    @staticmethod
    def _inclusion_mode_from_bools(is_optional: bool, is_required: bool, is_active: bool) -> str:
        """Derive a single inclusion mode string from the legacy DB bool columns."""
        if not is_active:
            return "Inactive"
        if is_required:
            return "Required"
        return "Optional"

    @staticmethod
    def _bools_from_inclusion_mode(mode: str):
        """Return (is_optional, is_required, is_active) for a given inclusion mode."""
        if mode == "Required":
            return (False, True, True)
        if mode == "Optional":
            return (True, False, True)
        # "Inactive" or unrecognised
        return (False, False, False)

    # ── Source documents ───────────────────────────────────────────────────────

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
        # Do not auto-select the first source document.
        # Standalone clause authoring depends on selected_source_document_id staying 0
        # until the user explicitly chooses a source document or clicks Split ->.
        if self.selected_source_document_id:
            current_ids = {int(row.source_document_id) for row in self.source_documents}
            if int(self.selected_source_document_id) in current_ids:
                self._load_sections()
            else:
                self.selected_source_document_id = 0
                self.selected_source_page_count = 0
                self.selected_source_path = ""
                self.sections = []
        else:
            self.sections = []

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
        # Storage root is a deployment setting loaded from AppSettings.
        # Do not let an older source document row change the active root.
        self.f_notes = str(r.get("Notes") or "")
        self.f_is_active = bool(r.get("IsActive"))
        self.selected_source_path = str(r.get("StoredFilePath") or "")
        try:
            self.selected_source_page_count = int(r.get("PageCount") or 0)
        except Exception:
            self.selected_source_page_count = 0

        # Important: switching source documents must reset the parse/edit form.
        # Page ranges are only meaningful within the currently selected source PDF.
        # Without this reset, stale section edits can accidentally be saved against
        # the wrong source document and trigger false page-overlap errors.
        self.editing_section_id = 0
        self.p_creation_mode = "PDF Page Split"
        self.p_section_type = str(r.get("DocumentCategory") or "Base Lease")
        self.p_section_name = ""
        self.p_exhibit_code = ""
        self.p_start_page = "1"
        self.p_end_page = str(max(self.selected_source_page_count, 1))
        self.p_sort_order = str(self._next_section_sort_order())
        self.p_is_reusable = True
        self.p_is_active = True
        self.p_clause_tag = ""
        self.p_article_number = ""
        self.p_display_label = ""
        self.p_content = ""
        self.p_is_standalone_clause = False
        self._load_sections()
        self._load_all_sections()
        self._load_reusable_section_options()

    def save_source_document_metadata(self):
        self.form_error = ""
        self.form_success = ""
        if not self.selected_source_document_id:
            self.form_error = "Select a source document first."
            return
        if not self.f_template_name.strip():
            self.form_error = "Template name is required."
            return
        try:
            run_exec(
                "UPDATE LeaseSourceDocuments SET TemplateName=?, PropertyID=?, DocumentCategory=?, "
                "TemplateVersion=?, StorageRoot=?, Notes=?, IsActive=? "
                "WHERE LeaseSourceDocumentID=?",
                (
                    self.f_template_name.strip(),
                    self._selected_property_id(),
                    self.f_document_category,
                    self.f_template_version.strip(),
                    self.storage_root.strip() or DEFAULT_DOCUMENT_ROOT,
                    self.f_notes,
                    1 if self.f_is_active else 0,
                    int(self.selected_source_document_id),
                ),
                db=self.db,
            )
            self.form_success = "Source document metadata saved."
            self._load_source_documents()
            self._load_sections()
            self._load_all_sections()
        except Exception as ex:
            self.form_error = f"Could not save metadata: {ex}"

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
        self.selected_upload_file_name = str(getattr(file, "filename", "") or getattr(file, "name", "") or "Selected PDF")
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
            self.form_success = f"Uploaded {self.selected_upload_file_name} with {pc} pages. Switch to Parse & Section to split it."
            self._load_source_documents()
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
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
            self.form_success = f"Imported source PDF with {pc} pages. Switch to Parse & Section to split it."
            self._load_source_documents()
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
        except Exception as ex:
            self.form_error = f"Import failed: {ex}"

    # ── Sections (Parse tab) ───────────────────────────────────────────────────

    def _load_sections(self):
        if not self.selected_source_document_id:
            self.sections = []
            return
        rows = run_query(
            "SELECT p.LeaseDocumentSectionID AS SectionID, p.SectionType, p.SectionName, p.ExhibitCode, "
            "ISNULL(p.ClauseTag, '') AS ClauseTag, ISNULL(p.ArticleNumber, '') AS ArticleNumber, ISNULL(p.DisplayLabel, '') AS DisplayLabel, "
            "p.StartPage, p.EndPage, p.SortOrder, p.IsReusable, p.IsActive, "
            "sd.PropertyID, ISNULL(sd.TemplateName, '') AS TemplateName, "
            "ISNULL(p.Content, '') AS ContentText, COALESCE(p.UpdatedOn, p.CreatedOn) AS UpdatedOn, 'No' AS HasSnapshot, "
            "CASE WHEN NULLIF(LTRIM(RTRIM(ISNULL(p.Content,''))), '') IS NULL THEN 'No' ELSE 'Yes' END AS HasContent "
            "FROM LeaseDocumentSections p "
            "INNER JOIN LeaseSourceDocuments sd ON p.LeaseSourceDocumentID = sd.LeaseSourceDocumentID "
            "WHERE p.LeaseSourceDocumentID = ? ORDER BY p.SortOrder, p.LeaseDocumentSectionID",
            (self.selected_source_document_id,), db=self.db,
        )
        self.sections = [
            SectionRow(
                section_id=int(r["SectionID"]),
                source_doc=str(r.get("TemplateName") or ""),
                source_property=self._property_name_for_id(r.get("PropertyID")),
                section_type=str(r.get("SectionType") or ""),
                section_name=str(r.get("SectionName") or ""),
                clause_tag=str(r.get("ClauseTag") or ""),
                article_number=str(r.get("ArticleNumber") or ""),
                display_label=str(r.get("DisplayLabel") or ""),
                exhibit_code=str(r.get("ExhibitCode") or ""),
                pages=f"{int(r.get('StartPage') or 0)}-{int(r.get('EndPage') or 0)}",
                sort_order=int(r.get("SortOrder") or 0),
                reusable="Yes" if r.get("IsReusable") else "No",
                active="Yes" if r.get("IsActive") else "No",
                content_status=str(r.get("HasContent") or "No"),
                content_text=str(r.get("ContentText") or ""),
                updated_on=self._fmt_date(r.get("UpdatedOn")),
                has_snapshot=str(r.get("HasSnapshot") or "No"),
            )
            for r in rows
        ]

    def _load_all_sections(self):
        """Load all sections across every source document for the Library tab."""
        try:
            snapshot_ref_col = self._first_existing_column(
                "LeasePackageSections",
                ["SectionID", "LeaseDocumentSectionID"],
            )
            snapshot_select = "'No' AS HasSnapshot"
            if snapshot_ref_col:
                snapshot_select = (
                    "CASE WHEN EXISTS (SELECT 1 FROM LeasePackageSections lps "
                    f"WHERE lps.[{snapshot_ref_col}] = p.LeaseDocumentSectionID) "
                    "THEN 'Yes' ELSE 'No' END AS HasSnapshot"
                )
            rows = run_query(
                "SELECT p.LeaseDocumentSectionID AS SectionID, p.SectionType, p.SectionName, p.ExhibitCode, "
                "ISNULL(p.ClauseTag, '') AS ClauseTag, ISNULL(p.ArticleNumber, '') AS ArticleNumber, ISNULL(p.DisplayLabel, '') AS DisplayLabel, "
                "p.StartPage, p.EndPage, p.SortOrder, p.IsReusable, p.IsActive, ISNULL(p.Content, '') AS ContentText, "
                "COALESCE(p.UpdatedOn, p.CreatedOn) AS UpdatedOn, sd.PropertyID, ISNULL(sd.TemplateName, '') AS TemplateName, "
                "CASE WHEN NULLIF(LTRIM(RTRIM(ISNULL(p.Content,''))), '') IS NULL THEN 'No' ELSE 'Yes' END AS HasContent, "
                f"{snapshot_select} "
                "FROM LeaseDocumentSections p "
                "LEFT JOIN LeaseSourceDocuments sd ON p.LeaseSourceDocumentID = sd.LeaseSourceDocumentID "
                "WHERE (sd.LeaseSourceDocumentID IS NULL OR ISNULL(sd.IsActive, 1) = 1) "
                "ORDER BY sd.TemplateName, p.SortOrder, p.LeaseDocumentSectionID",
                db=self.db,
            )
        except Exception:
            rows = []
        self.all_sections = [
            SectionRow(
                section_id=int(r["SectionID"]),
                source_doc=str(r.get("TemplateName") or ""),
                source_property=self._property_name_for_id(r.get("PropertyID")),
                section_type=str(r.get("SectionType") or ""),
                section_name=str(r.get("SectionName") or ""),
                clause_tag=str(r.get("ClauseTag") or ""),
                article_number=str(r.get("ArticleNumber") or ""),
                display_label=str(r.get("DisplayLabel") or ""),
                exhibit_code=str(r.get("ExhibitCode") or ""),
                pages=f"{int(r.get('StartPage') or 0)}-{int(r.get('EndPage') or 0)}",
                sort_order=int(r.get("SortOrder") or 0),
                reusable="Yes" if r.get("IsReusable") else "No",
                active="Yes" if r.get("IsActive") else "No",
                content_status=str(r.get("HasContent") or "No"),
                content_text=str(r.get("ContentText") or ""),
                updated_on=self._fmt_date(r.get("UpdatedOn")),
                has_snapshot=str(r.get("HasSnapshot") or "No"),
            )
            for r in rows
        ]

    def _next_exhibit_code(self) -> str:
        rows = run_query(
            "SELECT ExhibitCode FROM LeaseDocumentSections WHERE LeaseSourceDocumentID = ? AND SectionType = 'Exhibit'",
            (self.selected_source_document_id,), db=self.db,
        ) if self.selected_source_document_id else []
        used = {str(r.get("ExhibitCode") or "").replace("Exhibit", "").strip().upper() for r in rows}
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if letter not in used:
                return letter
        return ""

    def _next_section_sort_order(self) -> int:
        rows = run_query(
            "SELECT ISNULL(MAX(SortOrder), 0) AS MaxSort FROM LeaseDocumentSections WHERE LeaseSourceDocumentID = ?",
            (self.selected_source_document_id,), db=self.db,
        ) if self.selected_source_document_id else []
        try:
            return int(rows[0].get("MaxSort") or 0) + 10
        except Exception:
            return 10

    def _validate_section_range(self, start: int, end: int, ignore_section_id: int = 0, require_non_overlap: bool = True) -> bool:
        if start < 1 or end < start or end > self.selected_source_page_count:
            self.form_error = f"Page range must be between 1 and {self.selected_source_page_count}."
            return False
        if not require_non_overlap:
            return True
        ignore_id = int(ignore_section_id or 0)
        rows = run_query(
            "SELECT LeaseDocumentSectionID AS SectionID, StartPage, EndPage, SectionName "
            "FROM LeaseDocumentSections "
            "WHERE LeaseSourceDocumentID = ? AND IsActive = 1 AND LeaseDocumentSectionID <> ?",
            (self.selected_source_document_id, ignore_id), db=self.db,
        )
        for r in rows:
            existing_start = int(r.get("StartPage") or 0)
            existing_end = int(r.get("EndPage") or 0)
            if start <= existing_end and end >= existing_start:
                self.form_error = f"Page range overlaps existing section: {r.get('SectionName')}."
                return False
        return True

    def _is_metadata_only_section_update(self, section_id: int, start: int, end: int) -> bool:
        if not section_id:
            return False
        rows = run_query(
            "SELECT StartPage, EndPage FROM LeaseDocumentSections WHERE LeaseDocumentSectionID = ?",
            (int(section_id),), db=self.db,
        )
        if not rows:
            return False
        try:
            return int(rows[0].get("StartPage") or 0) == int(start) and int(rows[0].get("EndPage") or 0) == int(end)
        except Exception:
            return False

    def reset_section_form(self):
        self.editing_section_id = 0
        self.p_creation_mode = "PDF Page Split"
        self.p_section_type = "Base Lease"
        self.p_section_name = ""
        self.p_exhibit_code = ""
        self.p_start_page = "1"
        self.p_end_page = str(max(self.selected_source_page_count, 1))
        self.p_sort_order = str(self._next_section_sort_order())
        self.p_is_reusable = True
        self.p_is_active = True
        self.p_clause_tag = ""
        self.p_article_number = ""
        self.p_display_label = ""
        self.p_content = ""
        self.p_is_standalone_clause = False
        self.form_error = ""
        self.form_success = ""

    def new_standalone_clause(self):
        """Open the section editor for a standalone clause with no source document."""
        self.editing_section_id = 0
        self.selected_source_document_id = 0
        self.selected_source_page_count = 0
        self.selected_source_path = ""
        self.sections = []
        self.p_creation_mode = "Text Clause"
        self.p_section_type = "Base Lease"
        self.p_section_name = ""
        self.p_exhibit_code = ""
        self.p_start_page = ""
        self.p_end_page = ""
        self.p_sort_order = "10"
        self.p_is_reusable = True
        self.p_is_active = True
        self.p_clause_tag = ""
        self.p_article_number = ""
        self.p_display_label = ""
        self.p_content = ""
        self.p_is_standalone_clause = True
        self.form_error = ""
        self.form_success = ""
        self.admin_lease_tab = "parse"

    def detach_current_clause_from_source(self):
        """Keep current Text Clause form values but force the next save to be standalone."""
        self.p_creation_mode = "Text Clause"
        self.p_is_standalone_clause = True
        self.selected_source_document_id = 0
        self.selected_source_page_count = 0
        self.selected_source_path = ""
        self.sections = []
        self.p_start_page = ""
        self.p_end_page = ""
        self.form_error = ""
        self.form_success = "This clause is detached from any source document. Saving will leave LeaseSourceDocumentID blank."

    def edit_section(self, section_id: int):
        self.form_error = ""
        self.form_success = ""
        rows = run_query(
            "SELECT LeaseDocumentSectionID AS SectionID, SectionType, SectionName, ExhibitCode, "
            "ISNULL(ClauseTag, '') AS ClauseTag, ISNULL(ArticleNumber, '') AS ArticleNumber, ISNULL(DisplayLabel, '') AS DisplayLabel, "
            "LeaseSourceDocumentID, StartPage, EndPage, SortOrder, IsReusable, IsActive, StoredFilePath, Content FROM LeaseDocumentSections WHERE LeaseDocumentSectionID = ?",
            (int(section_id),), db=self.db,
        )
        if not rows:
            self.form_error = "Section not found."
            return
        r = rows[0]
        self.editing_section_id = int(r["SectionID"])
        stored_path = str(r.get("StoredFilePath") or "")
        source_doc_id = int(r.get("LeaseSourceDocumentID") or 0)
        self.p_is_standalone_clause = source_doc_id <= 0
        self.p_creation_mode = "Text Clause" if str(r.get("Content") or "").strip() and (self.p_is_standalone_clause or not stored_path or stored_path == str(self.selected_source_path or "")) else "PDF Page Split"
        self.p_section_type = str(r.get("SectionType") or "Base Lease")
        self.p_section_name = str(r.get("SectionName") or "")
        self.p_exhibit_code = str(r.get("ExhibitCode") or "")
        self.p_start_page = str(int(r.get("StartPage") or 1))
        self.p_end_page = str(int(r.get("EndPage") or 1))
        self.p_sort_order = str(int(r.get("SortOrder") or 0))
        self.p_is_reusable = bool(r.get("IsReusable"))
        self.p_is_active = bool(r.get("IsActive"))
        self.p_clause_tag = str(r.get("ClauseTag") or "")
        self.p_article_number = str(r.get("ArticleNumber") or "")
        self.p_display_label = str(r.get("DisplayLabel") or "")
        self.p_content = str(r.get("Content") or "")

    def delete_section(self, section_id: int):
        self.form_error = ""
        self.form_success = ""
        section_id_int = int(section_id)

        section_pk_col = self._first_existing_column(
            "LeaseDocumentSections",
            ["LeaseDocumentSectionID", "SectionID"],
        )
        if not section_pk_col:
            self.form_error = "Could not delete or archive section: no section ID column found on LeaseDocumentSections."
            return

        rows = run_query(
            f"SELECT StoredFilePath FROM LeaseDocumentSections WHERE [{section_pk_col}] = ?",
            (section_id_int,),
            db=self.db,
        )
        if not rows:
            self.form_error = "Section not found."
            return
        stored_path = str(rows[0].get("StoredFilePath") or "")

        try:
            generated_ref_col = self._first_existing_column(
                "LeaseGeneratedDocumentSections",
                ["LeaseDocumentSectionID", "SectionID"],
            )
            package_ref_col = self._first_existing_column(
                "LeasePackageSections",
                ["SectionID", "LeaseDocumentSectionID"],
            )

            used = []
            if generated_ref_col:
                used = run_query(
                    f"SELECT TOP 1 LeaseGeneratedDocumentSectionID "
                    f"FROM LeaseGeneratedDocumentSections WHERE [{generated_ref_col}] = ?",
                    (section_id_int,),
                    db=self.db,
                )

            used_in_package_sections = []
            if package_ref_col:
                used_in_package_sections = run_query(
                    f"SELECT TOP 1 LeasePackageSectionID FROM LeasePackageSections WHERE [{package_ref_col}] = ?",
                    (section_id_int,),
                    db=self.db,
                )

            if used or used_in_package_sections:
                run_exec(
                    f"UPDATE LeaseDocumentSections SET IsActive = 0 WHERE [{section_pk_col}] = ?",
                    (section_id_int,),
                    db=self.db,
                )
                self.form_success = "Section is used by a lease package - archived instead of deleted."
            else:
                run_exec(
                    f"DELETE FROM LeaseDocumentSections WHERE [{section_pk_col}] = ?",
                    (section_id_int,),
                    db=self.db,
                )
                if stored_path and os.path.isfile(stored_path):
                    try:
                        os.remove(stored_path)
                    except OSError:
                        pass
                self.form_success = "Section deleted."

            if self.editing_section_id == section_id_int:
                self.reset_section_form()
            self._load_sections()
            self._load_all_sections()
        except Exception as ex:
            self.form_error = f"Could not delete or archive section: {ex}"

    def set_section_reusable_flag(self, section_id: int, reusable: bool):
        self.form_error = ""
        self.form_success = ""
        try:
            run_exec(
                "UPDATE LeaseDocumentSections SET IsReusable = ? WHERE LeaseDocumentSectionID = ?",
                (1 if reusable else 0, int(section_id)), db=self.db,
            )
            if int(self.editing_section_id or 0) == int(section_id):
                self.p_is_reusable = bool(reusable)
            self._load_sections()
            self._load_all_sections()
            self.form_success = "Reusable flag updated."
        except Exception as ex:
            self.form_error = f"Could not update reusable flag: {ex}"

    def make_section_reusable(self, section_id: int):
        return self.set_section_reusable_flag(section_id, True)

    def hide_section_from_builder(self, section_id: int):
        return self.set_section_reusable_flag(section_id, False)

    def toggle_section_reusable(self, section_id: int):
        self.form_error = ""
        self.form_success = ""
        try:
            rows = run_query(
                "SELECT IsReusable FROM LeaseDocumentSections WHERE LeaseDocumentSectionID = ?",
                (int(section_id),), db=self.db,
            )
            if not rows:
                self.form_error = "Section not found."
                return
            current = bool(rows[0].get("IsReusable"))
            return self.set_section_reusable_flag(section_id, not current)
        except Exception as ex:
            self.form_error = f"Could not update reusable flag: {ex}"

    def toggle_section_active(self, section_id: int):
        self.form_error = ""
        self.form_success = ""
        try:
            run_exec(
                "UPDATE LeaseDocumentSections SET IsActive = CASE WHEN IsActive = 1 THEN 0 ELSE 1 END WHERE LeaseDocumentSectionID = ?",
                (int(section_id),), db=self.db,
            )
            self._load_sections()
            self._load_all_sections()
        except Exception as ex:
            self.form_error = f"Could not update active flag: {ex}"

    def save_section_content(self):
        self.form_error = ""
        self.form_success = ""
        if int(self.editing_section_id or 0) <= 0:
            self.form_error = "Select a section with Edit before saving content."
            return
        try:
            run_exec(
                "UPDATE LeaseDocumentSections SET ClauseTag=?, ArticleNumber=?, DisplayLabel=?, Content=?, UpdatedOn=SYSDATETIME() WHERE LeaseDocumentSectionID = ?",
                (
                    self.p_clause_tag.strip() or None,
                    self.p_article_number.strip() or None,
                    self.p_display_label.strip() or None,
                    self.p_content,
                    int(self.editing_section_id),
                ),
                db=self.db,
            )
            self.form_success = "Section content saved."
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
        except Exception as ex:
            self.form_error = f"Could not save content: {ex}"

    def copy_content_from_latest_snapshot(self):
        """Copy the newest tenant package snapshot back into the library editor.

        This is a recovery helper for Phase 5 authoring. It lets Mark reuse a
        revised/generated tenant-section snapshot as the new starting point for
        a library clause without changing the generated tenant package record.
        """
        self.form_error = ""
        self.form_success = ""
        section_id = int(self.editing_section_id or 0)
        if section_id <= 0:
            self.form_error = "Select a section with Edit before copying from snapshot."
            return
        try:
            ref_col = self._first_existing_column(
                "LeasePackageSections",
                ["SectionID", "LeaseDocumentSectionID"],
            )
            if not ref_col:
                self.form_error = "LeasePackageSections does not have a section reference column."
                return
            rows = run_query(
                f"SELECT TOP 1 ContentSnapshot, Content FROM LeasePackageSections "
                f"WHERE [{ref_col}] = ? "
                f"AND (NULLIF(LTRIM(RTRIM(ISNULL(ContentSnapshot,''))), '') IS NOT NULL "
                f"OR NULLIF(LTRIM(RTRIM(ISNULL(Content,''))), '') IS NOT NULL) "
                f"ORDER BY LeasePackageSectionID DESC",
                (section_id,),
                db=self.db,
            )
            if not rows:
                self.form_error = "No generated package snapshot was found for this section."
                return
            snapshot = str(rows[0].get("ContentSnapshot") or rows[0].get("Content") or "")
            if not snapshot.strip():
                self.form_error = "Latest snapshot is blank."
                return
            self.p_content = snapshot
            self.form_success = "Copied latest package snapshot into the editor. Review it, then click Save Section."
        except Exception as ex:
            self.form_error = f"Could not copy from snapshot: {ex}"

    def create_section(self):
        self.form_error = ""
        self.form_success = ""
        is_text_clause = self.p_creation_mode == "Text Clause"
        has_source_document = int(self.selected_source_document_id or 0) > 0 and not bool(self.p_is_standalone_clause)
        if not has_source_document and not is_text_clause:
            self.form_error = "Select a source document on the Load tab first, or switch to Text Clause mode for a standalone clause."
            return
        if not self.p_section_name.strip():
            self.form_error = "Section name is required."
            return
        try:
            sort_order = int(self.p_sort_order or 0)
            if is_text_clause and not has_source_document:
                start = None
                end = None
            else:
                start = int(self.p_start_page or 1)
                end = int(self.p_end_page or start)
        except ValueError:
            self.form_error = "Start page, end page, and sort order must be numbers."
            return

        current_edit_id = int(self.editing_section_id or 0)

        if is_text_clause:
            if has_source_document and (start < 1 or end < start or end > self.selected_source_page_count):
                self.form_error = f"Source page reference must be between 1 and {self.selected_source_page_count}."
                return
            if not str(self.p_content or "").strip():
                self.form_error = "Content is required for Text Clause mode. Paste or type the clause text before saving."
                return
        else:
            metadata_only_update = self._is_metadata_only_section_update(current_edit_id, start, end)
            if not self._validate_section_range(start, end, current_edit_id, require_non_overlap=not metadata_only_update):
                return

        code = self.p_exhibit_code.strip()
        if self.p_section_type == "Base Lease":
            code = ""
            if not self.p_section_name.strip():
                self.p_section_name = "Base Lease"
        if has_source_document and self.p_section_type == "Exhibit" and code:
            dup = run_query(
                "SELECT TOP 1 LeaseDocumentSectionID AS SectionID FROM LeaseDocumentSections "
                "WHERE LeaseSourceDocumentID = ? AND SectionType = 'Exhibit' "
                "AND UPPER(ISNULL(ExhibitCode,'')) = UPPER(?) AND LeaseDocumentSectionID <> ?",
                (self.selected_source_document_id, code, current_edit_id), db=self.db,
            )
            if dup:
                self.form_error = "This exhibit code already exists for the selected source document."
                return
        try:
            if not code and self.p_section_type == "Exhibit":
                code = self._next_exhibit_code()

            root = self.storage_root.strip() or DEFAULT_DOCUMENT_ROOT
            if is_text_clause:
                section_path = (str(self.selected_source_path or "").strip() or None) if has_source_document else None
                rel = relative_to_root(section_path, root) if section_path else None
            else:
                output_name = (
                    f"source_{self.selected_source_document_id}_"
                    f"{slugify(code) + '_' if code else ''}"
                    f"{slugify(self.p_section_name)}_p{start}_{end}.pdf"
                )
                section_path = split_pdf_pages(
                    self.selected_source_path,
                    start,
                    end,
                    output_name,
                    self.storage_root,
                    self.f_property,
                    self.f_document_category,
                )
                rel = relative_to_root(section_path, root)

            if current_edit_id:
                old_rows = run_query(
                    "SELECT StoredFilePath FROM LeaseDocumentSections WHERE LeaseDocumentSectionID = ?",
                    (current_edit_id,), db=self.db,
                )
                old_path = str(old_rows[0].get("StoredFilePath") or "") if old_rows else ""
                run_exec(
                    "UPDATE LeaseDocumentSections SET SectionType=?, SectionName=?, ExhibitCode=?, StartPage=?, EndPage=?, "
                    "StoredFilePath=?, StorageRoot=?, RelativePath=?, SortOrder=?, IsReusable=?, IsActive=?, "
                    "ClauseTag=?, ArticleNumber=?, DisplayLabel=?, Content=?, UpdatedOn=SYSDATETIME() "
                    "WHERE LeaseDocumentSectionID=?",
                    (
                        self.p_section_type, self.p_section_name.strip(), code or None,
                        start, end, section_path, root, rel, sort_order,
                        1 if self.p_is_reusable else 0, 1 if self.p_is_active else 0,
                        self.p_clause_tag.strip() or None,
                        self.p_article_number.strip() or None,
                        self.p_display_label.strip() or None,
                        self.p_content, current_edit_id,
                    ), db=self.db,
                )
                if (not is_text_clause) and old_path and old_path != section_path and os.path.isfile(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass
                self.form_success = "Text clause updated." if is_text_clause else "Section updated."
                self.editing_section_id = 0
            else:
                run_exec(
                    "INSERT INTO LeaseDocumentSections "
                    "(LeaseSourceDocumentID, LeaseID, SectionType, SectionName, ExhibitCode, StartPage, EndPage, "
                    "StoredFilePath, StorageRoot, RelativePath, SortOrder, IsReusable, IsActive, ClauseTag, ArticleNumber, DisplayLabel, Content, UpdatedOn) "
                    "VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSDATETIME())",
                    (
                        self.selected_source_document_id if has_source_document else None, self.p_section_type,
                        self.p_section_name.strip(), code or None, start, end,
                        section_path, root, rel, sort_order,
                        1 if self.p_is_reusable else 0, 1 if self.p_is_active else 0,
                        self.p_clause_tag.strip() or None,
                        self.p_article_number.strip() or None,
                        self.p_display_label.strip() or None,
                        self.p_content,
                    ), db=self.db,
                )
                self.form_success = "Text clause saved." if is_text_clause else "Section saved."

            if is_text_clause:
                self.p_sort_order = str(self._next_section_sort_order())
            else:
                next_page = end + 1
                self.p_start_page = str(next_page) if next_page <= self.selected_source_page_count else str(end)
                self.p_end_page = str(next_page) if next_page <= self.selected_source_page_count else str(end)
                self.p_sort_order = str(self._next_section_sort_order())

            self.p_section_name = ""
            self.p_exhibit_code = ""
            self.p_clause_tag = ""
            self.p_article_number = ""
            self.p_display_label = ""
            self.p_content = ""
            self.p_is_reusable = True
            self.p_is_active = True
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
        except Exception as ex:
            self.form_error = f"Could not save section: {ex}"


    # ── Paste-and-split clause tool ───────────────────────────────────────────

    def _slug_from_label(self, label: str) -> str:
        text = str(label or "").strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
        return text[:100]

    def _clean_clause_label(self, label: str, content: str, article: str) -> str:
        """Return a usable display label from messy pasted lease text."""
        label = re.sub(r"\s+", " ", str(label or "").strip(" -:\t"))
        article_text = str(article or "").strip()
        if not label or label == article_text or len(label) > 90:
            body = str(content or "")
            if article_text:
                body = re.sub(rf"^\s*{re.escape(article_text)}[\.)]?\s*", "", body, flags=re.IGNORECASE)
            body = re.sub(r"\s+", " ", body).strip()
            first_sentence = re.split(r"(?<=[.!?])\s+", body, maxsplit=1)[0].strip()
            label = first_sentence[:90].strip(" -:\t") or f"Clause {article_text}"
        words = label.split()
        if len(words) > 10:
            label = " ".join(words[:10])
        return label or "Clause"

    def _parse_clause_header(self, line: str) -> tuple[str, str]:
        text = str(line or "").strip()
        patterns = [
            r"^(?:ARTICLE|Article)\s+([0-9IVXLCDM]+)\s*[-:.]?\s*(.*)$",
            r"^(?:SECTION|Section)\s+([0-9A-Za-z\.]+)\s*[-:.]?\s*(.*)$",
            r"^([0-9]+(?:\.[0-9]+)*)(?:[\.)])?\s*(.*)$",
            r"^([A-Z])(?:[\.)])\s*(.*)$",
            r"^([a-z])\)\s*(.*)$",
            r"^([IVXLCDM]+)(?:[\.)])\s*(.*)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                article = match.group(1).strip()
                label = match.group(2).strip(" -:\t") if len(match.groups()) >= 2 else ""
                return article, label
        return "", text[:80]

    def _find_clause_markers(self, raw: str):
        """Find likely top-level clause starts in messy pasted lease text.

        Legal PDF copy/paste often wraps clauses with no blank lines and may put
        the article number on its own line. This returns character offsets rather
        than full-line regex matches so we can split on inline markers like:
        "... casualty. 12. In addition ...".
        """
        text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)

        # Force common top-level headers to their own line for easier visual review.
        text = re.sub(r"(?<!^)\s+((?:ARTICLE|Article)\s+[0-9IVXLCDM]+\b)", r"\n\1", text)
        text = re.sub(r"(?<!^)\s+((?:SECTION|Section)\s+[0-9A-Za-z\.]+\b)", r"\n\1", text)

        marker_re = re.compile(
            r"(?im)(?<![A-Za-z0-9_.])"
            r"(?P<header>"
            r"ARTICLE\s+[0-9IVXLCDM]+"
            r"|SECTION\s+[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*"
            r"|[0-9]{1,3}[\.)]"
            r")"
            r"(?=\s+[A-Z])"
        )

        markers = []
        seen = set()
        for match in marker_re.finditer(text):
            start = match.start("header")

            # Avoid false positives inside statutes/decimals like 54.021.
            after_header = text[match.end("header"):match.end("header") + 8]
            if re.match(r"^\s*\d", after_header):
                continue

            if start in seen:
                continue
            seen.add(start)
            markers.append((start, match.group("header").strip()))

        markers.sort(key=lambda item: item[0])
        return text, markers

    def parse_pasted_clauses(self):
        self.form_error = ""
        self.form_success = ""
        raw = str(self.paste_clause_text or "").strip()
        if not raw:
            self.form_error = "Paste clause text before splitting."
            self.draft_clauses = []
            self.draft_clause_count = "0 draft clause(s)"
            return

        text, markers = self._find_clause_markers(raw)
        chunks: list[str] = []
        if markers:
            for idx, marker in enumerate(markers):
                start = int(marker[0])
                end = int(markers[idx + 1][0]) if idx + 1 < len(markers) else len(text)
                chunk = text[start:end].strip()
                if chunk:
                    chunks.append(chunk)
        else:
            chunks = [c.strip() for c in re.split(r"\n\s*\n+", text) if c.strip()]
            if not chunks:
                chunks = [text.strip()]

        drafts: list[DraftClauseRow] = []
        for idx, content in enumerate(chunks, start=1):
            if not content:
                continue
            first_line = next((ln.strip() for ln in content.split("\n") if ln.strip()), "")
            article, raw_label = self._parse_clause_header(first_line)
            label = self._clean_clause_label(raw_label, content, article) or f"Clause {idx}"
            tag = self._slug_from_label(label)
            preview = content.replace("\n", " ").strip()
            if len(preview) > 180:
                preview = preview[:177].rstrip() + "..."
            drafts.append(
                DraftClauseRow(
                    draft_id=len(drafts) + 1,
                    article_number=article,
                    display_label=label,
                    clause_tag=tag,
                    preview=preview,
                    content=content,
                )
            )

        self.draft_clauses = drafts
        self.draft_clause_count = f"{len(drafts):,} draft clause(s)"
        if drafts:
            self.form_success = f"Split pasted text into {len(drafts):,} draft clause(s)."
        else:
            self.form_error = "Could not detect clauses in the pasted text. Try adding each clause number on its own line."

    def clear_pasted_clause_tool(self):
        self.paste_clause_text = ""
        self.draft_clauses = []
        self.draft_clause_count = "0 draft clause(s)"
        self.form_error = ""
        self.form_success = ""

    def load_draft_clause(self, draft_id: int):
        did = int(draft_id or 0)
        for draft in self.draft_clauses:
            if int(draft.draft_id or 0) == did:
                self.editing_section_id = 0
                self.p_creation_mode = "Text Clause"
                self.p_section_type = self.library_type_filter if self.library_type_filter in SECTION_TYPES else "Base Lease"
                self.p_section_name = draft.display_label
                self.p_exhibit_code = ""
                self.p_start_page = "1"
                self.p_end_page = "1"
                self.p_sort_order = str(self._next_section_sort_order())
                self.p_is_reusable = True
                self.p_is_active = True
                self.p_clause_tag = draft.clause_tag
                self.p_article_number = draft.article_number
                self.p_display_label = draft.display_label
                self.p_content = draft.content
                self.form_success = "Draft clause loaded into the editor. Review it, then save it as a text clause."
                return
        self.form_error = "Draft clause not found."

    def _save_text_clause_section(self, draft: DraftClauseRow) -> int:
        has_source_document = int(self.selected_source_document_id or 0) > 0 and not bool(self.p_is_standalone_clause)
        source_path = (str(self.selected_source_path or "").strip() or None) if has_source_document else None
        root = self.storage_root.strip() or DEFAULT_DOCUMENT_ROOT
        sort_order = self._next_section_sort_order()
        section_name = str(draft.display_label or f"Clause {draft.draft_id}").strip()
        try:
            start = int(self.p_start_page or 1)
            end = int(self.p_end_page or start)
        except ValueError:
            start = 1
            end = 1
        if start < 1:
            start = 1
        if end < start:
            end = start
        if has_source_document and self.selected_source_page_count and end > self.selected_source_page_count:
            end = self.selected_source_page_count
        if not has_source_document:
            start = None
            end = None
        run_exec(
            "INSERT INTO LeaseDocumentSections "
            "(LeaseSourceDocumentID, LeaseID, SectionType, SectionName, ExhibitCode, StartPage, EndPage, "
            "StoredFilePath, StorageRoot, RelativePath, SortOrder, IsReusable, IsActive, ClauseTag, ArticleNumber, DisplayLabel, Content, UpdatedOn) "
            "VALUES (?, NULL, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, 1, 1, ?, ?, ?, ?, SYSDATETIME())",
            (
                int(self.selected_source_document_id) if has_source_document else None,
                self.p_section_type if self.p_section_type in SECTION_TYPES else "Base Lease",
                section_name,
                start,
                end,
                source_path,
                root,
                sort_order,
                str(draft.clause_tag or "").strip() or None,
                str(draft.article_number or "").strip() or None,
                str(draft.display_label or "").strip() or None,
                str(draft.content or ""),
            ),
            db=self.db,
        )
        rows = run_query(
            "SELECT TOP 1 LeaseDocumentSectionID FROM LeaseDocumentSections ORDER BY LeaseDocumentSectionID DESC",
            db=self.db,
        )
        return int(rows[0].get("LeaseDocumentSectionID") or 0) if rows else 0

    def save_draft_clause(self, draft_id: int):
        self.form_error = ""
        self.form_success = ""
        did = int(draft_id or 0)
        draft = next((d for d in self.draft_clauses if int(d.draft_id or 0) == did), None)
        if draft is None:
            self.form_error = "Draft clause not found."
            return
        try:
            new_id = self._save_text_clause_section(draft)
            self.form_success = f"Saved draft clause as section #{new_id}."
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
        except Exception as ex:
            self.form_error = f"Could not save draft clause: {ex}"

    def save_all_draft_clauses(self):
        self.form_error = ""
        self.form_success = ""
        if not self.draft_clauses:
            self.form_error = "No draft clauses to save."
            return
        saved = 0
        try:
            for draft in self.draft_clauses:
                self._save_text_clause_section(draft)
                saved += 1
            self.form_success = f"Saved {saved:,} draft clause(s)."
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
        except Exception as ex:
            self.form_error = f"Saved {saved:,} clause(s), then failed: {ex}"

    def save_loaded_draft_as_section(self):
        self.form_error = ""
        self.form_success = ""
        if not str(self.p_content or "").strip():
            self.form_error = "Load or enter clause content first."
            return
        draft = DraftClauseRow(
            draft_id=0,
            article_number=self.p_article_number,
            display_label=self.p_display_label or self.p_section_name or "Clause",
            clause_tag=self.p_clause_tag,
            preview="",
            content=self.p_content,
        )
        try:
            new_id = self._save_text_clause_section(draft)
            self.form_success = f"Saved loaded draft as section #{new_id}."
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
            self.reset_section_form()
        except Exception as ex:
            self.form_error = f"Could not save loaded draft: {ex}"

    # ── Lease template manager ─────────────────────────────────────────────────

    def _selected_lt_property_id(self) -> Optional[int]:
        if self.lt_property in self.property_names:
            pid = self.property_ids[self.property_names.index(self.lt_property)]
            return int(pid) if pid else None
        return None

    def _load_reusable_section_options(self):
        """Load reusable sections for package-template slots across all source documents.

        This must never be scoped to selected_source_document_id. A Source Document is
        only one uploaded PDF. A Package Template is allowed to combine reusable
        sections from many source PDFs, such as a base lease plus one or more
        addendums that each start on page 1.
        """
        try:
            rows = run_query(
                "SELECT p.LeaseDocumentSectionID AS SectionID, p.SectionType, p.SectionName, ISNULL(p.ExhibitCode,'') AS ExhibitCode, "
                "p.StartPage, p.EndPage, p.SortOrder, ISNULL(sd.TemplateName, '') AS TemplateName, ISNULL(sd.OriginalFileName, '') AS OriginalFileName, "
                "sd.PropertyID, sd.LeaseSourceDocumentID "
                "FROM LeaseDocumentSections p "
                "LEFT JOIN LeaseSourceDocuments sd ON p.LeaseSourceDocumentID = sd.LeaseSourceDocumentID "
                "WHERE ISNULL(p.IsReusable, 1) = 1 AND ISNULL(p.IsActive, 1) = 1 "
                "AND (sd.LeaseSourceDocumentID IS NULL OR ISNULL(sd.IsActive, 1) = 1) "
                "ORDER BY ISNULL(sd.TemplateName, ''), p.SectionType, p.SortOrder, p.SectionName, p.LeaseDocumentSectionID",
                db=self.db,
            )
        except Exception:
            rows = []
        labels = ["(No default section)"]
        ids = [0]
        for r in rows:
            pid = int(r.get("SectionID") or 0)
            ptype = str(r.get("SectionType") or "Other").strip() or "Other"
            name = str(r.get("SectionName") or "").strip() or f"Section {pid}"
            code = str(r.get("ExhibitCode") or "").strip()
            start_page = _safe_int(r.get("StartPage"))
            end_page = _safe_int(r.get("EndPage"))
            pages = f"Pages {start_page}-{end_page}" if start_page > 0 and end_page > 0 else ""
            tmpl = str(r.get("TemplateName") or "").strip()
            file_name = str(r.get("OriginalFileName") or "").strip()
            source_doc_id = r.get('LeaseSourceDocumentID')
            source_label = tmpl or file_name or (f"Source {int(source_doc_id)}" if source_doc_id else "Standalone")
            prop = self._property_name_for_id(r.get("PropertyID"))
            extras = []
            if code:
                extras.append(code)
            if pages:
                extras.append(pages)
            if source_label:
                extras.append(f"Source: {source_label}")
            if prop and prop != PROPERTY_GENERAL:
                extras.append(prop)
            suffix = f" ({' - '.join(extras)})" if extras else ""
            labels.append(f"{ptype}: {name}{suffix} [ID={pid}]")
            ids.append(pid)
        self.reusable_section_labels = labels
        self.reusable_section_ids = ids
        if self.sec_default_section_label not in labels:
            self.sec_default_section_label = labels[0]

    def _section_label_for_id(self, section_id) -> str:
        try:
            pid = int(section_id or 0)
        except Exception:
            pid = 0
        if pid in self.reusable_section_ids:
            return self.reusable_section_labels[self.reusable_section_ids.index(pid)]
        if pid == 0:
            return "(No default section)"
        rows = run_query(
            "SELECT s.SectionType, s.SectionName, ISNULL(s.ExhibitCode,'') AS ExhibitCode, "
            "s.StartPage, s.EndPage, ISNULL(sd.TemplateName, '') AS TemplateName, ISNULL(sd.OriginalFileName, '') AS OriginalFileName, "
            "sd.PropertyID, sd.LeaseSourceDocumentID "
            "FROM LeaseDocumentSections s "
            "LEFT JOIN LeaseSourceDocuments sd ON s.LeaseSourceDocumentID = sd.LeaseSourceDocumentID "
            "WHERE s.LeaseDocumentSectionID = ?",
            (pid,), db=self.db,
        )
        if not rows:
            return ""
        r = rows[0]
        code = str(r.get("ExhibitCode") or "").strip()
        start_page = _safe_int(r.get("StartPage"))
        end_page = _safe_int(r.get("EndPage"))
        pages = f"Pages {start_page}-{end_page}" if start_page > 0 and end_page > 0 else ""
        tmpl = str(r.get("TemplateName") or "").strip()
        file_name = str(r.get("OriginalFileName") or "").strip()
        source_doc_id = r.get('LeaseSourceDocumentID')
        source_label = tmpl or file_name or (f"Source {int(source_doc_id)}" if source_doc_id else "Standalone")
        prop = self._property_name_for_id(r.get("PropertyID"))
        extras = []
        if code:
            extras.append(code)
        if pages:
            extras.append(pages)
        if source_label:
            extras.append(f"Source: {source_label}")
        if prop and prop != PROPERTY_GENERAL:
            extras.append(prop)
        suffix = f" ({' - '.join(extras)})" if extras else ""
        return f"{str(r.get('SectionType') or 'Other')}: {str(r.get('SectionName') or '')}{suffix} [ID={pid}]"

    def _load_lease_templates(self):
        try:
            rows = run_query(
                "SELECT lt.LeaseTemplateID, lt.TemplateName, lt.PropertyID, lt.Description, lt.IsActive, "
                "COUNT(lts.LeaseTemplateSectionID) AS SectionCount "
                "FROM LeaseTemplates lt "
                "LEFT JOIN LeaseTemplateSections lts ON lt.LeaseTemplateID = lts.LeaseTemplateID "
                "AND ISNULL(lts.IsActive, 1) = 1 "
                "GROUP BY lt.LeaseTemplateID, lt.TemplateName, lt.PropertyID, lt.Description, lt.IsActive "
                "ORDER BY lt.TemplateName, lt.LeaseTemplateID",
                db=self.db,
            )
        except Exception:
            rows = []
        self.lease_templates = [
            LeaseTemplateRow(
                template_id=_safe_int(r.get("LeaseTemplateID")),
                template_name=str(r.get("TemplateName") or ""),
                property_name=self._property_name_for_id(r.get("PropertyID")),
                description=str(r.get("Description") or ""),
                active="Yes" if r.get("IsActive") else "No",
                section_count=int(r.get("SectionCount") or 0),
            )
            for r in rows
        ]
        self.lease_template_labels = [self._lease_template_label(t) for t in self.lease_templates]
        self.lease_template_ids = [_safe_int(t.template_id) for t in self.lease_templates]

        # Drop impossible zero-ID template options so rx.select cannot bind to an invalid row.
        valid_pairs = [(label, tid) for label, tid in zip(self.lease_template_labels, self.lease_template_ids) if _safe_int(tid) > 0]
        self.lease_template_labels = [label for label, _ in valid_pairs]
        self.lease_template_ids = [_safe_int(tid) for _, tid in valid_pairs]

        # Keep the template select in a valid state. Reflex can reset bound state
        # when rx.select renders with value="" while the option list is populated.
        if self.lease_template_labels and not str(self.selected_template_label or "").strip():
            self.selected_template_label = self.lease_template_labels[0]

        existing = [_safe_int(t.template_id) for t in self.lease_templates]
        current_id = _safe_int(self.selected_template_id)
        if current_id > 0 and current_id in existing:
            self.selected_template_id = current_id
            self.slot_template_id = current_id
            self.selected_template_label = self._ensure_template_label_for_id(current_id)
            self._load_template_sections()
        elif self.lease_templates:
            # Keep the UI in edit mode for the first valid template instead of
            # resetting to a blank new-template form during re-renders.
            first_id = _safe_int(self.lease_templates[0].template_id)
            self.select_lease_template(first_id)
        else:
            self.new_lease_template()

    def _lease_template_label(self, t: LeaseTemplateRow) -> str:
        prop = str(t.property_name or "").strip()
        name = str(t.template_name or "Untitled Template").strip()
        return f"{name} - {prop} [ID={_safe_int(t.template_id)}]" if prop else f"{name} [ID={_safe_int(t.template_id)}]"

    def _template_label_for_id(self, template_id: int) -> str:
        tid = _safe_int(template_id)
        for t in self.lease_templates:
            if _safe_int(t.template_id) == tid:
                return self._lease_template_label(t)
        return ""

    def _ensure_template_label_for_id(self, template_id: int) -> str:
        """Return a non-empty template label and ensure it exists in select options.

        Reflex rx.select can reset bound state if value is an empty string or if
        value is not present in the option list. Package-template row actions can
        fire before lease_templates is fully hydrated after rerenders, so this
        method falls back to the database and appends the label/id pair when
        needed.
        """
        tid = _safe_int(template_id)
        if tid <= 0:
            return ""

        label = self._template_label_for_id(tid)
        if not label:
            rows = run_query(
                "SELECT LeaseTemplateID, TemplateName, PropertyID, ISNULL(Description, '') AS Description, ISNULL(IsActive, 1) AS IsActive "
                "FROM LeaseTemplates WHERE LeaseTemplateID = ?",
                (tid,), db=self.db,
            )
            if rows:
                r = rows[0]
                template_row = LeaseTemplateRow(
                    template_id=_safe_int(r.get("LeaseTemplateID"), tid),
                    template_name=str(r.get("TemplateName") or "Untitled Template"),
                    property_name=self._property_name_for_id(r.get("PropertyID")),
                    description=str(r.get("Description") or ""),
                    active="Yes" if r.get("IsActive") else "No",
                    section_count=0,
                )
                label = self._lease_template_label(template_row)
                if not any(_safe_int(t.template_id) == tid for t in self.lease_templates):
                    self.lease_templates = self.lease_templates + [template_row]

        if not label:
            # Last-resort non-empty value. This prevents rx.select value="" from
            # causing a state reset. A later refresh will replace it with the
            # full display label.
            label = f"Template [ID={tid}]"

        if label not in self.lease_template_labels:
            self.lease_template_labels = self.lease_template_labels + [label]
            self.lease_template_ids = self.lease_template_ids + [tid]

        return label

    def set_selected_template_label(self, label: str):
        self.selected_template_label = label
        try:
            idx = self.lease_template_labels.index(label)
            template_id = _safe_int(self.lease_template_ids[idx])
        except Exception:
            template_id = 0
        if template_id > 0:
            self.select_lease_template(template_id)
        elif _safe_int(self.selected_template_id) > 0:
            self.selected_template_label = self._ensure_template_label_for_id(int(self.selected_template_id))

    def _load_template_sections(self):
        if _safe_int(self.selected_template_id) <= 0:
            self.lease_template_sections = []
            return
        rows = run_query(
            "SELECT LeaseTemplateSectionID, SortOrder, SectionLabel, DefaultSectionID, "
            "IsOptional, IsRequired, SectionType, IsActive "
            "FROM LeaseTemplateSections WHERE LeaseTemplateID = ? "
            "ORDER BY SortOrder, LeaseTemplateSectionID",
            (int(self.selected_template_id),), db=self.db,
        )
        self.lease_template_sections = [
            LeaseTemplateSectionRow(
                section_id=int(r.get("LeaseTemplateSectionID") or 0),
                sort_order=int(r.get("SortOrder") or 0),
                section_label=str(r.get("SectionLabel") or ""),
                section_type=str(r.get("SectionType") or ""),
                default_section_label=self._section_label_for_id(r.get("DefaultSectionID")),
                inclusion_mode=self._inclusion_mode_from_bools(
                    bool(r.get("IsOptional")),
                    bool(r.get("IsRequired")),
                    bool(r.get("IsActive") if r.get("IsActive") is not None else True),
                ),
                active="Yes" if r.get("IsActive") else "No",
            )
            for r in rows
        ]

    def _next_template_section_sort_order(self) -> int:
        if _safe_int(self.selected_template_id) <= 0:
            return 10
        rows = run_query(
            "SELECT ISNULL(MAX(SortOrder), 0) AS MaxSort FROM LeaseTemplateSections WHERE LeaseTemplateID = ?",
            (int(self.selected_template_id),), db=self.db,
        )
        try:
            return int(rows[0].get("MaxSort") or 0) + 10
        except Exception:
            return 10

    def select_lease_template(self, template_id: int):
        tid = _safe_int(template_id)
        self.selected_template_id = tid
        self.slot_template_id = tid
        self.selected_template_label = self._ensure_template_label_for_id(tid)
        self.form_error = ""
        self.form_success = ""
        if tid <= 0:
            self.new_lease_template()
            return
        rows = run_query(
            "SELECT LeaseTemplateID, TemplateName, PropertyID, Description, IsActive "
            "FROM LeaseTemplates WHERE LeaseTemplateID = ?",
            (tid,), db=self.db,
        )
        if not rows:
            self.new_lease_template()
            return
        r = rows[0]
        self.lt_template_mode = "edit"
        self.lt_template_name = str(r.get("TemplateName") or "")
        self.lt_property = self._property_name_for_id(r.get("PropertyID"))
        self.lt_description = str(r.get("Description") or "")
        self.lt_is_active = bool(r.get("IsActive"))
        # Keep the select value valid after the form fields hydrate.
        self.selected_template_label = self._ensure_template_label_for_id(tid)
        self.reset_template_section_form()
        self._load_template_sections()

    def new_lease_template(self):
        self.selected_template_id = 0
        self.slot_template_id = 0
        self.selected_template_label = ""
        self.lt_template_mode = "new"
        self.lt_template_name = ""
        self.lt_property = PROPERTY_GENERAL
        self.lt_description = ""
        self.lt_is_active = True
        self.lease_template_sections = []
        self.reset_template_section_form()

    def save_lease_template(self):
        self.form_error = ""
        self.form_success = ""
        if not self.lt_template_name.strip():
            self.form_error = "Lease template name is required."
            return
        now = datetime.datetime.now()
        try:
            if self.lt_template_mode == "edit" and _safe_int(self.selected_template_id) > 0:
                run_exec(
                    "UPDATE LeaseTemplates SET TemplateName=?, PropertyID=?, Description=?, IsActive=?, UpdatedOn=? "
                    "WHERE LeaseTemplateID=?",
                    (
                        self.lt_template_name.strip(), self._selected_lt_property_id(),
                        self.lt_description, 1 if self.lt_is_active else 0,
                        now, int(self.selected_template_id),
                    ), db=self.db,
                )
                self.form_success = "Lease template saved."
            else:
                run_exec(
                    "INSERT INTO LeaseTemplates (TemplateName, PropertyID, Description, IsActive, CreatedOn, UpdatedOn) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        self.lt_template_name.strip(), self._selected_lt_property_id(),
                        self.lt_description, 1 if self.lt_is_active else 0, now, now,
                    ), db=self.db,
                )
                row = run_query(
                    "SELECT TOP 1 LeaseTemplateID FROM LeaseTemplates WHERE TemplateName = ? ORDER BY LeaseTemplateID DESC",
                    (self.lt_template_name.strip(),), db=self.db,
                )
                self.selected_template_id = int(row[0].get("LeaseTemplateID") or 0) if row else 0
                self.slot_template_id = _safe_int(self.selected_template_id)
                self.selected_template_label = self._ensure_template_label_for_id(self.selected_template_id)
                self.lt_template_mode = "edit"
                self.form_success = "Lease template created."
            self._load_lease_templates()
            if self.selected_template_id:
                self.select_lease_template(self.selected_template_id)
        except Exception as ex:
            self.form_error = f"Could not save lease template: {ex}"

    def _selected_default_section_id(self) -> Optional[int]:
        label = str(self.sec_default_section_label or "").strip()
        if label in self.reusable_section_labels:
            pid = _safe_int(self.reusable_section_ids[self.reusable_section_labels.index(label)])
            return int(pid) if pid else None
        match = re.search(r"\[ID=(\d+)\]", label)
        if match:
            pid = _safe_int(match.group(1))
            return int(pid) if pid else None
        return None

    def reset_template_section_form(self):
        if _safe_int(self.slot_template_id) <= 0 and _safe_int(self.selected_template_id) > 0:
            self.slot_template_id = int(self.selected_template_id)
        self.section_mode = "new"
        self.selected_section_id = 0
        self.sec_label = ""
        self.sec_sort_order = str(self._next_template_section_sort_order())
        self.sec_default_section_label = self.reusable_section_labels[0] if self.reusable_section_labels else "(No default section)"
        self.sec_section_type = "Base Lease"
        self.sec_inclusion_mode = "Required"
        self.sec_is_active = True

    def start_new_template_section_for_template(self, template_id: int):
        """Select a package template and start a new slot for that template."""
        tid = _safe_int(template_id)
        if tid <= 0:
            self.form_error = "Select a lease package template first."
            return
        self.select_lease_template(tid)
        self.slot_template_id = tid
        self.reset_template_section_form()

    def edit_template_section(self, section_id: int):
        self.form_error = ""
        self.form_success = ""
        rows = run_query(
            "SELECT LeaseTemplateSectionID, SortOrder, SectionLabel, DefaultSectionID, "
            "IsOptional, IsRequired, SectionType, IsActive "
            "FROM LeaseTemplateSections WHERE LeaseTemplateSectionID = ?",
            (int(section_id),), db=self.db,
        )
        if not rows:
            self.form_error = "Template section not found."
            return
        r = rows[0]
        self.section_mode = "edit"
        self.selected_section_id = int(r.get("LeaseTemplateSectionID") or 0)
        self.sec_sort_order = str(int(r.get("SortOrder") or 0))
        self.sec_label = str(r.get("SectionLabel") or "")
        default_section_id = int(r.get("DefaultSectionID") or 0)
        self.sec_default_section_label = self._section_label_for_id(default_section_id) if default_section_id else "(No default section)"
        if self.sec_default_section_label and self.sec_default_section_label not in self.reusable_section_labels:
            self.reusable_section_labels = self.reusable_section_labels + [self.sec_default_section_label]
            self.reusable_section_ids = self.reusable_section_ids + [default_section_id]
        self.sec_section_type = str(r.get("SectionType") or "Base Lease")
        self.sec_inclusion_mode = self._inclusion_mode_from_bools(
            bool(r.get("IsOptional")),
            bool(r.get("IsRequired")),
            bool(r.get("IsActive") if r.get("IsActive") is not None else True),
        )
        self.sec_is_active = bool(r.get("IsActive") if r.get("IsActive") is not None else True)

    def _ensure_selected_template_before_slot_save(self) -> bool:
        """Resolve the active package template before saving a slot.

        Reflex can drop selected_template_id across tab/render transitions.
        This recovers it from every durable clue available before failing.
        """

        def apply_template_id(template_id: int) -> bool:
            tid = _safe_int(template_id)
            if tid <= 0:
                return False
            self.selected_template_id = tid
            self.slot_template_id = tid
            self.selected_template_label = self._ensure_template_label_for_id(tid)
            self.lt_template_mode = "edit"
            return True

        if _safe_int(self.slot_template_id) > 0:
            return apply_template_id(int(self.slot_template_id))
        if _safe_int(self.selected_template_id) > 0:
            return apply_template_id(int(self.selected_template_id))

        label = str(self.selected_template_label or "").strip()
        if label:
            if label in self.lease_template_labels:
                try:
                    idx = self.lease_template_labels.index(label)
                    if apply_template_id(_safe_int(self.lease_template_ids[idx])):
                        return True
                except Exception:
                    pass

            match = re.search(r"\[ID=(\d+)\]", label)
            if match and apply_template_id(int(match.group(1))):
                return True

        template_name = str(self.lt_template_name or "").strip()
        if template_name:
            try:
                rows = run_query(
                    "SELECT TOP 1 LeaseTemplateID FROM LeaseTemplates "
                    "WHERE TemplateName = ? ORDER BY LeaseTemplateID DESC",
                    (template_name,),
                    db=self.db,
                )
                if rows and apply_template_id(_safe_int(rows[0].get("LeaseTemplateID"))):
                    return True
            except Exception:
                pass

        try:
            self._load_lease_templates()
        except Exception:
            pass

        if _safe_int(self.selected_template_id) > 0:
            return True

        if label and label in self.lease_template_labels:
            try:
                idx = self.lease_template_labels.index(label)
                if apply_template_id(_safe_int(self.lease_template_ids[idx])):
                    return True
            except Exception:
                pass

        if template_name:
            for t in self.lease_templates:
                if str(t.template_name or "").strip() == template_name:
                    if apply_template_id(_safe_int(t.template_id)):
                        return True

        if len(self.lease_templates) == 1:
            return apply_template_id(_safe_int(self.lease_templates[0].template_id))

        return False

    def _template_section_validation_errors(self, active_template_id: int, sort_order: int) -> list[str]:
        """Validate a slot before insert/update. Keeps template structure stable."""
        errors: list[str] = []
        if _safe_int(active_template_id) <= 0:
            errors.append("Package template is required.")
        if not str(self.sec_label or "").strip():
            errors.append("Section label is required.")

        try:
            params = [int(active_template_id), int(sort_order)]
            sql = (
                "SELECT TOP 1 LeaseTemplateSectionID FROM LeaseTemplateSections "
                "WHERE LeaseTemplateID = ? AND SortOrder = ? AND ISNULL(IsActive, 1) = 1"
            )
            if self.section_mode == "edit" and _safe_int(self.selected_section_id) > 0:
                sql += " AND LeaseTemplateSectionID <> ?"
                params.append(_safe_int(self.selected_section_id))
            rows = run_query(sql, tuple(params), db=self.db)
            if rows:
                errors.append(f"Sort order {sort_order} is already used by another active slot.")
        except Exception:
            pass
        return errors

    def save_template_section(self):
        self.form_error = ""
        self.form_success = ""
        if not self._ensure_selected_template_before_slot_save():
            self.form_error = "Save or select a lease package template first."
            return
        active_template_id = int(self.slot_template_id or self.selected_template_id or 0)
        if active_template_id <= 0:
            self.form_error = "Save or select a lease package template first."
            return
        try:
            sort_order = int(self.sec_sort_order or 0)
        except ValueError:
            self.form_error = "Section sort order must be a number."
            return
        validation_errors = self._template_section_validation_errors(active_template_id, sort_order)
        if validation_errors:
            self.form_error = "Cannot save slot. " + " | ".join(validation_errors)
            return
        is_optional, is_required, is_active = self._bools_from_inclusion_mode(self.sec_inclusion_mode)
        try:
            if self.section_mode == "edit" and int(self.selected_section_id or 0) > 0:
                run_exec(
                    "UPDATE LeaseTemplateSections SET SortOrder=?, SectionLabel=?, DefaultSectionID=?, "
                    "IsOptional=?, IsRequired=?, SectionType=?, IsActive=? WHERE LeaseTemplateSectionID=?",
                    (
                        sort_order, self.sec_label.strip(), self._selected_default_section_id(),
                        1 if is_optional else 0, 1 if is_required else 0,
                        self.sec_section_type, 1 if is_active else 0,
                        int(self.selected_section_id),
                    ), db=self.db,
                )
                self.form_success = "Template section saved."
            else:
                run_exec(
                    "INSERT INTO LeaseTemplateSections "
                    "(LeaseTemplateID, SortOrder, SectionLabel, DefaultSectionID, IsOptional, IsRequired, SectionType, IsActive) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        active_template_id, sort_order, self.sec_label.strip(),
                        self._selected_default_section_id(),
                        1 if is_optional else 0, 1 if is_required else 0,
                        self.sec_section_type, 1 if is_active else 0,
                    ), db=self.db,
                )
                self.form_success = "Template section added."
            self.selected_template_id = active_template_id
            self.slot_template_id = active_template_id
            self._load_template_sections()
            self._load_lease_templates()
            self.selected_template_id = active_template_id
            self.slot_template_id = active_template_id
            self.selected_template_label = self._ensure_template_label_for_id(active_template_id)
            self.reset_template_section_form()
        except Exception as ex:
            self.form_error = f"Could not save template section: {ex}"

    def delete_template_section(self, section_id: int):
        self.form_error = ""
        self.form_success = ""
        sid = int(section_id or 0)
        if sid <= 0:
            return
        try:
            used = run_query(
                "SELECT TOP 1 LeasePackageSectionID FROM LeasePackageSections WHERE LeaseTemplateSectionID = ?",
                (sid,), db=self.db,
            )
            if used:
                run_exec(
                    "UPDATE LeaseTemplateSections SET IsActive = 0 WHERE LeaseTemplateSectionID = ?",
                    (sid,), db=self.db,
                )
                self.form_success = "Template section is referenced by a package - archived."
            else:
                run_exec("DELETE FROM LeaseTemplateSections WHERE LeaseTemplateSectionID = ?", (sid,), db=self.db)
                self.form_success = "Template section deleted."
            if self.selected_section_id == sid:
                self.reset_template_section_form()
            self._load_template_sections()
            self._load_lease_templates()
        except Exception as ex:
            self.form_error = f"Could not delete template section: {ex}"

    # ── Setters ────────────────────────────────────────────────────────────────

    def set_lt_template_name(self, v: str): self.lt_template_name = v
    def set_lt_property(self, v: str): self.lt_property = v
    def set_lt_description(self, v: str): self.lt_description = v
    def set_lt_is_active(self, v: bool): self.lt_is_active = v
    def set_sec_label(self, v: str): self.sec_label = v
    def set_sec_sort_order(self, v: str): self.sec_sort_order = v
    def set_sec_default_section_label(self, v: str): self.sec_default_section_label = v
    def set_sec_section_type(self, v: str): self.sec_section_type = v
    def set_sec_inclusion_mode(self, v: str): self.sec_inclusion_mode = v
    def set_sec_is_active(self, v: bool): self.sec_is_active = v

    def set_f_template_name(self, v: str): self.f_template_name = v
    def set_f_property(self, v: str): self.f_property = v
    def set_f_document_category(self, v: str): self.f_document_category = v
    def set_f_template_version(self, v: str): self.f_template_version = v
    def set_f_notes(self, v: str): self.f_notes = v
    def set_f_is_active(self, v: bool): self.f_is_active = v
    def set_storage_root(self, v: str): self.storage_root = v
    def set_load_tab_split_pct(self, v: int): self.load_tab_split_pct = int(v or 30)
    def set_template_tab_split_pct(self, v: int): self.template_tab_split_pct = int(v or 35)
    def set_local_pdf_path(self, v: str): self.local_pdf_path = v
    def set_p_creation_mode(self, v: str):
        self.p_creation_mode = v
        if v != "Text Clause":
            self.p_is_standalone_clause = False
    def set_p_section_name(self, v: str): self.p_section_name = v
    def set_p_exhibit_code(self, v: str): self.p_exhibit_code = v
    def set_p_start_page(self, v: str): self.p_start_page = v
    def set_p_end_page(self, v: str): self.p_end_page = v
    def set_p_sort_order(self, v: str): self.p_sort_order = v
    def set_p_is_reusable(self, v: bool): self.p_is_reusable = v
    def set_p_is_active(self, v: bool): self.p_is_active = v
    def set_p_clause_tag(self, v: str): self.p_clause_tag = v
    def set_p_article_number(self, v: str): self.p_article_number = v
    def set_p_display_label(self, v: str): self.p_display_label = v
    def set_p_content(self, v: str): self.p_content = v

    def append_token_to_p_content(self, token: str):
        """Append a merge token into the active clause/section text editor.

        Reflex cannot reliably insert at cursor position from Python state, so this
        v3.0.12 helper appends to the end with clean spacing. Later polish can
        add cursor-position insertion with client-side JavaScript.
        """
        token_text = str(token or "").strip()
        if not token_text:
            return
        current = str(self.p_content or "")
        if current and not current.endswith((" ", "\n")):
            current += " "
        self.p_content = current + token_text

    def set_paste_clause_text(self, v: str): self.paste_clause_text = v
    def set_library_search(self, v: str): self.library_search = v
    def set_library_type_filter(self, v: str): self.library_type_filter = v
    def set_library_tag_filter(self, v: str): self.library_tag_filter = v
    def set_library_status_filter(self, v: str): self.library_status_filter = v
    def set_library_group_by(self, v: str): self.library_group_by = v
    def set_library_sort_by(self, v: str): self.library_sort_by = v
    def set_library_sort_desc(self, v: bool): self.library_sort_desc = v

    def set_p_section_type(self, v: str):
        self.p_section_type = v
        if v == "Base Lease":
            self.p_exhibit_code = ""
            if int(self.editing_section_id or 0) == 0:
                self.p_is_reusable = True
            if not self.p_section_name.strip():
                self.p_section_name = "Base Lease"
        elif v == "Exhibit":
            if not self.p_exhibit_code.strip():
                self.p_exhibit_code = self._next_exhibit_code()
            if not self.p_section_name.strip() and self.p_exhibit_code:
                self.p_section_name = f"Exhibit {self.p_exhibit_code}"


# ── Row components ─────────────────────────────────────────────────────────────

def source_document_row(row: SourceDocumentRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.source_document_id.to_string(), size="2", color="#666")),
        rx.table.cell(rx.text(row.template_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.property_name, size="2")),
        rx.table.cell(rx.text(row.category, size="2")),
        rx.table.cell(rx.text(row.version, size="2")),
        rx.table.cell(rx.text(row.page_count, size="2")),
        rx.table.cell(rx.text(row.uploaded_on, size="2")),
        rx.table.cell(rx.badge(row.active, color_scheme="green", variant="soft")),
        rx.table.cell(
            rx.button(
                "Split ->",
                size="1",
                variant="soft",
                color_scheme="blue",
                on_click=LeaseDocumentState.go_to_parse_tab(row.source_document_id),
                title="Select this source document and go to Parse & Section tab",
            )
        ),
        style=rx.cond(
            LeaseDocumentState.selected_source_document_id == row.source_document_id,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
    )


def source_document_card(row: SourceDocumentRow) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(row.template_name, size="2", weight="bold", color=BRAND_DARK),
                rx.spacer(),
                rx.badge(row.active, color_scheme=rx.cond(row.active == "Yes", "green", "gray"), variant="soft"),
                width="100%",
                align="center",
            ),
            rx.text(row.category + " - " + row.page_count + " pages", size="1", color="#666"),
            rx.hstack(
                rx.button("Edit", size="1", variant="soft", color_scheme="gray", on_click=LeaseDocumentState.select_source_document(row.source_document_id)),
                rx.button("Split ->", size="1", variant="soft", color_scheme="blue", on_click=LeaseDocumentState.go_to_parse_tab(row.source_document_id)),
                spacing="2",
            ),
            spacing="2",
            align_items="start",
            width="100%",
        ),
        style=rx.cond(
            LeaseDocumentState.selected_source_document_id == row.source_document_id,
            {"background": "#f0f4ff", "border": "1px solid #c5d0f0", "border_left": f"4px solid {BRAND_PRIMARY}", "border_radius": "10px", "padding": "10px", "width": "100%"},
            {"background": "white", "border": "1px solid #e5e7eb", "border_left": "4px solid transparent", "border_radius": "10px", "padding": "10px", "width": "100%"},
        ),
    )


def section_row(row: SectionRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.sort_order, size="2")),
        rx.table.cell(rx.text(row.section_type, size="2")),
        rx.table.cell(rx.text(row.exhibit_code, size="2")),
        rx.table.cell(rx.text(row.section_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.article_number, size="2")),
        rx.table.cell(rx.text(row.display_label, size="2")),
        rx.table.cell(rx.text(row.clause_tag, size="2", color="#555")),
        rx.table.cell(rx.text(row.pages, size="2")),
        rx.table.cell(
            rx.button(
                row.reusable,
                size="1",
                variant="soft",
                color_scheme=rx.cond(row.reusable == "Yes", "green", "gray"),
                on_click=LeaseDocumentState.toggle_section_reusable(row.section_id),
            )
        ),
        rx.table.cell(
            rx.button(
                row.active,
                size="1",
                variant="soft",
                color_scheme=rx.cond(row.active == "Yes", "green", "gray"),
                on_click=LeaseDocumentState.toggle_section_active(row.section_id),
            )
        ),
        rx.table.cell(
            rx.cond(
                row.content_status == "Yes",
                rx.badge("Text", color_scheme="purple", variant="soft"),
                rx.badge("PDF only", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(
            rx.hstack(
                rx.button("Edit", size="1", variant="soft", color_scheme="blue", on_click=LeaseDocumentState.edit_section(row.section_id)),
                rx.button("Delete", size="1", variant="soft", color_scheme="red", on_click=LeaseDocumentState.delete_section(row.section_id)),
                spacing="2",
            )
        ),
        style=rx.cond(
            LeaseDocumentState.editing_section_id == row.section_id,
            {"background": "#fff8e1"},
            {"background": "white"},
        ),
    )


def library_section_row(row: SectionRow) -> rx.Component:
    """Section row for the Library tab with grouping and clause metadata."""
    group_value = rx.cond(
        LeaseDocumentState.library_group_by == "Clause Tag",
        rx.cond(row.clause_tag != "", row.clause_tag, "(No tag)"),
        rx.cond(
            LeaseDocumentState.library_group_by == "Section Type",
            row.section_type,
            rx.cond(LeaseDocumentState.library_group_by == "Active Status", row.active, ""),
        ),
    )
    return rx.table.row(
        rx.table.cell(rx.text(group_value, size="1", color="#666")),
        rx.table.cell(rx.text(row.source_doc, size="1", color="#888")),
        rx.table.cell(rx.text(row.article_number, size="2")),
        rx.table.cell(rx.text(row.display_label, size="2", weight="bold")),
        rx.table.cell(rx.text(row.section_name, size="2", color="#555")),
        rx.table.cell(rx.text(row.clause_tag, size="2", color="#555")),
        rx.table.cell(
            rx.hstack(
                rx.cond(row.section_type == "Base Lease", rx.badge("Core", color_scheme="blue", variant="soft"), rx.fragment()),
                rx.cond(row.section_type == "Addendum", rx.badge("Addendum", color_scheme="purple", variant="soft"), rx.fragment()),
                rx.cond(row.has_snapshot == "Yes", rx.badge("Snapshot", color_scheme="amber", variant="soft"), rx.fragment()),
                rx.badge(row.active, color_scheme=rx.cond(row.active == "Yes", "green", "gray"), variant="soft"),
                spacing="1",
            )
        ),
        rx.table.cell(rx.text(row.updated_on, size="1", color="#666")),
        rx.table.cell(rx.text(row.pages, size="2")),
        rx.table.cell(
            rx.button(
                row.reusable,
                size="1",
                variant="soft",
                color_scheme=rx.cond(row.reusable == "Yes", "green", "gray"),
                on_click=LeaseDocumentState.toggle_section_reusable(row.section_id),
            )
        ),
        rx.table.cell(
            rx.cond(
                row.content_status == "Yes",
                rx.badge("Text", color_scheme="purple", variant="soft"),
                rx.badge("PDF only", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(
            rx.hstack(
                rx.button("Edit", size="1", variant="soft", color_scheme="blue", on_click=LeaseDocumentState.edit_section(row.section_id)),
                rx.button("Delete", size="1", variant="soft", color_scheme="red", on_click=LeaseDocumentState.delete_section(row.section_id)),
                spacing="2",
            )
        ),
        style=rx.cond(
            LeaseDocumentState.editing_section_id == row.section_id,
            {"background": "#fff8e1"},
            {"background": "white"},
        ),
    )


def draft_clause_row(row: DraftClauseRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.article_number, size="2")),
        rx.table.cell(rx.text(row.display_label, size="2", weight="bold")),
        rx.table.cell(rx.badge(row.clause_tag, color_scheme="blue", variant="soft")),
        rx.table.cell(rx.text(row.preview, size="1", color="#555")),
        rx.table.cell(
            rx.hstack(
                rx.button("Load", size="1", variant="soft", color_scheme="blue", on_click=LeaseDocumentState.load_draft_clause(row.draft_id)),
                rx.button("Save", size="1", variant="soft", color_scheme="green", on_click=LeaseDocumentState.save_draft_clause(row.draft_id)),
                spacing="2",
            )
        ),
        style={"background": "white"},
    )


def load_tab_section_row(row: SectionRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.sort_order, size="2")),
        rx.table.cell(rx.text(row.section_type, size="2")),
        rx.table.cell(rx.text(row.exhibit_code, size="2")),
        rx.table.cell(rx.text(row.section_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.article_number, size="2")),
        rx.table.cell(rx.text(row.display_label, size="2")),
        rx.table.cell(rx.text(row.clause_tag, size="2", color="#555")),
        rx.table.cell(rx.text(row.pages, size="2")),
        rx.table.cell(rx.badge(row.reusable, color_scheme=rx.cond(row.reusable == "Yes", "green", "gray"), variant="soft")),
        rx.table.cell(rx.badge(row.active, color_scheme=rx.cond(row.active == "Yes", "green", "gray"), variant="soft")),
        style={"background": "white"},
    )


def lease_template_row(row: LeaseTemplateRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.template_name, size="2", weight="bold")),
        rx.table.cell(rx.text(row.property_name, size="2")),
        rx.table.cell(rx.text(row.section_count.to_string(), size="2")),
        rx.table.cell(
            rx.cond(
                row.active == "Yes",
                rx.badge("Active", color_scheme="green", variant="soft"),
                rx.badge("Inactive", color_scheme="gray", variant="soft"),
            )
        ),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    "Select",
                    size="1",
                    variant="soft",
                    color_scheme="blue",
                    on_click=LeaseDocumentState.select_lease_template(row.template_id),
                ),
                rx.button(
                    "Add Slot",
                    size="1",
                    variant="soft",
                    color_scheme="green",
                    on_click=LeaseDocumentState.start_new_template_section_for_template(row.template_id),
                ),
                spacing="2",
            )
        ),
        style=rx.cond(
            LeaseDocumentState.selected_template_id == row.template_id,
            {"background": "#f0f4ff"},
            {"background": "white"},
        ),
    )


def lease_template_section_row(row: LeaseTemplateSectionRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.sort_order, size="2")),
        rx.table.cell(rx.text(row.section_label, size="2", weight="bold")),
        rx.table.cell(rx.text(row.section_type, size="2")),
        rx.table.cell(rx.text(row.default_section_label, size="1", color="#555")),
        rx.table.cell(
            rx.cond(
                row.inclusion_mode == "Required",
                rx.badge("Required", color_scheme="green", variant="soft"),
                rx.cond(
                    row.inclusion_mode == "Optional",
                    rx.badge("Optional", color_scheme="blue", variant="soft"),
                    rx.badge("Inactive", color_scheme="gray", variant="soft"),
                ),
            )
        ),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    "Edit",
                    size="1",
                    variant="soft",
                    color_scheme="blue",
                    on_click=LeaseDocumentState.edit_template_section(row.section_id),
                ),
                rx.button(
                    "Delete",
                    size="1",
                    variant="soft",
                    color_scheme="red",
                    on_click=LeaseDocumentState.delete_template_section(row.section_id),
                ),
                spacing="2",
            )
        ),
        style=rx.cond(
            LeaseDocumentState.selected_section_id == row.section_id,
            {"background": "#fff8e1"},
            {"background": "white"},
        ),
    )


# ── Tab content components ─────────────────────────────────────────────────────

def _feedback_callouts() -> rx.Component:
    """Error / success callouts rendered at the top of whichever tab is active."""
    return rx.vstack(
        rx.cond(
            LeaseDocumentState.form_error != "",
            rx.callout.root(rx.callout.text(LeaseDocumentState.form_error), color_scheme="red", width="100%"),
        ),
        rx.cond(
            LeaseDocumentState.form_success != "",
            rx.callout.root(rx.callout.text(LeaseDocumentState.form_success), color_scheme="green", width="100%"),
        ),
        width="100%",
        spacing="2",
    )


LEASE_DOCUMENTS_RESIZER_SCRIPT = """
(function() {
    if (window.__lucidLeaseDocDelegatedResizer === true) {
        if (window.__lucidLeaseDocApplyWidths) window.__lucidLeaseDocApplyWidths();
        return;
    }
    window.__lucidLeaseDocDelegatedResizer = true;

    var configs = {
        'lease-doc-load-resizer': { leftId: 'lease-doc-load-left-panel', storageKey: 'lucidpm_lease_doc_load_left_width', defaultWidth: 360 },
        'lease-doc-template-resizer': { leftId: 'lease-doc-template-left-panel', storageKey: 'lucidpm_lease_doc_template_left_width', defaultWidth: 420 }
    };

    function px(value, fallback) {
        var parsed = parseInt(value || '', 10);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
    }

    function applyWidths() {
        Object.keys(configs).forEach(function(handleId) {
            var cfg = configs[handleId];
            var leftPanel = document.getElementById(cfg.leftId);
            if (!leftPanel) return;
            var saved = px(localStorage.getItem(cfg.storageKey), cfg.defaultWidth);
            leftPanel.style.width = saved + 'px';
            leftPanel.style.minWidth = saved + 'px';
        });
    }
    window.__lucidLeaseDocApplyWidths = applyWidths;

    var active = null;

    document.addEventListener('mousedown', function(e) {
        var handle = e.target.closest ? e.target.closest('#lease-doc-load-resizer, #lease-doc-template-resizer') : null;
        if (!handle) return;
        var cfg = configs[handle.id];
        if (!cfg) return;
        var leftPanel = document.getElementById(cfg.leftId);
        if (!leftPanel) return;

        active = { cfg: cfg, leftPanel: leftPanel, startX: e.clientX, startWidth: leftPanel.offsetWidth || cfg.defaultWidth };
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    }, true);

    document.addEventListener('mousemove', function(e) {
        if (!active) return;
        var delta = e.clientX - active.startX;
        var maxWidth = Math.max(520, window.innerWidth - 520);
        var newWidth = Math.min(Math.max(active.startWidth + delta, 220), maxWidth);
        active.leftPanel.style.width = newWidth + 'px';
        active.leftPanel.style.minWidth = newWidth + 'px';
    }, true);

    document.addEventListener('mouseup', function() {
        if (!active) return;
        localStorage.setItem(active.cfg.storageKey, String(active.leftPanel.offsetWidth));
        active = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }, true);

    applyWidths();
    setTimeout(applyWidths, 100);
    setTimeout(applyWidths, 500);
    new MutationObserver(function() { applyWidths(); }).observe(document.body, { childList: true, subtree: true });
})();
"""


def _token_insert_button(token: str) -> rx.Component:
    return rx.button(
        token,
        size="1",
        variant="soft",
        color_scheme="purple",
        on_click=LeaseDocumentState.append_token_to_p_content(token),
    )


def _available_token_buttons_panel() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Available tokens", size="1", weight="bold", color="#555"),
            rx.hstack(
                _token_insert_button("{{TenantName}}"),
                _token_insert_button("{{TenantPrimaryContact}}"),
                _token_insert_button("{{PropertyName}}"),
                _token_insert_button("{{LandlordEntity}}"),
                _token_insert_button("{{SuiteLabel}}"),
                _token_insert_button("{{SuiteFullAddress}}"),
                _token_insert_button("{{UseType}}"),
                wrap="wrap",
                spacing="2",
            ),
            rx.hstack(
                _token_insert_button("{{LeaseStart}}"),
                _token_insert_button("{{LeaseEnd}}"),
                _token_insert_button("{{LeaseTermDescription}}"),
                _token_insert_button("{{RentAmount}}"),
                _token_insert_button("{{TotalRent}}"),
                _token_insert_button("{{PaymentScheduleBlock}}"),
                wrap="wrap",
                spacing="2",
            ),
            rx.hstack(
                _token_insert_button("{{SecurityDeposit}}"),
                _token_insert_button("{{County}}"),
                _token_insert_button("{{State}}"),
                _token_insert_button("{{LeaseNoticeAddress}}"),
                _token_insert_button("{{PropertyAddress}}"),
                _token_insert_button("{{LegalDescription}}"),
                wrap="wrap",
                spacing="2",
            ),
            rx.text("Click a token to append it to the clause text.", size="1", color="#777"),
            spacing="2",
            align_items="start",
            width="100%",
        ),
        style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
    )


def _tab_load() -> rx.Component:
    """Tab 1 - Load: upload source PDFs and edit source metadata."""
    return rx.vstack(
        rx.script(LEASE_DOCUMENTS_RESIZER_SCRIPT),
        _feedback_callouts(),
        rx.hstack(
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("Source documents", size="3", weight="bold", color=BRAND_DARK),
                        rx.spacer(),
                        rx.button("New Source Document", size="1", variant="soft", color_scheme="blue", on_click=LeaseDocumentState.new_source_document),
                        width="100%",
                        align="center",
                    ),
                    rx.text("Select a source to edit metadata or jump straight to parsing.", size="1", color="#666"),
                    rx.cond(
                        LeaseDocumentState.source_documents.length() > 0,
                        rx.vstack(rx.foreach(LeaseDocumentState.source_documents, source_document_card), spacing="2", width="100%"),
                        rx.text("No source documents yet.", size="2", color="#888"),
                    ),
                    spacing="3",
                    width="100%",
                    align_items="start",
                ),
                id="lease-doc-load-left-panel",
                style={"width": "360px", "min_width": "360px", "overflow": "auto", "height": "calc(100vh - 260px)", "background": "#ffffff", "border": "1px solid #e5e7eb", "border_radius": "12px", "padding": "14px", "flex_shrink": "0"},
            ),
            rx.box(rx.box(style={"width": "4px", "height": "44px", "background": "#c5d0f0", "border_radius": "2px"}), id="lease-doc-load-resizer", style={"width": "12px", "min_width": "12px", "align_self": "stretch", "cursor": "col-resize", "display": "flex", "align_items": "center", "justify_content": "center", "border_radius": "4px", "flex_shrink": "0", "_hover": {"background": "#f0f4ff"}}),
            rx.box(
                rx.vstack(
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.text(rx.cond(LeaseDocumentState.selected_source_document_id > 0, "Source document metadata", "New source document"), size="3", weight="bold", color=BRAND_DARK),
                                rx.spacer(),
                                rx.cond(LeaseDocumentState.selected_source_document_id > 0, rx.badge("Editing source #" + LeaseDocumentState.selected_source_document_id.to_string(), color_scheme="blue", variant="soft"), rx.badge("New upload", color_scheme="gray", variant="soft")),
                                width="100%",
                                align="center",
                            ),
                            rx.box(
                                rx.hstack(rx.text("Files stored in:", size="1", color="#666"), rx.text(LeaseDocumentState.storage_root, size="1", weight="bold", color=BRAND_DARK), rx.spacer(), rx.badge("Edit in Settings", color_scheme="gray", variant="soft"), width="100%", align="center"),
                                style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                            ),
                            rx.grid(
                                rx.vstack(rx.text("Template name", size="1", color="#666"), rx.input(value=LeaseDocumentState.f_template_name, on_change=LeaseDocumentState.set_f_template_name, placeholder="Broadway Core Lease", width="100%"), spacing="1"),
                                rx.vstack(rx.text("Property", size="1", color="#666"), rx.select(LeaseDocumentState.property_names, value=LeaseDocumentState.f_property, on_change=LeaseDocumentState.set_f_property, width="100%"), spacing="1"),
                                rx.vstack(rx.text("Category", size="1", color="#666"), rx.select(DOCUMENT_CATEGORIES, value=LeaseDocumentState.f_document_category, on_change=LeaseDocumentState.set_f_document_category, width="100%"), spacing="1"),
                                rx.vstack(rx.text("Version", size="1", color="#666"), rx.input(value=LeaseDocumentState.f_template_version, on_change=LeaseDocumentState.set_f_template_version, width="100%"), spacing="1"),
                                columns="4", spacing="3", width="100%",
                            ),
                            rx.vstack(rx.text("Notes", size="1", color="#666"), rx.text_area(value=LeaseDocumentState.f_notes, on_change=LeaseDocumentState.set_f_notes, width="100%", height="90px"), spacing="1", width="100%"),
                            rx.checkbox("Active", checked=LeaseDocumentState.f_is_active, on_change=LeaseDocumentState.set_f_is_active),
                            rx.hstack(rx.button("Save Metadata", on_click=LeaseDocumentState.save_source_document_metadata, variant="soft", color_scheme="green"), rx.button("Clear / New", on_click=LeaseDocumentState.new_source_document, variant="soft", color_scheme="gray"), spacing="3"),
                            spacing="3", width="100%", align_items="start",
                        ), width="100%",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.text("Upload source PDF", size="3", weight="bold", color=BRAND_DARK),
                            rx.text(rx.cond(LeaseDocumentState.selected_source_document_id > 0, "Uploading a new PDF creates a new source document. Existing split sections are not replaced automatically.", "Upload a source PDF, then use Split -> to define reusable sections."), size="2", color="#666"),
                            rx.upload(rx.vstack(rx.button("Choose PDF", color_scheme="blue", variant="soft"), rx.text("Drop a source lease PDF here or click to choose.", size="2", color="#666"), spacing="2", align="center"), id="lease_template_pdf_upload", accept={"application/pdf": [".pdf"]}, max_files=1, border=f"1px dashed {BRAND_PRIMARY}", padding="18px", border_radius="8px", width="100%"),
                            rx.box(rx.text("Selected file", size="1", color="#666"), rx.cond(rx.selected_files("lease_template_pdf_upload"), rx.foreach(rx.selected_files("lease_template_pdf_upload"), lambda file_name: rx.text(file_name, size="2", weight="bold", color=BRAND_DARK)), rx.text("No file selected yet.", size="2", color="#777")), style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"}),
                            rx.button("Upload Source PDF", on_click=LeaseDocumentState.handle_upload(rx.upload_files(upload_id="lease_template_pdf_upload")), color_scheme="blue"),
                            rx.cond(LeaseDocumentState.developer_tools_enabled, rx.vstack(rx.divider(), rx.text("Developer local test import", size="2", weight="bold", color="#555"), rx.hstack(rx.input(value=LeaseDocumentState.local_pdf_path, on_change=LeaseDocumentState.set_local_pdf_path, placeholder=r"C:\path\to\lease.pdf", width="100%"), rx.button("Import Path", on_click=LeaseDocumentState.import_local_pdf_for_testing, variant="soft"), width="100%"), spacing="2", width="100%")),
                            spacing="3", width="100%", align_items="start",
                        ), width="100%",
                    ),
                    rx.card(
                        rx.vstack(
                            rx.hstack(
                                rx.text("Sections for selected source", size="3", weight="bold", color=BRAND_DARK),
                                rx.spacer(),
                                rx.cond(LeaseDocumentState.selected_source_document_id > 0, rx.button("Split / Add Section", size="1", variant="soft", color_scheme="blue", on_click=LeaseDocumentState.set_tab("parse")), rx.fragment()),
                                width="100%", align="center",
                            ),
                            rx.text("Shows only the sections created from the selected source document. Use the Section Library tab to see all sections across all source documents.", size="2", color="#666"),
                            rx.cond(
                                LeaseDocumentState.sections.length() > 0,
                                rx.table.root(
                                    rx.table.header(rx.table.row(rx.table.column_header_cell("Sort"), rx.table.column_header_cell("Type"), rx.table.column_header_cell("Code"), rx.table.column_header_cell("Name"), rx.table.column_header_cell("Article"), rx.table.column_header_cell("Display Label"), rx.table.column_header_cell("Tag"), rx.table.column_header_cell("Pages"), rx.table.column_header_cell("Reusable"), rx.table.column_header_cell("Active"), rx.table.column_header_cell("Content"), rx.table.column_header_cell("Actions"))),
                                    rx.table.body(rx.foreach(LeaseDocumentState.sections, section_row)),
                                    width="100%",
                                ),
                                rx.callout.root(rx.callout.text("No sections have been created for the selected source document yet."), color_scheme="gray", width="100%"),
                            ),
                            spacing="3", width="100%", align_items="start",
                        ), width="100%",
                    ),
                    spacing="4", width="100%",
                ), style={"flex": "1", "min_width": "0"},
            ),
            spacing="3", width="100%", align_items="stretch",
        ),
        spacing="4", width="100%",
    )

def _tab_parse() -> rx.Component:
    """Tab 2 - Parse & Section: split a selected source PDF into named sections."""
    return rx.vstack(
        _feedback_callouts(),

        # Source document selector
        rx.card(
            rx.vstack(
                rx.text("Active source document", size="3", weight="bold", color=BRAND_DARK),
                rx.cond(
                    LeaseDocumentState.has_source_document,
                    rx.hstack(
                        rx.badge(LeaseDocumentState.selected_source_summary, color_scheme="blue", variant="soft"),
                        rx.text("To switch documents, go to the Load tab and click Split ->.", size="1", color="#777"),
                        spacing="3",
                        align="center",
                    ),
                    rx.cond(
                        LeaseDocumentState.p_creation_mode == "PDF Page Split",
                        rx.callout.root(
                            rx.callout.text("No source document selected. Go to the Load tab to upload a PDF and click Split ->."),
                            color_scheme="amber",
                            width="100%",
                        ),
                        rx.callout.root(
                            rx.callout.text("Standalone text clause mode. No source document is required."),
                            color_scheme="green",
                            width="100%",
                        ),
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),

        # Section split form
        rx.card(
            rx.vstack(
                # Editing banner - only visible when in edit mode
                rx.cond(
                    LeaseDocumentState.editing_section_id > 0,
                    rx.callout.root(
                        rx.callout.text(
                            rx.hstack(
                                rx.text("Editing section ID", size="2"),
                                rx.badge(LeaseDocumentState.editing_section_id.to_string(), color_scheme="amber", variant="soft"),
                                rx.text("- update the fields below and click Update Section.", size="2"),
                                rx.spacer(),
                                rx.button("Cancel Edit", on_click=LeaseDocumentState.reset_section_form, variant="soft", color_scheme="gray", size="1"),
                                spacing="2",
                                align="center",
                                width="100%",
                            )
                        ),
                        color_scheme="amber",
                        width="100%",
                    ),
                ),
                rx.text("Create section", size="3", weight="bold", color=BRAND_DARK),
                rx.text(LeaseDocumentState.parse_mode_help_text, size="2", color="#666"),
                rx.cond(
                    LeaseDocumentState.will_save_without_source_document,
                    rx.callout.root(
                        rx.callout.text("Standalone mode is active. This save will write NULL to LeaseSourceDocumentID."),
                        color_scheme="green",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                rx.grid(
                    rx.vstack(rx.text("Creation mode", size="1", color="#666"), rx.select(SECTION_CREATION_MODES, value=LeaseDocumentState.p_creation_mode, on_change=LeaseDocumentState.set_p_creation_mode, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Exhibit code", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_exhibit_code, on_change=LeaseDocumentState.set_p_exhibit_code, placeholder="A", width="100%"), spacing="1"),
                    rx.box(),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.grid(
                    rx.vstack(rx.text("Section type", size="1", color="#666"), rx.select(SECTION_TYPES, value=LeaseDocumentState.p_section_type, on_change=LeaseDocumentState.set_p_section_type, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Section name", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_section_name, on_change=LeaseDocumentState.set_p_section_name, placeholder="Article 3 - Rent", width="100%"), spacing="1"),
                    rx.box(),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.grid(
                    rx.vstack(rx.text("Article number", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_article_number, on_change=LeaseDocumentState.set_p_article_number, placeholder="4 or A", width="100%"), spacing="1"),
                    rx.vstack(rx.text("Display label", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_display_label, on_change=LeaseDocumentState.set_p_display_label, placeholder="Holdover Tenancy", width="100%"), spacing="1"),
                    rx.vstack(rx.text("Clause tag", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_clause_tag, on_change=LeaseDocumentState.set_p_clause_tag, placeholder="holdover", width="100%"), spacing="1"),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.cond(
                    LeaseDocumentState.is_text_clause_mode,
                    rx.vstack(
                        rx.hstack(
                            rx.text("Clause text", size="1", color="#666"),
                            rx.spacer(),
                            rx.badge(LeaseDocumentState.section_content_character_count, color_scheme="purple", variant="soft"),
                            width="100%",
                            align="center",
                        ),
                        rx.text_area(
                            value=LeaseDocumentState.p_content,
                            on_change=LeaseDocumentState.set_p_content,
                            placeholder="Paste or type this clause text here. This content will be saved with the new text-backed section.",
                            width="100%",
                            height="220px",
                        ),
                        rx.box(
                            rx.text("Tokens detected in this clause", size="1", weight="bold", color="#555"),
                            rx.text(LeaseDocumentState.detected_section_tokens, size="1", color="#666"),
                            style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                        ),
                        _available_token_buttons_panel(),
                        spacing="2",
                        width="100%",
                    ),
                ),
                rx.grid(
                    rx.vstack(rx.text(LeaseDocumentState.parse_page_label, size="1", color="#666"), rx.input(value=LeaseDocumentState.p_start_page, on_change=LeaseDocumentState.set_p_start_page, width="100%"), spacing="1"),
                    rx.vstack(rx.text(LeaseDocumentState.parse_end_page_label, size="1", color="#666"), rx.input(value=LeaseDocumentState.p_end_page, on_change=LeaseDocumentState.set_p_end_page, width="100%"), spacing="1"),
                    rx.vstack(rx.text("Sort order", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_sort_order, on_change=LeaseDocumentState.set_p_sort_order, width="100%"), spacing="1"),
                    rx.vstack(
                        rx.text("Flags", size="1", color="#666"),
                        rx.hstack(
                            rx.checkbox("Reusable", checked=LeaseDocumentState.p_is_reusable, on_change=LeaseDocumentState.set_p_is_reusable),
                            rx.checkbox("Active", checked=LeaseDocumentState.p_is_active, on_change=LeaseDocumentState.set_p_is_active),
                            spacing="3",
                        ),
                        spacing="1",
                    ),
                    columns="4",
                    spacing="3",
                    width="100%",
                ),
                rx.hstack(
                    rx.button(
                        LeaseDocumentState.parse_save_button_label,
                        on_click=LeaseDocumentState.create_section,
                        color_scheme="blue",
                    ),
                    rx.cond(
                        LeaseDocumentState.is_text_clause_mode,
                        rx.button("Detach From Source", on_click=LeaseDocumentState.detach_current_clause_from_source, variant="soft", color_scheme="green"),
                        rx.fragment(),
                    ),
                    rx.cond(
                        LeaseDocumentState.editing_section_id > 0,
                        rx.button("Cancel Edit", on_click=LeaseDocumentState.reset_section_form, variant="soft", color_scheme="gray"),
                    ),
                    spacing="3",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),

        # Paste-and-split clause tool
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.text("Paste-and-split clause tool", size="3", weight="bold", color=BRAND_DARK),
                    rx.spacer(),
                    rx.badge(LeaseDocumentState.draft_clause_count, color_scheme="purple", variant="soft"),
                    width="100%", align="center",
                ),
                rx.text("Paste full lease article text here to split it into draft clause sections. This is part of the Parse workflow and creates text-backed sections without changing the PDF page-split workflow.", size="2", color="#666"),
                rx.cond(
                    LeaseDocumentState.selected_source_document_id > 0,
                    rx.callout.root(rx.callout.text("Draft clauses will be saved under the active source document shown above."), color_scheme="blue", width="100%"),
                    rx.callout.root(rx.callout.text("Select a source document on the Load tab before saving pasted clauses."), color_scheme="amber", width="100%"),
                ),
                rx.text_area(
                    value=LeaseDocumentState.paste_clause_text,
                    on_change=LeaseDocumentState.set_paste_clause_text,
                    placeholder="Paste clause text here. Example: 4. Holdover Tenancy\nFailure of Tenant to surrender...",
                    width="100%",
                    height="180px",
                ),
                rx.hstack(
                    rx.text(LeaseDocumentState.paste_clause_character_count, size="1", color="#666"),
                    rx.spacer(),
                    rx.button("Split Pasted Text", on_click=LeaseDocumentState.parse_pasted_clauses, color_scheme="purple"),
                    rx.button("Save All Draft Clauses", on_click=LeaseDocumentState.save_all_draft_clauses, variant="soft", color_scheme="green"),
                    rx.button("Clear", on_click=LeaseDocumentState.clear_pasted_clause_tool, variant="soft", color_scheme="gray"),
                    width="100%", align="center", spacing="3",
                ),
                rx.cond(
                    LeaseDocumentState.has_draft_clauses,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("Article"),
                                rx.table.column_header_cell("Display label"),
                                rx.table.column_header_cell("Clause tag"),
                                rx.table.column_header_cell("Preview"),
                                rx.table.column_header_cell("Actions"),
                            )
                        ),
                        rx.table.body(rx.foreach(LeaseDocumentState.draft_clauses, draft_clause_row)),
                        width="100%",
                    ),
                    rx.text("No draft clauses yet.", size="2", color="#888"),
                ),
                spacing="3", width="100%", align_items="start",
            ),
            width="100%",
        ),


        # Sections grid for this source document
        rx.card(
            rx.vstack(
                rx.text("Sections from this source document", size="3", weight="bold", color=BRAND_DARK),
                rx.text(
                    "PDF sections can be edited in the Section Library. Text clauses may be created here, then managed in the Library.",
                    size="2", color="#666",
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Sort"),
                            rx.table.column_header_cell("Type"),
                            rx.table.column_header_cell("Code"),
                            rx.table.column_header_cell("Name"),
                            rx.table.column_header_cell("Article"),
                            rx.table.column_header_cell("Display Label"),
                            rx.table.column_header_cell("Tag"),
                            rx.table.column_header_cell("Pages"),
                            rx.table.column_header_cell("Reusable"),
                            rx.table.column_header_cell("Active"),
                            rx.table.column_header_cell("Content"),
                            rx.table.column_header_cell("Actions"),
                        )
                    ),
                    rx.table.body(rx.foreach(LeaseDocumentState.sections, section_row)),
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


def _tab_library() -> rx.Component:
    """Tab 3 - Section Library: search, filter, group, and edit clause content."""
    return rx.vstack(
        _feedback_callouts(),

        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text("Section library", size="3", weight="bold", color=BRAND_DARK),
                        rx.text("Search, filter, and manage reusable lease clauses across all source documents.", size="2", color="#666"),
                        spacing="1",
                        align_items="start",
                    ),
                    rx.spacer(),
                    rx.badge(LeaseDocumentState.library_result_count, color_scheme="blue", variant="soft"),
                    rx.button(
                        "New Standalone Clause",
                        on_click=LeaseDocumentState.new_standalone_clause,
                        size="1",
                        variant="soft",
                        color_scheme="green",
                    ),
                    width="100%",
                    align="center",
                ),
                rx.grid(
                    rx.vstack(rx.text("Search library", size="1", color="#666"), rx.input(value=LeaseDocumentState.library_search, on_change=LeaseDocumentState.set_library_search, placeholder="Search name, label, tag, source, or content", width="100%"), spacing="1", width="100%"),
                    rx.vstack(rx.text("Type", size="1", color="#666"), rx.select(["All"] + SECTION_TYPES, value=LeaseDocumentState.library_type_filter, on_change=LeaseDocumentState.set_library_type_filter, width="100%"), spacing="1", width="100%"),
                    rx.vstack(rx.text("Tag status", size="1", color="#666"), rx.select(["All", "Tagged", "Untagged"], value=LeaseDocumentState.library_tag_filter, on_change=LeaseDocumentState.set_library_tag_filter, width="100%"), spacing="1", width="100%"),
                    rx.vstack(rx.text("Active", size="1", color="#666"), rx.select(["All", "Yes", "No"], value=LeaseDocumentState.library_status_filter, on_change=LeaseDocumentState.set_library_status_filter, width="100%"), spacing="1", width="100%"),
                    columns="4",
                    spacing="3",
                    width="100%",
                ),
                rx.grid(
                    rx.vstack(rx.text("Group by", size="1", color="#666"), rx.select(["Clause Tag", "Section Type", "Active Status", "None"], value=LeaseDocumentState.library_group_by, on_change=LeaseDocumentState.set_library_group_by, width="100%"), spacing="1", width="100%"),
                    rx.vstack(rx.text("Sort by", size="1", color="#666"), rx.select(["Article Number", "Display Label", "Updated On", "Clause Tag", "Source Document"], value=LeaseDocumentState.library_sort_by, on_change=LeaseDocumentState.set_library_sort_by, width="100%"), spacing="1", width="100%"),
                    rx.vstack(rx.text("Sort direction", size="1", color="#666"), rx.checkbox("Descending", checked=LeaseDocumentState.library_sort_desc, on_change=LeaseDocumentState.set_library_sort_desc), spacing="2", width="100%"),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Group"),
                            rx.table.column_header_cell("Source"),
                            rx.table.column_header_cell("Article"),
                            rx.table.column_header_cell("Display Label"),
                            rx.table.column_header_cell("Internal Name"),
                            rx.table.column_header_cell("Tag"),
                            rx.table.column_header_cell("Badges"),
                            rx.table.column_header_cell("Updated"),
                            rx.table.column_header_cell("Pages"),
                            rx.table.column_header_cell("Reusable"),
                            rx.table.column_header_cell("Content"),
                            rx.table.column_header_cell("Actions"),
                        )
                    ),
                    rx.table.body(rx.foreach(LeaseDocumentState.filtered_library_sections, library_section_row)),
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),

        # Content editor - only shown when a section is in edit mode
        rx.cond(
            LeaseDocumentState.editing_section_id > 0,
            rx.card(
                rx.vstack(
                    rx.callout.root(
                        rx.callout.text(
                            rx.hstack(
                                rx.text("Editing content for section ID", size="2"),
                                rx.badge(LeaseDocumentState.editing_section_id.to_string(), color_scheme="amber", variant="soft"),
                                rx.spacer(),
                                rx.button("Cancel", on_click=LeaseDocumentState.reset_section_form, variant="soft", color_scheme="gray", size="1"),
                                spacing="2",
                                align="center",
                                width="100%",
                            )
                        ),
                        color_scheme="amber",
                        width="100%",
                    ),
                    rx.text("Section content", size="3", weight="bold", color=BRAND_DARK),
                    rx.text(
                        "Write the section text here. Use {{TokenName}} syntax to inject lease data at generation time.",
                        size="2", color="#666",
                    ),
                    rx.box(
                        rx.text(LeaseDocumentState.section_display_heading, size="2", weight="bold", color=BRAND_DARK),
                        style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                    ),
                    rx.grid(
                        rx.vstack(rx.text("Article number", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_article_number, on_change=LeaseDocumentState.set_p_article_number, placeholder="4 or A", width="100%"), spacing="1"),
                        rx.vstack(rx.text("Display label", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_display_label, on_change=LeaseDocumentState.set_p_display_label, placeholder="Holdover Tenancy", width="100%"), spacing="1"),
                        rx.vstack(rx.text("Clause tag", size="1", color="#666"), rx.input(value=LeaseDocumentState.p_clause_tag, on_change=LeaseDocumentState.set_p_clause_tag, placeholder="holdover", width="100%"), spacing="1"),
                        columns="3", spacing="3", width="100%",
                    ),
                    rx.hstack(
                        rx.text(LeaseDocumentState.section_content_character_count, size="1", color="#666"),
                        rx.spacer(),
                        rx.button("Copy From Snapshot", on_click=LeaseDocumentState.copy_content_from_latest_snapshot, size="1", variant="soft", color_scheme="amber"),
                        width="100%", align="center",
                    ),
                    rx.text_area(
                        value=LeaseDocumentState.p_content,
                        on_change=LeaseDocumentState.set_p_content,
                        placeholder="This Lease shall commence on {{LeaseStart}} and expire on {{LeaseEnd}}...",
                        width="100%",
                        height="280px",
                    ),
                    rx.box(
                        rx.text("Tokens detected in this section", size="1", weight="bold", color="#555"),
                        rx.text(LeaseDocumentState.detected_section_tokens, size="1", color="#666"),
                        style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px", "padding": "10px", "width": "100%"},
                    ),
                    _available_token_buttons_panel(),
                    rx.hstack(
                        rx.button(
                            "Save Section",
                            on_click=LeaseDocumentState.save_section_content,
                            color_scheme="purple",
                        ),
                        rx.button(
                            "Save Draft as New Section",
                            on_click=LeaseDocumentState.save_loaded_draft_as_section,
                            variant="soft",
                            color_scheme="green",
                        ),
                        spacing="3",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        ),

        spacing="4",
        width="100%",
    )


def _tab_templates() -> rx.Component:
    """Tab 4 - Package Templates: build and manage lease package templates."""
    left_panel = rx.box(
        rx.vstack(
            rx.hstack(rx.text("Package templates", size="3", weight="bold", color=BRAND_DARK), rx.spacer(), rx.button("New Template", on_click=LeaseDocumentState.new_lease_template, size="1", variant="soft", color_scheme="blue"), width="100%", align="center"),
            rx.cond(LeaseDocumentState.lease_templates.length() > 0, rx.table.root(rx.table.header(rx.table.row(rx.table.column_header_cell("Name"), rx.table.column_header_cell("Property"), rx.table.column_header_cell("Sections"), rx.table.column_header_cell("Active"), rx.table.column_header_cell(""))), rx.table.body(rx.foreach(LeaseDocumentState.lease_templates, lease_template_row)), width="100%"), rx.text("No package templates yet.", size="2", color="#888")),
            spacing="3", width="100%", align_items="start",
        ),
        id="lease-doc-template-left-panel",
        style={"width": "420px", "min_width": "420px", "overflow": "auto", "height": "calc(100vh - 260px)", "background": "#ffffff", "border": "1px solid #e5e7eb", "border_radius": "12px", "padding": "14px", "flex_shrink": "0"},
    )
    right_panel = rx.box(
        rx.vstack(
            rx.card(rx.vstack(rx.text(rx.cond(LeaseDocumentState.selected_template_id > 0, "Edit package template", "New package template"), size="3", weight="bold", color=BRAND_DARK), rx.grid(rx.vstack(rx.text("Template name", size="1", color="#666"), rx.input(value=LeaseDocumentState.lt_template_name, on_change=LeaseDocumentState.set_lt_template_name, placeholder="Broadway Modified-Gross", width="100%"), spacing="1", width="100%"), rx.vstack(rx.text("Property", size="1", color="#666"), rx.select(LeaseDocumentState.property_names, value=LeaseDocumentState.lt_property, on_change=LeaseDocumentState.set_lt_property, width="100%"), spacing="1", width="100%"), columns="2", spacing="3", width="100%"), rx.vstack(rx.text("Description", size="1", color="#666"), rx.text_area(value=LeaseDocumentState.lt_description, on_change=LeaseDocumentState.set_lt_description, width="100%", height="60px"), spacing="1", width="100%"), rx.checkbox("Active", checked=LeaseDocumentState.lt_is_active, on_change=LeaseDocumentState.set_lt_is_active), rx.hstack(rx.button(rx.cond(LeaseDocumentState.selected_template_id > 0, "Save Template", "Create Template"), on_click=LeaseDocumentState.save_lease_template, color_scheme="blue"), rx.button("Clear", on_click=LeaseDocumentState.new_lease_template, variant="soft", color_scheme="gray"), spacing="3"), spacing="3", width="100%", align_items="start"), width="100%"),
            rx.card(rx.vstack(rx.hstack(rx.text("Section slots", size="3", weight="bold", color=BRAND_DARK), rx.spacer(), rx.button("New Section Slot", on_click=LeaseDocumentState.reset_template_section_form, size="1", variant="soft", color_scheme="blue"), width="100%", align="center"), rx.vstack(rx.text("Active package template for slots", size="1", color="#666"), rx.cond(LeaseDocumentState.lease_template_labels.length() > 0, rx.select(LeaseDocumentState.lease_template_labels, value=LeaseDocumentState.active_template_select_value, on_change=LeaseDocumentState.set_selected_template_label, width="100%"), rx.text("Create or select a package template before adding slots.", size="2", color="#888")), spacing="1", width="100%"), rx.cond(LeaseDocumentState.selected_section_id > 0, rx.callout.root(rx.callout.text(rx.hstack(rx.text("Editing slot ID", size="2"), rx.badge(LeaseDocumentState.selected_section_id.to_string(), color_scheme="amber", variant="soft"), spacing="2", align="center")), color_scheme="amber", width="100%")), rx.grid(rx.vstack(rx.text("Section label", size="1", color="#666"), rx.input(value=LeaseDocumentState.sec_label, on_change=LeaseDocumentState.set_sec_label, placeholder="Article 3 - Rent", width="100%"), spacing="1", width="100%"), rx.vstack(rx.text("Sort order", size="1", color="#666"), rx.input(value=LeaseDocumentState.sec_sort_order, on_change=LeaseDocumentState.set_sec_sort_order, width="100%"), spacing="1", width="100%"), rx.vstack(rx.text("Section type", size="1", color="#666"), rx.select(SECTION_TYPES, value=LeaseDocumentState.sec_section_type, on_change=LeaseDocumentState.set_sec_section_type, width="100%"), spacing="1", width="100%"), columns="3", spacing="3", width="100%"), rx.vstack(rx.text("Default section", size="1", color="#666"), rx.select(LeaseDocumentState.reusable_section_labels, value=LeaseDocumentState.sec_default_section_label, on_change=LeaseDocumentState.set_sec_default_section_label, width="100%"), rx.text("Reusable, active sections only.", size="1", color="#777"), spacing="1", width="100%"), rx.vstack(rx.text("Inclusion", size="1", color="#666"), rx.select(INCLUSION_MODES, value=LeaseDocumentState.sec_inclusion_mode, on_change=LeaseDocumentState.set_sec_inclusion_mode, width="100%"), rx.text("Required means always included. Optional means user may remove. Inactive means hidden from builder.", size="1", color="#777"), spacing="1", width="100%"), rx.hstack(rx.button(rx.cond(LeaseDocumentState.selected_section_id > 0, "Save Slot", "Add Slot"), on_click=LeaseDocumentState.save_template_section, color_scheme="blue"), rx.button("Cancel", on_click=LeaseDocumentState.reset_template_section_form, variant="soft", color_scheme="gray"), spacing="3"), rx.divider(), rx.cond(LeaseDocumentState.lease_template_sections.length() > 0, rx.table.root(rx.table.header(rx.table.row(rx.table.column_header_cell("Sort"), rx.table.column_header_cell("Label"), rx.table.column_header_cell("Type"), rx.table.column_header_cell("Default section"), rx.table.column_header_cell("Inclusion"), rx.table.column_header_cell("Actions"))), rx.table.body(rx.foreach(LeaseDocumentState.lease_template_sections, lease_template_section_row)), width="100%"), rx.text("No section slots yet. Add one above.", size="2", color="#888")), spacing="3", width="100%", align_items="start"), width="100%"),
            spacing="4", width="100%",
        ), style={"flex": "1", "min_width": "0"},
    )
    return rx.vstack(rx.script(LEASE_DOCUMENTS_RESIZER_SCRIPT), _feedback_callouts(), rx.hstack(left_panel, rx.box(rx.box(style={"width": "4px", "height": "44px", "background": "#c5d0f0", "border_radius": "2px"}), id="lease-doc-template-resizer", style={"width": "12px", "min_width": "12px", "align_self": "stretch", "cursor": "col-resize", "display": "flex", "align_items": "center", "justify_content": "center", "border_radius": "4px", "flex_shrink": "0", "_hover": {"background": "#f0f4ff"}}), right_panel, spacing="3", width="100%", align_items="stretch"), spacing="4", width="100%")

def _tab_button(label: str, tab_key: str) -> rx.Component:
    return rx.button(
        label,
        on_click=LeaseDocumentState.set_tab(tab_key),
        variant=rx.cond(LeaseDocumentState.admin_lease_tab == tab_key, "solid", "soft"),
        color_scheme=rx.cond(LeaseDocumentState.admin_lease_tab == tab_key, "blue", "gray"),
        size="2",
    )


# ── Page assembly ──────────────────────────────────────────────────────────────

def lease_documents_content() -> rx.Component:
    return rx.vstack(
        rx.heading("Lease Documents", size="6", color=BRAND_DARK),
        rx.text(
            "Admin library for source documents, reusable sections, and lease package templates.",
            size="2",
            color="#555",
        ),

        # Tab bar
        rx.hstack(
            _tab_button("Load", "load"),
            _tab_button("Parse & Section", "parse"),
            _tab_button("Section Library", "library"),
            _tab_button("Package Templates", "templates"),
            spacing="2",
            width="100%",
        ),

        rx.divider(),

        # Tab panes - only the active tab renders
        rx.cond(LeaseDocumentState.admin_lease_tab == "load", _tab_load()),
        rx.cond(LeaseDocumentState.admin_lease_tab == "parse", _tab_parse()),
        rx.cond(LeaseDocumentState.admin_lease_tab == "library", _tab_library()),
        rx.cond(LeaseDocumentState.admin_lease_tab == "templates", _tab_templates()),

        spacing="4",
        width="100%",
    )


def lease_documents_page() -> rx.Component:
    return page_shell(lease_documents_content(), current_path="/admin/lease-templates")

# v3.0.13 token business ordering patch applied
