# LucidoPM — ChatGPT Handoff 57
*Property Financials Analytics — Suite Rent PSF tab*
*Prepared: 2026-09-01*

---

## What This Is

Add a new **"Suite Rent"** tab to the Property Financials Analytics page
(`pages/property_financials_analytics.py`). For a single selected property it
shows, per active suite, the **in-place annual rent per square foot** against
the suite's **underwriting rent PSF**, plus the property's weighted-average
in-place PSF as a benchmark line. A small table under the chart carries the
exact numbers.

The metric is **annualized rent ÷ square feet**:

```
in-place PSF   = (current effective monthly rent  × 12) ÷ SquareFeet
underwriting PSF = (PropertySuites.UnderwritingRent × 12) ÷ SquareFeet
```

Both `Leases.RentAmount` / `LeaseRentSchedule.RentAmount` and
`PropertySuites.UnderwritingRent` are **monthly** dollar amounts — this is
already how `pages/rent_roll.py` treats them (`rate * 12`, line ~323) and how
the "Avg occupied annual rent PSF" stat tile on the Rent Roll page is computed.
This handoff reuses that same convention so the numbers reconcile with the
Rent Roll page.

**One file changes: `pages/property_financials_analytics.py`. No DB, no schema,
no new tables or columns, no route change (`LucidPM.py` untouched), no other
page. All five existing tabs and their code are untouched.**

### Scope constraint

This is a **read-only analytics view**. It does not add editing of suites,
rents, or underwriting values — those live on `/admin/suites` and the lease
pages. It does not change how rent or PSF is calculated anywhere else. If the
in-place-vs-underwriting comparison suggests a follow-up (e.g. flag stale
underwriting values), that is a **separate** future handoff, not this one.

---

## The Current State

File: `pages/property_financials_analytics.py` (post-commit `ce1ca75`).

### State class

`PropertyFinancialsAnalyticsState` (line 26) — current fields (lines 27–38):

```python
class PropertyFinancialsAnalyticsState(AppState):
    selected_property: str = "All properties"
    cap_rate: float = 6.0
    active_tab: str = "summary"
    compare_period: str = ""
    compare_metric: str = "all"
    margin_view: str = "margin_pct"   # "margin_pct" | "income_split"

    financials_data: list[dict] = []
    property_sqft: dict = {}
    property_names_map: dict = {}
    property_id_by_name: dict = {}
    property_options: list[str] = ["All properties"]
```

### `on_load` (lines 52–110)

Runs a handful of `run_query(...)` calls and populates the state fields above.
The relevant tail is the per-property square-footage loop and the final
assignments:

```python
        for pid in prop_map.keys():
            sqft_rows = run_query(
                "SELECT ISNULL(SUM(SquareFeet),0) AS total "
                "FROM PropertySuites WHERE PropertyID=? AND IsActive=1",
                (int(pid),),
                db=self.db,
            )
            sqft_map[pid] = float(sqft_rows[0]["total"] or 0) if sqft_rows else 0.0

        years = sorted({r["FiscalYear"] for r in normalized}, reverse=True)
        labels = ["All properties"] + sorted(id_by_name.keys())

        self.financials_data = normalized
        self.property_names_map = prop_map
        self.property_id_by_name = id_by_name
        self.property_sqft = sqft_map
        self.property_options = labels
        if self.selected_property not in labels:
            self.selected_property = "All properties"
        self.compare_period = years[0] if years else ""
```

### `reload_on_db_change` (lines 112–118)

```python
    def reload_on_db_change(self):
        self.financials_data = []
        self.property_sqft = {}
        self.property_names_map = {}
        self.property_id_by_name = {}
        self.property_options = ["All properties"]
        yield PropertyFinancialsAnalyticsState.on_load()
```

### Helpers already present

- `selected_property_id` computed var (lines 120–124) — returns `"0"` for
  "All properties", else the numeric PropertyID as a string.
- `tab_button(label, tab_id)` (lines 388–399) — the standard tab pill; calls
  the auto-generated `set_active_tab(tab_id)` setter. Any new string value of
  `active_tab` works with no extra setter.
- `chart_container(chart_component)` (lines 417–428) — the standard white card
  wrapper around a chart.
- `analytics_metric(label, value)` (line 371) — the standard metric tile
  (accepts a Var).
