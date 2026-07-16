"""
Lucid Property Manager - Lease Merge Utility
v0.1.8

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
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from LucidPM_Reflex.state import run_query, run_exec, TEST_DB_NAME

TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_\.\-]+)\s*\}\}")

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

def fmt_money(value: Any, decimals: int = 2) -> str:
    try:
        amount = Decimal(str(value or "0"))
    except InvalidOperation:
        return ""
    return f"${amount:,.{decimals}f}"

def get_lease_merge_context(tenant_id: int, lease_id: int, db: str = TEST_DB_NAME) -> dict[str, str]:
    lease = _first(run_query(
        "SELECT l.*, t.TenantName FROM Leases l LEFT JOIN Tenants t ON l.TenantID = t.TenantID WHERE l.LeaseID = ? AND l.TenantID = ?",
        (lease_id, tenant_id),
        db=db,
    ))
    if not lease:
        raise ValueError(f"Lease not found for TenantID={tenant_id}, LeaseID={lease_id}.")

    return {
        "TenantName": _s(lease.get("TenantName")),
        "LeaseStartDate": fmt_date(lease.get("LeaseStart")),
        "LeaseEndDate": fmt_date(lease.get("LeaseEnd")),
        "MonthlyRent": fmt_money(lease.get("RentAmount")),
    }

def render_text_template(template_text: str, context: dict[str, Any]) -> tuple[str, list[str]]:
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

def save_generated_lease_snapshot(
    tenant_id: int,
    lease_id: int,
    package_id: int,
    rendered_text: str,
    context: dict[str, Any],
    output_path: str = "",
    db: str = TEST_DB_NAME,
) -> int:
    now = dt.datetime.now()
    run_exec(
        "INSERT INTO GeneratedLeaseDocuments (TenantID, LeaseID, LeaseDocumentPackageID, GeneratedOn, OutputPath, MergeContextJson, RenderedText) VALUES (?,?,?,?,?,?,?)",
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
        "SELECT TOP 1 GeneratedLeaseDocumentID FROM GeneratedLeaseDocuments WHERE TenantID=? AND LeaseID=? AND LeaseDocumentPackageID=? ORDER BY GeneratedLeaseDocumentID DESC",
        (tenant_id, lease_id, package_id),
        db=db,
    ))
    return int(row.get("GeneratedLeaseDocumentID") or 0)
