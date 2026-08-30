# LucidoPM — ChatGPT Handoff 56

## Retire the Load tab — Source PDFs move into the Section Library

---

## What This Is

The `/admin/lease-templates` page has three tabs today: **Package Templates · Section Library · Load**. This handoff removes **Load** and folds its work into the **Section Library**, ending at **two tabs**.

### Why

The Load tab does four jobs, and after Handoff 54 they no longer justify a co-equal top-level tab:

| | Job | Reality |
|---|---|---|
| Upload / import a source PDF | still needed | but it's a step *toward* making a section, not its own destination |
| Edit source-doc metadata | still needed | low-frequency housekeeping |
| See sections cut from a source | duplicates the Library's own source grouping | |
| "Split ->" launch buttons | already just deep-links into the Library (`start_new_section_from_source`) | |

More importantly, the way the tool is actually used has shifted. The original vision — upload a whole lease PDF, explode it into 15–20 sections — still exists but is rare. The **frequent** use is capturing one heavily-formatted page (signature blocks, notary acknowledgements) as a single section, and iterating: variants by property, by document type (lease / amendment / acknowledgement), by tenant type (individual / multiple partners), plus layout revisions. That loop wants to live *next to the sections it produces*, in the Library, and be fast.

### End state

- **Two tabs: Package Templates · Section Library.**
- The Section Library's left panel gets a **Sections | Source PDFs** switch.
  - **Sections** — unchanged (the list/detail from Handoffs 53/54).
  - **Source PDFs** — the source-doc list; select one → metadata form + coverage + its sections + "Split a section from this PDF". Upload a new source PDF from here.
- **From-PDF create mode** (`_library_create_pdf_body`) gains an inline **"Upload a new source PDF"** path, so the common case is one flow: choose file → name it → Split & create. Single-page PDFs skip the page-range step.
- **PDF-backed sections** get a **Replace PDF** action for the revise-and-reupload loop.

### Scope constraint

