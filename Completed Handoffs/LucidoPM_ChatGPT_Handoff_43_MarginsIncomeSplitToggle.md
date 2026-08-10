# LucidoPM — ChatGPT Handoff 43
*Property Financials Analytics — Margins Tab Income Split Toggle*
*Prepared: 2026-08-09*

---

## What This Is

Add a second view inside the existing **Margins** tab of the Property Financials Analytics page: a 100%-stacked bar chart showing Opex % of revenue and NOI % of revenue per fiscal year, toggled against the current traffic-light NOI Margin % chart. The existing chart is not modified — a small toggle control switches between the two.

**One file changes. No DB, no schema, no other pages. The existing traffic-light chart's code, coloring, and behavior are untouched.**

---

## The Current State

File: `pages/property_financials_analytics.py`

The `PropertyFinancialsAnalyticsState` class (line 26) already has a computed var `chart_data` (ends ~line 205) producing, per fiscal year: `revenue`, `opex`, `noi`, `valuation`.

`margin_chart_data` (lines 207–232) derives NOI margin % per year from `chart_data` and pre-computes threshold colors:

```python
    @rx.var
    def margin_chart_data(self) -> list[dict]:
        """NOI margin % by year with pre-computed threshold display colors."""
        result = []
        for row in self.chart_data:
            rev = float(row.get("revenue", 0))
            noi = float(row.get("noi", 0))
            margin = round((noi / rev * 100.0), 1) if rev > 0 else 0.0

            if margin >= 60:
                fill = "rgba(42, 163, 122, 0.22)"
                stroke = COMPARE_WALNUT_FILL
            elif margin >= 45:
                fill = "rgba(196, 122, 22, 0.22)"
                stroke = COMPARE_EULESS_FILL
            else:
                fill = "rgba(244, 166, 166, 0.40)"
                stroke = CHART_MARGIN_RED

            result.append({
                "year": row["year"],
                "margin": margin,
                "fill": fill,
                "stroke": stroke,
            })
        return result
```

`margins_chart()` (lines 515–552) renders that as a single bar per year, colored per-bar via `rx.foreach` + `margin_bar_cell`, with a y-axis domain `[0, 100]` and two reference lines at 60% and 45%. **This function does not change.**

The tab bar (lines 774–778) and the render `rx.cond` chain (lines 783–799) currently read:

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
                            margins_chart(),
                            rx.cond(
                                PropertyFinancialsAnalyticsState.active_tab == "valuation",
                                valuation_chart(),
                                compare_chart(),
                            ),
                        ),
                    ),
                ),
```

Color constants already defined at the top of the file (lines 10–23) — reuse these, do not invent new colors: `CHART_OPEX_FILL`, `CHART_OPEX_STROKE`, `CHART_NOI_STROKE`, `COMPARE_WALNUT_FILL` (the existing "good margin" green, used for the ≥60% band above).

---

## The Fix

### Step 1 — Add the toggle state var and setter

In `PropertyFinancialsAnalyticsState` (line 26), immediately after `compare_metric: str = "all"` (line 31), add:

```python
    margin_view: str = "margin_pct"   # "margin_pct" | "income_split"
```

Immediately after `set_compare_period()` (line 45–46), add:

```python
    def set_margin_view(self, v: str):
        self.margin_view = v
```

### Step 2 — Add the `income_split_chart_data` computed var

Immediately after `margin_chart_data` (after line 232, before `compare_year_options` at line 234), add:

```python
    @rx.var
    def income_split_chart_data(self) -> list[dict]:
        """Opex % and NOI % of revenue by year — stacks to 100%."""
        result = []
        for row in self.chart_data:
            rev = float(row.get("revenue", 0))
            opex = float(row.get("opex", 0))
            noi = float(row.get("noi", 0))
            opex_pct = round((opex / rev * 100.0), 1) if rev > 0 else 0.0
            noi_pct = round((noi / rev * 100.0), 1) if rev > 0 else 0.0
            result.append({
                "year": row["year"],
                "opex_pct": opex_pct,
                "noi_pct": noi_pct,
            })
        return result
```

Do not modify `margin_chart_data` itself — this is a new, separate computed var reading from the same `chart_data` source.

### Step 3 — Add the toggle button helper and the new chart component

Immediately after `margins_chart()` (after line 552, before `valuation_chart()` at line 555), add:

```python
def margin_view_toggle_button(label: str, view_id: str) -> rx.Component:
    return rx.button(
        label,
        on_click=PropertyFinancialsAnalyticsState.set_margin_view(view_id),
        variant=rx.cond(
            PropertyFinancialsAnalyticsState.margin_view == view_id,
            "solid",
            "outline",
        ),
        color_scheme="blue",
        size="1",
    )


