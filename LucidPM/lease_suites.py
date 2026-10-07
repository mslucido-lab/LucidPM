"""Multi-suite lease helpers (Handoff 73).

Leases.SuiteID remains the primary-suite compatibility column.  Some legacy
report queries alias that value as ``LeaseSuiteID``; it is unrelated to this
module's dbo.LeaseSuites.LeaseSuiteID primary key.
"""

import datetime
from contextlib import contextmanager
from decimal import Decimal, ROUND_HALF_UP

from LucidPM.state import get_conn, run_query


_BATCH = 100
_PCT_Q = Decimal("0.000001")
_CENT = Decimal("0.01")


class LeaseSuitesError(ValueError):
    """A LeaseSuites write violated an invariant. Message is user-facing."""


def load_lease_suites(lease_ids, db: str) -> dict[int, list[dict]]:
    """Return linked suites by lease, primary first then property sort order."""
    ids = sorted({int(lease_id) for lease_id in lease_ids if lease_id is not None})
    result: dict[int, list[dict]] = {}
    for start in range(0, len(ids), _BATCH):
        batch = ids[start:start + _BATCH]
        placeholders = ",".join("?" for _ in batch)
        rows = run_query(
            "SELECT ls.LeaseID, ls.SuiteID, ls.IsPrimary, ls.RentAllocationPct, "
            "ps.SuiteLabel, ps.SquareFeet, ps.SortOrder, ps.PropertyID, ps.IsActive, "
            "ps.UnderwritingRent, ISNULL(ps.SuitePremisesDescription,'') AS SuitePremisesDescription, "
            "ISNULL(ps.SuiteLegalDescription,'') AS SuiteLegalDescription "
            "FROM LeaseSuites ls INNER JOIN PropertySuites ps ON ps.SuiteID = ls.SuiteID "
            f"WHERE ls.LeaseID IN ({placeholders}) "
            "ORDER BY ls.LeaseID, ls.IsPrimary DESC, ps.SortOrder, ps.SuiteLabel",
            tuple(batch), db=db,
        )
        for row in rows:
            result.setdefault(int(row["LeaseID"]), []).append(row)
    return result


def suite_ids_for(lease: dict, lease_suites: dict[int, list[dict]]) -> set[int]:
    """Return all suites covered by a lease, including legacy primary fallback."""
    rows = lease_suites.get(int(lease["LeaseID"]))
    if rows:
        return {int(row["SuiteID"]) for row in rows}
    for key in ("SuiteID", "LeaseSuiteID"):
        if lease.get(key) is not None:
            return {int(lease[key])}
    return set()


def allocation_pct(lease_id: int, suite_id: int,
                   lease_suites: dict[int, list[dict]]) -> float:
    for row in lease_suites.get(int(lease_id), []):
        if int(row["SuiteID"]) == int(suite_id):
            return float(row["RentAllocationPct"])
    return 100.0


def match_suite_to_lease(suite_id: int, prop_id: int, suite_label: str,
                         pool: list[dict], lease_suites: dict[int, list[dict]]) -> dict | None:
    for lease in pool:
        if suite_id in suite_ids_for(lease, lease_suites):
            return lease
    for lease in pool:
        tenant_suite_id = lease.get("TenantSuiteID")
        if (tenant_suite_id is not None and int(tenant_suite_id) == suite_id
                and int(lease.get("PropertyID", -1)) == prop_id):
            return lease
    for lease in pool:
        if (int(lease.get("PropertyID", -1)) == prop_id
                and str(lease.get("TenantSuite") or "").strip().upper() == suite_label.upper()):
            return lease
    return None


