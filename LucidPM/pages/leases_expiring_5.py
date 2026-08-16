"""
Leases Expiring page — upcoming lease expirations and rent escalation anniversaries.
Route: /leases-expiring

Mirrors the dashboard version from the Streamlit app:
  - Horizon window dropdown (30 / 60 / 90 / 180 / 365 days)
  - Expiration events: Fixed Term / Multi-year / Option Term leases ending in window
    (suppressed when a successor lease exists for same tenant/suite)
  - Escalation events: next anniversary of every active lease inside the window
    (uses scheduled rent if available, falls back to recommended 5%/$50 minimum)
  - Columns: EventDate, EventType, TenantName, PropertyName, RentAmount,
             RecommendedRent, RecommendedIncrease, NeedsSchedule
  - CSV download
"""

import datetime
import math
from typing import Optional

import reflex as rx

from LucidPM_Reflex.state import AppState, run_query, BRAND_PRIMARY, BRAND_DARK
from LucidPM_Reflex.components.sidebar import page_shell


# ── Pure calculation helpers (ported from Streamlit app) ──────────────────────

def _to_date(val) -> Optional[datetime.date]:
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    try:
        import pandas as pd
        d = pd.to_datetime(val, errors="coerce")
        if d is None or str(d) == "NaT":
            return None
        return d.date()
    except Exception:
        return None


def _safe_replace_year(d: datetime.date, year: int) -> datetime.date:
    try:
        return d.replace(year=year)
    except ValueError:
        return datetime.date(year, 2, 28)


def _next_anniversary(start: datetime.date, ref: datetime.date) -> datetime.date:
    candidate = _safe_replace_year(start, ref.year)
    if candidate < ref:
        candidate = _safe_replace_year(start, ref.year + 1)
    return candidate


def _rent_as_of(sched: list[dict], lease_id: int, event_date: datetime.date):
    """Return (rent_float, needs_schedule_bool) for a lease as of event_date."""
    rows = [r for r in sched if r.get("LeaseID") and int(r["LeaseID"]) == lease_id]
    if not rows:
        return None, True

    active = []
    for r in rows:
        s = _to_date(r.get("EffectiveStartDate"))
        e = _to_date(r.get("EffectiveEndDate"))
        if s is not None and s <= event_date and (e is None or e >= event_date):
            active.append((s, r))

    if not active:
        return None, True

    active.sort(key=lambda x: x[0], reverse=True)
    rent = active[0][1].get("RentAmount")
    try:
        if rent is None or (isinstance(rent, float) and math.isnan(rent)):
            return None, True
        return float(rent), False
    except Exception:
        return None, True


def _rent_on_date(sched: list[dict], lease_id: int, target: datetime.date) -> Optional[float]:
    """Rent from a schedule row that starts exactly on target (for explicit step detection)."""
    rows = [r for r in sched if r.get("LeaseID") and int(r["LeaseID"]) == lease_id]
    exact = [r for r in rows if _to_date(r.get("EffectiveStartDate")) == target]
    if not exact:
        return None
    rent = exact[0].get("RentAmount")
    try:
        if rent is None or (isinstance(rent, float) and math.isnan(rent)):
            return None
        return float(rent)
    except Exception:
        return None


def _successor_starting_rent(
    leases: list[dict],
    sched: list[dict],
    lease_id: int,
    ann: datetime.date,
) -> Optional[float]:
    """
    Find a successor lease for the same tenant+suite starting on ann,
    and return its first scheduled rent. Used to populate Rec. Rent
    when the current lease's schedule has no row on the anniversary date.
    """
    this_lease = next((l for l in leases if int(l["LeaseID"]) == lease_id), None)
    if not this_lease:
        return None
    tenant_id = this_lease.get("TenantID")
    suite_id  = this_lease.get("SuiteID")
    for l in leases:
        if (int(l["LeaseID"]) != lease_id
                and l.get("TenantID") == tenant_id
                and l.get("SuiteID") == suite_id):
            start = _to_date(l.get("LeaseStart"))
            if start is not None and start == ann:
                rent = _rent_on_date(sched, int(l["LeaseID"]), start)
                if rent is not None:
                    return rent
    return None


