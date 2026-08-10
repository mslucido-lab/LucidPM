# LucidoPM — ChatGPT Handoff 47
*Bank Package — Correctness Fixes From Code Review*
*Prepared: 2026-08-09*

---

## What This Is

Six correctness bugs found in code review of the Bank Package work (Handoff 46), all isolated and independently fixable. This handoff covers the bugs that will actually break or mislead a user — a garbled button label, a crash on bad input, a broken download header, an unusable input field, a query string that breaks on certain property names, and a silent wrong-data substitution.

**Two files change: `LucidPM_Reflex.py` and `pages/proforma.py`. No DB, no schema. The efficiency/architecture items from the same review (whole-state-tree cost, blocking event loop, duplicate queries, hardcoded basis/mode, NOI-margin triplication) are deliberately NOT in this handoff — they're real but lower-urgency design questions that deserve their own separately-scoped handoff, not bundled in with bug fixes.**

---

## Fix 1 — Mojibake button label

`pages/proforma.py`, in `proforma_content()`. The Bank Package button's label somehow ended up with corrupted encoding for the arrow character.

**Current** (line 674):

```python
                        rx.button("â¬‡ Download Bank Package", variant="outline",
                                  color_scheme="green", size="2"),
```

**Replace** with:

```python
                        rx.button("⬇ Download Bank Package", variant="outline",
                                  color_scheme="green", size="2"),
```

Same down-arrow character (⬇) already used correctly one hunk above on the existing "⬇ Download PDF" button (line 664).

---

## Fix 2 — `cap_rate` query param crashes on bad input

`LucidPM_Reflex.py`, in `bank_package_pdf_endpoint`. Every other numeric param in this file is parsed with a fallback; this one isn't.

**Current** (line 486):

```python
    cap_rate    = float(params.get("cap_rate", "6.0"))
```

**Replace** with:

```python
    try:
        cap_rate = float(params.get("cap_rate", "6.0"))
    except (ValueError, TypeError):
        cap_rate = 6.0
```

---

## Fix 3 — Bank Package filename unsanitized in `Content-Disposition`

`LucidPM_Reflex.py`, end of `bank_package_pdf_endpoint`. The three sibling endpoints all normalize the property name before using it in a filename; this one doesn't.

**Current** (line 521):

```python
    filename = f"{prop_filter}-{quarter_label}-Property Performance Package.pdf"
```

**Replace** with:

```python
    filename = f"{prop_filter.replace(' ', '_')}-{quarter_label}-Property_Performance_Package.pdf"
```

This matches the exact normalization pattern already used by `rent_roll_pdf_endpoint`, `proforma_pdf_endpoint`, and `property_financials_pdf_endpoint` in this same file. It doesn't fully eliminate every possible header-breaking character (a literal `"` in a property name is still a risk, same as it already is for the other three endpoints today) — full sanitization of all four filename sites is a separate, pre-existing concern out of scope here. This fix brings the new endpoint in line with the existing convention, not further ahead of it.

---

## Fix 4 — Cap Rate input can't accept decimals or be cleared

`pages/proforma.py`. `ProformaState.cap_rate` is a `float`, bound directly to a controlled `rx.input`. Every other free-typed numeric-ish field in this codebase (`selected_year_str` in this same class) avoids this exact problem with a string-mirror pattern — apply the same fix here.

### Add a string mirror field

Immediately after `cap_rate: float = 6.0` (line 72), add:

```python
    cap_rate_str: str = "6.0"   # display binding for the input — avoids snapping mid-keystroke
```

### Update the setter

**Current** (lines 125–129):

```python
    def set_cap_rate(self, v: str):
        try:
            self.cap_rate = float(v)
        except (TypeError, ValueError):
            pass
```

**Replace** with:

```python
    def set_cap_rate(self, v: str):
        self.cap_rate_str = v
        try:
            self.cap_rate = float(v)
        except (TypeError, ValueError):
            pass
```

The display string always reflects exactly what the user typed, even mid-decimal or empty; `cap_rate` (the numeric value actually used in `bank_package_url`) only updates when the string parses cleanly, same fail-safe behavior as before.

