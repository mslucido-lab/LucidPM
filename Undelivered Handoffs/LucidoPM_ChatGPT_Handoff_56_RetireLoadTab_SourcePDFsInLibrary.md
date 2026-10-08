# LucidoPM — ChatGPT Handoff 56

## Retire the Load tab — Source PDFs move into the Section Library

> **Revised 2026-10-07 against commit `80171cb`** ("Lease Templates UI: list/detail selection + button standard"). That commit already rebuilt the Load tab's screens to the new UI standard, so Phase 1 now **moves** finished components into the Library instead of porting the old cards. Every line number below is from `80171cb`. Phases 2 and 3 are unchanged in substance; only their references and button styles are updated.

---

## What This Is

The `/admin/lease-templates` page has three tabs today: **Package Templates · Section Library · Load**. This handoff removes **Load** and folds its work into the **Section Library**, ending at **two tabs**.

### Why

The Load tab does four jobs, and none of them justifies a co-equal top-level tab:

| Job | Reality |
|---|---|
| Upload / import a source PDF | Still needed, but it's a step *toward* making a section, not its own destination. |
| Edit source-doc metadata | Still needed; low-frequency housekeeping. |
| See sections cut from a source | Duplicates the Library's own source grouping. |
| "+ New Section" from a source | Already just a deep-link into the Library (`start_new_section_from_source`). |

More importantly, the tool's actual use has shifted. The original vision — upload a whole lease PDF, explode it into 15–20 sections — still exists but is rare. The **frequent** use is capturing one heavily formatted page (signature blocks, notary acknowledgements) as a single section, then iterating: variants by property, by document type (lease / amendment / acknowledgement), by tenant type (individual / multiple partners), plus layout revisions. That loop wants to live *next to the sections it produces*, in the Library, and be fast.

### End state

- **Two tabs: Package Templates · Section Library.**
- The Section Library's left panel gets a **Sections | Source PDFs** switch.
  - **Sections** — unchanged.
  - **Source PDFs** — the source list; click one → its header card, Edit → metadata form, plus its sections and a coverage line. Upload a new source PDF from here.
- **From-PDF create mode** (`_library_create_pdf_body`) gains an inline **"Upload a new source PDF"** path, so the common case is one flow: choose file → name it → Split & create. Single-page PDFs skip the page-range step.
- **PDF-backed sections** get a **Replace PDF** action for the revise-and-reupload loop.

### Scope constraint