- Color constants (lines 10–23): reuse `CHART_NOI_STROKE` (`#4AA384`, green,
  the "in-place" bar), `COMPARE_WALNUT_FILL`, `CHART_OPEX_STROKE`,
  `COMPARE_DEFAULT_FILL` (`#8A8A8A`, the "underwriting" outline). **Do not
  invent new colors.**

### Tab bar + render chain (lines 897–937)

```python
                rx.hstack(
                    tab_button("Summary", "summary"),
                    tab_button("Trend", "trend"),
                    tab_button("Margins", "margins"),
                    tab_button("Valuation", "valuation"),
                    tab_button("Compare", "compare"),
                    spacing="2",
                    width="100%",
                ),

                rx.cond(
                    PropertyFinancialsAnalyticsState.active_tab == "summary",
                    summary_chart(),
                    rx.cond(
                        PropertyFinancialsAnalyticsState.active_tab == "trend",
                        trend_chart(),
                        rx.cond(
                            PropertyFinancialsAnalyticsState.active_tab == "margins",
                            rx.vstack(
                                rx.hstack(
                                    margin_view_toggle_button("Margin %", "margin_pct"),
                                    margin_view_toggle_button("Income Split", "income_split"),
                                    spacing="2",
                                ),
                                rx.cond(
                                    PropertyFinancialsAnalyticsState.margin_view == "margin_pct",
                                    margins_chart(),
                                    income_split_chart(),
                                ),
                                spacing="3",
                                width="100%",
                                align_items="start",
                            ),
                            rx.cond(
                                PropertyFinancialsAnalyticsState.active_tab == "valuation",
                                valuation_chart(),
                                compare_chart(),
                            ),
                        ),
                    ),
                ),
```

### Schema facts (from `pages/rent_roll.py` and `pages/suites.py`)

| Column | Table | Meaning |
|---|---|---|
| `SuiteID, PropertyID, SuiteLabel, SquareFeet, SuiteUseType, UnderwritingRent, SortOrder, IsActive` | `PropertySuites` | Suite master. `UnderwritingRent` is a **monthly** $ amount (suites.py input placeholder "Monthly $"). `SquareFeet` can be NULL/0. |
| `LeaseID, TenantID, PropertyID, SuiteID, LeaseStart, LeaseEnd, RentAmount, LeaseTermTypeID` | `Leases` | `RentAmount` monthly. `SuiteID` may be NULL on older leases. |
| `LeaseID, RentAmount, EffectiveStartDate, EffectiveEndDate` | `LeaseRentSchedule` | Time-phased monthly rent; `COALESCE(lrs.RentAmount, l.RentAmount)` is the effective rent as of a date. |
| `TenantName, Suite, SuiteID` | `Tenants` | `t.SuiteID` / `t.Suite` are the fallback suite linkage when `Leases.SuiteID` is NULL. |
| `TenantStatusName` | `TenantStatuses` | Skip rows where this is `"Default"`. |

`rent_roll.py`'s `find_lease(...)` (lines 190–205) is the established
suite→lease matching cascade: **(1)** `Leases.SuiteID == SuiteID`, **(2)**
`Tenants.SuiteID == SuiteID AND Leases.PropertyID == PropertyID`, **(3)**
`Leases.PropertyID == PropertyID AND upper(Tenants.Suite) == upper(SuiteLabel)`.

---

## The Fix

### Step 1 — State fields

In `PropertyFinancialsAnalyticsState`, immediately after
`property_options: list[str] = ["All properties"]` (line 38), add:

```python

    # Suite Rent tab — portfolio-wide, filtered per selected property in a var
    suites_data: list[dict] = []
    suite_leases_data: list[dict] = []
```

Everything stored here must be JSON-safe primitives (str / int / float /
bool / None) — normalize in Step 2, same as `on_load` already does for
`financials_data`.

### Step 2 — Load suites + current leases in `on_load`

In `on_load`, **after** the `for pid in prop_map.keys():` sqft loop ends and
**before** `years = sorted(...)` (line ~100), add:

