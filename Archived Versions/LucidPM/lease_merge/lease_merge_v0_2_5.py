"""
Lucid Property Manager - Lease Merge Utility
v0.2.4

Purpose:
    Service layer for lease document tokenization and rendering.

What this does:
    1. Builds a lease merge context from Tenant, Lease, Property, Suite,
       Contact, and LeaseRentSchedule data.
    2. Replaces {{TokenName}} merge tokens in text templates.
    3. Generates structured lease content such as PaymentScheduleBlock.

What this does NOT do:
    - Does NOT assemble lease packages
    - Does NOT read from package/template tables
    - Does NOT merge PDFs

Those responsibilities live in the Lease Package Builder and merge pipeline.

Notes:
    This file is intentionally UI-agnostic and acts as the core token engine.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from LucidPM_Reflex.state import run_query, run_exec, TEST_DB_NAME

TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_\.\-]+)\s*\}\}")

OWNER_BY_PROPERTY = {
    "broadway": "Dor-Sal Capital Partners, LLC",
    "walnut": "Lucido Properties SP, LLC",
    "euless": "Lucido Properties 508, LLC",
}

LEASE_TYPE_BY_PROPERTY = {
    "broadway": "Modified Gross",
    "walnut": "Modified Gross",
    "euless": "NNN",
}


def _s(value: Any) -> str:
    return str(value or "").strip()


def _first(rows: list[dict]) -> dict:
    return rows[0] if rows else {}


def _date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def fmt_date(value: Any) -> str:
    d = _date(value)
    return d.strftime("%m/%d/%Y") if d else ""


def fmt_iso_date(value: Any) -> str:
    d = _date(value)
    return d.isoformat() if d else ""


def fmt_money(value: Any, decimals: int = 2) -> str:
    try:
        amount = Decimal(str(value or "0"))
    except InvalidOperation:
        return ""
    return f"${amount:,.{decimals}f}"


def fmt_number(value: Any, decimals: int = 0) -> str:
    try:
        amount = Decimal(str(value or "0"))
    except InvalidOperation:
        return ""
    return f"{amount:,.{decimals}f}"


def _property_owner(property_name: str) -> str:
    return OWNER_BY_PROPERTY.get(property_name.strip().lower(), "")


def _property_lease_type(property_name: str) -> str:
    return LEASE_TYPE_BY_PROPERTY.get(property_name.strip().lower(), "")


def _property_full_address(row: dict) -> str:
    parts = [
        _s(row.get("PropertyAddress1")),
        _s(row.get("PropertyAddress2")),
    ]
    city_state_zip = " ".join(x for x in [
        _s(row.get("PropertyCity")) + ("," if _s(row.get("PropertyCity")) else ""),
        _s(row.get("PropertyState")),
        _s(row.get("PropertyZip")),
    ] if x).strip()
    if city_state_zip:
        parts.append(city_state_zip)
    return ", ".join(p for p in parts if p)


def _notice_address(row: dict) -> str:
    parts = [
        _s(row.get("LeaseNoticeAddress1")),
        _s(row.get("LeaseNoticeAddress2")),
    ]
    city_state_zip = " ".join(x for x in [
        _s(row.get("LeaseNoticeCity")) + ("," if _s(row.get("LeaseNoticeCity")) else ""),
        _s(row.get("LeaseNoticeState")),
        _s(row.get("LeaseNoticeZip")),
    ] if x).strip()
    if city_state_zip:
        parts.append(city_state_zip)
    return ", ".join(p for p in parts if p)


def _suite_full_address(row: dict, suite_label: str) -> str:
    override = _s(row.get("SuiteAddressOverride"))
    if override:
        return override
    premises = _s(row.get("SuitePremisesDescription"))
    address = _property_full_address(row)
    if premises and address:
        return f"{premises}, {address}"
    if premises:
        return premises
    if suite_label and address:
        return f"Suite {suite_label}, {address}"
    return address


def _lease_term_description(start: dt.date | None, end: dt.date | None) -> str:
    if not start or not end:
        return ""

    months = (end.year - start.year) * 12 + (end.month - start.month + 1)

    if months <= 0:
        return ""

    # Legal-style written month descriptions
    _num_words = {
        1: "one (1)",
        2: "two (2)",
        3: "three (3)",
        4: "four (4)",
        5: "five (5)",
        6: "six (6)",
        7: "seven (7)",
        8: "eight (8)",
        9: "nine (9)",
        10: "ten (10)",
        11: "eleven (11)",
        12: "twelve (12)",
        18: "eighteen (18)",
        24: "twenty-four (24)",
        36: "thirty-six (36)",
        48: "forty-eight (48)",
        60: "sixty (60)",
    }

    word = _num_words.get(months, str(months))
    return f"{word} months"


def _ordinal(n: int) -> str:
    """Return ordinal suffix for a day number: 1st, 2nd, 3rd, 4th..."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"



