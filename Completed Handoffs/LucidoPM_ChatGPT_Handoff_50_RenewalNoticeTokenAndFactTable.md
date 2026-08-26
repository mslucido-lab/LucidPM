# LucidoPM — ChatGPT Handoff 50
*Renewal/Notice Documents — New Merge Token + Authorable Fact Table*
*Prepared: 2026-08-25*

---

## What This Is

Small, independent additions to the lease document merge/render pipeline needed to build a "Notice and Acknowledgment of Exercise of Renewal Option" document (and future short-form notices/amendments of the same shape) in the Section Library:

1. A new composed merge token, `OriginalLeaseDescription`, that produces a sentence like `"Short Form Commercial Lease beginning September 1, 2025, and ending August 31, 2026"` — built from the **parent** lease's dates (this document is generated against the new renewal-term lease record, so its own dates describe the renewal, not the original). Requires also fetching the parent lease's `LeaseEnd`, which isn't queried today, and adding the `OriginalLeaseEndDate`/`OriginalLeaseEndDateLong` tokens that gap was hiding.
2. A new, reusable, **authorable** fact-table rendering primitive — a bordered label/value table (Landlord / Tenant / Premises / Original Lease / Renewal Term, etc.) that can be added to any document by typing plain text into a Section Library `Content` field, with no code change per document.
3. Exposing the new token in the Section Library's existing "Available tokens" picker UI, so it's discoverable the same way every other token is — not just usable if someone happens to type it in from memory.

**Three files change: `LucidPM/lease_merge.py`, `LucidPM/pages/lease_documents_pdf.py`, and `LucidPM/pages/lease_documents.py`. No DB schema changes, no new columns.**

**Explicitly NOT in this handoff** (deferred by product decision, not oversight):
- No landlord signer name/title token or field (e.g. "Mark Lucido, President"). Mark is handling execution via a separately uploaded, already-signed signature page — the code-generated blank-line signature footer (`SIGNATURE_FOOTER_TEXT` in `lease_render_styles.py`) is untouched.
- No DBA / multi-tenant-party data model changes. `TenantName` remains a single free-text field; a co-tenant + d.b.a. string can be typed directly into it as a workaround, same as today.
- No actual Section Library rows for the renewal notice document itself. This handoff only adds the token and the table capability — authoring the real document content (header table + numbered clauses) is a follow-up content task, not a Codex code task, and can happen entirely through the Section Library once this ships.

---

## Current State

### Token: nothing composes "original lease description" today

`get_lease_merge_context()` in `LucidPM/lease_merge.py` builds a single large `context` dict (starts at line 727), then adds composed/alias tokens after it closes (lines 867–921). Relevant existing tokens it can build on:

- `DocTitle` — hardcoded `"SHORT FORM COMMERCIAL LEASE"` (line 732)
- `LeaseStartLong` / `LeaseEndLong` — e.g. `"September 1, 2025"` (lines 772, 777), driven by the same `lease_start` / `lease_end` local `datetime.date` variables used throughout this function
- `LeaseTermDescription` (line 836) and the composed `LeaseTermBlock` (lines 888–901) are close in spirit but produce a duration/occupancy sentence for the lease *header*, not the short "Doc Title beginning X, and ending Y" summary this document's fact table needs. Confirmed no existing token produces that exact sentence.

**Important:** this document is generated against the *renewal term's own* `Lease` row (`ParentLeaseID` pointing at the lease being renewed), the same convention already used for amendments — not against the expiring lease directly. That means `lease_start`/`lease_end` in this function are the **renewal term's** dates, not the original lease's. `OriginalLeaseDescription` must be built from the **parent** lease's dates (`parent_start`, and a new `parent_end` — see below), not from `lease_start`/`lease_end`. The existing `OriginalLeaseStartDate(Long)` tokens already do this correctly for the start date; there's no equivalent for the end date yet. Checked the parent-lease lookup query (`lease_merge.py:627–630`) directly — it only selects `LeaseStart, ExecutionDate`, so `LeaseEnd` isn't even fetched for the parent lease today. That's a genuine gap, not just a missing token, and Part A below fixes both.

