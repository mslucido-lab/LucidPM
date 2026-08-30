# LucidoPM — ChatGPT Handoff 54
*Make the Section Library the one place to create + edit sections; retire the Parse & Section tab*
*Prepared: 2026-08-29*

---

## What This Is

Handoff 53 turned the Section Library into a list/detail editor. This handoff finishes the job Mark described: the Library becomes the **single home for everything about a section** — browse, edit *every* field, and **create** (text clause, PDF page-split, and bulk paste-and-split) — and the **Parse & Section tab is deleted**.

End state = **three single-purpose tabs**:

| Tab | Job |
|---|---|
| Package Templates | assemble sections into templates |
| Section Library | browse · edit · **create** sections |
| Load | upload / manage the raw source PDFs — nothing else |

**One file: `LucidPM/pages/lease_documents.py`.** No schema change. No `lease_merge.py` / PDF-renderer change.

**Deliver in three phases** — each compiles and is verifiable on its own, so Mark can check after each:

- **Phase 1** — complete the Library *edit* form (Section name / type / exhibit code + full save). Small, independent.
- **Phase 2** — add `+ New section` to the Library (text / from-PDF / bulk paste-split), reusing Parse's existing backend.
- **Phase 3** — delete `_tab_parse`, rewire the Load tab, strip the now-dead code.

**Scope guard:** this is a relocation, not a rewrite. The paste-and-split *parsing heuristics* and the PDF-split call move **verbatim** — do not reimplement them. No new columns, no new merge tokens, no touching generation.

---

## Current State (real references, `lease_documents.py`)

### The editors today

- **Library edit form** — `_library_edit_body()` (~line 3838): Article # / Display label / Clause tag inputs, char count + Copy From Snapshot, content `rx.text_area(id="lease-section-content-textarea")`, token panel, "Save Draft as New Section".
- **Library save** — `save_library_section()` (~1656) → `save_section_content()` (~1631): `UPDATE LeaseDocumentSections SET ClauseTag=?, ArticleNumber=?, DisplayLabel=?, Content=?, UpdatedOn=SYSDATETIME()` — **only those four columns.**
- **Library header** — `_library_header_bar()` (~3767): name, type badge, `Tag:`/`Group:` badges, Active/Reusable toggle buttons, meta line, Edit/Delete/Close (view) or Save/Cancel (edit).

### Parse & Section (`_tab_parse()`, ~3471–3725) — everything that must move

1. **Section form** — `Creation mode` (`p_creation_mode`, `SECTION_CREATION_MODES = ["PDF Page Split", "Text Clause"]`), Exhibit code, Section type, Section name, Article #, Display label, Clause tag, (Text mode:) `Clause text` textarea `id="lease-clause-content-textarea"` + token panel, Start/End page, Sort order, Reusable/Active. Button → `create_section` (~1704). `Detach From Source` → `detach_current_clause_from_source` (~1431).
2. **Paste-and-split tool** — `paste_clause_text` textarea → `parse_pasted_clauses` (~1936) → `draft_clauses: list[DraftClauseRow]` table (`draft_clause_row`, ~2958) → `save_all_draft_clauses` (~2087) / per-row `save_draft_clause` (~2067) / `load_draft_clause` (~1996) / `clear_pasted_clause_tool` (~1989). Parsing helpers: `_slug_from_label`, `_clean_clause_label`, `_parse_clause_header`, `_find_clause_markers` (~1854–1934), `_save_text_clause_section` (~2019).
3. **"Sections from this source document"** table — `rx.foreach(sections, section_row)` (`section_row` ~2908). Redundant with the Library list.

### `create_section()` (~1704) — the overloaded method