### Update the input binding

**Current** (lines 722–728):

```python
                    rx.input(
                        value=ProformaState.cap_rate,
                        on_change=ProformaState.set_cap_rate,
                        type="number",
                        size="2",
                        width="80px",
                    ),
```

**Replace** with:

```python
                    rx.input(
                        value=ProformaState.cap_rate_str,
                        on_change=ProformaState.set_cap_rate,
                        type="number",
                        size="2",
                        width="80px",
                    ),
```

---

## Fix 5 — `bank_package_url` doesn't URL-encode the property name

`pages/proforma.py`. A property name containing `&` (or other query-string-special characters) truncates or corrupts the query string.

Add `from urllib.parse import quote` to the top of the file's imports (alongside the existing `import reflex as rx` / `import datetime` block).

**Current** (lines 87–93):

```python
    @rx.var
    def bank_package_url(self) -> str:
        prop = self.selected_property if self.selected_property else "All"
        return (
            f"http://localhost:8000/api/bank-package-pdf"
            f"?year={self.proforma_year}&property={prop}&db={self.db}&cap_rate={self.cap_rate}"
        )
```

**Replace** with:

```python
    @rx.var
    def bank_package_url(self) -> str:
        prop = quote(self.selected_property) if self.selected_property else "All"
        return (
            f"http://localhost:8000/api/bank-package-pdf"
            f"?year={self.proforma_year}&property={prop}&db={self.db}&cap_rate={self.cap_rate}"
        )
```

**Do not touch `pdf_download_url`** (lines 79–85) — it has the identical pre-existing issue, but it wasn't introduced by this work and isn't part of this handoff. Worth a follow-up fix, but leave it alone here.

---

## Fix 6 — Silent property substitution when `prop_filter` doesn't match

`LucidPM_Reflex.py`, in `_build_proforma_pdf_bytes`. If a non-`"All"` `prop_filter` doesn't exactly match a `Properties.PropertyName`, the current code silently falls back to the alphabetically-first property's data — while the generated PDF header still prints the originally-requested name. This must fail loudly instead, but **the existing `"All"` behavior (used by the standalone `/api/proforma-pdf` endpoint) must not change.**

### Change the property resolution and return type

**Current** (lines 290, 304):

```python
def _build_proforma_pdf_bytes(prop_filter: str, year: int, basis: str, db: str) -> bytes:
```
```python
    state.selected_property = prop_filter if prop_filter in prop_names else (prop_names[0] if prop_names else "")
```

**Replace** the signature line with:

```python
def _build_proforma_pdf_bytes(prop_filter: str, year: int, basis: str, db: str) -> bytes | None:
```

**Replace** the property-resolution line with:

```python
    if prop_filter == "All":
        state.selected_property = prop_names[0] if prop_names else ""
    elif prop_filter in prop_names:
        state.selected_property = prop_filter
    else:
        return None
```

`"All"` keeps exactly its current behavior (falls back to the first property — that existing behavior is unchanged, not part of this fix). A non-`"All"` value that doesn't match any real property now returns `None` instead of silently substituting a different property's data.

### Update both callers to check for `None`

**In `proforma_pdf_endpoint`** — current (around line 358):

```python
    pdf_bytes = _build_proforma_pdf_bytes(prop_filter, year, basis, db)

    filename = f"proforma_{prop_filter.replace(' ', '_')}_{year}.pdf"
```

**Replace** with:

```python
    pdf_bytes = _build_proforma_pdf_bytes(prop_filter, year, basis, db)
    if pdf_bytes is None:
        return Response(content=b"Property not found", status_code=404)

    filename = f"proforma_{prop_filter.replace(' ', '_')}_{year}.pdf"
```

**In `bank_package_pdf_endpoint`** — current:

```python
    rent_roll_bytes = _build_rent_roll_pdf_bytes(today, prop_filter, "Bank", db)
    proforma_bytes = _build_proforma_pdf_bytes(prop_filter, year, "Bank", db)
    financials_bytes = _build_property_financials_pdf_bytes(
        prop_filter, "Trend", cap_rate, year, db
    )
    if financials_bytes is None:
        return Response(content=b"Property not found", status_code=404)
```