def _get_table_columns(table_name: str, db: str) -> set[str]:
    rows = run_query(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?",
        (table_name,),
        db=db,
    )
    return {str(r["COLUMN_NAME"]) for r in rows}


def _table_exists(table_name: str, db: str) -> bool:
    rows = run_query(
        "SELECT 1 AS Found FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = ?",
        (table_name,),
        db=db,
    )
    return bool(rows)


def _rent_schedule_summary(lease_id: int, db: str) -> tuple[str, str]:
    if not _table_exists("LeaseRentSchedule", db):
        return "", ""

    cols = _get_table_columns("LeaseRentSchedule", db)
    increase_join = ""
    increase_select = "'' AS IncreaseTypeName"

    if "IncreaseTypeID" in cols and _table_exists("LeaseRentIncreaseTypes", db):
        lookup_cols = _get_table_columns("LeaseRentIncreaseTypes", db)
        lookup_pk = "LeaseRentIncreaseTypeID" if "LeaseRentIncreaseTypeID" in lookup_cols else "IncreaseTypeID"
        lookup_name = "IncreaseTypeName" if "IncreaseTypeName" in lookup_cols else "IncreaseType"
        increase_join = f"LEFT JOIN LeaseRentIncreaseTypes rit ON lrs.IncreaseTypeID = rit.{lookup_pk}"
        increase_select = f"ISNULL(rit.{lookup_name}, '') AS IncreaseTypeName"
    elif "IncreaseType" in cols:
        increase_select = "ISNULL(lrs.IncreaseType, '') AS IncreaseTypeName"

    rows = run_query(
        "SELECT lrs.EffectiveStartDate, lrs.EffectiveEndDate, lrs.RentAmount, "
        f"{increase_select}, ISNULL(lrs.Notes, '') AS Notes "
        "FROM LeaseRentSchedule lrs "
        f"{increase_join} "
        "WHERE lrs.LeaseID = ? "
        "ORDER BY lrs.EffectiveStartDate, lrs.LeaseRentScheduleID",
        (lease_id,),
        db=db,
    )

    if not rows:
        return "", ""

    lines = []
    first_rent = ""
    for i, row in enumerate(rows):
        start = fmt_date(row.get("EffectiveStartDate"))
        end = fmt_date(row.get("EffectiveEndDate")) or "thereafter"
        rent = fmt_money(row.get("RentAmount"))
        kind = _s(row.get("IncreaseTypeName"))
        note = _s(row.get("Notes"))
        if i == 0:
            first_rent = rent
        line = f"{start} through {end}: {rent}"
        if kind:
            line += f" ({kind})"
        if note:
            line += f" - {note}"
        lines.append(line)

    return first_rent, "\n".join(lines)


def _add_month(d: dt.date) -> dt.date:
    if d.month == 12:
        return dt.date(d.year + 1, 1, 1)
    return dt.date(d.year, d.month + 1, 1)