def _recommended_rent(current: Optional[float], pct: float = 0.05, min_inc: float = 50.0, round_to: int = 5):
    """Return (recommended_rent, recommended_increase). 5% or $50 min, rounded to $5."""
    if current is None:
        return None, None
    try:
        r = float(current)
        if math.isnan(r) or r <= 0:
            return None, None
    except Exception:
        return None, None

    raw = max(r * (1.0 + pct), r + min_inc)
    rounded = float(round_to * round(raw / round_to))
    if rounded < r + min_inc:
        rounded = float(round_to * math.ceil((r + min_inc) / round_to))
    return rounded, rounded - r


def _has_successor(row: dict, all_leases: list[dict], grace_days: int = 7) -> bool:
    """True if another lease for the same tenant starts within grace_days of this lease ending."""
    current_end = _to_date(row.get("LeaseEnd"))
    if current_end is None:
        return False
    try:
        current_id  = int(row.get("LeaseID"))
        tenant_id   = int(row.get("TenantID"))
    except Exception:
        return False

    latest_start = current_end + datetime.timedelta(days=grace_days)
    for other in all_leases:
        try:
            if int(other.get("LeaseID")) == current_id:
                continue
            if int(other.get("TenantID")) != tenant_id:
                continue
            other_start = _to_date(other.get("LeaseStart"))
            if other_start and current_end <= other_start <= latest_start:
                return True
        except Exception:
            continue
    return False


def _fmt_currency(val) -> str:
    try:
        return f"${float(val):,.2f}"
    except Exception:
        return ""


def _build_events(
    leases: list[dict],
    sched: list[dict],
    prop_map: dict,
    tenant_map: dict,
    term_type_map: dict,
    today: datetime.date,
    horizon: datetime.date,
) -> list[dict]:
    """Core event-building logic — matches Streamlit dashboard implementation."""
    EXPIRATION_TERMS = {"fixed term", "multi-year", "multi year", "option term"}
    events = []

    for r in leases:
        tenant_id     = r.get("TenantID")
        prop_id       = r.get("PropertyID")
        term_type_id  = r.get("LeaseTermTypeID")
        term_name     = str(term_type_map.get(term_type_id) or "").strip().lower().replace("–", "-")
        lease_start   = _to_date(r.get("LeaseStart"))
        lease_end     = _to_date(r.get("LeaseEnd"))
        lease_id      = r.get("LeaseID")
        rent_amt      = r.get("RentAmount")
        try:
            rent_amt = float(rent_amt) if rent_amt is not None else None
        except Exception:
            rent_amt = None

        t_name = str(tenant_map.get(tenant_id) or "").strip()
        p_name = str(prop_map.get(prop_id) or "").strip()

        # ── Expiration event ──────────────────────────────────────────────
        if lease_end is not None and today <= lease_end <= horizon:
            if term_name in EXPIRATION_TERMS:
                if not _has_successor(r, leases):
                    rent_use, needs_sched = _rent_as_of(sched, int(lease_id), lease_end)
                    if rent_use is None:
                        rent_use = rent_amt
                    rec_rent, rec_inc = _recommended_rent(rent_use)
                    events.append({
                        "EventDate":          lease_end,
                        "EventType":          "Expiration",
                        "TenantName":         t_name,
                        "PropertyName":       p_name,
                        "RentAmount":         rent_use,
                        "RecommendedRent":    rec_rent,
                        "RecommendedIncrease": rec_inc,
                        "NeedsSchedule":      needs_sched,
                    })

        # ── Escalation / anniversary event ────────────────────────────────
        # Skip if this lease is already expiring within the horizon window
        # (expiration event already covers the tenant — escalation is redundant)
        lease_expiring_in_window = (
            lease_end is not None and today <= lease_end <= horizon
        )

        if lease_start is not None and not lease_expiring_in_window:
            try:
                if lease_end is not None and lease_end < today:
                    pass  # past lease — skip
                else:
                    ann = _next_anniversary(lease_start, today)
                    if today <= ann <= horizon:
                        if lease_end is None or ann < lease_end:
                            lid = int(lease_id)
                            current_rent, _ = _rent_as_of(sched, lid, today)
                            if current_rent is None:
                                current_rent = rent_amt

                            scheduled_new = _rent_on_date(sched, lid, ann)
                            if scheduled_new is None:
                                scheduled_new = _successor_starting_rent(leases, sched, lid, ann)
                            rec_rent, rec_inc = None, None

                            if scheduled_new is not None and current_rent is not None:
                                try:
                                    rec_rent = float(scheduled_new)
                                    rec_inc  = float(rec_rent - float(current_rent))
                                except Exception:
                                    pass

                            if rec_rent is None:
                                rec_rent, rec_inc = _recommended_rent(current_rent)

                            _, needs_sched_ann = _rent_as_of(sched, lid, ann)

                            events.append({
                                "EventDate":           ann,
                                "EventType":           "Escalation",
                                "TenantName":          t_name,
                                "PropertyName":        p_name,
                                "RentAmount":          current_rent,
                                "RecommendedRent":     rec_rent,
                                "RecommendedIncrease": rec_inc,
                                "NeedsSchedule":       needs_sched_ann,
                            })
            except Exception:
                pass

    # Sort: Expiration before Escalation, then by date
    prio = {"Expiration": 0, "Escalation": 1}
    events.sort(key=lambda e: (prio.get(e["EventType"], 9), e["EventDate"]))
    return events