### Fact table: no reusable table primitive exists

`LucidPM/pages/lease_documents_pdf.py` builds PDF flowables from each Section Library `Content` block via `_paragraph_for_block()` (starts at line 800), which sniffs the plain text of the block against a chain of detector functions (`_is_doc_title`, `_is_jurisdiction`, `_is_party_label`, `_is_signature_block`, etc., each ~5–10 lines, e.g. lines 520–559) and routes matches to the appropriate flowable builder. This is the existing, working pattern for making document layout "authorable" from Section Library content without a code change per document — e.g. a payment schedule is authored as plain lines like `"a) March 1, 2026: $1,365.00"` and auto-detected by `_is_payment_schedule_line()`, then rendered as a table by `_schedule_table_flowable()` (lines 639–756).

There is no equivalent for a general label/value fact table. `_schedule_table_flowable()` is purpose-built for payment rows (2 or 4 numeric columns, no borders). The only other `Table`/`TableStyle` usage is the hardcoded 3-column signature line block (lines ~1004–1032). Building a bordered 2-column key/value table needs new code, but it can follow exactly the same "detect a text shape, dispatch to a flowable builder" pattern already used for the payment schedule.

---

## The Fix

### Part A — `OriginalLeaseDescription` token

`LucidPM/lease_merge.py`, in `get_lease_merge_context()`.

**This document must be generated against the new renewal-term `Lease` row, not the expiring one** — the same convention already used for amendments: a renewal is entered as a new row in `Leases` with `ParentLeaseID` pointing at the lease it renews and its own `LeaseStart`/`LeaseEnd` set to the renewal term (`pages/tenants.py`, the generic lease form that already handles `ParentLeaseID`/`ExecutionDate` for amendments). Under that convention, when this document is generated:

- `LeaseStartDate`/`LeaseEndDate`/`LeaseStartLong`/`LeaseEndLong` resolve to the **renewal term's own dates** (e.g. Sept 1, 2026 – Aug 31, 2027) — these already exist and need no changes. The "Renewal Term" fact-table row is authored as `{{LeaseStartLong}} through {{LeaseEndLong}}` (see Part B's authoring example) — no new token required.
- The **original lease's** dates must come from the parent lease, via `parent_lease_id`/`parent_start` — exactly like `OriginalLeaseStartDateLong` already does. But the parent-lease lookup only fetches `LeaseStart`/`ExecutionDate` today, not `LeaseEnd`, so there's no way to get the original lease's *end* date yet. This must be added alongside the new token, or `OriginalLeaseDescription` can't be built correctly.

#### A1. Fetch the parent lease's end date

**Current** (lines 624–634):

```python
    parent_lease_id = lease.get("ParentLeaseID")
    parent_lease = {}
    if parent_lease_id:
        parent_lease = _first(run_query(
            "SELECT LeaseStart, ExecutionDate FROM Leases WHERE LeaseID = ?",
            (int(parent_lease_id),),
            db=db,
        ))

    parent_execution = _date(parent_lease.get("ExecutionDate")) if parent_lease else None
    parent_start = _date(parent_lease.get("LeaseStart")) if parent_lease else None
```

**Replace** with:

```python
    parent_lease_id = lease.get("ParentLeaseID")
    parent_lease = {}
    if parent_lease_id:
        parent_lease = _first(run_query(
            "SELECT LeaseStart, LeaseEnd, ExecutionDate FROM Leases WHERE LeaseID = ?",
            (int(parent_lease_id),),
            db=db,
        ))

    parent_execution = _date(parent_lease.get("ExecutionDate")) if parent_lease else None
    parent_start = _date(parent_lease.get("LeaseStart")) if parent_lease else None
    parent_end = _date(parent_lease.get("LeaseEnd")) if parent_lease else None
```

