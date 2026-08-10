# LucidoPM — ChatGPT Handoff 46
*Bank Package — Merge Proforma + Financials Trend + Rent Roll Into One PDF*
*Prepared: 2026-08-09*

---

## What This Is

A new "Download Bank Package" export on the Proforma page that merges three PDFs the app already generates individually — Proforma (Bank basis), Property Financials (Trend mode, which already includes multi-year revenue/opex/NOI and cap-rate-driven valuation), and Rent Roll — into a single PDF using `pypdf`. Rationale: a bank underwriting a loan wants the current-year rent projection, the historical trend + valuation, and the current rent roll together, not three separate downloads. All three source reports already exist and are correct — this handoff reuses them via merge rather than building new chart/report code.

**Three existing endpoints get their bodies extracted into reusable helper functions (behavior unchanged). One new endpoint merges the three. One new state field + one new button on the Proforma page. No DB schema changes, no changes to any chart or existing report's output.**

---

## Part 1 — Extract each existing endpoint's PDF-building logic into a helper

Each of the three existing endpoints in `LucidPM_Reflex.py` currently does all its work inline, ending in a `generate_..._pdf(...)` call, then wraps the resulting bytes in a `Response`. Extract the "build the bytes" portion into a standalone function so both the original endpoint and the new merge endpoint can call it. **Behavior must be byte-for-byte identical to today for all three existing endpoints** — this is a pure extraction, not a rewrite.

### 1a — Rent Roll

Current `rent_roll_pdf_endpoint` (starts line 94) does param parsing (lines 96–105, `params`/`as_of_str`/`prop_filter`/`basis`/`db`/the `as_of` try/except), then everything from `fixed_term_types = {...}` (line 107) through the `generate_rent_roll_pdf(...)` call (ending line 274) computes the PDF bytes, then lines 275–279 build the filename and `Response`.

**Extract lines 107–274** (from `fixed_term_types = {"fixed term", ...}` through the closing `)` of the `generate_rent_roll_pdf(...)` call) into:

```python
def _build_rent_roll_pdf_bytes(as_of: datetime.date, prop_filter: str, basis: str, db: str) -> bytes:
    fixed_term_types = {"fixed term", "option term", "multi-year", "multi year"}
    # ... (unchanged body, exactly as it is today) ...
    prop_label = prop_filter if prop_filter != "All" else "All Properties"
    return generate_rent_roll_pdf(
        rows=rows, as_of_date=as_of, property_name=prop_label, basis=basis,
        property_address=prop_address, tax_account_number=tax_acct,
        total_rentable_sqft=total_rentable, total_occupied_sqft=total_occupied,
        vacancy_rate_pct=vac_pct, avg_annual_psf=avg_psf,
    )
```

The only changes from today's code: wrap it in this `def`, indent everything one level, and change the final `pdf_bytes = generate_rent_roll_pdf(...)` into `return generate_rent_roll_pdf(...)`.

`rent_roll_pdf_endpoint` becomes:

```python
@api.get("/api/rent-roll-pdf")
async def rent_roll_pdf_endpoint(request: Request):
    params      = request.query_params
    as_of_str   = params.get("as_of", "")
    prop_filter = params.get("property", "All")
    basis       = params.get("basis", "Tax")
    db          = params.get("db", TEST_DB_NAME)

    try:
        as_of = datetime.datetime.strptime(as_of_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        as_of = datetime.date.today()

    pdf_bytes = _build_rent_roll_pdf_bytes(as_of, prop_filter, basis, db)

    prop_label = prop_filter if prop_filter != "All" else "All Properties"
    filename = f"rent_roll_{as_of.strftime('%Y%m%d')}_{prop_label.replace(' ', '_')}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

Note `prop_label` is computed once inside the helper (needed for the `generate_rent_roll_pdf` call) and once again in the endpoint (needed for the filename) — this trivial one-line duplication is intentional, not a mistake to "fix" by returning it from the helper.

### 1b — Proforma

Current `proforma_pdf_endpoint` (starts line 283) parses params (lines 285–294), then everything from the `# Re-run computation server-side...` comment (line 296) through the `generate_proforma_pdf(...)` call (ending line 346) computes the bytes, then lines 348–352 build the filename and `Response`.