def _month_last_day(year: int, month: int) -> int:
    first = dt.date(year, month, 1)
    nxt = _add_month(first)
    return (nxt - dt.timedelta(days=1)).day


def _safe_month_day(year: int, month: int, day: int) -> dt.date:
    return dt.date(year, month, min(max(int(day or 1), 1), _month_last_day(year, month)))


def _alpha_label(index: int) -> str:
    """Return a), b), ... z), aa), ab) style labels."""
    n = index + 1
    chars = []
    while n:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(97 + rem))
    return "".join(reversed(chars)) + ")"


def _money_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _number_words_under_1000(n: int) -> str:
    ones = [
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
    ]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    if n < 20:
        return ones[n]
    if n < 100:
        t, r = divmod(n, 10)
        return tens[t] + ("-" + ones[r] if r else "")
    h, r = divmod(n, 100)
    return ones[h] + " hundred" + (" " + _number_words_under_1000(r) if r else "")


def number_to_words(value: Any) -> str:
    """Simple dollar amount wording for lease text."""
    amount = _money_decimal(value)
    dollars = int(amount)
    cents = int((amount - Decimal(dollars)) * 100)
    if dollars == 0:
        words = "zero"
    else:
        groups = [(1000000000, "billion"), (1000000, "million"), (1000, "thousand")]
        parts = []
        remaining = dollars
        for divisor, name in groups:
            q, remaining = divmod(remaining, divisor)
            if q:
                parts.append(_number_words_under_1000(q) + " " + name)
        if remaining:
            parts.append(_number_words_under_1000(remaining))
        words = " ".join(parts)
    return f"{words} and {cents:02d}/100 dollars"


def _load_rent_schedule_rows(lease_id: int, db: str) -> list[dict]:
    if not _table_exists("LeaseRentSchedule", db):
        return []
    cols = _get_table_columns("LeaseRentSchedule", db)
    order_col = "LeaseRentScheduleID" if "LeaseRentScheduleID" in cols else "EffectiveStartDate"
    return run_query(
        "SELECT EffectiveStartDate, EffectiveEndDate, RentAmount "
        "FROM LeaseRentSchedule WHERE LeaseID = ? "
        f"ORDER BY EffectiveStartDate, {order_col}",
        (lease_id,),
        db=db,
    )


def _rent_for_date(schedule_rows: list[dict], target_date: dt.date, fallback_rent: Any) -> Decimal:
    active: list[tuple[dt.date, Decimal]] = []
    for row in schedule_rows:
        start = _date(row.get("EffectiveStartDate"))
        end = _date(row.get("EffectiveEndDate"))
        if not start:
            continue
        if start <= target_date and (end is None or target_date <= end):
            active.append((start, _money_decimal(row.get("RentAmount"))))
    if active:
        active.sort(key=lambda x: x[0], reverse=True)
        return active[0][1]

    prior: list[tuple[dt.date, Decimal]] = []
    for row in schedule_rows:
        start = _date(row.get("EffectiveStartDate"))
        if start and start <= target_date:
            prior.append((start, _money_decimal(row.get("RentAmount"))))
    if prior:
        prior.sort(key=lambda x: x[0], reverse=True)
        return prior[0][1]

    return _money_decimal(fallback_rent)