#### A2. Add `OriginalLeaseEndDate`/`OriginalLeaseEndDateLong` and `OriginalLeaseDescription`

**Current** (lines 856–860):

```python
        "OriginalLeaseExecutionDate": _short_date_no_leading_zero(parent_execution) if parent_lease_id else "",
        "OriginalLeaseExecutionDateLong": _long_date(parent_execution) if parent_lease_id else "",
        "OriginalLeaseStartDate": _short_date_no_leading_zero(parent_start) if parent_lease_id else "",
        "OriginalLeaseStartDateLong": _long_date(parent_start) if parent_lease_id else "",
        "PriorAmendmentsClause": prior_amendments_text,
```

**Replace** with:

```python
        "OriginalLeaseExecutionDate": _short_date_no_leading_zero(parent_execution) if parent_lease_id else "",
        "OriginalLeaseExecutionDateLong": _long_date(parent_execution) if parent_lease_id else "",
        "OriginalLeaseStartDate": _short_date_no_leading_zero(parent_start) if parent_lease_id else "",
        "OriginalLeaseStartDateLong": _long_date(parent_start) if parent_lease_id else "",
        "OriginalLeaseEndDate": _short_date_no_leading_zero(parent_end) if parent_lease_id else "",
        "OriginalLeaseEndDateLong": _long_date(parent_end) if parent_lease_id else "",
        "PriorAmendmentsClause": prior_amendments_text,
```

Then, right after the existing alias block (lines 874–876, `LandlordEntityUpper`/`TenantNameUpper`/`TenantNameWithDBAUpper`):

```python
    # Original lease summary sentence for renewal/notice documents, e.g.
    # "Short Form Commercial Lease beginning September 1, 2025, and ending August 31, 2026"
    # Deliberately built from the PARENT lease's own dates, not this lease's —
    # this lease record IS the renewal term being documented, so its own
    # LeaseStartLong/LeaseEndLong describe the *new* term, not the original one.
    context["OriginalLeaseDescription"] = (
        f"{context['DocTitle'].title()} beginning {context['OriginalLeaseStartDateLong']}, "
        f"and ending {context['OriginalLeaseEndDateLong']}"
        if parent_lease_id and parent_start and parent_end else ""
    )
```

Only resolves when `ParentLeaseID` is set (a renewal/amendment lease) — same guard as every other `OriginalLease*`/`Amendment*` token. On a base lease with no parent, it's `""`, consistent with how those tokens already behave.

---

### Part B — Authorable fact table

`LucidPM/pages/lease_documents_pdf.py`.

#### B1. Add the `colors` import

**Current** (lines 67–70):

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Spacer, Preformatted, KeepTogether, Paragraph, CondPageBreak, Table, TableStyle
```

**Replace** with:

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Spacer, Preformatted, KeepTogether, Paragraph, CondPageBreak, Table, TableStyle
```

#### B2. Add the detector and flowable builder

Add these two new functions immediately after `_is_signature_block` (which currently ends around line 560, right before `_split_payment_schedule_item` at line 602 — place the new functions in that gap):