# ── Data model ────────────────────────────────────────────────────────────────

class LeaseEventRow(rx.Base):
    event_date:           str = ""
    event_type:           str = ""
    tenant_name:          str = ""
    property_name:        str = ""
    rent_amount:          str = ""
    recommended_rent:     str = ""
    recommended_increase: str = ""
    needs_schedule:       str = ""
    is_expiration:        bool = False


# ── State ─────────────────────────────────────────────────────────────────────

class LeasesExpiringState(AppState):

    horizon_days:  int = 60
    events:        list[LeaseEventRow] = []
    loading:       bool = False
    error_msg:     str = ""
    event_count:   int = 0

    def on_load(self):
        self.error_msg = ""
        self.load_events()

    def reload_on_db_change(self):
        self.events = []
        self.error_msg = ""
        self.load_events()

    def set_horizon(self, v: str):
        try:
            self.horizon_days = int(v)
        except Exception:
            pass
        self.load_events()

    def load_events(self):
        self.loading = True
        self.error_msg = ""
        self.events = []
        self.event_count = 0
        db = self.db

        try:
            today   = datetime.date.today()
            horizon = today + datetime.timedelta(days=self.horizon_days)

            # Properties
            prop_rows = run_query("SELECT PropertyID, PropertyName FROM Properties", db=db)
            prop_map  = {int(r["PropertyID"]): str(r["PropertyName"]) for r in prop_rows}

            # Tenants (active + default)
            tenant_rows = run_query(
                "SELECT t.TenantID, t.TenantName FROM Tenants t "
                "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
                "WHERE ISNULL(ts.TenantStatusName, '') IN ('Active', 'Default', '')",
                db=db,
            )
            tenant_map = {int(r["TenantID"]): str(r["TenantName"]) for r in tenant_rows}

            # Lease term types
            term_rows = run_query(
                "SELECT LeaseTermTypeID, LeaseTermTypeName FROM LeaseTermTypes",
                db=db,
            )
            term_map = {int(r["LeaseTermTypeID"]): str(r["LeaseTermTypeName"]) for r in term_rows}

            # Leases for active/default tenants
            leases = run_query(
                "SELECT l.LeaseID, l.TenantID, l.PropertyID, l.SuiteID, "
                "l.LeaseTermTypeID, l.LeaseStart, l.LeaseEnd, l.RentAmount, "
                "t.Suite AS TenantSuite, t.SuiteID AS TenantSuiteID "
                "FROM Leases l "
                "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
                "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
                "WHERE ISNULL(ts.TenantStatusName, '') IN ('Active', 'Default', '')",
                db=db,
            )

            # Rent schedules for those leases
            lease_ids = [int(r["LeaseID"]) for r in leases if r.get("LeaseID")]
            sched = []
            if lease_ids:
                # Query in batches of 100 to avoid parameter limits
                for i in range(0, len(lease_ids), 100):
                    batch = lease_ids[i:i+100]
                    placeholders = ",".join(["?"] * len(batch))
                    sched += run_query(
                        f"SELECT LeaseID, EffectiveStartDate, EffectiveEndDate, RentAmount "
                        f"FROM LeaseRentSchedule WHERE LeaseID IN ({placeholders})",
                        tuple(batch), db=db,
                    )

            raw_events = _build_events(leases, sched, prop_map, tenant_map, term_map, today, horizon)

            self.events = [
                LeaseEventRow(
                    event_date           = r["EventDate"].strftime("%m/%d/%Y"),
                    event_type           = r["EventType"],
                    tenant_name          = r["TenantName"],
                    property_name        = r["PropertyName"],
                    rent_amount          = _fmt_currency(r["RentAmount"]),
                    recommended_rent     = _fmt_currency(r["RecommendedRent"]),
                    recommended_increase = _fmt_currency(r["RecommendedIncrease"]),
                    needs_schedule       = "Yes" if r["NeedsSchedule"] else "",
                    is_expiration        = r["EventType"] == "Expiration",
                )
                for r in raw_events
            ]
            self.event_count = len(self.events)

        except Exception as ex:
            self.error_msg = f"Error loading events: {ex}"
        finally:
            self.loading = False

    def download_csv(self):
        import base64
        if not self.events:
            return
        headers = ["EventDate", "EventType", "TenantName", "PropertyName",
                   "RentAmount", "RecommendedRent", "RecommendedIncrease", "NeedsSchedule"]
        lines = [",".join(f'"{h}"' for h in headers)]
        for e in self.events:
            vals = [e.event_date, e.event_type, e.tenant_name, e.property_name,
                    e.rent_amount, e.recommended_rent, e.recommended_increase, e.needs_schedule]
            lines.append(",".join('"' + str(v).replace('"', '""') + '"' for v in vals))
        b64 = base64.b64encode("\n".join(lines).encode()).decode()
        return rx.download(
            data=f"data:text/csv;base64,{b64}",
            filename=f"leases_expiring_{self.horizon_days}d.csv",
        )

    @rx.var
    def horizon_label(self) -> str:
        return f"Next {self.horizon_days} days"

    @rx.var
    def pdf_url(self) -> str:
        return (
            f"http://localhost:8000/api/leases-expiring-pdf"
            f"?horizon={self.horizon_days}&db={self.db}"
        )