- **One file: `LucidPM/pages/lease_documents.py`.** No schema change. No merge/render change. No new route.
- **Three phases, one commit each**, verified between (same cadence as Handoff 54).
- Reuse every existing handler — `handle_upload`, `import_local_pdf_for_testing`, `save_source_document_metadata`, `select_source_document`, `start_new_section_from_source`, `create_section`, `_load_source_documents`, `_load_sections`, `section_row`, `open_section_in_library` — **verbatim** unless this doc says otherwise.
- Naming: the user controls the Source PDF name (it's the field currently labelled "Template name" — `f_template_name`). Keep that. It seeds the section name in the one-page case.
- **Do not** touch Package Templates, the Sections list/detail behaviour, `lease_merge.py`, `lease_documents_pdf.py`, `lease_package_builder.py`, or the merge-token picker (that's Handoff 55).

---

## Current State (real references, `lease_documents.py`)

### Tab plumbing
- `admin_lease_tab: str = "templates"` (line 352). Values today: `"load" | "library" | "templates"` (`"parse"` already gone).
- `set_tab(tab)` (line 670) — H53 guard drops Library selection when leaving the Library with an edit armed.
- `lease_documents_content()` (line 3961) — tab bar `rx.hstack` (lines 3971–3977) has `_tab_button("Load", "load")`; tab panes are three `rx.cond` at lines 3982–3984.
- `_tab_button(label, key)` (line 3949).

### The Load tab
- `_tab_load()` (line 3429) — `rx.hstack` of:
  - **left** `#lease-doc-load-left-panel` — "Source documents" heading + **New Source Document** button (`new_source_document`) + `rx.foreach(source_documents, source_document_card)`.
  - **resizer** `#lease-doc-load-resizer`.
  - **right** three `rx.card`s:
    1. Source metadata form — `f_template_name` / `f_property` / `f_document_category` / `f_template_version` / `f_notes` / `f_is_active`; **Save Metadata** (`save_source_document_metadata`, line 1189) + **Clear / New** (`new_source_document`, line 680).
    2. Upload — `rx.upload` id `lease_template_pdf_upload` → **Upload Source PDF** (`handle_upload`, line 1222) + dev-tools local-path import (`import_local_pdf_for_testing`, line 1279, gated on `developer_tools_enabled`).
    3. "Sections for selected source" — **Split / Add Section** button (`start_new_section_from_source`, line 1123) + `rx.table` of `rx.foreach(sections, section_row)`; `section_row`'s Edit → `open_section_in_library` (line 1522).
- `source_document_card(row)` (line 2935) — **Load-only.** Edit → `select_source_document` (line 1139), Split -> → `start_new_section_from_source`.
- `source_document_row(row)` (line 2907) — a `rx.table.row` variant, **currently unused** after H54 (grep to confirm). Reuse or delete.
- `SourceDocumentRow` model (line ~280): `source_document_id, template_name, property_name, category, version, file_name, page_count, saved_path, uploaded_on, active`.

### Handlers already in place (reuse)
- `handle_upload` (1222) — requires `f_template_name`; `save_uploaded_pdf(...)` → INSERT `LeaseSourceDocuments` (`DocumentScope='AdminTemplate'`) → sets `selected_source_document_id/_page_count/_path`, `p_start_page="1"`, `p_end_page=str(pc)` → `_load_source_documents()` + `_load_sections()` + `_load_all_sections()` + `_load_reusable_section_options()`.
- `import_local_pdf_for_testing` (1279) — same shape via `copy_existing_pdf`.
- `_load_source_documents` (994) — `source_documents` from `LeaseSourceDocuments WHERE DocumentScope='AdminTemplate' ORDER BY UploadedOn DESC`; re-validates `selected_source_document_id`.
- `select_source_document(id)` (1139) — loads a source into the `f_*` metadata fields + `selected_source_path/_page_count`; **resets `p_*` / `editing_section_id`** (see Gotchas).
- `start_new_section_from_source(id)` (1123) — `reset_section_form()` → `library_create_mode="pdf"` → `set_new_section_source(str(id))` → `admin_lease_tab="library"`. Already the Library entry point.
- `set_new_section_source(value)` (1094) — resolves label/id → `new_section_source_id`, `selected_source_document_id`, `_load_source_context`.
- `_load_source_context(id)` (1034) — non-destructive source load (path, page count, property, category) + clamps `p_start_page/p_end_page` to `[1, PageCount]`. **This is the one to use in the create flow** — `select_source_document` wipes the form.
- `create_section()` (1792) — INSERT-only. PDF branch: `split_pdf_pages(selected_source_path, start, end, output_name, storage_root, f_property, f_document_category)` → INSERT → on success stays in `library_create_mode="pdf"` with the range advanced (`next_start = min(end+1, page_count)`), or for text/bulk navigates to the new section.
- `edit_section(id)` (1485) — loads a section into `p_*`; `p_creation_mode` is `"PDF Page Split"` when the row has a `StoredFilePath` that isn't the current source path and no usable Content.
- `delete_section(id)` (1542) — reads `StoredFilePath`, checks generated/package usage, deletes or archives.

### The Section Library tab
- `_tab_library()` (line 3866): `left_panel` (`#lease-doc-library-left-panel`) / `resizer` (`#lease-doc-library-resizer`) / `right_panel`.
  - left: heading + **+ New section** (`start_new_section("text")`) + search + 6-control filter grid + `_library_list_header()` + `rx.foreach(filtered_library_sections, _library_list_item)`.
  - right `rx.cond` chain: `library_create_mode != ""` → `_library_create_body()` ; elif `editing_section_id > 0` → `_library_header_bar()` + (`_library_edit_body()` | `_library_view_body()`) ; else empty-state text.
- `_library_create_body()` (3818) — "New section" header + Cancel (`cancel_new_section`, 1115) + `_library_create_mode_buttons()` + "Attach to source document" `rx.select(source_doc_labels, …, set_new_section_source)` + Section type / Flags grid + mode-body `rx.cond` (`_library_create_text_body` | `_library_create_pdf_body` | `_library_create_bulk_body`).
- `_library_create_pdf_body()` (3746) — `_library_create_metadata_fields()` + page-count callout + Start/End page grid + **Split & create** (`create_section`, disabled when `new_section_source_id <= 0`).
- `state`: `library_create_mode: str = ""` (378), `new_section_source_id: int = 0` (379), `source_doc_labels`/`source_doc_ids`/`selected_new_section_source_label` `@rx.var` (512–531).

### Resizer
- `LEASE_DOCUMENTS_RESIZER_SCRIPT` (line 3182) — window-singleton. `configs` map has `lease-doc-load-resizer` / `lease-doc-template-resizer` / `lease-doc-library-resizer`; the `mousedown` handler `closest('#lease-doc-load-resizer, #lease-doc-template-resizer, #lease-doc-library-resizer')`. Tolerates missing elements.

---

## Phase 1 — Move Source PDFs into the Library; delete the Load tab

**Goal:** two tabs; the Source PDFs work is reachable from a switch in the Library. No behaviour lost.

### 1A. Left-panel view switch

Add state:
```python
library_left_view: str = "sections"   # "sections" | "sources"

def set_library_left_view(self, view: str):
    self.library_left_view = "sources" if view == "sources" else "sections"
    if self.library_left_view == "sources":
        self.library_create_mode = ""
        self.reset_section_form()
        self.library_detail_mode = "view"
        self._load_source_documents()
    self.form_error = ""
    self.form_success = ""
```

In `_tab_library()`'s `left_panel`, above the search box, add a 2-button segmented control (same pattern as `_library_create_mode_buttons`): **Sections** / **Source PDFs**, `variant` solid/soft on `library_left_view`.

- When `library_left_view == "sections"`: render the existing search + filter grid + `_library_list_header()` + section list (unchanged).
- When `library_left_view == "sources"`: render a **+ Add source PDF** button (`start_new_source_pdf`, below) + `rx.foreach(source_documents, _library_source_list_item)` — a compact row per source (name, `category · N pages`, active badge), `on_click=select_source_document(row.source_document_id)`, highlighted when `selected_source_document_id == row.source_document_id`. Style it like `_library_list_item` (grid row, hover, selected border-left).

### 1B. Right panel — source detail / upload

Extend the `right_panel` `rx.cond` chain in `_tab_library()`. Put the Source-PDFs branch **first**:

```
if library_left_view == "sources":
    if selected_source_document_id > 0 and not adding_source  -> _library_source_detail_body()
    else                                                      -> _library_source_upload_body()
else:
    (existing create / edit / empty chain, unchanged)
```

Add state `adding_source: bool = False` and:
```python
def start_new_source_pdf(self):
    self.adding_source = True
    self.selected_source_document_id = 0
    self.new_source_document()      # clears f_* + selected_source_* (existing handler)
    self.form_error = ""; self.form_success = ""
```
`select_source_document` should set `self.adding_source = False` (add that one line).

**`_library_source_upload_body()`** — port cards 1+2 of `_tab_load`'s right side into one panel:
- Heading "New source PDF".
- Metadata grid: **Source PDF name** (`f_template_name`, required — relabel from "Template name"), Property (`f_property`), Category (`f_document_category`), Version (`f_template_version`). Notes + Active below.
- The `rx.upload` block (id `lease_template_pdf_upload`, unchanged) + **Upload Source PDF** (`handle_upload`) + the dev-tools local import (`import_local_pdf_for_testing`, still gated on `developer_tools_enabled`).
- After `handle_upload` succeeds it already sets `selected_source_document_id`; add `self.adding_source = False` at the end of `handle_upload` **and** `import_local_pdf_for_testing` so the panel flips to the detail view showing the just-uploaded source.

**`_library_source_detail_body()`** — port cards 1+3:
- `_library_header_bar`-style strip: source name + `Editing source #N` badge + active badge.
- The metadata form (same fields as upload) + **Save Metadata** (`save_source_document_metadata`) + **Clear / New** (`start_new_source_pdf`).
- A coverage line: `"{sections_from_source} section(s) · pages {max_end}/{page_count} split"` — compute from `self.sections` (already loaded for `selected_source_document_id`) and `self.selected_source_page_count`. A `@rx.var` `source_coverage_summary` is fine.
- **Split a section from this PDF** button → `start_new_section_from_source(selected_source_document_id)` (this flips `library_left_view`? — no. Add `self.library_left_view = "sections"` to `start_new_section_from_source` so the create panel is visible, since the create chain only renders under the "sections" view).
- `rx.table` of `rx.foreach(self.sections, section_row)` — unchanged; `section_row` Edit already calls `open_section_in_library` (make that also set `library_left_view = "sections"`).

### 1C. Delete the Load tab

- Delete `_tab_load()` entirely.
- Delete `source_document_card()` (Load-only; grep-confirm no other caller).
- `lease_documents_content()`: remove `_tab_button("Load", "load")` and the `rx.cond(admin_lease_tab == "load", _tab_load())` line. Tab bar = Package Templates · Section Library.
- `set_tab`: nothing to change structurally, but if `admin_lease_tab` is somehow `"load"` on load, coerce to `"templates"` in `on_load` (line 612) — add `if self.admin_lease_tab not in ("templates", "library"): self.admin_lease_tab = "templates"`.
- Resizer script: drop `lease-doc-load-resizer` from `configs` and from the `closest(...)` selector string. (`#lease-doc-load-left-panel` / `-resizer` no longer exist.)
- `SourceDocumentRow`: keep. `source_document_row()`: keep only if you use it for 1B's list; otherwise delete. `_library_source_list_item` (new) can be its own small component.
- Update the `admin_lease_tab` comment at line 351 (`"load" | "parse" | ...` → `"library" | "templates"`).

### Phase 1 checklist
- [ ] Two tab buttons; both panes render; no "Load".
- [ ] Library left panel: **Sections / Source PDFs** switch. Sections view unchanged.
- [ ] Source PDFs view: list of sources; **+ Add source PDF** opens the upload panel; upload creates the row and flips to its detail.
- [ ] Source detail: metadata edits save; coverage line correct; sections table lists that source's sections; **Split a section from this PDF** opens the From-PDF create panel with the source preselected.
- [ ] `section_row` Edit from the source detail opens the section in the Sections view.
- [ ] `grep -n "_tab_load\|source_document_card\|\"load\"\|'load'"` → nothing live.
- [ ] Resizer still works for Library + Package Templates; no console error about the missing load handle.
- [ ] `import LucidPM.LucidPM` builds; `reflex run` console clean.

---

## Phase 2 — Upload-and-split in one flow (the frequent path)

**Goal:** creating a section from a brand-new one-page PDF is: switch to From-PDF → upload → name → Split & create. No separate stop in the Source PDFs view.

### 2A. Inline upload inside `_library_create_pdf_body`

Above the "Attach to source document" select (or as the first thing in `_library_create_pdf_body`), add a collapsible **"Upload a new source PDF"** disclosure (`rx.cond` on a new `show_inline_source_upload: bool = False`, toggled by a small link-button):
- `rx.upload` — **use a different id**: `lease_inline_source_upload` (a second upload widget; `lease_template_pdf_upload` still lives in the Source PDFs view).
- **Source PDF name** input (bind to `f_template_name`).
- Property / Category selects (bind `f_property` / `f_document_category`) — default from context, collapsed-secondary.
- **Upload & use** button → new handler:

```python
async def upload_source_for_new_section(self, files):
    # same body as handle_upload up through the INSERT + new_id fetch,
    # then instead of the Load-tab tail:
    self.set_new_section_source(str(new_id))      # wires new_section_source_id + _load_source_context
    self.adding_source = False
    self.show_inline_source_upload = False
    if not str(self.p_section_name or "").strip():
        self.p_section_name = self.f_template_name.strip()
    if int(self.selected_source_page_count or 0) == 1:
        self.p_start_page = "1"; self.p_end_page = "1"
    self._load_source_documents()
    self.form_success = f"Uploaded '{self.f_template_name.strip()}' ({pc} pages). Name the section and click Split & create."
```
Factor the shared upload body out of `handle_upload` into a helper `_persist_source_pdf(data, upload_name) -> (new_id, page_count, stored_path)` so both call sites stay identical.

### 2B. Collapse the page-range step for single-page sources

In `_library_create_pdf_body`, wrap the Start/End page `rx.grid` in `rx.cond(LeaseDocumentState.selected_source_page_count == 1, <caption "Whole page → one section.">, <the Start/End grid>)`. `create_section`'s PDF branch already handles `start == end == 1`.

### 2C. Section name defaults from source name

When `set_new_section_source` resolves a source and `p_section_name` is blank, prefill it from that source's `TemplateName`. (Add a `SELECT TemplateName` to `_load_source_context` or read from `source_documents`.)

### Phase 2 checklist
- [ ] From-PDF create → "Upload a new source PDF" → pick a 1-page PDF, name it, **Upload & use** → source attached, section name prefilled, no page-range inputs shown.
- [ ] **Split & create** → section created, appears in the Sections list, opens in the editor (existing text/PDF post-create behaviour: PDF stays open with range advanced — for a 1-page source that's the F3 end-of-doc case, acceptable, see Handoff 54 backlog).
- [ ] Multi-page upload still shows the range inputs and the batch "next range ready" flow.
- [ ] The Source PDFs view upload (`lease_template_pdf_upload`) still works independently.
- [ ] Two upload widgets don't collide (distinct ids).

---

## Phase 3 — Replace PDF on a PDF-backed section

**Goal:** revise a signature page externally, re-upload it behind the existing section (same section ID; packages pick it up on next generation). This retires the deferred "re-cut page range" item for the common case.

### 3A. Action + handler

In `_library_header_bar` (or `_library_view_body`), when the open section is PDF-backed (`p_creation_mode == "PDF Page Split"` **and** `p_is_standalone_clause` is False / `editing_section_id > 0` with a stored path), show a **Replace PDF** button that reveals an uploader (`rx.upload` id `lease_replace_pdf_upload`).

```python
async def replace_section_pdf(self, files):
    sid = int(self.editing_section_id or 0)
    if sid <= 0: return
    row = _first(run_query("SELECT LeaseSourceDocumentID, StartPage, EndPage, StoredFilePath, StorageRoot "
                           "FROM LeaseDocumentSections WHERE LeaseDocumentSectionID = ?", (sid,), db=self.db))
    # read new PDF, page_count(new); require page_count(new) >= EndPage (or ==1 when the section is 1-1)
    # split_pdf_pages(new_pdf, StartPage, EndPage, output_name, storage_root, f_property, f_document_category)
    # UPDATE LeaseDocumentSections SET StoredFilePath=?, RelativePath=?, StorageRoot=?, UpdatedOn=SYSDATETIME() WHERE ...
    # if the section is 1:1 with its source (StartPage=1 AND EndPage=source PageCount):
    #     also UPDATE LeaseSourceDocuments SET StoredFilePath, RelativePath, PageCount for that source
    # self.edit_section(sid); self._load_sections(); self._load_all_sections()
    # form_success = "Replaced the PDF behind this section."
```

- **In place** — same `LeaseDocumentSectionID`, same `LeaseSourceDocumentID`. No new source row (that's what **+ New section** is for — Mark's call: "Replace for fixes, ＋New for genuinely new variants").
- Store the new split file with a fresh filename (timestamp suffix) so a stale generated package that still references the old path doesn't silently change — regeneration is snapshot-based anyway.
- Error, don't crash, if the new PDF has too few pages for the section's range.

### Phase 3 checklist
- [ ] Open a 1-page PDF section → **Replace PDF** → upload a revised 1-page PDF → section's stored file updates, `UpdatedOn` bumps, view refreshes.
- [ ] Multi-page section: replace with a PDF that has ≥ EndPage pages → re-split for the same range; fewer pages → clean error.
- [ ] A previously generated package that used the section is unchanged until regenerated.
- [ ] Text-backed sections do **not** show Replace PDF.

---

## Do Not Touch

| What | Why |
|---|---|
| `split_pdf_pages`, `save_uploaded_pdf`, `copy_existing_pdf`, storage-path helpers | PDF/file handling is unchanged; only *where it's triggered from* moves. |
| `create_section` PDF branch / F3 "advance range" behaviour (Handoff 54) | Reused as-is. |
| Sections list/detail, `library_detail_mode`, `_library_edit_body`, `save_section_content` | Built on, not changed. |
| `LeaseSourceDocuments` / `LeaseDocumentSections` schema | No columns added. Replace PDF updates existing columns only. |
| Package Templates tab, `lease_merge.py`, `lease_documents_pdf.py`, `lease_package_builder.py` | Out of scope. |
| The merge-token picker (`_available_token_buttons_panel`) | Handoff 55. |
| `LEASE_DOCUMENTS_RESIZER_SCRIPT` beyond removing the dead `load` handle | Window-singleton; other edits risk both other tabs. |

---

## Gotchas

- **`select_source_document` wipes `p_*` and `editing_section_id`** (comment at line 1166). Fine for the Source PDFs *detail* view (no section being edited there), but never call it from the create flow — use `_load_source_context` / `set_new_section_source`.
- The **create panel only renders under `library_left_view == "sections"`** (it's in that branch of the right-panel `rx.cond`). Any handler that opens the create panel (`start_new_section_from_source`, `start_new_section`, `open_section_in_library`) must also set `library_left_view = "sections"`.
- **Two (Phase 2: three) `rx.upload` widgets on one page** — each needs a unique `id` or `rx.selected_files(...)` / `rx.upload_files(...)` cross-wire. Ids: `lease_template_pdf_upload` (Source PDFs view), `lease_inline_source_upload` (create flow), `lease_replace_pdf_upload` (Phase 3).
- `handle_upload` / `import_local_pdf_for_testing` currently end by leaving `admin_lease_tab` wherever it was — since Load is gone, add `self.admin_lease_tab = "library"` defensively is **not** needed (you're already in the Library), but do add `self.adding_source = False`.
- `_load_source_documents` re-validates `selected_source_document_id` and zeroes it if the row vanished — good, keep relying on it after uploads/metadata saves.
- `on_load` (line 612) currently may set `admin_lease_tab` — check it doesn't hard-set `"load"`.
- `developer_tools_enabled` gate on the local-path import — preserve it in the ported panel.
- Reflex `rx.cond` nesting is already 2 deep in the right panel; adding the sources branch makes 3. If the compiler balks, pull the branch into a `_library_right_panel()` helper that returns the right component via plain Python `if` on `@rx.var`s isn't possible (state is reactive) — keep `rx.cond` but flatten with early `rx.cond(a, X, rx.cond(b, Y, rx.cond(c, Z, W)))`.

---

## Deferred / out

- Merging or renaming the **Package Templates** tab — not touched.
- Structured property/tenant-type **fields on a section** for filtering signature-page variants — noted as a possible follow-up; for now naming + `ClauseTag` + the Library filters carry it. (Sections are currently property-agnostic and reusable; adding a real property scope is a schema + merge question worth its own handoff.)
- **Re-cut a section's page range** (change StartPage/EndPage without replacing the file) — still deferred; Replace PDF covers the revise-the-file case, which is the one that actually comes up.
- Bulk "explode a whole lease PDF" wizard — the existing per-range "next range ready" flow (F3) is the tool; no dedicated wizard.

---

## File Locations

```
LucidPM/pages/lease_documents.py            ← the only file

Phase 1:
  state: library_left_view, adding_source, set_library_left_view, start_new_source_pdf
  _tab_library(): left-panel view switch + right-panel sources branch
  new: _library_source_list_item, _library_source_upload_body, _library_source_detail_body,
       source_coverage_summary (@rx.var)
  delete: _tab_load, source_document_card
  edit: lease_documents_content() tab bar, LEASE_DOCUMENTS_RESIZER_SCRIPT, on_load, line-351 comment

Phase 2:
  state: show_inline_source_upload
  _persist_source_pdf() helper (factored from handle_upload)
  upload_source_for_new_section()
  _library_create_pdf_body(): inline upload disclosure + single-page range collapse
  set_new_section_source(): prefill p_section_name

Phase 3:
  replace_section_pdf()
  _library_header_bar() / _library_view_body(): Replace PDF button + uploader

Frontend http://localhost:3000 · Backend http://localhost:8000 · Test DB green / Prod red
```

---

*Load stops being a tab. Source PDFs become a switchable view inside the Section Library — list, upload, metadata, coverage — right next to the sections they feed. The frequent path (one formatted page → one section) collapses to upload-name-split in the From-PDF create mode, and revising that page is a Replace PDF button on the section. The rare path (explode a whole lease) still works through the same source list and the existing per-range flow. Two tabs, one file, three commits.*