**Extract lines 296–346** into:

```python
def _build_proforma_pdf_bytes(prop_filter: str, year: int, basis: str, db: str) -> bytes:
    # Re-run computation server-side using same logic as ProformaState._do_compute
    from LucidPM_Reflex.pages.proforma import ProformaState
    state = _standalone_state(ProformaState)
    state.use_test_db = (db == TEST_DB_NAME)
    # ... (unchanged body, exactly as it is today) ...
    return generate_proforma_pdf(
        rows=rows_for_pdf,
        suite_headers=state.suite_headers,
        property_name=prop_filter if prop_filter != "All" else "All Properties",
        year=year,
        basis=basis,
        property_address=prop_address,
        tax_account_number=tax_acct,
    )
```

Same mechanical change: wrap in `def`, indent one level, `pdf_bytes = generate_proforma_pdf(...)` → `return generate_proforma_pdf(...)`.

`proforma_pdf_endpoint` becomes:

```python
@api.get("/api/proforma-pdf")
async def proforma_pdf_endpoint(request: Request):
    """Generate proforma PDF. Params: year, property, basis, db"""
    params       = request.query_params
    year_str     = params.get("year", str(datetime.date.today().year))
    prop_filter  = params.get("property", "All")
    basis        = params.get("basis", "Tax")
    db           = params.get("db", TEST_DB_NAME)

    try:
        year = int(year_str)
    except (ValueError, TypeError):
        year = datetime.date.today().year

    pdf_bytes = _build_proforma_pdf_bytes(prop_filter, year, basis, db)

    filename = f"proforma_{prop_filter.replace(' ', '_')}_{year}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

### 1c — Property Financials

Current `property_financials_pdf_endpoint` (starts line 356) parses params (lines 358–368), then everything from `# Get property ID` (line 370) through the `generate_property_financials_pdf(...)` call (ending line 441) computes the bytes — **including the early `return Response(content=b"Property not found", status_code=404)` at line 374, which cannot stay as a `Response` return once this is a bytes-returning helper.**

**Extract lines 370–441** into:

```python
def _build_property_financials_pdf_bytes(prop_filter: str, mode: str, cap_rate: float, fiscal_year: int, db: str) -> bytes | None:
    """Returns None if the property isn't found — caller must handle that case."""
    # Get property ID
    prop_rows = run_query("SELECT PropertyID, PropertyName FROM Properties WHERE PropertyName=?",
                          (prop_filter,), db=db)
    if not prop_rows:
        return None
    # ... (unchanged body, exactly as it is today) ...
    return generate_property_financials_pdf(
        property_name=prop_filter,
        report_mode=mode,
        cap_rate=cap_rate,
        total_rentable_sqft=total_sqft,
        fiscal_year=fiscal_year,
        revenue=revenue,
        opex=opex,
        notes=notes,
        trend_rows=trend_rows,
        property_address=prop_address,
        tax_account_number=tax_acct,
    )
```

Only real change from a pure extraction: the `return Response(content=b"Property not found", status_code=404)` at the top becomes `return None` — the caller is responsible for turning that into a 404.

`property_financials_pdf_endpoint` becomes:

```python
@api.get("/api/property-financials-pdf")
async def property_financials_pdf_endpoint(request: Request):
    """Generate property financials PDF. Params: property, mode, cap_rate, year, db"""
    params      = request.query_params
    prop_filter = params.get("property", "")
    mode        = params.get("mode", "Single Year")
    db          = params.get("db", TEST_DB_NAME)
    year_str    = params.get("year", str(datetime.date.today().year))
    cap_rate    = float(params.get("cap_rate", "6.0"))

    try:
        fiscal_year = int(year_str)
    except (ValueError, TypeError):
        fiscal_year = datetime.date.today().year

    pdf_bytes = _build_property_financials_pdf_bytes(prop_filter, mode, cap_rate, fiscal_year, db)
    if pdf_bytes is None:
        return Response(content=b"Property not found", status_code=404)

    filename = f"property_financials_{prop_filter.replace(' ', '_')}_{fiscal_year}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

---

## Part 2 — New merge endpoint

Add near the other PDF endpoints in `LucidPM_Reflex.py` (after the three above). Requires `import io` and `from pypdf import PdfReader, PdfWriter` at the top of the file (mirroring the exact merge pattern already used in `pages/lease_documents_pdf.py`: `PdfWriter()`, loop `PdfReader(...)` → `for page in reader.pages: writer.add_page(page)`, then `writer.write(...)`):

```python
@api.get("/api/bank-package-pdf")
async def bank_package_pdf_endpoint(request: Request):
    """Merge Proforma (Bank basis) + Property Financials (Trend) + Rent Roll into one PDF.
    Params: property, year, cap_rate, db. Requires a specific property — "All" is rejected."""
    params      = request.query_params
    prop_filter = params.get("property", "")
    year_str    = params.get("year", str(datetime.date.today().year))
    cap_rate    = float(params.get("cap_rate", "6.0"))
    db          = params.get("db", TEST_DB_NAME)

    if not prop_filter or prop_filter == "All":
        return Response(
            content=b'Select a specific property for the Bank Package (not "All Properties").',
            status_code=400,
        )

    try:
        year = int(year_str)
    except (ValueError, TypeError):
        year = datetime.date.today().year

    proforma_bytes = _build_proforma_pdf_bytes(prop_filter, year, "Bank", db)
    financials_bytes = _build_property_financials_pdf_bytes(prop_filter, "Trend", cap_rate, year, db)
    if financials_bytes is None:
        return Response(content=b"Property not found", status_code=404)
    rent_roll_bytes = _build_rent_roll_pdf_bytes(datetime.date.today(), prop_filter, "Bank", db)

    writer = PdfWriter()
    for section_bytes in (proforma_bytes, financials_bytes, rent_roll_bytes):
        reader = PdfReader(io.BytesIO(section_bytes))
        for page in reader.pages:
            writer.add_page(page)

    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    merged_bytes = buffer.read()

    filename = f"bank_package_{prop_filter.replace(' ', '_')}_{year}.pdf"
    return Response(
        content=merged_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

**Both the Proforma and Rent Roll sections are forced to `basis="Bank"` regardless of the caller's own on-screen basis selection** — the package is specifically "for the bank," so it always uses the underwriting-rent basis, independent of whatever the Proforma page's Basis dropdown currently shows. The Property Financials section always uses `"Trend"` mode (multi-year + valuation), never `"Single Year"`.

---

## Part 3 — Proforma page: cap rate input + Bank Package button

`ProformaState` (`pages/proforma.py`, class starts line 62) has no `cap_rate` field today — cap rate only exists on `PropertyFinancialsAnalyticsState` for the Analytics page's Valuation tab. Add an independent one here, following the same on-screen-setting-drives-the-export pattern already used for `year`/`property`/`basis` via `pdf_download_url`.

### Add state field + setter

Immediately after `selected_year_str: str = ""` (line 71), add:

```python
    cap_rate: float = 6.0
```

Immediately after `set_basis()` (ends line 114), add:

```python
    def set_cap_rate(self, v: str):
        try:
            self.cap_rate = float(v)
        except (TypeError, ValueError):
            pass
```

### Add the download URL computed var

Immediately after `pdf_download_url` (ends line 84), add:

```python
    @rx.var
    def bank_package_url(self) -> str:
        prop = self.selected_property if self.selected_property else "All"
        return (
            f"http://localhost:8000/api/bank-package-pdf"
            f"?year={self.proforma_year}&property={prop}&db={self.db}&cap_rate={self.cap_rate}"
        )
```

### Add the Cap Rate input to the filter bar

In `proforma_content()`, immediately after the "Basis" `rx.vstack` (ends line 694, right before the `rx.button("Run", ...)`), add:

```python
                rx.vstack(
                    rx.text("Cap Rate %", size="1", color="#666"),
                    rx.input(
                        value=ProformaState.cap_rate,
                        on_change=ProformaState.set_cap_rate,
                        type="number",
                        size="2",
                        width="80px",
                    ),
                    spacing="1",
                ),
```

### Add the Bank Package button next to the existing Download PDF button

In the header `rx.hstack` (lines 643–657), immediately after the existing `rx.cond(ProformaState.rows.length() > 0, rx.link(...), rx.fragment())` block that renders the "⬇ Download PDF" link, add a second, identically-guarded block:

```python
                rx.cond(
                    ProformaState.rows.length() > 0,
                    rx.link(
                        rx.button("⬇ Download Bank Package", variant="outline",
                                  color_scheme="green", size="2"),
                        href=ProformaState.bank_package_url,
                        is_external=True,
                    ),
                    rx.fragment(),
                ),
```

Use `color_scheme="green"` (vs. the existing button's `"blue"`) purely so the two buttons are visually distinguishable — not a functional requirement.

---

## Do Not Touch

| What | Why |
|---|---|
| `generate_rent_roll_pdf`, `generate_proforma_pdf`, `generate_property_financials_pdf` (the `pages/*_pdf.py` generator functions) | Not touched at all — only their callers are reorganized |
| Any chart or computed var in `pages/property_financials_analytics.py` | Not in scope — this handoff doesn't touch the Analytics page |
| `PropertyFinancialsAnalyticsState.cap_rate` | Stays independent from the new `ProformaState.cap_rate` — deliberately not shared/coupled between pages |
| `_standalone_state()` | Used as-is by the extracted proforma helper; not modified here (see Handoff 45 for that helper's own follow-up) |
| Any other page or endpoint | Not in scope |

---

## Validation Checklist

- [ ] `/api/rent-roll-pdf`, `/api/proforma-pdf`, `/api/property-financials-pdf` all still produce byte-identical PDFs to before this change, for the same params
- [ ] Proforma page shows a new "Cap Rate %" input in the filter bar, defaulting to 6.0
- [ ] Proforma page shows a new "⬇ Download Bank Package" button next to the existing "⬇ Download PDF" button, both only visible when `rows.length() > 0`
- [ ] Clicking Download Bank Package with a specific property selected produces one merged PDF containing, in order: the Bank-basis proforma, the Trend-mode property financials (with valuation), then the Bank-basis rent roll
- [ ] Changing the Cap Rate input changes the valuation numbers in the downloaded Bank Package's financials section
- [ ] Hitting `/api/bank-package-pdf` with `property=All` (or omitted) returns a 400, not a broken PDF
- [ ] Hitting `/api/bank-package-pdf` with a property name that doesn't exist returns a 404
- [ ] The Proforma page's own Basis dropdown (Tax/Bank) is unaffected by and doesn't affect the Bank Package button — the package always uses Bank basis regardless of what's selected on screen

---

## How to Deliver This

Per `CLAUDE.md`: edit `LucidPM_Reflex.py` and `pages/proforma.py` in place, no new versioned files, no versioned-file archive step for either (neither is part of the `_vN.py` duplicate cleanup queue — `pages/proforma.py`'s old versions weren't flagged for cleanup by this handoff; leave them for whenever that file is scoped for archiving separately).

1. Apply Part 1 (three extractions), Part 2 (new endpoint), and Part 3 (Proforma page UI) directly to the live files.
2. Verify against the checklist above.
3. Commit with a descriptive message (e.g. "Add Bank Package PDF export merging Proforma, Financials Trend, and Rent Roll").

---

## File Locations

```
C:\Dell Inspirion\TenantCRM\LucidPM_Reflex - ChatGPT\LucidPM_Reflex\
  LucidPM_Reflex.py       ← three endpoints refactored, one new endpoint, new imports (io, pypdf)
  pages\proforma.py       ← one new state field, one new setter, one new computed var, two UI additions

Frontend: http://localhost:3000
Backend:  http://localhost:8000
Test DB: green banner | Prod DB: red banner
```

---

*Three endpoint bodies extracted into reusable helpers (behavior unchanged), one new endpoint merges their output via pypdf, one new state field and two new UI elements on the Proforma page drive it. No existing report's output changes.*