Handles text-clause create, PDF-split create, **and update** (branch `if current_edit_id:` at ~1782). The INSERT branch (~1810–1827) reads `p_creation_mode`, all `p_*`, `selected_source_document_id`, `p_is_standalone_clause`, `selected_source_path`, `selected_source_page_count`, `storage_root`, `f_property`, `f_document_category`; for PDF it calls `split_pdf_pages(...)`. Post-save it advances `p_start_page`/`p_sort_order` and clears the form. Exhibit rules (~1742–1759): Base Lease → `code = ""`; Exhibit + code → per-source-doc uniqueness check `WHERE LeaseSourceDocumentID=? AND SectionType='Exhibit' AND UPPER(ExhibitCode)=UPPER(?) AND id<>?`; Exhibit + no code → `_next_exhibit_code()`.

### Load tab (`_tab_load()`, ~3374)

- "Split / Add Section" button (~3447): `on_click=set_tab("parse")`.
- "Sections for selected source" table: `rx.foreach(sections, section_row)` — `section_row`'s Edit → `edit_section(id)` (no tab change).
- `source_document_card` (~2807) "Split ->" button → `go_to_parse_tab(id)` (~687) → `select_source_document(id)` + `admin_lease_tab = "parse"`.

### Parse-only state / vars to remove in Phase 3 (verify each with grep first)

`is_text_clause_mode`, `parse_mode_help_text`, `parse_save_button_label`, `parse_page_label`, `parse_end_page_label`, `will_save_without_source_document`, `selected_source_summary` (each referenced twice = def + `_tab_parse`). Keep `has_source_document` (14 refs), `p_creation_mode`, `p_is_standalone_clause`, `selected_source_*`, `storage_root`, `draft_clauses`, `paste_clause_text` — still used.

---

## Phase 1 — Complete the Library edit form

Add **Section name**, **Section type**, **Exhibit code** to the edit form and persist the full editable column set. (This is the original stand-alone Handoff 54; ship it first.)

### 1A. Full save handler

Replace `save_section_content()` (~1631) — or add a `save_library_section` that supersedes it — so it writes every editable column:

```python
    def save_section_content(self):
        self.form_error = ""
        self.form_success = ""
        sid = int(self.editing_section_id or 0)
        if sid <= 0:
            self.form_error = "Select a section with Edit before saving."
            return
        name = str(self.p_section_name or "").strip()
        if not name:
            self.form_error = "Section name is required."
            return
        sect_type = self.p_section_type if self.p_section_type in SECTION_TYPES else "Base Lease"
        code = str(self.p_exhibit_code or "").strip()
        # Base Lease sections never carry an exhibit code (mirrors create_section).
        if sect_type == "Base Lease":
            code = ""
        # Per-source-document exhibit-code uniqueness (mirrors create_section).
        if code and sect_type == "Exhibit":
            src_rows = run_query(
                "SELECT LeaseSourceDocumentID FROM LeaseDocumentSections WHERE LeaseDocumentSectionID = ?",
                (sid,), db=self.db,
            )
            src_id = int(src_rows[0].get("LeaseSourceDocumentID") or 0) if src_rows else 0
            if src_id:
                dup = run_query(
                    "SELECT TOP 1 LeaseDocumentSectionID FROM LeaseDocumentSections "
                    "WHERE LeaseSourceDocumentID = ? AND SectionType = 'Exhibit' "
                    "AND UPPER(ISNULL(ExhibitCode,'')) = UPPER(?) AND LeaseDocumentSectionID <> ?",
                    (src_id, code, sid), db=self.db,
                )
                if dup:
                    self.form_error = "This exhibit code already exists for that source document."
                    return
        try:
            run_exec(
                "UPDATE LeaseDocumentSections SET SectionName=?, SectionType=?, ExhibitCode=?, "
                "ClauseTag=?, ArticleNumber=?, DisplayLabel=?, Content=?, UpdatedOn=SYSDATETIME() "
                "WHERE LeaseDocumentSectionID = ?",
                (
                    name, sect_type, code or None,
                    str(self.p_clause_tag or "").strip() or None,
                    str(self.p_article_number or "").strip() or None,
                    str(self.p_display_label or "").strip() or None,
                    self.p_content,
                    sid,
                ),
                db=self.db,
            )
            self.form_success = "Section saved."
            self._load_sections()
            self._load_all_sections()
            self._load_reusable_section_options()
        except Exception as ex:
            self.form_error = f"Could not save section: {ex}"
```

