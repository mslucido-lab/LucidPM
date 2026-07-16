"""
Lucid Property Manager - Lease Merge Utility
v0.1.3

Purpose:
    First usable slice for the lease document merge/render layer.

What this does:
    1. Builds a lease merge context from existing Tenant, Lease, Property, Suite,
       Contact, and LeaseRentSchedule data.
    2. Replaces {{TokenName}} merge tokens in text.
    3. Optionally assembles package pieces if your package tables follow the
       LeaseDocumentPackage / LeaseDocumentPiece pattern.

Install target:
    LucidPM_Reflex/LucidPM_Reflex/pages/lease_merge.py
    or LucidPM_Reflex/LucidPM_Reflex/services/lease_merge.py

Notes:
    This file intentionally avoids Reflex UI code. It is a service layer that can
    be called from your existing Lease Packages page or a future Generate button.
"""

from __future__ import annotations

import datetime as dt
import json
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
    days = (end - start).days + 1
    if 364 <= days <= 366:
        return "one (1) year"
    if 729 <= days <= 731:
        return "two (2) years"
    if 1094 <= days <= 1096:
        return "three (3) years"
    if 1459 <= days <= 1461:
        return "four (4) years"
    if 1824 <= days <= 1827:
        return "five (5) years"
    return f"{days} days"


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


def _payment_schedule_block(lease: dict, lease_id: int, db: str) -> tuple[str, str]:
    if not _table_exists("LeaseRentSchedule", db):
        return "", ""
    rows = run_query(
        "SELECT EffectiveStartDate, EffectiveEndDate, RentAmount "
        "FROM LeaseRentSchedule WHERE LeaseID = ? "
        "ORDER BY EffectiveStartDate, LeaseRentScheduleID",
        (lease_id,),
        db=db,
    )
    if not rows:
        rent = fmt_money(lease.get("RentAmount"))
        due_day = int(lease.get("RentDueDay") or 1)
        start = _date(lease.get("LeaseStart"))
        if start:
            return f"{start.strftime('%B')} {due_day}, {start.year}: {rent}", rent
        return "", rent

    labels = "abcdefghijklmnopqrstuvwxyz"
    lines = []
    total = Decimal("0")
    for idx, row in enumerate(rows):
        start = _date(row.get("EffectiveStartDate"))
        end = _date(row.get("EffectiveEndDate"))
        rent_raw = row.get("RentAmount")
        rent = fmt_money(rent_raw)
        try:
            total += Decimal(str(rent_raw or "0"))
        except InvalidOperation:
            pass
        label = labels[idx] + ")" if idx < len(labels) else f"{idx + 1}.)"
        if start and end:
            lines.append(f"{label} {fmt_date(start)} through {fmt_date(end)}: {rent}")
        elif start:
            lines.append(f"{label} {fmt_date(start)}: {rent}")
        else:
            lines.append(f"{label} {rent}")
    return "\n".join(lines), fmt_money(total)


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

        "TenantID": str(tenant_id),
        "TenantName": _s(lease.get("TenantName")),
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
        "LeaseTermDays": str(term_days) if term_days else "",
        "BaseRent": base_rent,
        "BaseRentAmount": fmt_number(lease.get("RentAmount"), 2),
        "SecurityDeposit": fmt_money(lease.get("SecurityDeposit")),
        "RentDueDay": str(lease.get("RentDueDay") or "1"),
        "NextRentDueDate": fmt_date(lease.get("NextRentDueDate")),
        "RentScheduleText": rent_schedule_text,
        "PaymentScheduleBlock": payment_schedule_block,
        "TotalRent": total_rent,

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
    }

    # Useful aliases for shorter tokens.
    context["Landlord"] = context["LandlordEntity"]
    context["Premises"] = context["SuiteFullAddress"]
    context["MonthlyRent"] = context["BaseRent"]
    context["Deposit"] = context["SecurityDeposit"]

    # Compatibility aliases for current test templates.
    context["RentAmount"] = context["BaseRent"]
    context["RentAmountRaw"] = context["BaseRentAmount"]
    context["LeaseStart"] = context["LeaseStartDate"]
    context["LeaseEnd"] = context["LeaseEndDate"]
    context["StartDate"] = context["LeaseStartDate"]
    context["EndDate"] = context["LeaseEndDate"]
    context["Property"] = context["PropertyName"]
    context["SuiteName"] = context["SuiteLabel"]

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
    return {
        "tokens": tokens,
        "resolved": [t for t in tokens if t in available],
        "missing": [t for t in tokens if t not in available],
    }