# ── UI ────────────────────────────────────────────────────────────────────────

HORIZON_OPTIONS = ["30", "60", "90", "180", "365"]

EVENT_TYPE_COLOR = {
    "Expiration": ("#fce4ec", "#b71c1c"),
    "Escalation": ("#e8f5e9", "#1b5e20"),
}


def _event_row(row: LeaseEventRow) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.text(row.event_date, size="2", weight="bold", color="#333")),
        rx.table.cell(
            rx.cond(
                row.is_expiration,
                rx.box(
                    rx.text(row.event_type, size="1", weight="bold",
                            style={"color": "#b71c1c"}),
                    style={"background": "#fce4ec", "border_radius": "999px",
                           "padding": "2px 10px", "display": "inline-block"},
                ),
                rx.box(
                    rx.text(row.event_type, size="1", weight="bold",
                            style={"color": "#1b5e20"}),
                    style={"background": "#e8f5e9", "border_radius": "999px",
                           "padding": "2px 10px", "display": "inline-block"},
                ),
            )
        ),
        rx.table.cell(rx.text(row.tenant_name, size="2")),
        rx.table.cell(rx.text(row.property_name, size="2", color="#555")),
        rx.table.cell(rx.text(row.rent_amount, size="2", color=BRAND_DARK, weight="bold")),
        rx.table.cell(rx.text(row.recommended_rent, size="2", color="#2e7d32", weight="bold")),
        rx.table.cell(rx.text(row.recommended_increase, size="2", color="#1565c0")),
        rx.table.cell(
            rx.cond(
                row.needs_schedule == "Yes",
                rx.badge("Needs schedule", color_scheme="orange", variant="soft"),
                rx.text(""),
            )
        ),
        _hover={"background": "#f8fafc"},
        vertical_align="middle",
    )