def _to_date(value) -> datetime.date | None:
    """Normalize a pyodbc datetime/date value for date-only lease comparisons."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return None


def effective_end(lease: dict) -> datetime.date | None:
    end = _to_date(lease.get("LeaseEnd"))
    if str(lease.get("LeaseStatus") or "").strip() == "Terminated":
        terminated = _to_date(lease.get("LeaseTerminationDate"))
        if terminated is not None:
            end = terminated if end is None else min(end, terminated)
    return end


def join_labels(labels: list[str], conjunction: str = "and") -> str:
    labels = [str(label).strip() for label in labels if str(label).strip()]
    if len(labels) < 2:
        return labels[0] if labels else ""
    return f"{', '.join(labels[:-1])} {conjunction} {labels[-1]}"


def report_label(labels: list[str]) -> str:
    return " / ".join(str(label).strip() for label in labels if str(label).strip())


def _s(value) -> str:
    return str(value or "").strip()


def combine_descriptions(premises: list[str], full: list[str]) -> str:
    """Combine suite descriptions, factoring out a shared trailing address."""
    pairs = [(_s(premise), _s(text)) for premise, text in zip(premises, full)]
    if pairs and all(premise and text.startswith(premise) for premise, text in pairs):
        tails = {text[len(premise):] for premise, text in pairs}
        if len(tails) == 1:
            return join_labels([premise for premise, _ in pairs]) + tails.pop()
    texts = [text for _, text in pairs if text]
    return "; and ".join(texts) if len(texts) > 1 else (texts[0] if texts else "")


def pcts_from_amounts(amounts: list[Decimal]) -> list[Decimal]:
    if not amounts:
        return []
    total = sum(amounts)
    if total <= 0:
        amounts, total = [Decimal(1)] * len(amounts), Decimal(len(amounts))
    pcts = [(amount * 100 / total).quantize(_PCT_Q, rounding=ROUND_HALF_UP)
            for amount in amounts]
    pcts[0] += Decimal(100) - sum(pcts)
    return pcts


def split_amount(total: Decimal, pcts: list[Decimal]) -> list[Decimal]:
    if not pcts:
        return []
    parts = [(total * pct / 100).quantize(_CENT, rounding=ROUND_HALF_UP) for pct in pcts]
    parts[0] += total.quantize(_CENT) - sum(parts)
    return parts


def sf_amounts(total: Decimal, suites: list[dict]) -> list[Decimal]:
    try:
        square_feet = [Decimal(str(suite.get("SquareFeet"))) for suite in suites]
        if any(value <= 0 for value in square_feet):
            raise ValueError
    except (ArithmeticError, TypeError, ValueError):
        square_feet = [Decimal(1)] * len(suites)
    return split_amount(total, pcts_from_amounts(square_feet))


def is_superseded_holdover(lease: dict, all_leases: list[dict],
                           lease_suites: dict[int, list[dict]]) -> bool:
    """Whether a later lease for this tenant replaces this holdover's suite(s)."""
    tenant_id = lease.get("TenantID")
    start = _to_date(lease.get("LeaseStart"))
    if tenant_id is None or start is None:
        return False
    lease_id = int(lease["LeaseID"])
    lease_suite_ids = suite_ids_for(lease, lease_suites)
    legacy_suite_id = lease.get("TenantSuiteID")
    for other in all_leases:
        if int(other.get("LeaseID") or 0) == lease_id or other.get("TenantID") != tenant_id:
            continue
        other_start = _to_date(other.get("LeaseStart"))
        if other_start is None or other_start <= start:
            continue
        other_suite_ids = suite_ids_for(other, lease_suites)
        if lease_suite_ids and other_suite_ids and lease_suite_ids & other_suite_ids:
            return True
        if (not lease_suite_ids and not other_suite_ids and legacy_suite_id is not None
                and other.get("TenantSuiteID") is not None
                and int(legacy_suite_id) == int(other["TenantSuiteID"])):
            return True
    return False