Leave `save_library_section` (~1656) as-is — it already calls this and flips back to view mode.

> Not touched: `IsReusable`/`IsActive` still flip via the header toggle buttons (`toggle_section_active`/`toggle_section_reusable`); `SortOrder`, `StartPage`, `EndPage`, `StoredFilePath` are **not** editable here (deliberate — see "Deferred").

### 1B. Edit-form fields

In `_library_edit_body()` add, above the existing Article/Label/Tag grid:

```python
        rx.grid(
            rx.vstack(rx.text("Internal name", size="1", color="#666"),
                      rx.input(value=LeaseDocumentState.p_section_name, on_change=LeaseDocumentState.set_p_section_name, width="100%"), spacing="1"),
            rx.vstack(rx.text("Section type", size="1", color="#666"),
                      rx.select(SECTION_TYPES, value=LeaseDocumentState.p_section_type, on_change=LeaseDocumentState.set_p_section_type, width="100%"), spacing="1"),
            rx.vstack(rx.text("Exhibit code", size="1", color="#666"),
                      rx.input(value=LeaseDocumentState.p_exhibit_code, on_change=LeaseDocumentState.set_p_exhibit_code, placeholder="A", width="100%"), spacing="1"),
            columns="3", spacing="3", width="100%",
        ),
```

`set_p_section_name` / `set_p_section_type` / `set_p_exhibit_code` already exist. The header bar's type badge already reads `p_section_type` (Handoff 53 fix), so it updates live.

### Phase 1 checklist
- [ ] Editing a section, changing Internal name / Type / Exhibit code, Save → persists; list item + header reflect the new name/type.
- [ ] Blank name → "Section name is required."
- [ ] Set type to Base Lease with an exhibit code → code is cleared on save.
- [ ] Two Exhibit sections under the same source doc can't share a code.
- [ ] Article/Label/Tag/Content still save exactly as before.

---

## Phase 2 — `+ New section` in the Library

A create flow living in the Library's right panel. Reuses Parse's backend; only the container is new.

### 2A. State

```python
    # "" = not creating; otherwise "text" | "pdf" | "bulk"
    library_create_mode: str = ""
    new_section_source_id: int = 0   # optional source doc to attach a new section to
```

### 2B. Handlers