def assemble_package_text(package_id: int, db: str = TEST_DB_NAME) -> str:
    """
    Best-effort text assembly for existing package tables.

    Expected pattern:
        LeaseDocumentPackages
        LeaseDocumentPackagePieces
        LeaseDocumentPieces

    Required piece text column can be one of:
        PieceText, BodyText, TemplateText, ContentText

    If your actual table names differ, keep get_lease_merge_context() and
    render_text_template(), then wire this function to your real package query.
    """
    package_table = "LeaseDocumentPackages"
    link_table = "LeaseDocumentPackagePieces"
    piece_table = "LeaseDocumentPieces"

    for table in [package_table, link_table, piece_table]:
        if not _table_exists(table, db):
            raise ValueError(f"Missing expected table: {table}")

    piece_cols = _get_table_columns(piece_table, db)
    text_col = next((c for c in ["PieceText", "BodyText", "TemplateText", "ContentText"] if c in piece_cols), "")
    if not text_col:
        raise ValueError(f"No supported text column found on {piece_table}.")

    link_cols = _get_table_columns(link_table, db)
    sort_expr = "l.SortOrder" if "SortOrder" in link_cols else "p.SortOrder"

    rows = run_query(
        f"SELECT p.{text_col} AS PieceText "
        f"FROM {link_table} l "
        f"INNER JOIN {piece_table} p ON l.LeaseDocumentPieceID = p.LeaseDocumentPieceID "
        "WHERE l.LeaseDocumentPackageID = ? "
        f"ORDER BY {sort_expr}, p.LeaseDocumentPieceID",
        (package_id,),
        db=db,
    )

    return "\n\n".join(_s(r.get("PieceText")) for r in rows if _s(r.get("PieceText")))


def render_package_preview(
    tenant_id: int,
    lease_id: int,
    package_id: int,
    db: str = TEST_DB_NAME,
) -> dict[str, Any]:
    context = get_lease_merge_context(tenant_id=tenant_id, lease_id=lease_id, db=db)
    raw_text = assemble_package_text(package_id=package_id, db=db)
    rendered_text, unresolved = render_text_template(raw_text, context)
    validation = validate_template_tokens(raw_text, context)
    return {
        "tenant_id": tenant_id,
        "lease_id": lease_id,
        "package_id": package_id,
        "context": context,
        "rendered_text": rendered_text,
        "unresolved_tokens": unresolved,
        "validation": validation,
    }


def save_generated_lease_snapshot(
    tenant_id: int,
    lease_id: int,
    package_id: int,
    rendered_text: str,
    context: dict[str, Any],
    output_path: str = "",
    db: str = TEST_DB_NAME,
) -> int:
    """
    Optional audit trail insert.

    Requires the table from lease_generated_documents.sql.
    Returns the new GeneratedLeaseDocumentID.
    """
    if not _table_exists("GeneratedLeaseDocuments", db):
        raise ValueError("GeneratedLeaseDocuments table does not exist. Run lease_generated_documents.sql first.")

    now = dt.datetime.now()
    run_exec(
        "INSERT INTO GeneratedLeaseDocuments "
        "(TenantID, LeaseID, LeaseDocumentPackageID, GeneratedOn, OutputPath, MergeContextJson, RenderedText) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            tenant_id,
            lease_id,
            package_id,
            now,
            output_path,
            json.dumps(context, default=str, indent=2),
            rendered_text,
        ),
        db=db,
    )

    row = _first(run_query(
        "SELECT TOP 1 GeneratedLeaseDocumentID FROM GeneratedLeaseDocuments "
        "WHERE TenantID=? AND LeaseID=? AND LeaseDocumentPackageID=? "
        "ORDER BY GeneratedLeaseDocumentID DESC",
        (tenant_id, lease_id, package_id),
        db=db,
    ))
    return int(row.get("GeneratedLeaseDocumentID") or 0)

# Backward-compatible aliases used by the Reflex Lease Package Builder page.
def build_lease_context(db: str, tenant_id: int, lease_id: int) -> dict[str, str]:
    return get_lease_merge_context(tenant_id=tenant_id, lease_id=lease_id, db=db)


def merge_template(template_text: str, context: dict[str, Any]) -> str:
    rendered, _ = render_text_template(template_text, context)
    return rendered


def find_unresolved_tokens(rendered_text: str) -> list[str]:
    return extract_tokens(rendered_text)