def build_rent_roll(as_of: datetime.date, prop_filter: str, basis: str, db: str) -> dict:
    """Build the schedule-aware, termination-aware Rent Roll shared by page and PDF."""
    suite_sql = (
        "SELECT ps.SuiteID, ps.PropertyID, ps.SuiteLabel, ps.SquareFeet, "
        "ps.SuiteUseType, ps.UnderwritingRent, p.PropertyName "
        "FROM PropertySuites ps "
        "LEFT JOIN Properties p ON ps.PropertyID = p.PropertyID "
        "WHERE ps.IsActive = 1 "
    )
    suite_params = []
    if prop_filter != "All":
        suite_sql += "AND p.PropertyName = ? "
        suite_params.append(prop_filter)
    suite_sql += "ORDER BY p.PropertyName, ps.SortOrder, ps.SuiteLabel"
    suites = run_query(suite_sql, tuple(suite_params), db=db)

    lease_sql = (
        "SELECT l.LeaseID, l.TenantID, l.PropertyID, l.SuiteID, "
        "l.LeaseStart, l.LeaseEnd, l.LeaseStatus, l.LeaseTerminationDate, l.RentAmount, "
        "COALESCE(lrs.RentAmount, l.RentAmount) AS EffectiveRent, "
        "ltt.LeaseTermTypeName, t.TenantName, t.Suite AS TenantSuite, "
        "t.SuiteID AS TenantSuiteID, ts.TenantStatusName "
        "FROM Leases l "
        "INNER JOIN Tenants t ON l.TenantID = t.TenantID "
        "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
        "LEFT JOIN TenantStatuses ts ON t.TenantStatusID = ts.TenantStatusID "
        "LEFT JOIN LeaseRentSchedule lrs ON lrs.LeaseID = l.LeaseID "
        "AND lrs.EffectiveStartDate <= ? "
        "AND (lrs.EffectiveEndDate IS NULL OR lrs.EffectiveEndDate >= ?) "
    )
    lease_params = [as_of, as_of]
    if prop_filter != "All":
        lease_sql += "WHERE EXISTS (SELECT 1 FROM Properties p WHERE p.PropertyID = l.PropertyID AND p.PropertyName = ?) "
        lease_params.append(prop_filter)
    lease_sql += "ORDER BY l.LeaseStart DESC, l.LeaseID DESC"
    leases = run_query(lease_sql, tuple(lease_params), db=db)

    active_leases: list[dict] = []
    holdover_candidates: list[dict] = []
    fixed_term_types = {"fixed term", "option term", "multi-year", "multi year"}
    for lease in leases:
        tenant_status = str(lease.get("TenantStatusName") or "").strip().lower()
        if tenant_status == "default":
            continue
        start = _to_date(lease.get("LeaseStart"))
        end = effective_end(lease)
        if start is None:
            continue
        if start <= as_of and (end is None or end >= as_of):
            active_leases.append(lease)
        elif (
            str(lease.get("LeaseStatus") or "").strip() != "Terminated"
            and tenant_status == "active"
            and end is not None and end < as_of
            and str(lease.get("TenantSuite") or "").strip()
            and str(lease.get("LeaseTermTypeName") or "").strip().lower() in fixed_term_types
        ):
            holdover_candidates.append(lease)

    lease_suites = load_lease_suites(
        [lease["LeaseID"] for lease in leases], db
    )
    holdover_leases = [
        lease for lease in holdover_candidates
        if not is_superseded_holdover(lease, leases, lease_suites)
    ]
    report_ids = {int(suite["SuiteID"]) for suite in suites}

    def fmt_date(value) -> str:
        date_value = _to_date(value)
        return date_value.strftime("%m/%d/%Y") if date_value else ""

    def fmt_sqft(value) -> str:
        try:
            return f"{float(value):,.0f}" if value is not None else ""
        except (TypeError, ValueError):
            return ""

    def fmt_money(value) -> str:
        try:
            return f"${float(value):,.2f}" if value is not None else ""
        except (TypeError, ValueError):
            return ""

    # Pass 1: determine every suite's controlling lease before emitting rows.
    match_by_suite: dict[int, tuple[dict, bool]] = {}
    for suite in suites:
        suite_id = int(suite["SuiteID"])
        property_id = int(suite["PropertyID"])
        label = str(suite.get("SuiteLabel") or "").strip()
        active_match = match_suite_to_lease(
            suite_id, property_id, label, active_leases, lease_suites
        )
        holdover_match = (
            match_suite_to_lease(suite_id, property_id, label, holdover_leases, lease_suites)
            if active_match is None else None
        )
        if active_match is not None or holdover_match is not None:
            match_by_suite[suite_id] = (active_match or holdover_match, active_match is None)

    def matched_member_ids(lease: dict) -> set[int]:
        lease_id = int(lease["LeaseID"])
        return {
            suite_id for suite_id, (matched, _) in match_by_suite.items()
            if int(matched["LeaseID"]) == lease_id
        }

    def anchor_suite(lease: dict) -> int | None:
        member_ids = matched_member_ids(lease)
        for row in lease_suites.get(int(lease["LeaseID"]), []):
            if int(row["SuiteID"]) in member_ids:
                return int(row["SuiteID"])
        for suite in suites:
            if int(suite["SuiteID"]) in member_ids:
                return int(suite["SuiteID"])
        return None

    rows: list[dict] = []
    emitted_lease_ids: set[int] = set()
    for suite in suites:
        suite_id = int(suite["SuiteID"])
        property_id = int(suite["PropertyID"])
        label = str(suite.get("SuiteLabel") or "").strip()
        property_name = str(suite.get("PropertyName") or "")
        square_feet = suite.get("SquareFeet")
        use_type = str(suite.get("SuiteUseType") or "Standard").strip()
        underwriting_rent = suite.get("UnderwritingRent")
        match = match_by_suite.get(suite_id)

        if match is None:
            owner_occupied = basis == "Bank" and use_type == "Owner Occupied"
            rows.append({
                "property_name": property_name,
                "suite": label,
                "sq_ft": fmt_sqft(square_feet),
                "occupancy": "Occupied" if owner_occupied else "Vacant",
                "occupant": "Owner Occupied" if owner_occupied else "",
                "rental_rate": fmt_money(underwriting_rent) if owner_occupied else "",
                "lease_type": "Owner Occupied" if owner_occupied else "",
                "lease_start": "",
                "lease_end": "",
            })
            continue

        lease, is_holdover = match
        lease_id = int(lease["LeaseID"])
        anchor = anchor_suite(lease)
        if anchor is not None and anchor != suite_id:
            continue
        member_ids = matched_member_ids(lease)
        if lease_id in emitted_lease_ids:
            if suite_id in member_ids:
                continue
            owner_occupied = basis == "Bank" and use_type == "Owner Occupied"
            rows.append({
                "property_name": property_name, "suite": label, "sq_ft": fmt_sqft(square_feet),
                "occupancy": "Occupied" if owner_occupied else "Vacant",
                "occupant": "Owner Occupied" if owner_occupied else "",
                "rental_rate": fmt_money(underwriting_rent) if owner_occupied else "",
                "lease_type": "Owner Occupied" if owner_occupied else "",
                "lease_start": "", "lease_end": "",
            })
            continue

        linked_rows = [
            row for row in lease_suites.get(lease_id, [])
            if int(row["SuiteID"]) in member_ids
        ]
        if len(linked_rows) > 1:
            row_label = report_label([row.get("SuiteLabel") for row in linked_rows])
            row_square_feet = sum(float(row.get("SquareFeet") or 0) for row in linked_rows)
        else:
            row_label = label
            row_square_feet = square_feet
        emitted_lease_ids.add(lease_id)
        rows.append({
            "property_name": property_name,
            "suite": row_label,
            "sq_ft": fmt_sqft(row_square_feet),
            "occupancy": "Occupied",
            "occupant": str(lease.get("TenantName") or "").strip(),
            "rental_rate": fmt_money(lease.get("EffectiveRent")),
            "lease_type": "Month-to-Month (holdover)" if is_holdover else str(lease.get("LeaseTermTypeName") or ""),
            "lease_start": fmt_date(lease.get("LeaseStart")),
            "lease_end": "" if is_holdover else fmt_date(effective_end(lease)),
        })

    # Active leases without a report-suite match still appear once, as today.
    for lease in active_leases:
        lease_id = int(lease["LeaseID"])
        if lease_id in emitted_lease_ids:
            continue
        if suite_ids_for(lease, lease_suites) & report_ids:
            continue
        property_rows = run_query(
            "SELECT PropertyName FROM Properties WHERE PropertyID = ?",
            (int(lease["PropertyID"]),), db=db,
        ) if lease.get("PropertyID") else []
        rows.append({
            "property_name": str(property_rows[0].get("PropertyName") or "") if property_rows else "",
            "suite": str(lease.get("TenantSuite") or "").strip(),
            "sq_ft": "",
            "occupancy": "Occupied (unlinked)",
            "occupant": str(lease.get("TenantName") or "").strip(),
            "rental_rate": fmt_money(lease.get("RentAmount")),
            "lease_type": str(lease.get("LeaseTermTypeName") or ""),
            "lease_start": fmt_date(lease.get("LeaseStart")),
            "lease_end": fmt_date(effective_end(lease)),
        })

    total_rentable = sum(float(suite.get("SquareFeet") or 0) for suite in suites)
    total_occupied = 0.0
    psf_entries: list[tuple[float, float]] = []
    for row in rows:
        if not row["occupancy"].lower().startswith("occupied"):
            continue
        try:
            square_feet = float(row["sq_ft"].replace(",", "")) if row["sq_ft"] else 0.0
            rent = float(row["rental_rate"].replace("$", "").replace(",", "")) if row["rental_rate"] else 0.0
        except (TypeError, ValueError):
            square_feet, rent = 0.0, 0.0
        total_occupied += square_feet
        if square_feet > 0 and rent > 0:
            psf_entries.append((square_feet, rent))
    vacancy_rate = (total_rentable - total_occupied) / total_rentable if total_rentable else 0.0
    avg_annual_psf = (
        sum(rent * 12 for _, rent in psf_entries) / sum(square_feet for square_feet, _ in psf_entries)
        if psf_entries else None
    )
    return {
        "rows": rows,
        "total_rentable": total_rentable,
        "total_occupied": total_occupied,
        "vacancy_rate": vacancy_rate,
        "avg_annual_psf": avg_annual_psf,
    }