def _leases_expiring_content() -> rx.Component:
    return rx.vstack(
        # Header
        rx.hstack(
            rx.heading("Leases Expiring", size="5", color=BRAND_DARK),
            rx.spacer(),
            rx.cond(
                LeasesExpiringState.event_count > 0,
                rx.hstack(
                    rx.button(
                        "⬇ CSV",
                        on_click=LeasesExpiringState.download_csv,
                        variant="outline", color_scheme="blue", size="2",
                    ),
                    rx.link(
                        rx.button(
                            "⬇ PDF",
                            variant="outline", color_scheme="blue", size="2",
                        ),
                        href=LeasesExpiringState.pdf_url,
                        is_external=True,
                    ),
                    spacing="2",
                ),
            ),
            align="center", width="100%",
        ),

        # Error
        rx.cond(
            LeasesExpiringState.error_msg != "",
            rx.callout(LeasesExpiringState.error_msg, icon="triangle_alert",
                       color_scheme="red", width="100%"),
        ),

        # Controls
        rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text("Look ahead window (days)", size="1", color="#666"),
                    rx.select(
                        HORIZON_OPTIONS,
                        value=LeasesExpiringState.horizon_days.to_string(),
                        on_change=LeasesExpiringState.set_horizon,
                        size="2",
                        width="160px",
                    ),
                    spacing="1", align="start",
                ),
                rx.cond(
                    LeasesExpiringState.loading,
                    rx.spinner(size="2"),
                    rx.fragment(),
                ),
                spacing="4", align="end",
            ),
            background="#F8FAFC",
            border="1px solid #E2E8F0",
            border_radius="8px",
            padding="16px",
            width="100%",
        ),

        # Summary
        rx.cond(
            LeasesExpiringState.event_count > 0,
            rx.hstack(
                rx.heading(LeasesExpiringState.horizon_label, size="4", color=BRAND_DARK),
                rx.badge(
                    LeasesExpiringState.event_count.to_string() + " events",
                    color_scheme="blue", variant="soft",
                ),
                spacing="3", align="center",
            ),
        ),

        # Legend
        rx.hstack(
            rx.hstack(
                rx.box(style={"width": "12px", "height": "12px", "border_radius": "3px",
                              "background": "#fce4ec", "border": "1px solid #b71c1c"}),
                rx.text("Expiration — lease ending", size="1", color="#666"),
                spacing="2", align="center",
            ),
            rx.hstack(
                rx.box(style={"width": "12px", "height": "12px", "border_radius": "3px",
                              "background": "#e8f5e9", "border": "1px solid #1b5e20"}),
                rx.text("Escalation — rent anniversary", size="1", color="#666"),
                spacing="2", align="center",
            ),
            rx.hstack(
                rx.badge("Needs schedule", color_scheme="orange", variant="soft"),
                rx.text("— no effective rent schedule row found; using header rent", size="1", color="#666"),
                spacing="2", align="center",
            ),
            spacing="5", wrap="wrap",
        ),

        # Table
        rx.cond(
            LeasesExpiringState.event_count > 0,
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            *[
                                rx.table.column_header_cell(
                                    h,
                                    style={"font_size": "11px", "font_weight": "700",
                                           "color": BRAND_PRIMARY, "padding": "8px 10px",
                                           "white_space": "nowrap"},
                                )
                                for h in ["Date", "Type", "Tenant", "Property",
                                          "Current Rent", "Rec. Rent", "Rec. Increase", ""]
                            ]
                        )
                    ),
                    rx.table.body(
                        rx.foreach(LeasesExpiringState.events, _event_row)
                    ),
                    width="100%",
                    variant="surface",
                ),
                overflow_x="auto",
                width="100%",
                border="1px solid #E2E8F0",
                border_radius="8px",
            ),
            rx.cond(
                ~LeasesExpiringState.loading,
                rx.callout(
                    "No lease expirations or anniversaries in the selected window.",
                    icon="info", color_scheme="gray",
                ),
            ),
        ),

        spacing="4",
        width="100%",
        align_items="start",
        padding="24px",
    )


def leases_expiring_page() -> rx.Component:
    return page_shell(_leases_expiring_content(), current_path="/leases-expiring")