- **One file: `LucidPM/pages/lease_documents.py`.** No schema change. No merge/render change. No new route. `LucidPM/components/buttons.py` is used, not changed.
- **Three phases, one commit each**, verified between (same cadence as Handoff 54).
- Reuse every existing handler and component named in "Current State" **verbatim** unless this doc says otherwise.
- Naming: the user controls the source PDF name (the field labelled "Template name" — `f_template_name`). Keep that. It seeds the section name in the one-page case.
- **Do not** touch Package Templates, the Sections list/detail behaviour, `lease_merge.py`, `lease_documents_pdf.py`, `lease_package_builder.py`, or the merge-token picker (that's Handoff 55).

### UI standard (decided by Mark 2026-10-07; follow it for everything new here)

- **List → detail:** clicking a list row opens the record read-only. No per-row action buttons; the selected row is highlighted.
- **Header card:** `_record_header_card(icon, title_row, subtitle, actions)` (line 3137). Two lines: line 1 = name + primary status; line 2 = secondary metadata. Actions sit top-right.
- **Edit** opens the form *below* the header. Save returns to read-only; Cancel discards edits by re-reading the saved record.
- **Buttons:** general CTAs (open/start something, save nothing) = `variant="outline", color_scheme="blue"`, size 1, with a `"+ "` prefix for new-record CTAs. Commits (write to the DB) = solid blue (`color_scheme="blue"`, default variant). Edit = `edit_button()`, Delete = `delete_button()` (both from `LucidPM.components.buttons`, already imported at line 222). Close/dismiss = `variant="ghost", color_scheme="gray"`. Red and green are for badges/status labels only, never for CTAs. Cancel stays `variant="soft", color_scheme="gray"` to match the existing Cancels (Mark hasn't settled Cancel styling yet — don't restyle existing ones).

---

## Current State (real references, `lease_documents.py` @ `80171cb`)

### Tab plumbing
- `admin_lease_tab: str = "templates"` (line 344). Comment at line 342 still says `"load" | "parse" | "library" | "templates"`; `"parse"` is already gone.
- `load_tab_split_pct: int = 30` (line 345) + `set_load_tab_split_pct` (line 2941) + header comment at line 170 — leftovers from an older Load-tab splitter; no live UI reads them (grep to confirm).
- `set_tab(tab)` (line 692) — H53 guard: leaving the Library with a section selected calls `reset_section_form()`.
- `on_load` (line 634) does **not** set `admin_lease_tab`; it keeps whatever the state holds (default `"templates"`).
- `lease_documents_content()` (line 4183) — tab bar has `_tab_button("Load", "load")` (line 4196); the Load pane is `rx.cond(admin_lease_tab == "load", _tab_load())` (line 4206).
- `_tab_button(label, key)` (line 4171).

### The Load tab — already on the new standard (commit `80171cb`)
- `_tab_load()` (line 3702) — `rx.hstack` of:
  - **left** `#lease-doc-load-left-panel`: "Source documents" heading + **+ New Source** (`new_source_document`) + `rx.foreach(source_documents, source_document_card)`.
  - **resizer** `#lease-doc-load-resizer`.
  - **right:** `rx.cond(selected_source_document_id > 0, [_source_header_card() + (src_edit_mode ? _source_edit_form()) + _source_sections_card()], _source_new_upload_form())`.
- Components (all Load-only today; **these move, not change**):
  - `source_document_card(row)` (line 3016) — clickable card (`on_click=select_source_document`), name + Active badge + `category - N pages`; highlighted when selected.
  - `_source_header_card()` (line 3568) — `_record_header_card("file", …)`; reads `selected_source_summary`; actions: `edit_button` → `start_edit_source_document` (hidden while `src_edit_mode`), **Close** → `new_source_document`.
  - `_source_metadata_fields()` (line 3604) — the `f_*` inputs, shared by both forms.
  - `_source_edit_form()` (line 3620) — **Save Metadata** (`save_source_document_metadata`) + **Cancel** (`cancel_source_edit`).
  - `_source_new_upload_form()` (line 3636) — storage-location strip + `_source_metadata_fields()` + `rx.upload` id `lease_template_pdf_upload` + **Upload Source PDF** (`handle_upload`) + **Cancel** (`cancel_source_edit`) + dev-tools local import (gated on `developer_tools_enabled`).
  - `_source_sections_card()` (line 3677) — **+ New Section** (`start_new_section_from_source(selected_source_document_id)`) + `rx.table` of `rx.foreach(sections, section_row)`.
  - `section_row(row)` (line 3044) — row `on_click=open_section_in_library`; Reusable/Active toggles use `.stop_propagation`. No Edit/Delete buttons.
- Dead code (grep-confirm zero callers): `source_document_row()` (line 2988), `load_tab_section_row()` (line 3107).
- `SourceDocumentRow` model (line ~271): `source_document_id, template_name, property_name, category, version, file_name, page_count, saved_path, uploaded_on, active`. `SectionRow.pages` (line 294) is a `"start-end"` string (`"0-0"` for text-only sections).

### State and handlers already in place (reuse)
- `src_edit_mode: bool` (line 353), `src_cancel_source_id: int` (line 354). **"New source" mode is simply `selected_source_document_id == 0`** — no separate `adding_source` flag is needed (the original H56 proposed one).
- `selected_source_summary` `@rx.var` (line 459) — saved row from `source_documents` for the header.
- `new_source_document()` (line 702) — remembers the current source in `src_cancel_source_id`, clears `selected_source_*`, `sections`, `editing_section_id`, `f_*` and `p_*`.
- `_load_source_documents()` (line 1019) — loads `source_documents` (`DocumentScope='AdminTemplate'`, newest first); re-validates `selected_source_document_id` and zeroes it if the row vanished.
- `_load_source_context(id)` (line 1059) — non-destructive source load + clamps `p_start_page/p_end_page`. **Use this in the create flow.**
- `set_new_section_source(value)` (line 1119) — resolves label/id → `new_section_source_id`, `selected_source_document_id`, `_load_source_context`.
- `start_new_section(mode)` (line 1093), `cancel_new_section()` (line 1140), `start_new_section_from_source(id)` (line 1148) — the last sets `library_create_mode="pdf"`, calls `set_new_section_source`, and sets `admin_lease_tab="library"`.
- `_load_source_metadata_fields()` (line 1164) — reads only the `f_*` metadata for `selected_source_document_id`. Used by `select_source_document` and `cancel_source_edit`.
- `select_source_document(id)` (line 1185) — sets `src_edit_mode=False`, loads metadata + `selected_source_path/_page_count`, then **resets `p_*` / `editing_section_id`** and reloads sections (see Gotchas).
- `start_edit_source_document()` (line 1222), `cancel_source_edit()` (line 1230) — Cancel re-reads `f_*` only; from new mode it returns to `src_cancel_source_id` if that source still exists, else stays on a blank new form.
- `save_source_document_metadata()` (line 1247) — UPDATE, then `src_edit_mode=False`.
- `handle_upload(files)` (line 1281) and `import_local_pdf_for_testing()` (line 1338) — INSERT a `LeaseSourceDocuments` row, set `selected_source_document_id`, `src_edit_mode=False`, `p_start_page="1"`, `p_end_page=str(pc)`, reload lists. Both already land on the new source's read-only view.
- `open_section_in_library(id)` (line 1581) — `select_library_section(id)` + `admin_lease_tab="library"`.
- `edit_section(id)` (line 1544), `delete_section(id)` (line 1601), `create_section()` (line 1851) — as in Handoff 54. `create_section`'s PDF branch stays in `library_create_mode="pdf"` with the range advanced (F3).

### The Section Library tab
- `_tab_library()` (line 4080): `left_panel` (`#lease-doc-library-left-panel`) / `resizer` (`#lease-doc-library-resizer`) / `right_panel`.
  - left: heading + count badge, **+ New Section** (`start_new_section("text")`), search, 6-control filter grid, divider, `_library_list_header()`, `rx.foreach(filtered_library_sections, _library_list_item)`.
  - right: `rx.cond(library_create_mode != "", _library_create_body(), rx.cond(editing_section_id > 0, [_library_header_bar() + edit|view body], empty-state text))`.
- `_library_header_bar()` (line 3786) — `_record_header_card("scroll-text", …)`; actions in view mode: `edit_button`, `delete_button`, **Close**; in edit mode: **Save Section** (solid blue) + **Cancel**.
- `_library_create_mode_buttons()` (line 3894) — segmented control: solid when active, soft otherwise. Reuse this pattern for the new view switch.
- `_library_create_pdf_body()` (line 3960), `_library_create_body()` (line 4032).
- State: `library_create_mode` (line 372), `new_section_source_id` (line 373), `source_doc_labels` / `source_doc_ids` / `selected_new_section_source_label` `@rx.var`s (from line 535).

### Resizer
- `LEASE_DOCUMENTS_RESIZER_SCRIPT` (line 3319) — window singleton. The `configs` map has a `lease-doc-load-resizer` entry (line 3328), and the `mousedown` handler's `closest('#lease-doc-load-resizer, #lease-doc-template-resizer, #lease-doc-library-resizer')` (line 3353) includes it. It tolerates missing elements.

---

## Phase 1 — Move Source PDFs into the Library; delete the Load tab

**Goal:** two tabs; the Source PDFs screens from `80171cb` are reachable from a switch in the Library. No behaviour lost.

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

In `_tab_library()`'s `left_panel`, directly under the heading row, add a 2-button segmented control in the `_library_create_mode_buttons` pattern: **Sections** / **Source PDFs**, `variant="solid"` when active, `"soft"` otherwise, `color_scheme="blue"`, size 1.

- `library_left_view == "sections"`: render the existing **+ New Section** button, search, filter grid, divider, list header and list — unchanged.
- `library_left_view == "sources"`: render **+ New Source** (`new_source_document`, blue outline, full width, same as **+ New Section**) + `rx.foreach(source_documents, source_document_card)` (or "No source documents yet."). Reuse `source_document_card` as-is.

The heading's count badge (`library_result_count`) only applies to sections — wrap it in `rx.cond(library_left_view == "sections", …)`.

### 1B. Right panel — source detail / upload

Put a Source-PDFs branch **first** in `_tab_library()`'s `right_panel`:

```
rx.cond(library_left_view == "sources",
    rx.cond(selected_source_document_id > 0,
        vstack(_source_header_card(), rx.cond(src_edit_mode, _source_edit_form()), _source_coverage_line(), _source_sections_card()),
        _source_new_upload_form()),
    <existing create / edit / empty chain, unchanged>)
```

Pull the right-panel expression into a small `_library_right_panel()` helper if the nesting gets hard to read (it becomes three `rx.cond`s deep).

**Coverage line (new).** Add `@rx.var source_coverage_summary -> str`, computed from `self.sections` (already loaded for the selected source) and `self.selected_source_page_count`:
- Count sections; count **distinct** pages covered by the union of their `pages` ranges (parse `"start-end"`; skip `"0-0"` and anything unparsable).
- Format: `"3 section(s) · 5 of 8 pages split"`. When `selected_source_page_count` is 0: `"3 section(s)"`.

Render it as `_source_coverage_line()` — `rx.text(source_coverage_summary, size="2", color="#666")` — between the header (and edit form) and the sections card. Don't add it to `_source_sections_card()`, so that component still moves untouched.

### 1C. Navigation fixes (required — see Gotchas)

The create and edit panels render only under `library_left_view == "sections"`. Add `self.library_left_view = "sections"` to:
- `start_new_section_from_source` (line 1148) — the **+ New Section** button in `_source_sections_card()`.
- `open_section_in_library` (line 1581) — clicking a row in `_source_sections_card()`.
- `start_new_section` (line 1093) — defensive; it's only reachable from the Sections view today.

### 1D. Delete the Load tab

- Delete `_tab_load()` (line 3702).
- Keep `source_document_card`, `_source_header_card`, `_source_metadata_fields`, `_source_edit_form`, `_source_new_upload_form`, `_source_sections_card` and `section_row` — they now render inside the Library. Update their docstrings that say "Load tab".
- Delete the dead `source_document_row()` (line 2988) and `load_tab_section_row()` (line 3107) after grep-confirming zero callers.
- Delete `load_tab_split_pct` (line 345), `set_load_tab_split_pct` (line 2941) and the line-170 header note, after grep-confirming nothing else reads them.
- `lease_documents_content()`: remove `_tab_button("Load", "load")` (line 4196) and the `"load"` pane (line 4206). The tab bar becomes Package Templates · Section Library.
- In `on_load` (line 634), coerce stale values: `if self.admin_lease_tab not in ("templates", "library"): self.admin_lease_tab = "templates"`.
- Resizer script: drop the `lease-doc-load-resizer` entry from `configs` (line 3328) and from the `closest(...)` selector (line 3353). Nothing else in the script changes.
- Line-342 comment → `# Active tab: "library" | "templates"`.

### Phase 1 checklist
- [ ] Two tab buttons; both panes render; no "Load".
- [ ] Library left panel: **Sections / Source PDFs** switch. The Sections view is unchanged (filters, sort, + New Section, list/detail).
- [ ] Source PDFs view: source list; clicking a source opens its header card (olive Edit, Close); the selected card is highlighted.
- [ ] **Edit** → metadata form below the header → **Save Metadata** saves and returns to read-only; **Cancel** restores the saved values.
- [ ] **+ New Source** → upload form; upload creates the row and lands on its read-only view; **Cancel** returns to the previously viewed source.
- [ ] Coverage line is correct for a multi-section source and for a source with no sections.
- [ ] **+ New Section** in the sections card switches to the Sections view with the From-PDF create panel open and this source preselected.
- [ ] Clicking a row in the sections card opens that section in the Sections view; the Reusable/Active toggles still toggle without navigating.
- [ ] `grep -n "_tab_load\|source_document_row\|load_tab_section_row\|load_tab_split_pct\|\"load\"\|'load'"` → nothing live.
- [ ] Resizer still works for Library and Package Templates; no console error about the missing load handle.
- [ ] `reflex compile` succeeds (84/84); `reflex run` console clean.

---

## Phase 2 — Upload-and-split in one flow (the frequent path)

**Goal:** creating a section from a brand-new one-page PDF is: From PDF → upload → name → Split & create, without a separate stop in the Source PDFs view.

### 2A. Inline upload inside `_library_create_pdf_body`

At the top of `_library_create_pdf_body()` (line 3960), add a collapsible **"Upload a new source PDF"** panel, shown by `rx.cond` on a new `show_inline_source_upload: bool = False`:
- Toggle: **+ Upload New PDF** — blue outline, size 1 (a general CTA; it only reveals the panel).
- `rx.upload` with a **different id**: `lease_inline_source_upload` (`lease_template_pdf_upload` still lives in the Source PDFs view).
- **Source PDF name** input bound to `f_template_name`.
- Property / Category selects bound to `f_property` / `f_document_category`, defaulted from context.
- **Upload & Use** — solid blue (commit) → new handler:

```python
async def upload_source_for_new_section(self, files):
    # Same body as handle_upload through the INSERT + new_id fetch,
    # then, instead of handle_upload's tail:
    self.set_new_section_source(str(new_id))      # wires new_section_source_id + _load_source_context
    self.show_inline_source_upload = False
    if not str(self.p_section_name or "").strip():
        self.p_section_name = self.f_template_name.strip()
    if int(self.selected_source_page_count or 0) == 1:
        self.p_start_page = "1"; self.p_end_page = "1"
    self._load_source_documents()
    self.form_success = f"Uploaded '{self.f_template_name.strip()}' ({pc} pages). Name the section and click Split & create."
```

Factor the shared upload body out of `handle_upload` into `_persist_source_pdf(data, upload_name) -> (new_id, page_count, stored_path)`, so both call sites stay identical. `handle_upload`'s own tail (select the new source, `src_edit_mode=False`, reload lists) stays as it is.

### 2B. Collapse the page-range step for single-page sources

In `_library_create_pdf_body`, wrap the Start/End page `rx.grid` in `rx.cond(selected_source_page_count == 1, <caption "Whole page → one section.">, <the Start/End grid>)`. `create_section`'s PDF branch already handles `start == end == 1`.

### 2C. Section name defaults from source name

When `set_new_section_source` (line 1119) resolves a source and `p_section_name` is blank, prefill it from that source's `TemplateName` (read it from `source_documents`, or add `TemplateName` to `_load_source_context`'s SELECT).

