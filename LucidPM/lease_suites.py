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