@contextmanager
def transaction(db: str):
    """Yield one cursor and commit or roll back every statement together."""
    conn = get_conn(db)
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def validate_lease_suites(cur, property_id: int,
                          rows: list[tuple[int, bool, Decimal]]) -> None:
    """Validate all application-owned LeaseSuites invariants."""
    if not rows:
        return
    suite_ids = [int(suite_id) for suite_id, _, _ in rows]
    if len(suite_ids) != len(set(suite_ids)):
        raise LeaseSuitesError("A suite is listed twice on this lease.")
    if sum(1 for _, is_primary, _ in rows if is_primary) != 1:
        raise LeaseSuitesError("A lease with suites must have exactly one primary suite.")
    pcts = [Decimal(str(pct)) for _, _, pct in rows]
    if any(pct <= 0 for pct in pcts) or sum(pcts) != Decimal(100):
        raise LeaseSuitesError("Suite rent shares must each be above 0 and total exactly 100%.")
    placeholders = ",".join("?" for _ in suite_ids)
    cur.execute(
        f"SELECT SuiteID, PropertyID FROM PropertySuites WHERE SuiteID IN ({placeholders})",
        tuple(suite_ids),
    )
    found = {int(row[0]): int(row[1]) for row in cur.fetchall()}
    if set(found) != set(suite_ids) or any(found_id != int(property_id) for found_id in found.values()):
        raise LeaseSuitesError("All suites on a lease must belong to the lease's property.")


def replace_lease_suites(cur, lease_id: int, property_id: int,
                         rows: list[tuple[int, bool, Decimal]]) -> None:
    """Replace links and synchronize Leases.SuiteID on the caller's transaction."""
    validate_lease_suites(cur, property_id, rows)
    cur.execute("DELETE FROM LeaseSuites WHERE LeaseID = ?", (lease_id,))
    primary_id = None
    for suite_id, is_primary, pct in rows:
        cur.execute(
            "INSERT INTO LeaseSuites (LeaseID, SuiteID, IsPrimary, RentAllocationPct) "
            "VALUES (?, ?, ?, ?)",
            (lease_id, suite_id, 1 if is_primary else 0, pct),
        )
        if is_primary:
            primary_id = suite_id
    cur.execute("UPDATE Leases SET SuiteID = ? WHERE LeaseID = ?", (primary_id, lease_id))