```python
def _is_fact_table_block(block: str) -> bool:
    """Detect an explicitly-authored fact table: <table>...</table> wrapping
    'Label: value' lines. Explicit marker (same convention as the '>>' indent
    prefix) so ordinary clause prose containing a colon never false-positives."""
    text = str(block or "").strip()
    return bool(re.match(r"^<table>", text, re.IGNORECASE)) and bool(re.search(r"</table>\s*$", text, re.IGNORECASE))


def _fact_table_rows(block: str) -> list[tuple[str, str]]:
    inner = re.sub(r"^<table>\s*", "", block.strip(), flags=re.IGNORECASE)
    inner = re.sub(r"\s*</table>$", "", inner, flags=re.IGNORECASE)
    rows = []
    for line in inner.split("\n"):
        line = line.strip()
        if not line:
            continue
        label, sep, value = line.partition(":")
        if not sep:
            raise ValueError(
                f"Fact table row is missing a ':' separator and cannot be rendered: {line!r}"
            )
        rows.append((label.strip(), value.strip()))
    return rows


def _fact_table_flowable(rows: list[tuple[str, str]]):
    """Render a bordered label/value fact table (Landlord/Tenant/Premises/... header
    block). Authored entirely from Section Library Content text -- no per-document code."""
    if not rows:
        return []

    label_style = ParagraphStyle(
        "FactTableLabel",
        parent=LEASE_STYLES["CLAUSE_BODY"],
        fontName="Times-Bold",
        leftIndent=0,
        firstLineIndent=0,
        alignment=0,  # TA_LEFT
        spaceAfter=0,
    )
    value_style = ParagraphStyle(
        "FactTableValue",
        parent=label_style,
        fontName="Times-Roman",
    )

    effective_setup = _page_setup_with_word_margins()
    frame_width = letter[0] - effective_setup.get("leftMargin", 36) - effective_setup.get("rightMargin", 36)
    label_w = 1.4 * inch
    value_w = frame_width - label_w

    table_rows = [
        [Paragraph(_xml(label), label_style), Paragraph(_xml(value), value_style)]
        for label, value in rows
    ]
    tbl = Table(table_rows, colWidths=[label_w, value_w], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [KeepTogether([tbl]), Spacer(1, 8)]
```

A malformed row (a non-blank line inside `<table>...</table>` with no `:`, e.g. a typo like `Original Lease {{OriginalLeaseDescription}}` missing its colon) must fail document generation loudly, not silently drop the row from a legal document. `_fact_table_rows` is called directly from `_paragraph_for_block()` at line 982's story-building loop (`flowables = _paragraph_for_block(block)`), which has no surrounding `try/except` — so this `ValueError` will propagate up out of PDF generation as-is. **Verify during implementation** that whatever wraps the top-level PDF-build call for this document type does not swallow the exception into a silently-truncated or blank PDF — it must surface as a visible generation failure the user sees (e.g. an error response or on-screen message identifying the malformed line), not a partial document with a row missing.

#### B3. Wire the detector into the dispatch chain

`_paragraph_for_block()`.

**Current** (lines 806–815):

```python
    if clean.startswith(">>"):
        indented_style = ParagraphStyle(
            name="LeaseMarkerIndented",
            parent=LEASE_STYLES["CLAUSE_BODY"],
            leftIndent=(getattr(LEASE_STYLES["CLAUSE_BODY"], "leftIndent", 0) or 0) + 36,
        )
        return _markup_flowables(clean[2:].lstrip(), indented_style)

    if _is_doc_title(clean):
        return _markup_flowables(clean, LEASE_STYLES["DOC_TITLE"])
```

**Replace** with:

```python
    if clean.startswith(">>"):
        indented_style = ParagraphStyle(
            name="LeaseMarkerIndented",
            parent=LEASE_STYLES["CLAUSE_BODY"],
            leftIndent=(getattr(LEASE_STYLES["CLAUSE_BODY"], "leftIndent", 0) or 0) + 36,
        )
        return _markup_flowables(clean[2:].lstrip(), indented_style)

    if _is_fact_table_block(clean):
        return _fact_table_flowable(_fact_table_rows(clean))

    if _is_doc_title(clean):
        return _markup_flowables(clean, LEASE_STYLES["DOC_TITLE"])
```

#### How this gets authored (no code, once this ships)

A Section Library row's `Content` field for the renewal notice's header table would just be plain text with the existing `{{Token}}` merge syntax, wrapped in the new marker:

```
<table>
Landlord: {{LandlordEntity}}
Tenant: {{TenantName}}
Premises: {{SuiteFullAddress}}
Original Lease: {{OriginalLeaseDescription}}
Renewal Term: {{LeaseStartLong}} through {{LeaseEndLong}}
</table>
```