def income_split_chart() -> rx.Component:
    return chart_container(
        rx.recharts.bar_chart(
            rx.recharts.bar(
                data_key="opex_pct",
                name="Opex % of Revenue",
                fill=CHART_OPEX_FILL,
                stroke=CHART_OPEX_STROKE,
                stroke_width=1.0,
                stack_id="1",
            ),
            rx.recharts.bar(
                data_key="noi_pct",
                name="NOI % of Revenue",
                fill="rgba(42, 163, 122, 0.35)",
                stroke=COMPARE_WALNUT_FILL,
                stroke_width=1.0,
                stack_id="1",
            ),
            rx.recharts.x_axis(data_key="year"),
            rx.recharts.y_axis(
                domain=[0, 100],
                unit="%",
            ),
            rx.recharts.cartesian_grid(stroke_dasharray="3 3", vertical=False),
            rx.recharts.graphing_tooltip(),
            rx.recharts.legend(),
            rx.recharts.reference_line(
                y=60,
                stroke="#1F4E79",
                stroke_dasharray="4 2",
                stroke_width=2.0,
                label="60%",
            ),
            data=PropertyFinancialsAnalyticsState.income_split_chart_data,
            width="100%",
            height=320,
            margin={"top": 10, "right": 30, "left": 10, "bottom": 0},
        )
    )
```

**Notes:**
- Both bars share `stack_id="1"` — this is what makes them stack instead of sit side-by-side.
- `CHART_OPEX_FILL` / `CHART_OPEX_STROKE` are the same constants `trend_chart()` and `summary_chart()` use for Opex, for visual consistency across tabs.
- The NOI segment reuses the ≥60% green (`COMPARE_WALNUT_FILL`, fill `rgba(42, 163, 122, ...)`) from `margin_chart_data`'s threshold coloring, for the same reason.
- Only the 60% reference line is kept — the 45% amber line from `margins_chart()` is intentionally **not** carried over; it was a two-way threshold split that doesn't map cleanly onto a stacked view.

### Step 4 — Wire the toggle into the Margins tab render

**Current** (lines 789–791, inside the `rx.cond` chain):

```python
                        rx.cond(
                            PropertyFinancialsAnalyticsState.active_tab == "margins",
                            margins_chart(),
```

**Replace** those three lines with:

```python
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
```

Everything else in the `rx.cond` chain (the `valuation` / `compare` branches and all their closing parens) is unchanged — only the body of the `"margins"` branch changes, from a single `margins_chart()` call to the `rx.vstack(...)` above.

---

## Do Not Touch

| What | Why |
|---|---|
| `margin_chart_data` | Must keep producing identical output — traffic-light view is unchanged |
| `margins_chart()` | Must render pixel-identical to today when `margin_view == "margin_pct"` |
| `chart_data` | Shared source of truth for both views — do not alter its shape |
| `active_tab` / `tab_button()` / the outer tab bar | Tab-level navigation is unchanged; this is a sub-toggle inside one tab only |
| `summary_chart()`, `trend_chart()`, `valuation_chart()`, `compare_chart()` | Not in scope |
| Any other page file | Not in scope |

---

## Validation Checklist

- [ ] Margins tab opens by default to the existing traffic-light Margin % view (`margin_view` defaults to `"margin_pct"`)
- [ ] Traffic-light chart renders exactly as before — same bar colors, same 60%/45% reference lines
- [ ] Toggle to "Income Split" — each year's two bar segments visually stack and their values sum to 100
- [ ] Income Split values match: `opex_pct = opex / revenue * 100`, `noi_pct = noi / revenue * 100`, cross-checked against a year or two on the Trend tab
- [ ] Toggle back to "Margin %" — chart still renders correctly, no leftover state from the other view
- [ ] Switching to a different top-level tab and back to Margins preserves whichever `margin_view` was last selected (state var doesn't reset unexpectedly)
- [ ] No console/runtime errors from the new `rx.recharts.bar_chart` (stacked bars, two series)

---

## How to Deliver This

Per the project's current convention (see `CLAUDE.md`), edit the live file in place — **do not** create a new versioned copy.

1. Apply the changes above directly to `pages/property_financials_analytics.py`. The diffs in this handoff are written against that file's current content (which is identical to the old `property_financials_analytics_v15.py` copy still sitting in `pages/` from before this convention changed).
2. Once implemented and verified against the checklist above, this change gets committed to git with a descriptive message (e.g. "Add income-split toggle to Margins tab").
3. **Then**, as the cleanup step for this file specifically: move `property_financials_analytics_v1.py` through `property_financials_analytics_v15.py` (all lettered variants included — `v8_1`, `v14a/b/c/d`) out of `pages/` and into `Archived Versions/` at the repo root, and commit that move separately. Do not touch versioned files belonging to any other page in this pass.

---

## File Locations

```
C:\Dell Inspirion\TenantCRM\LucidPM_Reflex - ChatGPT\LucidPM_Reflex\
  pages\property_financials_analytics.py     ← only file changing

Frontend: http://localhost:3000
Backend:  http://localhost:8000
Test DB: green banner | Prod DB: red banner
```

---

*One state var, one setter, one computed var, one chart component, one toggle helper added. One `rx.cond` branch rewired. Nothing else in the file changes.*