**Replace** with:

```python
    rent_roll_bytes = _build_rent_roll_pdf_bytes(today, prop_filter, "Bank", db)
    proforma_bytes = _build_proforma_pdf_bytes(prop_filter, year, "Bank", db)
    if proforma_bytes is None:
        return Response(content=b"Property not found", status_code=404)
    financials_bytes = _build_property_financials_pdf_bytes(
        prop_filter, "Trend", cap_rate, year, db
    )
    if financials_bytes is None:
        return Response(content=b"Property not found", status_code=404)
```

(This doesn't fix the separate, already-known "existence isn't checked until after some PDFs are built" ordering issue — that's one of the deferred efficiency items. This just makes sure a mismatch is caught instead of silently producing wrong data.)

---

## Do Not Touch

| What | Why |
|---|---|
| `pdf_download_url` (proforma.py) | Has the identical URL-encoding gap as Fix 5, but pre-existing and out of scope — see Fix 5 |
| `_build_rent_roll_pdf_bytes` | Not touched — no equivalent property-mismatch bug (rent roll doesn't do an exact-match lookup the same way) |
| `"All"` behavior in `_build_proforma_pdf_bytes` | Explicitly preserved as-is — Fix 6 only changes the non-`"All"`-mismatch case |
| `_standalone_state()`, the whole-state-tree cost, the blocking/async structure of `bank_package_pdf_endpoint`, the duplicate Properties queries, the hardcoded `basis`/`mode`/`as_of` in the merge endpoint, the triplicated NOI-margin-% calculation | All real findings from the same review, all deliberately deferred to a future handoff — not bug fixes, design/perf decisions that need their own scoping |
| Any other page or endpoint | Not in scope |

---

## Validation Checklist

- [ ] Bank Package button shows a correct down-arrow (⬇), not garbled text
- [ ] `GET /api/bank-package-pdf?property=X&cap_rate=notanumber` returns a normal response using the 6.0 default instead of a 500
- [ ] Bank Package filename downloads with underscores in place of spaces, matching the other three PDF downloads' naming convention
- [ ] Typing "6.25" into the Cap Rate field works correctly — the decimal point doesn't get dropped mid-keystroke
- [ ] Clearing the Cap Rate field to retype a new value works — it doesn't snap back to the old value
- [ ] A property name containing `&` downloads the correct property's Bank Package (not truncated/wrong)
- [ ] `GET /api/proforma-pdf?property=All&...` still works exactly as before (falls back to the first property, unchanged)
- [ ] `GET /api/proforma-pdf?property=SomeTypoName&...` now returns 404 instead of silently returning a PDF for a different property
- [ ] `GET /api/bank-package-pdf?property=SomeTypoName&...` now returns 404 instead of a package with mismatched proforma data
- [ ] All existing valid Bank Package and Proforma downloads still work exactly as before for correct property names

---

## How to Deliver This

Per `CLAUDE.md`: edit both files in place, no new versioned files.

1. Apply all six fixes directly to the live files.
2. Verify against the checklist above.
3. Commit with a descriptive message (e.g. "Fix Bank Package correctness bugs: encoding, crash, sanitization, decimal input, URL encoding, property mismatch").
4. No archive step needed here — `pages/proforma.py` and `LucidPM_Reflex.py` aren't part of the `_vN.py` duplicate-file cleanup queue for this change.

---

## File Locations

```
C:\Dell Inspirion\TenantCRM\LucidPM_Reflex - ChatGPT\LucidPM_Reflex\
  LucidPM_Reflex.py       ← Fixes 2, 3, 6
  pages\proforma.py       ← Fixes 1, 4, 5

Frontend: http://localhost:3000
Backend:  http://localhost:8000
Test DB: green banner | Prod DB: red banner
```

---

*Six isolated correctness fixes, each independently testable. No architecture changes, no efficiency work — those are tracked separately for a future handoff.*