Note this document is generated against the **new renewal lease record** (see Part A), so `{{LeaseStartLong}}`/`{{LeaseEndLong}}` here correctly resolve to the renewal term's own dates — not the original lease's, which is what `{{OriginalLeaseDescription}}` is for. No `{{ExtensionTermDescription}}` needed here; that token only produces a duration phrase (e.g. "twelve (12) months"), not a date range.

Tokens are substituted before this dispatch runs (same as every other section), so `_is_fact_table_block`/`_fact_table_rows` see the final merged text. Adding, removing, reordering, or relabeling rows is a Section Library content edit — no code change, no new handoff.

---

### Part C — Add the token to the "Available tokens" picker

`LucidPM/pages/lease_documents.py`. The Section Library editor already has a live, hand-maintained "Available tokens" panel (`_available_token_buttons_panel()`, defined at line 3238) that Section Library authors use to insert tokens without typing them from memory. It already has an "Amendment / Renewal" group (added separately, line 3320) holding the two closest existing tokens — `OriginalLeaseExecutionDateLong` and `OriginalLeaseStartDateLong`. `OriginalLeaseDescription` must be added there; otherwise it works only for someone who already knows the exact token name, defeating the purpose of the picker.

**Current** (lines 3320–3331):

```python
            _token_group("Amendment / Renewal", [
                "{{AmendmentNumber}}",
                "{{AmendmentNumberProperCase}}",
                "{{AmendmentEffectiveDateLong}}",
                "{{AmendmentEndDateLong}}",
                "{{OriginalLeaseExecutionDateLong}}",
                "{{OriginalLeaseStartDateLong}}",
                "{{PriorAmendmentsClause}}",
                "{{LandlordEntityUpper}}",
                "{{TenantNameUpper}}",
                "{{TenantNameWithDBAUpper}}",
                "{{AmendmentTermBlock}}",
            ], target_id),
```

**Replace** with:

```python
            _token_group("Amendment / Renewal", [
                "{{AmendmentNumber}}",
                "{{AmendmentNumberProperCase}}",
                "{{AmendmentEffectiveDateLong}}",
                "{{AmendmentEndDateLong}}",
                "{{OriginalLeaseExecutionDateLong}}",
                "{{OriginalLeaseStartDateLong}}",
                "{{OriginalLeaseEndDateLong}}",
                "{{OriginalLeaseDescription}}",
                "{{PriorAmendmentsClause}}",
                "{{LandlordEntityUpper}}",
                "{{TenantNameUpper}}",
                "{{TenantNameWithDBAUpper}}",
                "{{AmendmentTermBlock}}",
            ], target_id),
```

No new token group needed — this one already exists and is the right home for it. `{{OriginalLeaseEndDateLong}}` is added alongside `{{OriginalLeaseDescription}}` since Part A introduces both (see A2) and neither existed in the picker before.

---

## Do Not Touch

| What | Why |
|---|---|
| `_schedule_table_flowable`, `_split_payment_schedule_row`, `_split_payment_schedule_item` | Separate, already-working payment-schedule table. Not modified — the new fact table is deliberately a parallel primitive, not a refactor of this one. |
| `SIGNATURE_FOOTER_TEXT`, the signature-line `Table` calls (~lines 1004–1032) | Signer name/title is explicitly out of scope this round — see What This Is. |
| `TenantName`, `DBAName`, `TenantNameWithDBA` | DBA/multi-tenant-party data modeling is explicitly deferred. `DBAName` remains hardcoded to `""` — not populated here. |
| `DocTitle`'s existing all-caps usages (document headings) | Only the new `OriginalLeaseDescription` token applies `.title()`; the heading token itself is untouched. |
| Any Section Library row content | Authoring the actual renewal notice document (header table content + numbered clauses 1–7) is a follow-up content task using the capability this handoff adds, not part of this code change. |
| Every other entry in `_available_token_buttons_panel()` | Only the "Amendment / Renewal" group's list gains one new line (Part C). No other group, button, or the picker's dispatch/script logic changes. |