```python
    def _load_source_context(self, source_id: int):
        """Load selected_source_path / page_count / f_property / f_document_category
        for a source doc. Unlike select_source_document (~1046), this does NOT
        reset the p_* form — so attaching a source to a half-filled + New section
        form does not wipe it. (Copy just the SELECT + the
        selected_source_path / selected_source_page_count / f_property /
        f_document_category assignments out of select_source_document; skip
        everything from the 'reset the parse/edit form' comment onward.)

        Page range IS source-specific, so clamp/initialize it here (one code
        path — initializes on first attach, clamps on a source switch;
        everything else in the form is preserved):
            pc = self.selected_source_page_count or 1
            try: s = int(self.p_start_page or 0)
            except ValueError: s = 0
            try: e = int(self.p_end_page or 0)
            except ValueError: e = 0
            s = min(max(s or 1, 1), pc)
            e = min(max(e or pc, s), pc)
            self.p_start_page, self.p_end_page = str(s), str(e)
        """
        ...

    # Source-doc select options — LeaseSourceDocuments has no ready label/id
    # pair; build one (template names alone can collide).
    @rx.var
    def source_doc_labels(self) -> list[str]:
        out = ["(standalone — no source)"]
        for r in self.source_documents:
            prop = str(r.property_name or "").strip() or "General"
            out.append(f"{r.template_name} · {prop} · ID {r.source_document_id}")
        return out

    @rx.var
    def source_doc_ids(self) -> list[int]:
        return [0] + [int(r.source_document_id) for r in self.source_documents]
        # set_new_section_source resolves the picked label -> id via these lists.

    def start_new_section(self, mode: str = "text"):
        self.reset_section_form()                 # clears editing_section_id + p_*
        self.library_detail_mode = "view"
        self.library_create_mode = mode
        self.new_section_source_id = 0
        self.selected_source_document_id = 0
        self.p_creation_mode = "Text Clause" if mode != "pdf" else "PDF Page Split"
        self.p_is_standalone_clause = True
        self.form_error = ""
        self.form_success = ""

    def set_library_create_mode(self, mode: str):
        self.library_create_mode = mode
        self.p_creation_mode = "Text Clause" if mode != "pdf" else "PDF Page Split"

    def set_new_section_source(self, value: str):
        try:
            self.new_section_source_id = int(value or 0)
        except (TypeError, ValueError):
            self.new_section_source_id = 0
        # These are what create_section / _save_text_clause_section actually read.
        self.selected_source_document_id = self.new_section_source_id
        self.p_is_standalone_clause = self.new_section_source_id <= 0
        if self.new_section_source_id > 0:
            self._load_source_context(self.new_section_source_id)

    def cancel_new_section(self):
        self.library_create_mode = ""
        self.new_section_source_id = 0
        self.selected_source_document_id = 0
        self.reset_section_form()

    def start_new_section_from_source(self, source_id: int):
        """Load-tab 'Split / Add Section' entry point — source already selected."""
        sid = int(source_id or 0)
        self.reset_section_form()
        self.library_detail_mode = "view"
        self.library_create_mode = "pdf"
        self.p_creation_mode = "PDF Page Split"
        self.set_new_section_source(str(sid))   # sets p_is_standalone_clause = False, loads context
        self.admin_lease_tab = "library"
        self.form_error = ""
        self.form_success = ""
```

**`create_section` surgery** — make it INSERT-only and return to the Library:

- Delete the whole `if current_edit_id:` UPDATE block (~1782–1809); de-indent the `else:` INSERT so it always runs.
- Replace the tail (`self.p_start_page = ...` / form-clearing / etc., ~1829–1847) with:
  ```python
          new_id = ... # SELECT TOP 1 LeaseDocumentSectionID ORDER BY ... DESC  (as _save_text_clause_section does)
          self._load_sections()
          self._load_all_sections()
          self._load_reusable_section_options()
          self.library_create_mode = ""
          self.select_library_section(new_id)   # open the new section in the Library editor
          self.form_success = "Section created."
  ```
- It still reads `selected_source_document_id` for the source link. Ensure `set_new_section_source` populated `selected_source_document_id` (via `_load_source_context`) so `has_source_document` is true for PDF mode. Standalone text: `new_section_source_id == 0` → `p_is_standalone_clause = True` → `has_source_document` false → INSERT with `LeaseSourceDocumentID = NULL`.
- Also parameterize `_save_text_clause_section` (~2019): its INSERT hardcodes `IsReusable, IsActive` to `1, 1` — take `reusable`/`active` args (from the shared bulk toggles) instead.

Nothing else in `create_section` changes — the exhibit rules, `split_pdf_pages`, path handling all stay.

### 2C. UI — `_library_create_body()`

New component. Rendered by `_tab_library()`'s right panel when `library_create_mode != ""` (takes priority over the section detail). A mode switch at the top — `rx.segmented_control` if it renders under this Reflex pin, otherwise a plain `rx.hstack` of three `rx.button`s with `variant=rx.cond(library_create_mode == "<x>", "solid", "soft")`:

```python
rx.segmented_control.root(
    rx.segmented_control.item("Text clause", value="text"),
    rx.segmented_control.item("From PDF", value="pdf"),
    rx.segmented_control.item("Bulk paste-split", value="bulk"),
    value=LeaseDocumentState.library_create_mode,
    on_change=LeaseDocumentState.set_library_create_mode,
)
```

