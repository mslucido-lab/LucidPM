# LucidoPM — ChatGPT Handoff 44
*Property Financials Analytics — Income Split Chart Correctness Fixes*
*Prepared: 2026-08-09*

---

## What This Is

Two correctness fixes to the Income Split view added in Handoff 43 (`pages/property_financials_analytics.py`), found in code review after that handoff landed. Both are in the same file; neither touches the existing traffic-light Margin % view.

**One file changes. Two isolated fixes: one computed var, one chart prop. No DB, no schema, no other pages.**

---

## Fix 1 — Segments don't always sum to exactly 100

### The Problem

`income_split_chart_data` (lines 238–253) rounds `opex_pct` and `noi_pct` **independently**:

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

Independently rounding two values that should sum to 100 doesn't guarantee they actually do. Example: revenue=100000, opex=33350 → `opex_pct` rounds to 33.4, `noi_pct` (66.65) rounds to 66.7 → displayed total is 100.1, not 100. This contradicts Handoff 43's own validation checklist ("each year's two bar segments... sum to 100").

### The Fix

Derive `noi_pct` as the complement of `opex_pct` **after** `opex_pct` is rounded, instead of rounding it independently from `noi`:

```python
    @rx.var
    def income_split_chart_data(self) -> list[dict]:
        """Opex % and NOI % of revenue by year — stacks to 100%."""
        result = []
        for row in self.chart_data:
            rev = float(row.get("revenue", 0))
            opex = float(row.get("opex", 0))
            opex_pct = round((opex / rev * 100.0), 1) if rev > 0 else 0.0
            noi_pct = round(100.0 - opex_pct, 1) if rev > 0 else 0.0
            result.append({
                "year": row["year"],
                "opex_pct": opex_pct,
                "noi_pct": noi_pct,
            })
        return result
```

`noi` is no longer read in this method (it's unused now — `noi_pct` is defined purely as the complement of `opex_pct`), so the `noi = float(row.get("noi", 0))` line is removed. This guarantees `opex_pct + noi_pct == 100.0` exactly whenever `rev > 0`, by construction — not by coincidence of rounding.

---

## Fix 2 — Loss years get silently clipped off the chart

### The Problem

`income_split_chart()` (lines 590–629) hard-locks the y-axis:

```python
            rx.recharts.y_axis(
                domain=[0, 100],
                unit="%",
            ),
```

In a fiscal year where `TotalOperatingExpenses > TotalRevenue` (a real, plausible case for a struggling property), Fix 1 above means `opex_pct` can now legitimately exceed 100 and `noi_pct` can go negative — that's correct and expected (a loss year genuinely isn't "100% split between two positive shares"). But with the axis locked to `[0, 100]`, that year's bar gets clipped at the top and the negative segment renders off-axis. The chart ends up visually indistinguishable from a normal ~100%-opex year — silently hiding the one thing this chart most needs to show: a property losing money.

### The Fix

**Current** (line 610–613):

```python
            rx.recharts.y_axis(
                domain=[0, 100],
                unit="%",
            ),
```

**Replace** with:

```python
            rx.recharts.y_axis(
                domain=["dataMin - 5", "dataMax + 5"],
                unit="%",
            ),
```

This lets the axis auto-fit to whatever the actual data range is (recharts' documented `dataMin`/`dataMax` domain syntax, with a small padding margin), so a normal year still renders close to the familiar 0–100 range, but a loss year's negative segment and an opex-heavy year's >100 segment are both fully visible instead of clipped.

**Do not** change the `reference_line` at `y=60` (lines 617–623) — it remains meaningful as a horizontal marker regardless of how the axis auto-scales.

---

## Do Not Touch

| What | Why |
|---|---|
| `margin_chart_data` / `margins_chart()` | Traffic-light Margin % view — unaffected by either fix, must stay identical |
| `chart_data` | Shared source of truth — not modified by either fix |
| `margin_view_toggle_button()`, the toggle wiring in the tab render | Not in scope — only the two locations above change |
| The `stack_id="1"` bars themselves in `income_split_chart()` | Only the `y_axis` domain prop changes; the two `rx.recharts.bar` calls are unchanged |
| Any other page file | Not in scope |

---

## Validation Checklist

- [ ] Normal (profitable) year: Opex % + NOI % segments still visually sum to 100, chart looks the same as before these fixes
- [ ] Pick or construct a test year where `TotalOperatingExpenses > TotalRevenue` for some property — confirm the bar now shows an opex segment extending past the old 100% line and/or a visible negative NOI segment, instead of being clipped
- [ ] Confirm `opex_pct + noi_pct == 100.0` exactly for a few sampled years (spot-check the tooltip values, not just visually)
- [ ] Traffic-light Margin % view (the other toggle option) is completely unaffected — same colors, same 60%/45% reference lines, same values
- [ ] No console/runtime errors from the string-based `domain` values on `y_axis`

---

## How to Deliver This

Per `CLAUDE.md`: edit `pages/property_financials_analytics.py` in place, no new versioned file.

1. Apply both fixes directly to the live file.
2. Once verified against the checklist above, commit with a descriptive message (e.g. "Fix income-split chart rounding and axis clipping").
3. This is also the point to finish the cleanup deferred from Handoff 43: `property_financials_analytics_v1.py` through `_v15.py` (including `_v8_1`, `_v14a/b/c/d`) are still sitting in `pages/` — move them into `Archived Versions/` at the repo root (create it if it doesn't exist yet) and commit that move separately, now that this file's changes are fully verified.

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

*One computed var simplified (complement instead of independent rounding), one y-axis prop changed. Nothing else in the file changes.*