```python
        suite_rows = run_query(
            "SELECT ps.SuiteID, ps.PropertyID, ps.SuiteLabel, ps.SquareFeet, "
            "ps.SuiteUseType, ps.UnderwritingRent, ps.SortOrder "
            "FROM PropertySuites ps "
            "WHERE ps.IsActive = 1 "
            "ORDER BY ps.PropertyID, ps.SortOrder, ps.SuiteLabel",
            db=self.db,
        )
        suites_norm = []
        for s in suite_rows:
            suites_norm.append({
                "SuiteID": int(s["SuiteID"]),
                "PropertyID": str(int(s["PropertyID"])),
                "SuiteLabel": str(s.get("SuiteLabel") or "").strip(),
                "SquareFeet": float(s["SquareFeet"] or 0),
                "SuiteUseType": str(s.get("SuiteUseType") or "Standard").strip(),
                "UnderwritingRent": (
                    float(s["UnderwritingRent"])
                    if s.get("UnderwritingRent") is not None else None
                ),
                "SortOrder": int(s.get("SortOrder") or 0),
            })

        lease_rows = run_query(
            "SELECT l.LeaseID, l.PropertyID, l.SuiteID, "
            "COALESCE(lrs.RentAmount, l.RentAmount) AS EffectiveRent, "
            "t.TenantName, t.SuiteID AS TenantSuiteID, t.Suite AS TenantSuite, "
            "ts.TenantStatusName "
            "FROM Leases l "
            "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
            "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
            "LEFT JOIN LeaseRentSchedule lrs "
            "  ON lrs.LeaseID = l.LeaseID "
            "  AND lrs.EffectiveStartDate <= CAST(GETDATE() AS date) "
            "  AND (lrs.EffectiveEndDate IS NULL "
            "       OR lrs.EffectiveEndDate >= CAST(GETDATE() AS date)) "
            "WHERE l.LeaseStart <= CAST(GETDATE() AS date) "
            "  AND (l.LeaseEnd IS NULL OR l.LeaseEnd >= CAST(GETDATE() AS date))",
            db=self.db,
        )
        leases_norm = []
        seen_lease_ids = set()
        for l in lease_rows:
            lid = int(l["LeaseID"])
            if lid in seen_lease_ids:
                continue   # dedupe: overlapping LeaseRentSchedule rows
            if str(l.get("TenantStatusName") or "").strip().lower() == "default":
                continue
            seen_lease_ids.add(lid)
            leases_norm.append({
                "LeaseID": lid,
                "PropertyID": str(int(l["PropertyID"])),
                "SuiteID": int(l["SuiteID"]) if l.get("SuiteID") is not None else None,
                "TenantSuiteID": int(l["TenantSuiteID"]) if l.get("TenantSuiteID") is not None else None,
                "TenantSuite": str(l.get("TenantSuite") or "").strip(),
                "TenantName": str(l.get("TenantName") or "").strip(),
                "EffectiveRent": float(l["EffectiveRent"] or 0),
            })
```

Then, in the block of `self.… =` assignments at the end of `on_load`, add
(next to `self.property_sqft = sqft_map`):

```python
        self.suites_data = suites_norm
        self.suite_leases_data = leases_norm
```

### Step 3 — `reload_on_db_change`

Add the two resets alongside the existing ones:

```python
    def reload_on_db_change(self):
        self.financials_data = []
        self.property_sqft = {}
        self.property_names_map = {}
        self.property_id_by_name = {}
        self.property_options = ["All properties"]
        self.suites_data = []
        self.suite_leases_data = []
        yield PropertyFinancialsAnalyticsState.on_load()
```

### Step 4 — Matching helper + computed vars

Add this **module-level** function just above the `PropertyFinancialsAnalyticsState`
class (after the color constants, ~line 24). It is the `rent_roll.find_lease`
cascade, adapted to the normalized dicts from Step 2:

```python
def _match_suite_lease(suite_id: int, prop_id: str, suite_label: str,
                       leases: list[dict]) -> dict | None:
    """Suite -> current lease, same cascade as rent_roll.find_lease."""
    for l in leases:
        if l.get("SuiteID") is not None and l["SuiteID"] == suite_id:
            return l
    for l in leases:
        if (l.get("TenantSuiteID") is not None
                and l["TenantSuiteID"] == suite_id
                and l.get("PropertyID") == prop_id):
            return l
    label_u = suite_label.upper()
    for l in leases:
        if (l.get("PropertyID") == prop_id
                and str(l.get("TenantSuite") or "").strip().upper() == label_u):
            return l
    return None
```

Then, inside `PropertyFinancialsAnalyticsState`, immediately after
`valuation_chart_data` (the last `@rx.var`, ends ~line 416 — just before
`def analytics_metric`), add:

```python
    @rx.var
    def suite_rent_psf_rows(self) -> list[dict]:
        """Per-suite in-place vs underwriting annual rent PSF for the selected property."""
        pid = self.selected_property_id
        if pid == "0":
            return []

        prop_leases = [l for l in self.suite_leases_data if l["PropertyID"] == pid]
        rows = []
        for s in self.suites_data:
            if s["PropertyID"] != pid:
                continue
            sqft = float(s["SquareFeet"] or 0)
            match = _match_suite_lease(s["SuiteID"], pid, s["SuiteLabel"], prop_leases)

            in_place_psf = None
            if match is not None and sqft > 0 and match["EffectiveRent"] > 0:
                in_place_psf = round(match["EffectiveRent"] * 12.0 / sqft, 2)

            uw_psf = None
            if s["UnderwritingRent"] and sqft > 0:
                uw_psf = round(s["UnderwritingRent"] * 12.0 / sqft, 2)

            delta_uw = (
                round(in_place_psf - uw_psf, 2)
                if in_place_psf is not None and uw_psf is not None else None
            )

            rows.append({
                "suite": s["SuiteLabel"],
                "sqft": round(sqft),
                "sqft_display": f"{sqft:,.0f}" if sqft > 0 else "—",
                "occupancy": "Occupied" if match is not None else "Vacant",
                "tenant": match["TenantName"] if match is not None else "—",
                "in_place_psf": in_place_psf if in_place_psf is not None else 0.0,
                "uw_psf": uw_psf if uw_psf is not None else 0.0,
                "in_place_display": f"${in_place_psf:,.2f}" if in_place_psf is not None else "—",
                "uw_display": f"${uw_psf:,.2f}" if uw_psf is not None else "—",
                "delta_display": (
                    (("+" if delta_uw >= 0 else "") + f"${delta_uw:,.2f}")
                    if delta_uw is not None else "—"
                ),
                "sort_order": s["SortOrder"],
            })
        return sorted(rows, key=lambda r: (r["sort_order"], r["suite"]))

    @rx.var
    def suite_rent_psf_property_avg(self) -> float:
        """SquareFeet-weighted in-place annual PSF across occupied suites."""
        num = 0.0
        den = 0.0
        for r in self.suite_rent_psf_rows:
            if r["occupancy"] == "Occupied" and r["in_place_psf"] > 0 and r["sqft"] > 0:
                num += r["in_place_psf"] * r["sqft"]
                den += r["sqft"]
        return round(num / den, 2) if den > 0 else 0.0

    @rx.var
    def suite_rent_psf_avg_display(self) -> str:
        v = self.suite_rent_psf_property_avg
        return f"${v:,.2f}/sf" if v > 0 else "—"

    @rx.var
    def suite_rent_psf_below_uw(self) -> str:
        n = sum(
            1 for r in self.suite_rent_psf_rows
            if r["occupancy"] == "Occupied"
            and r["in_place_psf"] > 0 and r["uw_psf"] > 0
            and r["in_place_psf"] < r["uw_psf"]
        )
        return str(n)

    @rx.var
    def suite_rent_psf_chart_height(self) -> int:
        return max(240, len(self.suite_rent_psf_rows) * 52 + 60)
```

**Notes**
- `in_place_psf` / `uw_psf` are stored as `0.0` (not `None`) in the row dicts
  because Recharts bars need a number; the `*_display` strings carry the "—"
  for the table. A `0.0` bar simply renders nothing, which is the intent for
  vacant / missing-data suites.
- Weighted average matches `rent_roll.py`'s `avg_annual_psf`
  (`sum(rate*12) / sum(sf)` over occupied suites), so the benchmark line
  reconciles with the Rent Roll page's stat tile for the same property.

### Step 5 — Chart + table components

Add just before `def page_property_financials_analytics()` (line 855):