- **Attach to source document** (all modes, optional): `rx.select` over `source_doc_labels`, resolve label → id via `source_doc_ids`, → `set_new_section_source`. Default `"(standalone — no source)"` (id 0).
- **Shared for all modes:** Section type + Reusable/Active (`p_section_type`, `p_is_reusable`, `p_is_active`).
- **Text clause** and **From PDF** modes additionally show the per-section metadata (Internal name, Exhibit code, Article #, Display label, Clause tag) — same widgets as `_library_edit_body` Phase 1B, bound to the same `p_*` vars.
  - Text clause: content `rx.text_area(id="lease-clause-content-textarea", value=p_content, ...)` + `_available_token_buttons_panel("lease-clause-content-textarea")` + "Create section" → `create_section`.
  - From PDF: require a source doc; Start page / End page inputs (`p_start_page`/`p_end_page`, clamped by `_load_source_context`); show the source's page count; "Split & create" → `create_section`.
- **Bulk paste-split** mode: **no per-section metadata fields** — each parsed draft keeps its own derived name / article / display label / clause tag. Move the "Paste-and-split clause tool" card body here verbatim — `paste_clause_text` textarea, "Split Pasted Text" → `parse_pasted_clauses`, the `draft_clauses` table (`draft_clause_row`, its per-row Load → `load_draft_clause`, which now also sets `library_create_mode = "text"` so the clause opens in the text editor), "Save All Draft Clauses" → `save_all_draft_clauses` (passes the shared `p_is_reusable`/`p_is_active` through to `_save_text_clause_section`), "Clear". Source link is whatever `set_new_section_source` set. After "Save All", set `library_create_mode = ""` and refresh.
- Footer: "Cancel" → `cancel_new_section`.

### 2D. Wire into `_tab_library()`

- Left panel: add a **`+ New section`** button next to "New Standalone Clause" (or replace it) → `start_new_section("text")`. Keep `new_standalone_clause` working or point its button here.
- Right panel `rx.cond` chain:
  ```python
  rx.cond(
      LeaseDocumentState.library_create_mode != "",
      _library_create_body(),
      rx.cond(
          LeaseDocumentState.editing_section_id > 0,
          rx.vstack(_library_header_bar(), rx.cond(... edit/view ...), ...),
          rx.box(rx.text("Select a section from the list, or click + New section.", ...)),
      ),
  )
  ```

### Phase 2 checklist
- [ ] `+ New section` → Text clause: fill name + content, Create → new section appears in the list and opens in the editor.
- [ ] From PDF: pick a source doc, pages 3–5, Create → PDF is split, section created, opens in editor; file exists on disk.
- [ ] Bulk paste-split: paste an article, Split → draft rows; Save All → N sections created; standalone vs "attach to source" both work.
- [ ] Exhibit code uniqueness + Base-Lease-clears-code still enforced on create.
- [ ] Cancel returns to the list with no row created.

---

## Phase 3 — Retire Parse & Section

### 3A. Delete the tab

- `lease_documents_content()`: remove `_tab_button("Parse & Section", "parse")` and `rx.cond(admin_lease_tab == "parse", _tab_parse())`. Tab bar is now **Package Templates · Section Library · Load**.
- Delete `_tab_parse()` entirely.
- `set_tab`: the `admin_lease_tab == "library"` guard added in Handoff 53 can stay (harmless) or be removed — no more Parse tab to leak into. Leave it.

### 3B. Rewire the Load tab

- "Split / Add Section" button (~3447): `on_click=set_tab("parse")` → `on_click=LeaseDocumentState.start_new_section_from_source(LeaseDocumentState.selected_source_document_id)`.
- `source_document_card` "Split ->" (~2820): `on_click=go_to_parse_tab(id)` → `on_click=LeaseDocumentState.start_new_section_from_source(row.source_document_id)`.
- "Sections for selected source" table: **keep it** (handy right after a split) but repoint `section_row`'s Edit button: `on_click=edit_section(row.section_id)` → `on_click=LeaseDocumentState.select_library_section(row.section_id)` then a `set_tab("library")` — simplest is a tiny handler `open_section_in_library(id)` = `select_library_section(id)` + `admin_lease_tab = "library"`. Delete button stays.

### 3C. Strip dead code (grep-verify each is unreferenced after 3A/3B)

- `go_to_parse_tab`, `detach_current_clause_from_source`.
- Computed vars: `is_text_clause_mode`, `parse_mode_help_text`, `parse_save_button_label`, `parse_page_label`, `parse_end_page_label`, `will_save_without_source_document`, `selected_source_summary`.
- `new_standalone_clause` — repoint its body to `start_new_section("text")` + `set_tab("library")`, or delete it and its button.
- **`_is_metadata_only_section_update` (~1506)** — became dead when the `create_section` UPDATE branch was removed in Phase 2. Confirm no other caller, then delete it. (`_validate_section_range` is still used — keep.)
- `reset_section_form`'s `self.admin_lease_tab` references — none; leave it.
- Keep: `create_section`, `_save_text_clause_section`, all `_parse_*`/`_find_clause_markers`/`_clean_clause_label`/`_slug_from_label` helpers, `parse_pasted_clauses`, `save_all_draft_clauses`, `save_draft_clause`, `load_draft_clause`, `clear_pasted_clause_tool`, `DraftClauseRow`, `draft_clause_row`, `section_row`, `p_creation_mode`, `p_start_page`/`p_end_page`, `p_is_standalone_clause`, `has_source_document`, `_validate_section_range`.

### 3D. Phase 1/2 review follow-ups

- **PDF batch-split flow (from review F3).** After a successful `create_section`, Phase 2 always navigates to the new section's editor (`library_create_mode = ""` + `select_library_section(new_id)`). That's right for **text** and **bulk** modes, but it forces a full `+ New section → From PDF → re-pick source` for every range when cutting one PDF into many sections. **For PDF mode only:** on success, keep `library_create_mode = "pdf"`, keep the source selected, clear the per-section metadata (`p_section_name` / `p_exhibit_code` / `p_article_number` / `p_display_label` / `p_clause_tag` / `p_content`), advance the range (`start = min(end + 1, page_count)`, `end = page_count`, or `end` if already at the end), bump `p_sort_order` via `_next_section_sort_order()`, and show `form_success` = "Section N created — next range ready." Text/bulk behavior is unchanged.
- **`save_loaded_draft_as_section` (from review F4)** — unlike `save_all_draft_clauses`, it doesn't clear `library_create_mode` or navigate; you're left in the `"text"` create form with the just-saved content still in it. On success, either `select_library_section(new_id)` (consistent with `create_section`) or at least clear the form. Pick one and match `create_section`.
- **`_library_create_metadata_fields` grouping (from review F5, nit).** Section type + Reusable/Active sit in the shared block above the mode body, but Exhibit code sits *inside* `_library_create_metadata_fields` with name/article/label/tag. Move Section type down next to Exhibit code (both are per-section, not per-batch), or leave it — cosmetic only, ship either way.

### Phase 3 checklist
- [ ] No "Parse & Section" tab. Three tabs, all render.
- [ ] Load → "Split / Add Section" and a card's "Split ->" both land in the Library with `+ New section` open in From-PDF mode, source preselected.
- [ ] Load's per-source Edit → opens that section in the Library.
- [ ] `grep -n "_tab_parse\|go_to_parse_tab\|parse_save_button_label\|_is_metadata_only_section_update" lease_documents.py` → nothing but comments.
- [ ] From PDF: cut range 1–3, "Split & create" → section created, form **stays** in From-PDF mode with source kept and range advanced to 4–end; cut 4–6 → second section created. (F3)
- [ ] Text / bulk create still navigate to the new section / clear the panel.
- [ ] All 17 pages compile; `reflex run --backend-only` clean.

---

## Do Not Touch

| What | Why |
|---|---|
| `_find_clause_markers`, `_parse_clause_header`, `_clean_clause_label`, `_slug_from_label` (the parsing heuristics) | Move the *call sites'* UI, not the parsing. Reimplementing the heuristics is a regression risk with no upside. (`_save_text_clause_section` gets one signature change — reusable/active args — nothing else.) |
| `split_pdf_pages` and the storage-path logic in `create_section` | PDF splitting is unchanged. |
| `LeaseDocumentSections` schema / `SortOrder` / `StartPage` / `EndPage` semantics | No new columns; page range and sort order are create-time only. |
| `edit_section` | Still the loader; just called from more places (Library + Load's per-source table). |
| Package Templates tab, generation, `lease_merge.py`, `lease_documents_pdf.py` | Out of scope. |
| Handoff 53's list/detail, `library_detail_mode`, the resizer | Built on, not changed. |

## Gotchas

- `create_section`'s early-return messages ("Select a source document on the Load tab first, or switch to Text Clause mode…", "…click Split ->") mention the deleted tab — update them to point at the `+ New section` form.
- `select_source_document` (~1046) **resets `p_*`** past its "reset the parse/edit form" comment — that is why Phase 2 uses `_load_source_context` instead. Don't call `select_source_document` from the create flow.
- `save_all_draft_clauses` / `save_draft_clause` / `parse_pasted_clauses` currently only run from Parse; after they move, add `self.library_create_mode = ""` to the success path of `save_all_draft_clauses` so the panel closes.
- After Phase 3, `grep -n "\"parse\"\|'parse'" lease_documents.py` — the only hits should be the `p_creation_mode` string values `"PDF Page Split"` / `"Text Clause"` (unrelated) and comments; no `admin_lease_tab == "parse"`.
- `rx.foreach(sections, section_row)` stays on the Load tab; `section_row`'s Edit is the only thing repointed. `LeaseDocumentState.sections` is still loaded by `_load_sections()` (per-source list) — unchanged.

## Deferred (explicitly out)

- **Editing a PDF section's page range** ("re-split") — gone for now; recourse is delete + `+ New section` → From PDF. A dedicated "Re-cut pages" action can come later.
- **Sort order** in the editor — `LeaseDocumentSections.SortOrder` is a per-source ordering that Package Templates made moot; not surfaced.
- Merging the Load tab away / renaming it.

---

## Status / How to Deliver

- **Phase 1 — done** (`d09cc1c`). Also folded in a Mark-requested full-width page fix (`FULL_PAGE_WIDTH` on `lease_documents_content()`).
- **Phase 2 — done** (`bdbc01c`), reviewed. Both P1/P2 verified in a live `reflex run`, console clean.
- **Phase 3 — this is what's left**: 3A–3D above. Section 3D carries three review follow-ups (F3 = PDF batch-split flow, the one real behaviour change; F4/F5 nits).

Per `CLAUDE.md`: edit `lease_documents.py` in place. **One commit per phase.** The `_vN` archive move for `lease_documents*` / `lease_documents_pdf*` / `pages/LeaseDocuments History/` is still pending from Handoff 53 — do it as its own commit after Phase 3 verifies.

---

## File Locations

```
C:\Inspirion\Dev\TenantCRM\LucidPM\LucidPM\pages\lease_documents.py   ← the only file
  save_section_content / _library_edit_body / _library_header_bar     — Phase 1
  new: library_create_mode, start_new_section, _library_create_body   — Phase 2
  create_section (INSERT-only surgery)                                — Phase 2
  _tab_parse (delete), _tab_load rewire, dead-code strip              — Phase 3
  lease_documents_content() tab bar                                   — Phase 3

Frontend http://localhost:3000 · Backend http://localhost:8000 · Test DB green / Prod red
```

---

*Three phases, one file. Phase 1 completes the editor (name/type/exhibit + full save). Phase 2 moves Parse's three creation paths into a `+ New section` panel in the Library, reusing every existing backend handler and parsing helper untouched. Phase 3 deletes the Parse tab and points the Load tab at the Library. The overloaded `create_section` loses its UPDATE half and becomes a plain insert. Page-range and sort-order editing are intentionally dropped.*