---

## Validation Checklist

- [ ] `get_lease_merge_context()` still returns successfully for existing leases/amendments with no errors (no regression to the dict-building or the existing alias block)
- [ ] For a renewal/amendment lease (`ParentLeaseID` set, parent has both `LeaseStart` and `LeaseEnd`), `{{OriginalLeaseDescription}}` renders as `"Short Form Commercial Lease beginning <parent's start>, and ending <parent's end>"` — the **parent** lease's dates, not this lease's own
- [ ] For that same renewal lease, `{{LeaseStartLong}}`/`{{LeaseEndLong}}` still resolve to *this* lease's own (renewal-term) dates, confirming the two don't get mixed up
- [ ] For a base lease with no `ParentLeaseID`, `{{OriginalLeaseDescription}}`, `{{OriginalLeaseEndDate}}`, and `{{OriginalLeaseEndDateLong}}` all render as empty strings (no crash, no `"None"` in output) — matching existing `OriginalLeaseStartDate(Long)` behavior
- [ ] `{{OriginalLeaseEndDateLong}}` resolves correctly for a renewal/amendment lease whose parent has a `LeaseEnd` set (this is the new query column added in A1 — confirm it isn't silently still `NULL`/empty due to a stale query)
- [ ] A Section Library test row containing a `<table>...</table>` block with 3–5 `Label: value` lines renders as a bordered two-column PDF table, left column bold
- [ ] A `<table>...</table>` block containing a malformed row (a non-blank line with no `:`, e.g. `Original Lease {{OriginalLeaseDescription}}` with the colon missing) **fails document generation visibly** — an error identifying the bad line, not a PDF that silently omits the row
- [ ] Existing payment-schedule sections still render exactly as before (unaffected by the new detector added to the dispatch chain)
- [ ] Existing documents with **no** `<table>` marker in any section are visually unchanged (new detector never fires on ordinary clause text, including clauses that happen to contain a colon)
- [ ] A fact table with a long value (e.g. a full street address) wraps within its column instead of overflowing the page width
- [ ] `{{OriginalLeaseDescription}}` appears as a clickable button in the Section Library's "Available tokens" panel, under "Amendment / Renewal", in both the clause editor and section editor views
- [ ] All 17 previously-registered pages still compile and the app still runs (`reflex run --backend-only`)

---

## How to Deliver This

Per `CLAUDE.md`: edit all three files in place, no new versioned files.

1. Apply Part A (A1–A2) to `LucidPM/lease_merge.py`.
2. Apply Part B (B1–B3) to `LucidPM/pages/lease_documents_pdf.py`.
3. Apply Part C to `LucidPM/pages/lease_documents.py`.
4. Verify against the checklist above, including a scratch Section Library row exercising the new `<table>` marker, one exercising the malformed-row failure case, and confirming the token button appears in the picker.
5. Commit with a descriptive message (e.g. "Add OriginalLeaseDescription token, authorable fact-table rendering, and token-picker entry for renewal/notice documents").
6. No archive step needed — none of the three files is part of the `_vN.py` duplicate-file cleanup queue for this change.

---

## File Locations

```
C:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\lease_merge.py            ← Part A
  LucidPM\pages\lease_documents_pdf.py  ← Part B
  LucidPM\pages\lease_documents.py      ← Part C

Frontend: http://localhost:3000
Backend:  http://localhost:8000
Test DB: green banner | Prod DB: red banner
```

---

*Three isolated, independently testable additions — a composed token, a new authorable table primitive that fails loudly on malformed input, and the token-picker entry that makes the new token discoverable. No signer/DBA data-model work, and no actual renewal-notice document content — both explicitly deferred to follow-up work once this ships.*