```python
def suite_psf_table_row(row) -> rx.Component:
    return rx.table.row(
        rx.table.cell(row["suite"]),
        rx.table.cell(row["sqft_display"]),
        rx.table.cell(row["occupancy"]),
        rx.table.cell(row["tenant"]),
        rx.table.cell(row["in_place_display"]),
        rx.table.cell(row["uw_display"]),
        rx.table.cell(row["delta_display"]),
    )


def suite_rent_chart() -> rx.Component:
    return rx.cond(
        PropertyFinancialsAnalyticsState.selected_property_id == "0",
        chart_container(
            rx.callout(
                "Pick a single property above to see per-suite rent PSF.",
                icon="info",
                color_scheme="blue",
            ),
        ),
        chart_container(
            rx.vstack(
                rx.hstack(
                    analytics_metric(
                        "Property avg in-place $/SF",
                        PropertyFinancialsAnalyticsState.suite_rent_psf_avg_display,
                    ),
                    analytics_metric(
                        "Suites below underwriting",
                        PropertyFinancialsAnalyticsState.suite_rent_psf_below_uw,
                    ),
                    width="100%",
                    spacing="4",
                ),
                rx.recharts.bar_chart(
                    rx.recharts.bar(
                        data_key="in_place_psf",
                        name="In-place $/SF",
                        fill="rgba(74, 163, 132, 0.55)",
                        stroke=CHART_NOI_STROKE,
                        stroke_width=1.0,
                    ),
                    rx.recharts.bar(
                        data_key="uw_psf",
                        name="Underwriting $/SF",
                        fill="rgba(138, 138, 138, 0.20)",
                        stroke=COMPARE_DEFAULT_FILL,
                        stroke_width=1.0,
                    ),
                    rx.recharts.x_axis(type_="number", unit="$"),
                    rx.recharts.y_axis(
                        type_="category",
                        data_key="suite",
                        width=90,
                    ),
                    rx.recharts.cartesian_grid(stroke_dasharray="3 3", horizontal=False),
                    rx.recharts.graphing_tooltip(),
                    rx.recharts.legend(),
                    rx.recharts.reference_line(
                        rx.recharts.label(
                            value="property avg",
                            position="insideTopRight",
                            style={"fill": "#1F4E79", "fontSize": "11px"},
                        ),
                        x=PropertyFinancialsAnalyticsState.suite_rent_psf_property_avg,
                        stroke="#1F4E79",
                        stroke_dasharray="4 2",
                        stroke_width=2.0,
                    ),
                    data=PropertyFinancialsAnalyticsState.suite_rent_psf_rows,
                    layout="vertical",
                    width="100%",
                    height=PropertyFinancialsAnalyticsState.suite_rent_psf_chart_height,
                    bar_gap=2,
                    bar_category_gap="25%",
                    margin={"top": 10, "right": 40, "left": 10, "bottom": 0},
                ),
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Suite"),
                            rx.table.column_header_cell("Sq Ft"),
                            rx.table.column_header_cell("Occupancy"),
                            rx.table.column_header_cell("Tenant"),
                            rx.table.column_header_cell("In-place $/SF"),
                            rx.table.column_header_cell("UW $/SF"),
                            rx.table.column_header_cell("Δ vs UW"),
                        ),
                    ),
                    rx.table.body(
                        rx.foreach(
                            PropertyFinancialsAnalyticsState.suite_rent_psf_rows,
                            suite_psf_table_row,
                        ),
                    ),
                    width="100%",
                    variant="surface",
                    size="1",
                ),
                width="100%",
                spacing="4",
                align_items="start",
            ),
        ),
    )
```

- `layout="vertical"` → horizontal bars; the **number** axis is X, so the
  benchmark uses `reference_line(x=...)`.
- `height` is a Var (`suite_rent_psf_chart_height`) so the chart grows with the
  suite count instead of squashing.
- `type_="number"` / `type_="category"` are required on the axes in vertical
  layout or Recharts silently renders nothing.

### Step 6 — Tab bar + render chain

**Current** tab bar (lines 897–905) — add one button after "Valuation":

```python
                rx.hstack(
                    tab_button("Summary", "summary"),
                    tab_button("Trend", "trend"),
                    tab_button("Margins", "margins"),
                    tab_button("Valuation", "valuation"),
                    tab_button("Suite Rent", "suite_rent"),
                    tab_button("Compare", "compare"),
                    spacing="2",
                    width="100%",
                ),
```

**Current** innermost `rx.cond` (the `valuation` / `compare` branch, lines
930–934):

```python
                            rx.cond(
                                PropertyFinancialsAnalyticsState.active_tab == "valuation",
                                valuation_chart(),
                                compare_chart(),
                            ),
```

**Replace** with:

```python
                            rx.cond(
                                PropertyFinancialsAnalyticsState.active_tab == "valuation",
                                valuation_chart(),
                                rx.cond(
                                    PropertyFinancialsAnalyticsState.active_tab == "suite_rent",
                                    suite_rent_chart(),
                                    compare_chart(),
                                ),
                            ),
```

That is the only change to the render chain — one more nesting level, exactly
mirroring how the other tabs are chained.

---

## Do Not Touch

| What | Why |
|---|---|
| `on_load`'s existing queries and the `financials_data` / `property_sqft` / `property_names_map` / `property_id_by_name` / `property_options` assignments | Only **append** the two new loads and two new assignments |
| `chart_data`, `margin_chart_data`, `income_split_chart_data`, `compare_*`, `valuation_chart_data` | Not read or modified — the new vars are independent |
| `summary_chart()`, `trend_chart()`, `margins_chart()`, `income_split_chart()`, `valuation_chart()`, `compare_chart()` | Not in scope; must render identically |
| `tab_button()`, `chart_container()`, `analytics_metric()` | Reused as-is, not modified |
| `LucidPM.py` (route + `on_load` wiring) | No change — the tab is internal to the page |
| Any DB object | Read-only; no new table, column, view, or trigger |
| `pages/rent_roll.py`, `pages/suites.py`, `pages/proforma.py` | Referenced for schema only; not edited |

---

## Validation Checklist

- [ ] With **"All properties"** selected, the Suite Rent tab shows the
      "Pick a single property…" callout and no chart.
- [ ] Select a property with several suites → one horizontal bar pair per
      suite (In-place $/SF, Underwriting $/SF), suites ordered by SortOrder
      then label (same order as `/admin/suites` and the Rent Roll).
- [ ] A **vacant** suite shows no in-place bar, still shows its underwriting
      bar, and the table row reads "Vacant" / "—" for tenant and in-place.
- [ ] A suite with **no `UnderwritingRent`** shows only the in-place bar and
      "—" in the UW column.
- [ ] A suite with **NULL/0 `SquareFeet`** appears in the table with "—" for
      Sq Ft and both PSF columns, and contributes no bar and nothing to the
      average.
- [ ] Spot-check one suite by hand: `EffectiveRent × 12 ÷ SquareFeet` equals
      the "In-place $/SF" value (tooltip and table).
- [ ] The dashed "property avg" line's X position equals
      `suite_rent_psf_avg_display`, and that value matches the Rent Roll
      page's "Avg occupied annual rent PSF" stat tile for the **same property**
      (both are SquareFeet-weighted over occupied suites).
- [ ] "Suites below underwriting" tile counts only occupied suites where both
      PSF values are known and in-place < underwriting.
- [ ] Effective rent respects `LeaseRentSchedule`: for a lease with a
      scheduled step that is active today, the in-place PSF uses the scheduled
      amount, not `Leases.RentAmount`.
- [ ] `Tenants` rows with `TenantStatusName = 'Default'` are excluded (a
      defaulted tenant's suite reads as Vacant).
- [ ] Toggle the DB switch (Test ↔ Prod): the tab reloads via
      `reload_on_db_change` and shows the new DB's suites with no stale rows.
- [ ] Switch away to another tab and back — no console/runtime errors, chart
      re-renders.
- [ ] Chart height grows with suite count (a property with 10+ suites is not
      squashed).

---

## How to Deliver This

Per `CLAUDE.md`: edit `pages/property_financials_analytics.py` in place, no new
versioned file. Its `_vN` siblings were already archived this cycle
(commit `ce1ca75`), so there is **no** archive-cleanup step for this handoff.

1. Apply Steps 1–6 to the live file.
2. Verify against the checklist in the running app (Test DB first).
3. Commit with a descriptive message
   (e.g. "Add Suite Rent PSF tab to Property Financials Analytics").
4. Move this doc to `Completed Handoffs/`.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\pages\property_financials_analytics.py     ← only file changing
  LucidPM\pages\rent_roll.py                         ← schema / matching reference only
  LucidPM\pages\suites.py                            ← UnderwritingRent semantics reference only

Dev app (this handoff): http://localhost:3002   (backend :8002)
Live app:               http://localhost:3000   (backend :8000)
Test DB: green banner | Prod DB: red banner
```

---

*Two state fields, two queries appended to `on_load`, one module-level helper,
five computed vars, one chart component + one table-row helper, one tab button,
one `rx.cond` nesting level. No existing code path changes behavior.*