def _fmt_long_date(d: dt.date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _format_monthly_2_column_schedule(payment_rows: list[tuple[dt.date, Decimal]]) -> str:
    """Format <=24 monthly payment rows as a 2-column text table.

    Plain text is intentional here because the current merge preview is text-based.
    When DOCX export is added, this same row data can become a real Word table.
    """
    if not payment_rows:
        return ""

    split_at = (len(payment_rows) + 1) // 2
    left = payment_rows[:split_at]
    right = payment_rows[split_at:]
    left_width = 38
    lines = []

    for i in range(split_at):
        left_date, left_amount = left[i]
        left_text = f"{_alpha_label(i)} {_fmt_long_date(left_date)}: {fmt_money(left_amount)}"
        if i < len(right):
            right_index = split_at + i
            right_date, right_amount = right[i]
            right_text = f"{_alpha_label(right_index)} {_fmt_long_date(right_date)}: {fmt_money(right_amount)}"
            lines.append(left_text.ljust(left_width) + right_text)
        else:
            lines.append(left_text)

    return "\n".join(lines)


def _format_grouped_rent_schedule(
    schedule_rows: list[dict],
    lease_start: dt.date,
    lease_end: dt.date,
) -> str:
    """Format >24 payment rows as grouped rent periods.

    Uses LeaseRentSchedule period boundaries directly so that mid-month
    lease start dates produce correct anniversary-aligned display ranges
    (e.g. May 16 → May 15 the following year) instead of rolling to the
    nearest 1st-of-month boundary.
    """
    if not schedule_rows:
        return ""

    lines = []
    for i, row in enumerate(schedule_rows):
        seg_start = _date(row.get("EffectiveStartDate")) or lease_start
        seg_start = max(seg_start, lease_start)

        explicit_end = _date(row.get("EffectiveEndDate"))
        if explicit_end:
            seg_end = min(explicit_end, lease_end)
        elif i + 1 < len(schedule_rows):
            next_start = _date(schedule_rows[i + 1].get("EffectiveStartDate"))
            seg_end = (next_start - dt.timedelta(days=1)) if next_start else lease_end
            seg_end = min(seg_end, lease_end)
        else:
            seg_end = lease_end

        if seg_start > seg_end:
            continue

        amount = _money_decimal(row.get("RentAmount"))
        lines.append(
            f"{_alpha_label(i)} {_fmt_long_date(seg_start)} to "
            f"{_fmt_long_date(seg_end)}: {fmt_money(amount)} per month"
        )

    return "\n".join(lines)


def _payment_schedule_block(lease: dict, lease_id: int, db: str) -> tuple[str, str]:
    """Build PaymentScheduleBlock and TotalRent for the lease term.

    Display rule:
      - 24 monthly payments or fewer: 2-column monthly schedule.
      - More than 24 monthly payments: grouped rent-period schedule.

    TotalRent always sums the full monthly payment list.
    """
    lease_start = _date(lease.get("LeaseStart"))
    lease_end = _date(lease.get("LeaseEnd"))
    if not lease_start:
        rent = fmt_money(lease.get("RentAmount"))
        return "", rent

    due_day = int(lease.get("RentDueDay") or 1)
    schedule_rows = _load_rent_schedule_rows(lease_id, db)
    fallback_rent = lease.get("RentAmount")

    if not lease_end:
        rent_dec = _rent_for_date(schedule_rows, lease_start, fallback_rent)
        return f"a) {_fmt_long_date(lease_start)}: {fmt_money(rent_dec)}", fmt_money(rent_dec)

    # Generate one payment row per month of the lease term.
    # LeaseRentSchedule rows are rate periods, not payment rows.
    payment_rows: list[tuple[dt.date, Decimal]] = []
    current_month = dt.date(lease_start.year, lease_start.month, 1)
    last_month = dt.date(lease_end.year, lease_end.month, 1)

    while current_month <= last_month:
        due_date = _safe_month_day(current_month.year, current_month.month, due_day)

        # If the first due date would fall before the lease starts, use the
        # actual lease start date for the first payment line.
        if current_month.year == lease_start.year and current_month.month == lease_start.month:
            if due_date < lease_start or lease_start > due_date:
                due_date = lease_start

        if due_date < lease_start:
            due_date = lease_start

        if due_date <= lease_end:
            payment_rows.append((due_date, _rent_for_date(schedule_rows, due_date, fallback_rent)))

        current_month = _add_month(current_month)

    payment_rows.sort(key=lambda x: x[0])
    total = sum((amount for _, amount in payment_rows), Decimal("0.00"))

    if len(payment_rows) <= 24:
        block = _format_monthly_2_column_schedule(payment_rows)
    else:
        block = _format_grouped_rent_schedule(schedule_rows, lease_start, lease_end)

    return block, fmt_money(total)

def get_lease_merge_context(tenant_id: int, lease_id: int, db: str = TEST_DB_NAME) -> dict[str, str]:
    """
    Return a flat merge dictionary for {{Token}} replacement.

    Use this as the single source for all lease documents.
    """
    lease = _first(run_query(
        "SELECT l.*, "
        "t.TenantName, t.Suite AS TenantSuiteText, "
        "p.PropertyName, p.PropertyAddress1, p.PropertyAddress2, p.PropertyCity, p.PropertyState, p.PropertyZip, p.TaxAccountNumber, "
        "ISNULL(p.LandlordEntityName,'') AS LandlordEntityName, ISNULL(p.PropertyCounty,'') AS PropertyCounty, "
        "ISNULL(p.PropertyLegalDescription,'') AS PropertyLegalDescription, ISNULL(p.PropertyUseDefault,'') AS PropertyUseDefault, "
        "ISNULL(p.LeaseNoticeAddress1,'') AS LeaseNoticeAddress1, ISNULL(p.LeaseNoticeAddress2,'') AS LeaseNoticeAddress2, "
        "ISNULL(p.LeaseNoticeCity,'') AS LeaseNoticeCity, ISNULL(p.LeaseNoticeState,'') AS LeaseNoticeState, ISNULL(p.LeaseNoticeZip,'') AS LeaseNoticeZip, "
        "ps.SuiteLabel, ps.SquareFeet, ps.SuiteUseType, ps.UnderwritingRent, "
        "ISNULL(ps.SuitePremisesDescription,'') AS SuitePremisesDescription, ISNULL(ps.SuiteLegalDescription,'') AS SuiteLegalDescription, "
        "ISNULL(ps.SuiteAddressOverride,'') AS SuiteAddressOverride, "
        "lt.LeaseTypeName, ltt.LeaseTermTypeName "
        "FROM Leases l "
        "LEFT JOIN Tenants t ON l.TenantID = t.TenantID "
        "LEFT JOIN Properties p ON l.PropertyID = p.PropertyID "
        "LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID "
        "LEFT JOIN LeaseTypes lt ON l.LeaseTypeID = lt.LeaseTypeID "
        "LEFT JOIN LeaseTermTypes ltt ON l.LeaseTermTypeID = ltt.LeaseTermTypeID "
        "WHERE l.LeaseID = ? AND l.TenantID = ?",
        (lease_id, tenant_id),
        db=db,
    ))

    if not lease:
        raise ValueError(f"Lease not found for TenantID={tenant_id}, LeaseID={lease_id}.")

    contact = _first(run_query(
        "SELECT TOP 1 FirstName, LastName, Salutation, Title, ContactRole, Email1, Email2, WorkPhone, HomePhone "
        "FROM Contacts WHERE TenantID = ? "
        "ORDER BY CASE WHEN IsPrimary = 1 THEN 0 ELSE 1 END, ContactID",
        (tenant_id,),
        db=db,
    ))

    guarantor = _first(run_query(
        "SELECT TOP 1 FirstName, LastName FROM Contacts "
        "WHERE TenantID = ? AND ContactRole = 'Guarantor' "
        "ORDER BY ContactID",
        (tenant_id,),
        db=db,
    ))
    guarantor_name = " ".join(x for x in [
        _s(guarantor.get("FirstName")),
        _s(guarantor.get("LastName")),
    ] if x)

    lease_start = _date(lease.get("LeaseStart"))
    lease_end = _date(lease.get("LeaseEnd"))
    term_days = (lease_end - lease_start).days + 1 if lease_start and lease_end else 0

    first_schedule_rent, rent_schedule_text = _rent_schedule_summary(lease_id, db)
    payment_schedule_block, total_rent = _payment_schedule_block(lease, lease_id, db)
    base_rent = first_schedule_rent or fmt_money(lease.get("RentAmount"))

    property_name = _s(lease.get("PropertyName"))
    suite_label = _s(lease.get("SuiteLabel")) or _s(lease.get("TenantSuiteText"))
    full_contact_name = " ".join(x for x in [_s(contact.get("FirstName")), _s(contact.get("LastName"))] if x)
    landlord_entity = _s(lease.get("LandlordEntityName")) or _property_owner(property_name)
    property_address = _property_full_address(lease)
    suite_full_address = _suite_full_address(lease, suite_label)
    use_type = _s(lease.get("SuiteUseType")) or _s(lease.get("PropertyUseDefault"))
    legal_description = _s(lease.get("SuiteLegalDescription")) or _s(lease.get("PropertyLegalDescription"))
    county = _s(lease.get("PropertyCounty")) or "Dallas"
    raw_state = _s(lease.get("PropertyState")) or "Texas"
    state = "Texas" if raw_state.upper() == "TX" else raw_state

    context = {
        "GeneratedDate": fmt_date(dt.date.today()),
        "GeneratedDateISO": fmt_iso_date(dt.date.today()),

        # Header section tokens
        "DocTitle": "SHORT FORM COMMERCIAL LEASE",
        "LandlordLabel": '(hereinafter referred to as "Landlord").',
        "TenantLabel": '(hereinafter referred to as "Tenant").',
        "JurisdictionBlock": f"State of {state}\nCounty of {county}",

        "TenantID": str(tenant_id),
        "TenantName": _s(lease.get("TenantName")),

        # Guarantor and DBA name variants
        "GuarantorName": guarantor_name,
        "TenantNameWithGuarantor": (
            f"{_s(lease.get('TenantName'))} and {guarantor_name}"
            if guarantor_name
            else _s(lease.get("TenantName"))
        ),
        "DBAName": "",
        "TenantNameWithDBA": _s(lease.get("TenantName")),
        "TenantPrimaryContact": full_contact_name,
        "TenantContactFirstName": _s(contact.get("FirstName")),
        "TenantContactLastName": _s(contact.get("LastName")),
        "TenantContactTitle": _s(contact.get("Title")),
        "TenantContactRole": _s(contact.get("ContactRole")),
        "TenantContactEmail": _s(contact.get("Email1")),
        "TenantContactEmail2": _s(contact.get("Email2")),
        "TenantContactPhone": _s(contact.get("WorkPhone")) or _s(contact.get("HomePhone")),
        "TenantSalutation": _s(contact.get("Salutation")) or full_contact_name,

        "LeaseID": str(lease_id),
        "LeaseType": _s(lease.get("LeaseTypeName")) or _property_lease_type(property_name),
        "LeaseTermType": _s(lease.get("LeaseTermTypeName")),
        "LeaseStartDate": fmt_date(lease.get("LeaseStart")),
        "LeaseEndDate": fmt_date(lease.get("LeaseEnd")),
        "LeaseStartDateISO": fmt_iso_date(lease.get("LeaseStart")),
        "LeaseEndDateISO": fmt_iso_date(lease.get("LeaseEnd")),

        # Ordinal date formatting for formal lease header
        "LeaseStartOrdinal": _ordinal(lease_start.day) if lease_start else "",
        "LeaseStartMonth": lease_start.strftime("%B") if lease_start else "",
        "LeaseStartYear": str(lease_start.year) if lease_start else "",
        "LeaseEndOrdinal": _ordinal(lease_end.day) if lease_end else "",
        "LeaseEndMonth": lease_end.strftime("%B") if lease_end else "",
        "LeaseEndYear": str(lease_end.year) if lease_end else "",
        "LeaseTermDays": str(term_days) if term_days else "",
        "BaseRent": base_rent,
        "BaseRentAmount": fmt_number(lease.get("RentAmount"), 2),
        "BaseRentWords": number_to_words(lease.get("RentAmount")),

        # Holdover rent — formula fallback until schema addition
        "HoldoverRent": fmt_money(
            _money_decimal(lease.get("HoldoverRate"))
            if lease.get("HoldoverRate")
            else (_money_decimal(lease.get("RentAmount")) * Decimal("1.20")).quantize(Decimal("0.01"))
        ),
        "RentAmountWords": number_to_words(lease.get("RentAmount")),
        "SecurityDeposit": fmt_money(lease.get("DepositAmount")),

        # Late charge fields — static defaults until schema additions
        "LateChargePct": "12%",
        "LateChargeFlatFee": fmt_money(lease.get("LateFeeFlat") or 50),
        "LateChargePerDay": fmt_money(lease.get("LateFeePerDay") or 20),
        "DepositAmount": fmt_money(lease.get("DepositAmount")),
        "RentDueDay": str(lease.get("RentDueDay") or "1"),
        "NextRentDueDate": fmt_date(lease.get("NextRentDueDate")),
        "RentScheduleText": rent_schedule_text,
        "PaymentScheduleBlock": payment_schedule_block,
        "TotalRent": total_rent,
        "TotalRentWords": number_to_words(total_rent.replace("$", "").replace(",", "")) if total_rent else "",

        "PropertyName": property_name,
        "LandlordEntity": landlord_entity,
        "PropertyLegalDescription": _s(lease.get("PropertyLegalDescription")),
        "PropertyUseDefault": _s(lease.get("PropertyUseDefault")),
        "County": county,
        "State": state,
        "PropertyAddress": property_address,
        "PropertyAddress1": _s(lease.get("PropertyAddress1")),
        "PropertyAddress2": _s(lease.get("PropertyAddress2")),
        "PropertyCity": _s(lease.get("PropertyCity")),
        "PropertyState": _s(lease.get("PropertyState")),
        "PropertyZip": _s(lease.get("PropertyZip")),
        "TaxAccountNumber": _s(lease.get("TaxAccountNumber")),
        "LeaseNoticeAddress": _notice_address(lease) or property_address,
        "LeaseNoticeAddress1": _s(lease.get("LeaseNoticeAddress1")),
        "LeaseNoticeAddress2": _s(lease.get("LeaseNoticeAddress2")),
        "LeaseNoticeCity": _s(lease.get("LeaseNoticeCity")),
        "LeaseNoticeState": _s(lease.get("LeaseNoticeState")),
        "LeaseNoticeZip": _s(lease.get("LeaseNoticeZip")),

        "Suite": suite_label,
        "SuiteLabel": suite_label,
        "SuiteFullAddress": suite_full_address,
        "SuitePremisesDescription": _s(lease.get("SuitePremisesDescription")),
        "SuiteLegalDescription": _s(lease.get("SuiteLegalDescription")),
        "SuiteAddressOverride": _s(lease.get("SuiteAddressOverride")),
        "LegalDescription": legal_description,
        "PremisesDescription": suite_full_address,
        "SuiteSquareFeet": fmt_number(lease.get("SquareFeet"), 0),
        "SuiteUseType": use_type,
        "UseType": use_type,
        "UnderwritingRent": fmt_money(lease.get("UnderwritingRent")),
        "LeaseTermDescription": _lease_term_description(lease_start, lease_end),

        # Extension / option term
        "ExtensionTermMonths": str(int(lease.get("OptionTermMonths") or 0)) if lease.get("OptionTermMonths") else "",
        "ExtensionTermDescription": (
            f"{int(lease.get('OptionTermMonths'))} months"
            if lease.get("OptionTermMonths")
            else ""
        ),
        "ExtensionRent": fmt_money(lease.get("OptionRent")) if lease.get("OptionRent") else "",
        "ExtensionRentWords": number_to_words(lease.get("OptionRent")) if lease.get("OptionRent") else "",

        # HVAC warranty
        "HVACWarrantyPeriod": "Five years (5 years)",
        "HVACWarrantyYears": "5",
    }

    # Useful aliases for shorter tokens.
    context["Landlord"] = context["LandlordEntity"]
    context["Premises"] = context["SuiteFullAddress"]
    context["MonthlyRent"] = context["BaseRent"]
    context["Deposit"] = context["SecurityDeposit"]
    context["LeaseDeposit"] = context["SecurityDeposit"]

    # Compatibility aliases for current test templates.
    context["RentAmount"] = context["BaseRent"]
    context["RentAmountRaw"] = context["BaseRentAmount"]
    context["LeaseStart"] = context["LeaseStartDate"]
    context["LeaseEnd"] = context["LeaseEndDate"]
    context["StartDate"] = context["LeaseStartDate"]
    context["EndDate"] = context["LeaseEndDate"]
    context["Property"] = context["PropertyName"]
    context["SuiteName"] = context["SuiteLabel"]

    # Formal lease term sentence for Header section
    if lease_start and lease_end and context.get("LeaseTermDescription") and use_type:
        context["LeaseTermBlock"] = (
            f"{context['LeaseTermDescription']}, "
            f"beginning the {_ordinal(lease_start.day)} day of "
            f"{lease_start.strftime('%B')}, {lease_start.year}, "
            f"and ending the {_ordinal(lease_end.day)} day of "
            f"{lease_end.strftime('%B')}, {lease_end.year} "
            f"to be occupied as {use_type} and not otherwise, "
            f"paying therefore the sum of {context['BaseRentWords']} "
            f"per month, payable upon the schedule, conditions, and covenants following:"
        )
    else:
        context["LeaseTermBlock"] = ""

    context["PremisesIntro"] = (
        "Landlord hereby leases to Tenant, and Tenant hereby takes from Landlord "
        "the following described premises situated within the County of "
        f"{county}, State of {state}:"
    )

    return context


def render_text_template(template_text: str, context: dict[str, Any]) -> tuple[str, list[str]]:
    """
    Replace {{Token}} values in a text template.

    Returns:
        rendered_text, unresolved_tokens
    """
    unresolved: list[str] = []

    def replace(match: re.Match) -> str:
        key = match.group(1).strip()
        if key in context and context[key] is not None:
            return str(context[key])
        unresolved.append(key)
        return match.group(0)

    rendered = TOKEN_PATTERN.sub(replace, template_text or "")
    return rendered, sorted(set(unresolved))


def extract_tokens(template_text: str) -> list[str]:
    return sorted(set(m.group(1).strip() for m in TOKEN_PATTERN.finditer(template_text or "")))


def validate_template_tokens(template_text: str, context: dict[str, Any]) -> dict[str, list[str]]:
    tokens = extract_tokens(template_text)
    available = set(context.keys())
    missing = [t for t in tokens if t not in available]
    empty = [t for t in tokens if t in available and not str(context.get(t) or "").strip()]
    return {
        "tokens": tokens,
        "resolved": [t for t in tokens if t in available and t not in empty],
        "missing": missing,
        "empty": empty,
        "unresolved": sorted(set(missing + empty)),
    }



# Backward-compatible aliases used by the Reflex Lease Package Builder page.
def build_lease_context(db: str, tenant_id: int, lease_id: int) -> dict[str, str]:
    return get_lease_merge_context(tenant_id=tenant_id, lease_id=lease_id, db=db)


def merge_template(template_text: str, context: dict[str, Any]) -> str:
    rendered, _ = render_text_template(template_text, context)
    return rendered


def find_unresolved_tokens(rendered_text: str) -> list[str]:
    return extract_tokens(rendered_text)
