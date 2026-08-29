# LucidoPM — ChatGPT Handoff 53
*Lease Templates: reorder the tabs + rebuild the Section Library as list / detail*
*Prepared: 2026-08-29*

---

## What This Is

The Lease Templates admin area (`/admin/lease-templates`, one page, four tabs) forces constant hopping. This is the **first, deliberately small** step of a larger reorganization — it does **only two things**, both UI-only:

1. **Reorder the tab bar** to the order Mark actually works in: `Package Templates` · `Section Library` · `Parse & Section` · `Load` (today it's the reverse).
2. **Rebuild the Section Library tab** from its current "big filter card → very wide table → editor card appears below" into LucidPM's standard **left scrollable list / right detail** layout (the same shape the Load and Package Templates tabs already use): pick a section on the left, view/edit it on the right with a proper header bar (badges, tag, group, source info) and **Edit / Delete** buttons in that header — exactly like the Tenants and Work Items detail panels.

**Explicitly NOT in this handoff** (later steps): merging Parse & Section into the Library, inline section editing from Package Templates, the section-duplicate feature, the merge-token catalog, retiring the Load tab, adding any new editable fields to the Library editor. Use **only the fields and handlers that already exist**. If you find yourself adding a column to `LeaseDocumentSections`, changing `save_section_content`'s column list, or touching `lease_merge.py` / the PDF renderer — stop, that's out of scope.

**One file changes: `LucidPM/pages/lease_documents.py`.** No schema change, no other file.

---

## Current State

### The tab bar — `lease_documents_content()` (lines ~3898–3927)

```python
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
```

Tab keys are `"load" | "parse" | "library" | "templates"` — **keep these keys unchanged**, only the visible order changes. Default tab: `admin_lease_tab: str = "load"` (line ~348).

### The standard list/detail shape (copy this pattern) — `_tab_load()` (lines ~3360–3455)

```python
    return rx.vstack(
        rx.script(LEASE_DOCUMENTS_RESIZER_SCRIPT),
        _feedback_callouts(),
        rx.hstack(
            rx.box(  # LEFT PANEL
                rx.vstack( ...list header + rx.foreach(..., source_document_card)... ),
                id="lease-doc-load-left-panel",
                style={"width": "360px", "min_width": "360px", "overflow": "auto",
                       "height": "calc(100vh - 260px)", "background": "#ffffff",
                       "border": "1px solid #e5e7eb", "border_radius": "12px",
                       "padding": "14px", "flex_shrink": "0"},
            ),
            rx.box(rx.box(style={...4px handle...}), id="lease-doc-load-resizer",
                   style={"width": "12px", "min_width": "12px", "align_self": "stretch",
                          "cursor": "col-resize", ...}),
            rx.box(  # RIGHT PANEL
                rx.vstack( ...detail cards... ),
                style={"flex": "1", "min_width": "0"},
            ),
            spacing="3", width="100%", align_items="stretch",
        ),
        spacing="4", width="100%",
    )
```

The **left-list card** pattern — `source_document_card()` (lines ~2807–2832): an `rx.box` with a `vstack` (bold name, small meta line, action buttons) whose `style` is an `rx.cond` on the selected id that adds `border_left: "4px solid {BRAND_PRIMARY}"` + `background: "#f0f4ff"` when selected.

### The resizer script — `LEASE_DOCUMENTS_RESIZER_SCRIPT` (lines ~3114–3182)

A window-singleton delegated resizer. Two things are hardcoded and must gain a third entry:

```javascript
    var configs = {
        'lease-doc-load-resizer': { leftId: 'lease-doc-load-left-panel', storageKey: 'lucidpm_lease_doc_load_left_width', defaultWidth: 360 },
        'lease-doc-template-resizer': { leftId: 'lease-doc-template-left-panel', storageKey: 'lucidpm_lease_doc_template_left_width', defaultWidth: 420 }
    };
```
```javascript
        var handle = e.target.closest ? e.target.closest('#lease-doc-load-resizer, #lease-doc-template-resizer') : null;
```

### Section Library today — `_tab_library()` (lines ~3716–3863)

- A single `rx.card` containing: header (`"Section library"` + `library_result_count` badge + `New Standalone Clause` button), a 4-col filter `rx.grid` (`library_search`, `library_type_filter`, `library_tag_filter`, `library_status_filter`), a 3-col `rx.grid` (`library_group_by`, `library_sort_by`, `library_sort_desc`), then a very wide `rx.table` of `rx.foreach(filtered_library_sections, library_section_row)`.
- Below it, `rx.cond(editing_section_id > 0, rx.card(...editor...))` — the editor only appears after clicking **Edit** in a table row. The editor card holds: the "Editing content for section ID {n}" amber callout with a Cancel, `section_display_heading` box, a 3-col grid of **Article number / Display label / Clause tag** inputs (`p_article_number`, `p_display_label`, `p_clause_tag`), a char-count + `Copy From Snapshot` button, the content `rx.text_area(id="lease-section-content-textarea", value=p_content, ...)`, a "Tokens detected" box, `_available_token_buttons_panel("lease-section-content-textarea")`, and `Save Section` / `Save Draft as New Section` buttons.

### Handlers & state that already exist (use these — do not add fields)

| Name | Line | What it does |
|---|---|---|
| `filtered_library_sections` (`@rx.var` → `list[SectionRow]`) | ~511 | search + type/tag/active filter, then group/sort. Drives the list. |
| `library_result_count` (`@rx.var`) | ~557 | `"N section(s) shown"` |
| `section_display_heading` (`@rx.var`) | ~497 | `"{article} | {label} | Tag: {tag}"` from the `p_*` vars |
| `edit_section(section_id)` | ~1405 | loads one section into `editing_section_id` + all `p_*` vars. **Does not change the tab.** |
| `delete_section(section_id)` | ~1436 | deletes, or archives (`IsActive=0`) if used by a package; clears the form if it was the one being edited |
| `save_section_content()` | ~1564 | `UPDATE … SET ClauseTag, ArticleNumber, DisplayLabel, Content` (only those 4). Library-only — not called from Parse. |
| `save_loaded_draft_as_section()` | — | "Save Draft as New Section" |
| `copy_content_from_latest_snapshot()` | ~1589 | the `Copy From Snapshot` button |
| `new_standalone_clause()` | ~1367 | clears the form for a new clause **and switches to the Parse tab** (`admin_lease_tab = "parse"`) |
| `toggle_section_active(section_id)` | ~1551 | flips `IsActive` |
| `toggle_section_reusable(section_id)` | ~1535 | flips `IsReusable` |
| `reset_section_form()` | ~1348 | clears `editing_section_id` + `p_*` |
| `SectionRow` fields | ~288 | `section_id, source_doc, source_property, section_type, section_name, clause_tag, article_number, display_label, exhibit_code, pages, sort_order, reusable ("Yes"/"No"), active ("Yes"/"No"), content_status ("Yes"/"No"), content_text, updated_on, has_snapshot ("Yes"/"No")` |
| `p_*` editable vars | ~421–432 | `p_section_type, p_section_name, p_exhibit_code, p_sort_order, p_is_reusable, p_is_active, p_clause_tag, p_article_number, p_display_label, p_content` |

---

## The Fix

### Part A — Reorder the tab bar

**In `lease_documents_content()`** replace the tab-bar `rx.hstack` and the tab-pane `rx.cond` block:

**Current:**
```python
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
```

**Replace with:**
```python
        # Tab bar — ordered by how often each is used (Handoff 53)
        rx.hstack(
            _tab_button("Package Templates", "templates"),
            _tab_button("Section Library", "library"),
            _tab_button("Parse & Section", "parse"),
            _tab_button("Load", "load"),
            spacing="2",
            width="100%",
        ),

        rx.divider(),

        # Tab panes - only the active tab renders
        rx.cond(LeaseDocumentState.admin_lease_tab == "templates", _tab_templates()),
        rx.cond(LeaseDocumentState.admin_lease_tab == "library", _tab_library()),
        rx.cond(LeaseDocumentState.admin_lease_tab == "parse", _tab_parse()),
        rx.cond(LeaseDocumentState.admin_lease_tab == "load", _tab_load()),
```

**And change the default landing tab** (line ~348):

**Current:** `    admin_lease_tab: str = "load"`
**Replace with:** `    admin_lease_tab: str = "templates"`

Leave the `"load" | "parse" | "library" | "templates"` keys, `set_tab()`, `go_to_parse_tab()`, `new_standalone_clause()` (still sends to `"parse"`), and every other tab reference untouched.

---

### Part B — New Section Library state (small additions)

Add to `LeaseDocumentState` near the other `library_*` vars (~line 370):

```python
    # Section Library list/detail: "view" shows the section read-only with a
    # header bar; "edit" shows the existing editable form. Handoff 53.
    library_detail_mode: str = "view"
```

Add these handlers near `edit_section` / `reset_section_form`:

```python
    def select_library_section(self, section_id: int):
        """Select a section in the Library list and show it read-only."""
        self.edit_section(section_id)      # loads editing_section_id + p_* vars
        self.library_detail_mode = "view"

    def start_library_edit(self):
        self.form_error = ""
        self.form_success = ""
        self.library_detail_mode = "edit"

    def cancel_library_edit(self):
        """Discard unsaved edits and return to read-only view."""
        if int(self.editing_section_id or 0) > 0:
            self.edit_section(int(self.editing_section_id))   # reload from DB
        self.library_detail_mode = "view"

    def close_library_section(self):
        self.reset_section_form()
        self.library_detail_mode = "view"
```

Add two `@rx.var`s near `section_display_heading` for the header bar's display-only bits (the `p_*` vars already cover name/type/tag/article/label/flags; these cover the rest from `all_sections`):

```python
    def _selected_library_row(self) -> "SectionRow":
        for row in self.all_sections:
            if int(row.section_id) == int(self.editing_section_id or 0):
                return row
        return SectionRow()

    @rx.var
    def selected_library_group(self) -> str:
        row = self._selected_library_row()
        if self.library_group_by == "Clause Tag":
            return (row.clause_tag or "").strip() or "(No tag)"
        if self.library_group_by == "Section Type":
            return row.section_type
        if self.library_group_by == "Active Status":
            return row.active
        return ""

    @rx.var
    def selected_library_meta(self) -> str:
        row = self._selected_library_row()
        if int(self.editing_section_id or 0) <= 0:
            return ""
        parts = [f"ID {row.section_id}"]
        if str(row.source_doc or "").strip():
            parts.append(f"Source: {row.source_doc}")
        if str(row.pages or "").strip() and row.pages != "0-0":
            parts.append(f"Pages {row.pages}")
        if str(row.updated_on or "").strip():
            parts.append(f"Updated {row.updated_on}")
        return "  ·  ".join(parts)
```

> If Reflex rejects returning a `SectionRow` from a plain helper used inside an `@rx.var`, inline the loop into each `@rx.var` instead — the logic is trivial and there are only two.

**Do not** modify `edit_section`, `save_section_content`, `delete_section`, `filtered_library_sections`, or any `SectionRow`/`p_*` definition.

---

### Part C — Register the Library resizer

In `LEASE_DOCUMENTS_RESIZER_SCRIPT`, add the third panel.

**Current:**
```javascript
    var configs = {
        'lease-doc-load-resizer': { leftId: 'lease-doc-load-left-panel', storageKey: 'lucidpm_lease_doc_load_left_width', defaultWidth: 360 },
        'lease-doc-template-resizer': { leftId: 'lease-doc-template-left-panel', storageKey: 'lucidpm_lease_doc_template_left_width', defaultWidth: 420 }
    };
```
**Replace with:**
```javascript
    var configs = {
        'lease-doc-load-resizer': { leftId: 'lease-doc-load-left-panel', storageKey: 'lucidpm_lease_doc_load_left_width', defaultWidth: 360 },
        'lease-doc-template-resizer': { leftId: 'lease-doc-template-left-panel', storageKey: 'lucidpm_lease_doc_template_left_width', defaultWidth: 420 },
        'lease-doc-library-resizer': { leftId: 'lease-doc-library-left-panel', storageKey: 'lucidpm_lease_doc_library_left_width', defaultWidth: 340 }
    };
```

**Current:**
```javascript
        var handle = e.target.closest ? e.target.closest('#lease-doc-load-resizer, #lease-doc-template-resizer') : null;
```
**Replace with:**
```javascript
        var handle = e.target.closest ? e.target.closest('#lease-doc-load-resizer, #lease-doc-template-resizer, #lease-doc-library-resizer') : null;
```

---

### Part D — Rebuild `_tab_library()`

Replace the **entire** `_tab_library()` function with the list/detail layout below. It reuses every existing handler; nothing new is saved.

```python
def _library_list_item(row: SectionRow) -> rx.Component:
    """Left-list card: internal name + group value + a couple of status chips."""
    group_value = rx.cond(
        LeaseDocumentState.library_group_by == "Clause Tag",
        rx.cond(row.clause_tag != "", row.clause_tag, "(No tag)"),
        rx.cond(
            LeaseDocumentState.library_group_by == "Section Type",
            row.section_type,
            rx.cond(LeaseDocumentState.library_group_by == "Active Status", row.active, ""),
        ),
    )
    return rx.box(
        rx.vstack(
            rx.text(row.section_name, size="2", weight="bold", color=BRAND_DARK),
            rx.hstack(
                rx.cond(group_value != "", rx.badge(group_value, color_scheme="gray", variant="soft"), rx.fragment()),
                rx.cond(
                    row.content_status == "Yes",
                    rx.badge("Text", color_scheme="purple", variant="soft"),
                    rx.badge("PDF", color_scheme="gray", variant="soft"),
                ),
                rx.cond(row.active == "No", rx.badge("Inactive", color_scheme="gray", variant="soft"), rx.fragment()),
                spacing="1",
                wrap="wrap",
            ),
            spacing="1",
            align_items="start",
            width="100%",
        ),
        on_click=LeaseDocumentState.select_library_section(row.section_id),
        style=rx.cond(
            LeaseDocumentState.editing_section_id == row.section_id,
            {"background": "#f0f4ff", "border": "1px solid #c5d0f0", "border_left": f"4px solid {BRAND_PRIMARY}",
             "border_radius": "10px", "padding": "9px 11px", "width": "100%", "cursor": "pointer"},
            {"background": "white", "border": "1px solid #e5e7eb", "border_left": "4px solid transparent",
             "border_radius": "10px", "padding": "9px 11px", "width": "100%", "cursor": "pointer"},
        ),
    )


def _library_header_bar() -> rx.Component:
    """Right-panel header: heading, badges, tag, group, source info, Edit/Delete."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(
                    rx.cond(LeaseDocumentState.p_section_name != "", LeaseDocumentState.p_section_name, "Section"),
                    size="4", weight="bold", color=BRAND_DARK,
                ),
                rx.spacer(),
                rx.cond(
                    LeaseDocumentState.library_detail_mode == "view",
                    rx.hstack(
                        rx.button("Edit", size="1", variant="soft", color_scheme="blue",
                                  on_click=LeaseDocumentState.start_library_edit),
                        rx.button("Delete", size="1", variant="soft", color_scheme="red",
                                  on_click=LeaseDocumentState.delete_section(LeaseDocumentState.editing_section_id)),
                        rx.button("Close", size="1", variant="ghost", color_scheme="gray",
                                  on_click=LeaseDocumentState.close_library_section),
                        spacing="2",
                    ),
                    rx.hstack(
                        rx.button("Save Section", size="1", color_scheme="purple",
                                  on_click=LeaseDocumentState.save_section_content),
                        rx.button("Cancel", size="1", variant="soft", color_scheme="gray",
                                  on_click=LeaseDocumentState.cancel_library_edit),
                        spacing="2",
                    ),
                ),
                width="100%", align="center",
            ),
            rx.hstack(
                rx.badge(
                    LeaseDocumentState.p_section_type,
                    color_scheme=rx.cond(LeaseDocumentState.p_section_type == "Base Lease", "blue",
                                 rx.cond(LeaseDocumentState.p_section_type == "Addendum", "purple", "gray")),
                    variant="soft",
                ),
                rx.cond(LeaseDocumentState.p_clause_tag != "",
                        rx.badge("Tag: " + LeaseDocumentState.p_clause_tag, color_scheme="cyan", variant="soft"),
                        rx.fragment()),
                rx.cond(LeaseDocumentState.selected_library_group != "",
                        rx.badge("Group: " + LeaseDocumentState.selected_library_group, color_scheme="gray", variant="soft"),
                        rx.fragment()),
                # Active / Reusable stay clickable toggles (existing handlers)
                rx.button(rx.cond(LeaseDocumentState.p_is_active, "Active", "Inactive"),
                          size="1", variant="soft",
                          color_scheme=rx.cond(LeaseDocumentState.p_is_active, "green", "gray"),
                          on_click=LeaseDocumentState.toggle_section_active(LeaseDocumentState.editing_section_id)),
                rx.button(rx.cond(LeaseDocumentState.p_is_reusable, "Reusable", "Hidden"),
                          size="1", variant="soft",
                          color_scheme=rx.cond(LeaseDocumentState.p_is_reusable, "green", "gray"),
                          on_click=LeaseDocumentState.toggle_section_reusable(LeaseDocumentState.editing_section_id)),
                spacing="1", wrap="wrap", align="center",
            ),
            rx.text(LeaseDocumentState.selected_library_meta, size="1", color="#777"),
            spacing="2", align_items="start", width="100%",
        ),
        style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "10px",
               "padding": "12px 14px", "width": "100%"},
    )


def _library_view_body() -> rx.Component:
    """Read-only content for the selected section."""
    return rx.vstack(
        rx.grid(
            rx.vstack(rx.text("Article number", size="1", color="#666"),
                      rx.text(rx.cond(LeaseDocumentState.p_article_number != "", LeaseDocumentState.p_article_number, "—"),
                              size="2", weight="bold"), spacing="1"),
            rx.vstack(rx.text("Display label", size="1", color="#666"),
                      rx.text(rx.cond(LeaseDocumentState.p_display_label != "", LeaseDocumentState.p_display_label, "—"),
                              size="2", weight="bold"), spacing="1"),
            rx.vstack(rx.text("Internal name", size="1", color="#666"),
                      rx.text(LeaseDocumentState.p_section_name, size="2"), spacing="1"),
            columns="3", spacing="3", width="100%",
        ),
        rx.text("Content", size="1", color="#666"),
        rx.box(
            rx.text(
                rx.cond(LeaseDocumentState.p_content != "", LeaseDocumentState.p_content,
                        "This section has no text content (PDF-only or header-only)."),
                size="1", color="#333", white_space="pre-wrap",
            ),
            style={"background": "#ffffff", "border": "1px solid #e1e5ee", "border_radius": "8px",
                   "padding": "12px", "width": "100%", "max_height": "420px", "overflow": "auto",
                   "font_family": "monospace"},
        ),
        spacing="3", width="100%", align_items="start",
    )


def _library_edit_body() -> rx.Component:
    """Editable form — the existing Library editor fields, unchanged."""
    return rx.vstack(
        rx.grid(
            rx.vstack(rx.text("Article number", size="1", color="#666"),
                      rx.input(value=LeaseDocumentState.p_article_number, on_change=LeaseDocumentState.set_p_article_number,
                               placeholder="4 or A", width="100%"), spacing="1"),
            rx.vstack(rx.text("Display label", size="1", color="#666"),
                      rx.input(value=LeaseDocumentState.p_display_label, on_change=LeaseDocumentState.set_p_display_label,
                               placeholder="Holdover Tenancy", width="100%"), spacing="1"),
            rx.vstack(rx.text("Clause tag", size="1", color="#666"),
                      rx.input(value=LeaseDocumentState.p_clause_tag, on_change=LeaseDocumentState.set_p_clause_tag,
                               placeholder="holdover", width="100%"), spacing="1"),
            columns="3", spacing="3", width="100%",
        ),
        rx.hstack(
            rx.text(LeaseDocumentState.section_content_character_count, size="1", color="#666"),
            rx.spacer(),
            rx.button("Copy From Snapshot", on_click=LeaseDocumentState.copy_content_from_latest_snapshot,
                      size="1", variant="soft", color_scheme="amber"),
            width="100%", align="center",
        ),
        rx.text_area(
            id="lease-section-content-textarea",
            value=LeaseDocumentState.p_content,
            on_change=LeaseDocumentState.set_p_content,
            placeholder="This Lease shall commence on {{LeaseStart}}...",
            width="100%", height="280px",
        ),
        rx.box(
            rx.text("Tokens detected in this section", size="1", weight="bold", color="#555"),
            rx.text(LeaseDocumentState.detected_section_tokens, size="1", color="#666"),
            style={"background": "#f8f9fc", "border": "1px solid #e1e5ee", "border_radius": "8px",
                   "padding": "10px", "width": "100%"},
        ),
        _available_token_buttons_panel("lease-section-content-textarea"),
        rx.button("Save Draft as New Section", on_click=LeaseDocumentState.save_loaded_draft_as_section,
                  variant="soft", color_scheme="green"),
        spacing="3", width="100%", align_items="start",
    )


def _tab_library() -> rx.Component:
    """Tab: Section Library — left scrollable list, right view/edit detail."""
    left_panel = rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Section Library", size="3", weight="bold", color=BRAND_DARK),
                rx.spacer(),
                rx.badge(LeaseDocumentState.library_result_count, color_scheme="blue", variant="soft"),
                width="100%", align="center",
            ),
            rx.button("New Standalone Clause", on_click=LeaseDocumentState.new_standalone_clause,
                      size="1", variant="soft", color_scheme="green", width="100%"),
            rx.input(value=LeaseDocumentState.library_search, on_change=LeaseDocumentState.set_library_search,
                     placeholder="Search name, label, tag, source, content", width="100%"),
            rx.grid(
                rx.vstack(rx.text("Type", size="1", color="#666"),
                          rx.select(["All"] + SECTION_TYPES, value=LeaseDocumentState.library_type_filter,
                                    on_change=LeaseDocumentState.set_library_type_filter, width="100%"), spacing="1"),
                rx.vstack(rx.text("Active", size="1", color="#666"),
                          rx.select(["All", "Yes", "No"], value=LeaseDocumentState.library_status_filter,
                                    on_change=LeaseDocumentState.set_library_status_filter, width="100%"), spacing="1"),
                rx.vstack(rx.text("Tag status", size="1", color="#666"),
                          rx.select(["All", "Tagged", "Untagged"], value=LeaseDocumentState.library_tag_filter,
                                    on_change=LeaseDocumentState.set_library_tag_filter, width="100%"), spacing="1"),
                rx.vstack(rx.text("Group by", size="1", color="#666"),
                          rx.select(["Clause Tag", "Section Type", "Active Status", "None"],
                                    value=LeaseDocumentState.library_group_by,
                                    on_change=LeaseDocumentState.set_library_group_by, width="100%"), spacing="1"),
                rx.vstack(rx.text("Sort by", size="1", color="#666"),
                          rx.select(["Article Number", "Display Label", "Updated On", "Clause Tag", "Source Document"],
                                    value=LeaseDocumentState.library_sort_by,
                                    on_change=LeaseDocumentState.set_library_sort_by, width="100%"), spacing="1"),
                rx.vstack(rx.text("Direction", size="1", color="#666"),
                          rx.checkbox("Descending", checked=LeaseDocumentState.library_sort_desc,
                                      on_change=LeaseDocumentState.set_library_sort_desc), spacing="1"),
                columns="2", spacing="2", width="100%",
            ),
            rx.divider(),
            rx.cond(
                LeaseDocumentState.filtered_library_sections.length() > 0,
                rx.vstack(rx.foreach(LeaseDocumentState.filtered_library_sections, _library_list_item),
                          spacing="2", width="100%"),
                rx.text("No sections match the current filters.", size="2", color="#888"),
            ),
            spacing="3", width="100%", align_items="start",
        ),
        id="lease-doc-library-left-panel",
        style={"width": "340px", "min_width": "340px", "overflow": "auto", "height": "calc(100vh - 260px)",
               "background": "#ffffff", "border": "1px solid #e5e7eb", "border_radius": "12px",
               "padding": "14px", "flex_shrink": "0"},
    )

    resizer = rx.box(
        rx.box(style={"width": "4px", "height": "44px", "background": "#c5d0f0", "border_radius": "2px"}),
        id="lease-doc-library-resizer",
        style={"width": "12px", "min_width": "12px", "align_self": "stretch", "cursor": "col-resize",
               "display": "flex", "align_items": "center", "justify_content": "center",
               "border_radius": "4px", "flex_shrink": "0", "_hover": {"background": "#f0f4ff"}},
    )

    right_panel = rx.box(
        rx.cond(
            LeaseDocumentState.editing_section_id > 0,
            rx.vstack(
                _library_header_bar(),
                rx.cond(
                    LeaseDocumentState.library_detail_mode == "edit",
                    _library_edit_body(),
                    _library_view_body(),
                ),
                spacing="4", width="100%",
            ),
            rx.box(
                rx.text("Select a section from the list to view or edit it.", size="2", color="#888"),
                style={"padding": "24px"},
            ),
        ),
        style={"flex": "1", "min_width": "0", "overflow": "auto", "height": "calc(100vh - 260px)"},
    )

    return rx.vstack(
        rx.script(LEASE_DOCUMENTS_RESIZER_SCRIPT),
        _feedback_callouts(),
        rx.hstack(left_panel, resizer, right_panel, spacing="3", width="100%", align_items="stretch"),
        spacing="4", width="100%",
    )
```

**After this replaces the old `_tab_library()`, the old `library_section_row()` function (lines ~2885–2942) is no longer referenced — delete it.** (Verify with a search that nothing else calls it; `section_row()` at ~2835 is still used by the Load/Parse tabs — leave that one.)

---

## Do Not Touch

| What | Why |
|---|---|
| `edit_section`, `save_section_content`, `delete_section`, `save_loaded_draft_as_section`, `copy_content_from_latest_snapshot`, `create_section` | Reused as-is. `save_section_content` still writes only Tag/Article/Label/Content — that's the "existing functionality" line. |
| `SectionRow`, the `p_*` vars, `filtered_library_sections`, `library_*` filter vars & setters | Unchanged. |
| `_tab_parse()`, `_tab_load()`, `_tab_templates()`, `section_row()`, `source_document_card()` | Only the Library tab and the tab-bar order change. The Parse tab still shows its own edit form for `editing_section_id > 0` — that shared behavior is fine and stays. |
| `LeaseDocumentSections` schema / any DB table | No schema change in this handoff. |
| Tab keys `"load" / "parse" / "library" / "templates"`, `set_tab()`, `go_to_parse_tab()` | Only display order + default value change. |
| `lease_merge.py`, `lease_documents_pdf.py`, `lease_package_builder.py` | Not involved. |

---

## Validation Checklist

- [ ] Tab bar reads **Package Templates · Section Library · Parse & Section · Load**, left to right.
- [ ] Opening `/admin/lease-templates` lands on **Package Templates**.
- [ ] All four tabs still switch and render without error; Parse & Section and Load are visually unchanged.
- [ ] Section Library shows a left scrollable list (each item = internal name + group badge + Text/PDF + Inactive) and an empty right panel until a section is picked.
- [ ] The left panel is drag-resizable via its handle, and the width persists across a reload (localStorage key `lucidpm_lease_doc_library_left_width`).
- [ ] Search / Type / Active / Tag status / Group by / Sort by / Direction all still filter and reorder the list. Changing **Group by** changes the badge shown on each list item and the "Group: …" badge in the header.
- [ ] Clicking a list item highlights it (left accent) and shows it **read-only** on the right: header bar with Core/Addendum/Other badge, Tag badge, Group badge, clickable Active + Reusable toggles, and an `ID / Source / Pages / Updated` meta line; below it the article/label/name and the content in a read-only mono box.
- [ ] **Edit** in the header switches the right side to the existing editable form (article/label/tag inputs, char count, Copy From Snapshot, content textarea, token panel, Save Draft as New Section). Header buttons become **Save Section / Cancel**.
- [ ] **Save Section** persists Tag/Article/Label/Content (unchanged behavior), shows the green callout, and returns to read-only view with the new values; the list item reflects any tag/label change.
- [ ] **Cancel** discards unsaved edits (reloads from DB) and returns to read-only view.
- [ ] **Delete** on an unused section deletes it and clears the right panel; on a package-used section it archives (`Active` flips to No) and shows the "archived instead of deleted" message.
- [ ] The **Active** and **Reusable** toggle buttons in the header still flip those flags immediately.
- [ ] **New Standalone Clause** still jumps to the Parse & Section tab with a blank form (existing behavior).
- [ ] The content textarea keeps `id="lease-section-content-textarea"` so the token-insert buttons still insert at the cursor.
- [ ] All 17 registered pages compile; `reflex run --backend-only` starts clean.

---

## How to Deliver This

Per `CLAUDE.md`: edit `LucidPM/pages/lease_documents.py` in place, no `_vN` files. One commit (e.g. "Reorder lease-template tabs and rebuild Section Library as list/detail"). If `lease_documents.py` has no un-archived `_vN` siblings left, skip the archive step; if it does, move `pages/lease_documents_v*.py` and `pages/LeaseDocuments History/` into `Archived Versions/` as a separate commit **after** Mark verifies.

---

## File Locations

```
C:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\pages\lease_documents.py   ← the only file that changes
      lease_documents_content()          — Part A (tab order + default)
      LeaseDocumentState (~line 348, 370) — Part A default, Part B state
      LEASE_DOCUMENTS_RESIZER_SCRIPT      — Part C
      _tab_library() + new helpers        — Part D
      library_section_row()               — delete (Part D)

Frontend: http://localhost:3000   Backend: http://localhost:8000
Test DB green banner · Prod DB red banner
```

---

*Two UI changes, one file, zero new saved fields. Reorder four tabs; turn the Section Library's wide table into the same list/detail panel the Load and Package Templates tabs already use, with a Tenants-style header bar (badges, tag, group, Edit/Delete) driving the existing edit form. Everything the Library could already do, it still does — it's just laid out like the rest of the app.*