### Phase 2 checklist
- [ ] From PDF → **+ Upload New PDF** → pick a 1-page PDF, name it, **Upload & Use** → source attached, section name prefilled, no page-range inputs.
- [ ] **Split & create** → section created and listed (PDF post-create behaviour as in Handoff 54; for a 1-page source that's the F3 end-of-document case — acceptable, see the Handoff 54 backlog).
- [ ] A multi-page upload still shows the range inputs and the "next range ready" flow.
- [ ] The Source PDFs view upload (`lease_template_pdf_upload`) still works independently; the two upload widgets don't collide.

---

## Phase 3 — Replace PDF on a PDF-backed section

**Goal:** revise a signature page externally and re-upload it behind the existing section (same section ID; packages pick it up on next generation). This covers the common case of the deferred "re-cut page range" item.

### 3A. Action + handler

In `_library_header_bar()` (line 3786), view mode, when the open section is PDF-backed (`editing_section_id > 0`, a stored path, and `p_is_standalone_clause` False), add **Replace PDF** to the actions, between Edit and Delete — blue outline, size 1. It reveals an uploader below the header (`rx.upload` id `lease_replace_pdf_upload`) with a solid blue **Replace** commit button and a **Cancel**.

```python
async def replace_section_pdf(self, files):
    sid = int(self.editing_section_id or 0)
    if sid <= 0: return
    row = _first(run_query("SELECT LeaseSourceDocumentID, StartPage, EndPage, StoredFilePath, StorageRoot "
                           "FROM LeaseDocumentSections WHERE LeaseDocumentSectionID = ?", (sid,), db=self.db))
    # read new PDF, page_count(new); require page_count(new) >= EndPage (or == 1 when the section is 1-1)
    # split_pdf_pages(new_pdf, StartPage, EndPage, output_name, storage_root, f_property, f_document_category)
    # UPDATE LeaseDocumentSections SET StoredFilePath=?, RelativePath=?, StorageRoot=?, UpdatedOn=SYSDATETIME() WHERE ...
    # if the section is 1:1 with its source (StartPage=1 AND EndPage=source PageCount):
    #     also UPDATE LeaseSourceDocuments SET StoredFilePath, RelativePath, PageCount for that source
    # self.edit_section(sid); self._load_sections(); self._load_all_sections()
    # form_success = "Replaced the PDF behind this section."
```

- **In place** — same `LeaseDocumentSectionID`, same `LeaseSourceDocumentID`. No new source row (that's what **+ New Section** is for — Mark's call: "Replace for fixes, + New for genuinely new variants").
- Store the new split file under a fresh filename (timestamp suffix), so a stale generated package that still references the old path doesn't silently change. Regeneration is snapshot-based anyway.
- Show an error, don't crash, if the new PDF has too few pages for the section's range.

### Phase 3 checklist
- [ ] Open a 1-page PDF section → **Replace PDF** → upload a revised 1-page PDF → the stored file updates, `UpdatedOn` bumps, the view refreshes.
- [ ] Multi-page section: replacing with a PDF that has ≥ EndPage pages re-splits the same range; fewer pages → a clean error.
- [ ] A previously generated package that used the section is unchanged until regenerated.
- [ ] Text-backed sections do **not** show Replace PDF.

---

## Do Not Touch

| What | Why |
|---|---|
| `split_pdf_pages`, `save_uploaded_pdf`, `copy_existing_pdf`, storage-path helpers | PDF/file handling is unchanged; only *where it's triggered from* moves. |
| `create_section` PDF branch / F3 "advance range" behaviour (Handoff 54) | Reused as-is. |
| Sections list/detail, `library_detail_mode`, `_library_edit_body`, `save_section_content` | Built on, not changed. |
| The `_source_*` components, `source_document_card`, `section_row`, `_record_header_card` | Built in `80171cb` to Mark's standard; Phase 1 moves them, it doesn't restyle them. |
| `LucidPM/components/buttons.py` | Shared; any change affects other pages. |
| `LeaseSourceDocuments` / `LeaseDocumentSections` schema | No columns added. Replace PDF updates existing columns only. |
| Package Templates tab, `lease_merge.py`, `lease_documents_pdf.py`, `lease_package_builder.py` | Out of scope. |
| The merge-token picker (`_available_token_buttons_panel`) | Handoff 55. |
| `LEASE_DOCUMENTS_RESIZER_SCRIPT` beyond removing the dead load handle | Window singleton; other edits risk both other tabs. |

---

## Gotchas

- **`select_source_document` wipes `p_*` and `editing_section_id`** (comment inside it, after line 1185). Fine in the Source PDFs view (no section is open there), but never call it from the create flow — use `_load_source_context` / `set_new_section_source`. `cancel_source_edit` deliberately uses `_load_source_metadata_fields` instead for the same reason.
- **The create and edit panels render only under `library_left_view == "sections"`.** Any handler that opens one must also set `library_left_view = "sections"` (1C).
- **`selected_source_document_id` is shared** between the Source PDFs view and the create flow (`set_new_section_source` sets it). Switching to Source PDFs after a From-PDF create will open that source's detail rather than the upload form — that's expected.
- **`new_source_document` (Close / + New Source) also clears `p_*`, `sections` and `editing_section_id`.** Fine from the Source PDFs view; don't wire it to anything in the Sections view.
- **Two (Phase 2: three) `rx.upload` widgets on one page** — each needs a unique id or `rx.selected_files(...)` / `rx.upload_files(...)` cross-wire. Ids: `lease_template_pdf_upload` (Source PDFs view), `lease_inline_source_upload` (create flow), `lease_replace_pdf_upload` (Phase 3).
- **`_load_source_documents` re-validates `selected_source_document_id`** and zeroes it if the row vanished — keep relying on it after uploads and metadata saves.
- **`developer_tools_enabled`** gates the local-path import; it moves with `_source_new_upload_form()` unchanged.
- **Reflex `.stop_propagation`** on the Reusable/Active toggles in `section_row` is what stops a toggle click from also opening the row. Keep it when the table moves.
- **Edit/olive styling depends on `!important`** in `edit_button()`. If Edit ever renders gray, check that first.

---

## Deferred / out

- Merging or renaming the **Package Templates** tab — not touched.
- Structured property/tenant-type **fields on a section** for filtering signature-page variants — possible follow-up; for now naming + `ClauseTag` + the Library filters carry it. (Sections are property-agnostic and reusable today; a real property scope is a schema + merge question for its own handoff.)
- **Re-cut a section's page range** (change StartPage/EndPage without replacing the file) — still deferred; Replace PDF covers the revise-the-file case.
- Bulk "explode a whole lease PDF" wizard — the existing per-range "next range ready" flow (F3) is the tool.
- A **Delete** for source documents — none exists today and none is added here.
- Final **Cancel** styling and a Delete **confirmation dialog** — Mark's open decisions on the UI standard; not part of this handoff.

---

## File Locations

```
LucidPM/pages/lease_documents.py            ← the only file changed
LucidPM/components/buttons.py               ← used (edit_button / delete_button), not changed

Phase 1:
  state: library_left_view, set_library_left_view, source_coverage_summary (@rx.var)
  _tab_library(): left-panel view switch + right-panel sources branch (optional _library_right_panel helper)
  new: _source_coverage_line
  edit: start_new_section_from_source, open_section_in_library, start_new_section (+ library_left_view)
  delete: _tab_load, source_document_row, load_tab_section_row, load_tab_split_pct (+ setter)
  edit: lease_documents_content() tab bar, LEASE_DOCUMENTS_RESIZER_SCRIPT, on_load, line-342 comment

Phase 2:
  state: show_inline_source_upload
  _persist_source_pdf() helper (factored from handle_upload)
  upload_source_for_new_section()
  _library_create_pdf_body(): inline upload panel + single-page range collapse
  set_new_section_source(): prefill p_section_name

Phase 3:
  replace_section_pdf()
  _library_header_bar(): Replace PDF action + uploader

Frontend http://localhost:3000 · Backend http://localhost:8000 · Test DB green / Prod red
```

---

*Load stops being a tab. Source PDFs become a switchable view inside the Section Library — list, upload, metadata, coverage — right next to the sections they feed, using the screens already built to the new UI standard. The frequent path (one formatted page → one section) collapses to upload-name-split in the From-PDF create mode, and revising that page is a Replace PDF action on the section. Two tabs, one file, three commits.*
