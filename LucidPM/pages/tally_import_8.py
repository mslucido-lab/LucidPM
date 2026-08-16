"""
Tally import utility — ported from Streamlit import_tally_row() and helpers.

Handles:
  - CSV parsing with normalized column name matching
  - Prospect matching by phone/email
  - Tenant creation with Prospect status
  - Contact creation
  - SSN/DL encryption via Fernet (TENANTCRM_FERNET_KEY env var)
"""

import os
import re
import csv
import io
import datetime
from typing import Optional

from LucidPM_Reflex.state import run_query, run_exec, get_conn, TEST_DB_NAME


# ── Encryption ────────────────────────────────────────────────────────────────

def get_cipher():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError("cryptography package not installed. Run: pip install cryptography")
    key = os.environ.get("TENANTCRM_FERNET_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing TENANTCRM_FERNET_KEY environment variable.")
    return Fernet(key.encode("utf-8"))


def encrypt_text(value: str) -> Optional[str]:
    if not value or not str(value).strip():
        return None
    return get_cipher().encrypt(str(value).strip().encode("utf-8")).decode("utf-8")


def digits_only(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def last4(value: str) -> str:
    d = digits_only(value)
    return d[-4:] if len(d) >= 4 else d


# ── CSV parsing ───────────────────────────────────────────────────────────────

def normalize_col(name: str) -> str:
    """Strip non-alphanumeric chars and lowercase — for fuzzy column matching."""
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


def parse_tally_csv(file_bytes: bytes) -> list[dict]:
    """
    Parse a Tally CSV export. Returns list of dicts with normalized keys.
    Handles UTF-8 BOM and various line endings.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for raw_row in reader:
        normalized = {normalize_col(k): str(v or "").strip() for k, v in raw_row.items()}
        normalized["_raw"] = raw_row  # keep original for display
        rows.append(normalized)
    return rows


def pick(row_norm: dict, *candidates: str) -> str:
    """Return first non-empty value from normalized row for given candidate keys."""
    for key in candidates:
        val = row_norm.get(key, "")
        if val and str(val).strip():
            return str(val).strip()
    return ""


def _build_full_name(row_norm: dict) -> str:
    """
    Build applicant full name from Tally fields.
    Priority: first+last combination → individual name fields → full name fields.
    NOTE: contactname is the emergency/business contact, NOT the applicant — excluded.
    """
    # Best: explicit first + last name fields (Tally standard layout)
    first = pick(row_norm, "firstname", "first", "givenname")
    last  = pick(row_norm, "lastname", "last", "surname", "familyname")
    if first or last:
        return " ".join(p for p in [first, last] if p).strip()
    # Fallback: other full-name fields (but NOT contactname — that's the business contact)
    return pick(row_norm, "individualname", "fullname", "applicantname", "name")


def preview_rows(rows: list[dict]) -> list[dict]:
    """Extract display fields from parsed rows for preview table."""
    out = []
    for r in rows:
        out.append({
            "Name":     _build_full_name(r),
            "Business": pick(r, "businessname", "companyname", "dbaname"),
            "Email":    pick(r, "email", "businessemail"),
            "Phone":    pick(r, "phonenumber", "phone", "businessphone"),
            "Property": pick(r, "propertyofinterest", "propertyinterest"),
            "Move-in":  pick(r, "desiredmoveindate", "moveindate"),
        })
    return out


# ── Import logic ──────────────────────────────────────────────────────────────

def _to_date(val: str) -> Optional[datetime.date]:
    if not val or not val.strip():
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _get_prospect_status_id(db: str) -> Optional[int]:
    rows = run_query(
        "SELECT TenantStatusID FROM TenantStatuses WHERE TenantStatusName = 'Applicant'",
        db=db,
    )
    return int(rows[0]["TenantStatusID"]) if rows else None


def _get_default_type_id(db: str) -> Optional[int]:
    rows = run_query(
        "SELECT TOP 1 TenantTypeID FROM TenantTypes ORDER BY TenantTypeID",
        db=db,
    )
    return int(rows[0]["TenantTypeID"]) if rows else None


def _get_property_id_by_name(name: str, db: str) -> Optional[int]:
    if not name:
        return None
    wanted = name.strip().lower()
    rows = run_query("SELECT PropertyID, PropertyName FROM Properties", db=db)
    for r in rows:
        label = str(r["PropertyName"] or "").strip().lower()
        if label == wanted or wanted in label or label in wanted:
            return int(r["PropertyID"])
    return None


def _get_default_property_id(db: str) -> Optional[int]:
    rows = run_query("SELECT TOP 1 PropertyID FROM Properties ORDER BY PropertyID", db=db)
    return int(rows[0]["PropertyID"]) if rows else None


def _get_matching_prospect(applicant_name: str, phone: str, email: str, db: str) -> Optional[dict]:
    """
    Match Tally submission to existing Waiting List Prospect.
    Priority: 1) Full name match, 2) Phone match, 3) Email match.
    Includes already-converted prospects to prevent duplicate tenant creation.
    """
    rows = run_query(
        "SELECT ProspectID, ProspectName, PropertyID, Phone, Email, "
        "DesiredUnitType, DesiredSize, DesiredMoveInDate, BudgetRange, "
        "Source, ProspectStatus, LastContactDate, Notes, ConvertedTenantID "
        "FROM Prospects "
        "ORDER BY DateCreated DESC, ProspectID DESC",
        db=db,
    )

    target_name  = str(applicant_name or "").strip().lower()
    target_phone = digits_only(phone)
    target_email = str(email or "").strip().lower()

    # 1. Name match — Tally first+last vs Prospect name
    if target_name:
        for r in rows:
            prospect_name = str(r.get("ProspectName") or "").strip().lower()
            if prospect_name and prospect_name == target_name:
                return r

    # 2. Phone match
    if target_phone:
        for r in rows:
            if digits_only(str(r.get("Phone") or "")) == target_phone:
                return r

    # 3. Email match
    if target_email:
        for r in rows:
            if str(r.get("Email") or "").strip().lower() == target_email:
                return r

    return None


def _build_import_notes(row_norm: dict) -> str:
    mapping = [
        ("Applicant",          _build_full_name(row_norm)),
        ("Business",           pick(row_norm, "businessname", "companyname", "dbaname")),
        ("Business email",     pick(row_norm, "email2", "businessemail")),
        ("Business phone",     pick(row_norm, "businessphone")),
        ("Property interest",  pick(row_norm, "propertyofinterest", "propertyinterest")),
        ("Desired sq ft",      pick(row_norm, "desiredsquarefootage", "desiredsqft", "squarefootage")),
        ("Desired move-in",    pick(row_norm, "desiredmoveindate", "moveindate")),
        ("Monthly budget",     pick(row_norm, "monthlyrentbudget")),
        ("Owner name",         pick(row_norm, "nameofowner", "ownername", "ownername1")),
        ("Nature of business", pick(row_norm, "natureofbusiness", "natureofthebusiness", "businessdescription")),
        ("Annual sales",       pick(row_norm, "annualsales", "estimatedannualsales")),
        ("Bankruptcy",         pick(row_norm, "bankruptcy", "haveyoueverfiledforbankruptcy")),
        ("Remarks",            pick(row_norm, "additionalremarks", "additionalremarksandinformation", "remarks", "notes")),
        ("Address",               pick(row_norm, "address", "homeaddress", "currentaddress")),
        ("Emergency contact name", pick(row_norm, "emergencycontactname", "emergencyname", "contactname")),
        ("Emergency contact phone", pick(row_norm, "emergencycontactphone", "emergencyphone", "contactphone", "contactphonenumber")),
        ("Emergency contact email", pick(row_norm, "emergencycontactemail", "emergencyemail", "contactemail")),
        ("When established",      pick(row_norm, "dateestablished", "whenestablished", "yearestablished", "businessestablished")),
        ("Payment contact",       pick(row_norm, "paymentcontact", "paymentcontactname", "whotocontactregardingpayment")),
        ("Payment contact phone", pick(row_norm, "paymentcontactphone", "paymentphone", "paymentcontactphonenumber")),
        ("Payment contact email", pick(row_norm, "paymentcontactemail", "paymentemail")),
        ("Form of business",      pick(row_norm, "formofbusiness", "businessform", "businesstype", "businessstructure")),
        ("Business website",      pick(row_norm, "website", "businesswebsite", "webaddress")),
        ("Trade reference 1",     pick(row_norm, "tradereference1", "tradereference1name", "reference1name")),
        ("Trade reference 2",     pick(row_norm, "tradereference2", "tradereference2name", "reference2name")),
        ("Trade reference 3",     pick(row_norm, "tradereference3", "tradereference3name", "reference3name")),
        ("Personal reference 1",  pick(row_norm, "personalreference1", "personalreference1name")),
        ("Personal reference 2",  pick(row_norm, "personalreference2", "personalreference2name")),
        ("Personal reference 3",  pick(row_norm, "personalreference3", "personalreference3name")),
        ("Imported from",      "Tally application"),
    ]
    return "\n".join(f"{label}: {value}" for label, value in mapping if value)


def _append_note(existing: str, title: str, body: str) -> str:
    existing = str(existing or "").strip()
    body = str(body or "").strip()
    if not body:
        return existing
    section = f"{title}: {body}"
    if not existing:
        return section
    if section in existing:
        return existing
    return existing + "\n" + section


def _ensure_primary_contact(tenant_id: int, full_name: str, email: str, phone: str, db: str) -> int:
    existing = run_query(
        "SELECT TOP 1 ContactID FROM Contacts WHERE TenantID=? ORDER BY IsPrimary DESC, ContactID",
        (tenant_id,), db=db,
    )
    if existing:
        return int(existing[0]["ContactID"])

    parts = [p for p in str(full_name or "").strip().split() if p]
    first = parts[0] if parts else ""
    last  = " ".join(parts[1:]) if len(parts) > 1 else ""

    run_exec(
        "INSERT INTO Contacts (TenantID, Title, FirstName, LastName, WorkPhone, HomePhone, "
        "Email1, Email2, ContactRole, IsPrimary, Salutation) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (tenant_id, "", first, last, str(phone or "").strip(), "",
         str(email or "").strip().lower(), "", "Applicant", True, ""),
        db=db,
    )
    created = run_query(
        "SELECT TOP 1 ContactID FROM Contacts WHERE TenantID=? ORDER BY IsPrimary DESC, ContactID DESC",
        (tenant_id,), db=db,
    )
    if not created:
        raise RuntimeError(f"Created contact for TenantID {tenant_id} but could not retrieve ContactID.")
    return int(created[0]["ContactID"])


def _save_sensitive_info(contact_id: int, ssn: str, dl_number: str, dob_str: str, db: str) -> None:
    ssn_clean = str(ssn or "").strip()
    dl_clean  = str(dl_number or "").strip()
    dob_value = _to_date(dob_str)
    now = datetime.datetime.now()

    ssn_enc   = encrypt_text(ssn_clean)
    dl_enc    = encrypt_text(dl_clean)
    ssn_last4 = last4(ssn_clean)
    dl_last4  = last4(dl_clean)

    existing = run_query(
        "SELECT ContactSensitiveInfoID FROM ContactSensitiveInfo WHERE ContactID=?",
        (contact_id,), db=db,
    )
    if existing:
        run_exec(
            "UPDATE ContactSensitiveInfo SET SSN_Encrypted=?, DL_Encrypted=?, DOB=?, "
            "Last4SSN=?, DL_Last4=?, UpdatedOn=? WHERE ContactID=?",
            (ssn_enc, dl_enc, dob_value, ssn_last4, dl_last4, now, contact_id),
            db=db,
        )
    else:
        run_exec(
            "INSERT INTO ContactSensitiveInfo "
            "(ContactID, SSN_Encrypted, DL_Encrypted, DOB, Last4SSN, DL_Last4, CreatedOn, UpdatedOn) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (contact_id, ssn_enc, dl_enc, dob_value, ssn_last4, dl_last4, now, now),
            db=db,
        )


def import_tally_row(row_norm: dict, db: str) -> tuple[str, Optional[int]]:
    """
    Import a single normalized Tally CSV row.
    Returns ("imported", tenant_id) or ("skipped", tenant_id).
    Raises RuntimeError on fatal errors.
    """
    applicant_name   = _build_full_name(row_norm)
    business_name    = pick(row_norm, "businessname", "companyname", "dbaname")
    email            = pick(row_norm, "email", "businessemail", "email2")
    phone            = pick(row_norm, "phonenumber", "phone", "businessphone", "cellphone")
    ssn              = pick(row_norm, "socialsecurity", "socialsecuritynumber", "ssn", "socsecno")
    dl_number        = pick(row_norm, "driverslicense", "driverlicensenumberstate",
                            "driverslicensenumberstate", "dlnumberstate", "dlnostate")
    dob_raw          = pick(row_norm, "dob", "dateofbirth", "birthdate")
    property_interest = pick(row_norm, "propertyofinterest", "propertyinterest")

    tenant_name = business_name or applicant_name
    if not tenant_name:
        raise RuntimeError("Could not determine tenant name from this row.")

    prospect_status_id = _get_prospect_status_id(db)
    if prospect_status_id is None:
        raise RuntimeError("Applicant status not found. Add 'Applicant' to TenantStatuses before importing.")

    property_id = _get_property_id_by_name(property_interest, db) or _get_default_property_id(db)
    type_id     = _get_default_type_id(db)
    notes       = _build_import_notes(row_norm)

    matched_prospect = _get_matching_prospect(applicant_name, phone, email, db)
    matched_prospect_id = int(matched_prospect["ProspectID"]) if matched_prospect else None

    # Check if tenant already exists
    existing = []
    if matched_prospect_id is not None:
        # If prospect was already manually converted, use that TenantID directly
        already_converted_id = matched_prospect.get("ConvertedTenantID") if matched_prospect else None
        if already_converted_id:
            existing = [{"TenantID": int(already_converted_id)}]
        else:
            existing = run_query(
                "SELECT TOP 1 TenantID FROM Tenants WHERE ProspectID=? ORDER BY TenantID DESC",
                (matched_prospect_id,), db=db,
            )
    if not existing:
        # Fallback: match by tenant name
        existing = run_query(
            "SELECT TOP 1 TenantID FROM Tenants WHERE TenantName=? ORDER BY TenantID DESC",
            (tenant_name,), db=db,
        )

    if existing:
        tenant_id = int(existing[0]["TenantID"])
        if matched_prospect_id:
            _update_prospect(matched_prospect_id, matched_prospect, tenant_id, row_norm, db)
        return ("skipped", tenant_id)

    # Build notes with waiting list context
    tenant_notes = notes
    if matched_prospect:
        wl_summary = _build_waiting_list_summary(matched_prospect)
        tenant_notes = _append_note(tenant_notes, "Waiting list record", wl_summary)

    # Insert tenant
    run_exec(
        "INSERT INTO Tenants (TenantName, Suite, PropertyID, TenantStatusID, TenantTypeID, Notes, ProspectID) "
        "VALUES (?,?,?,?,?,?,?)",
        (tenant_name.strip(), "", property_id, int(prospect_status_id), type_id,
         tenant_notes, matched_prospect_id),
        db=db,
    )

    # Retrieve new TenantID
    if matched_prospect_id:
        created = run_query(
            "SELECT TOP 1 TenantID FROM Tenants WHERE ProspectID=? ORDER BY TenantID DESC",
            (matched_prospect_id,), db=db,
        )
    else:
        created = run_query(
            "SELECT TOP 1 TenantID FROM Tenants WHERE TenantName=? ORDER BY TenantID DESC",
            (tenant_name.strip(),), db=db,
        )
    if not created:
        raise RuntimeError(f"Inserted tenant '{tenant_name}' but could not retrieve TenantID.")
    tenant_id = int(created[0]["TenantID"])

    if matched_prospect_id:
        _update_prospect(matched_prospect_id, matched_prospect, tenant_id, row_norm, db)

    # Create contact record
    contact_id = None
    if applicant_name or email or phone:
        contact_id = _ensure_primary_contact(tenant_id, applicant_name, email, phone, db)

    # Encrypt and store sensitive info
    if contact_id and (ssn or dl_number or dob_raw):
        _save_sensitive_info(contact_id, ssn, dl_number, dob_raw, db)

    return ("imported", tenant_id)


def _build_waiting_list_summary(p: dict) -> str:
    parts = []
    for label, key in [
        ("Name",          "ProspectName"),
        ("Source",        "Source"),
        ("Phone",         "Phone"),
        ("Email",         "Email"),
        ("Desired unit",  "DesiredUnitType"),
        ("Desired size",  "DesiredSize"),
        ("Budget",        "BudgetRange"),
        ("Notes",         "Notes"),
    ]:
        val = str(p.get(key) or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    move_in = p.get("DesiredMoveInDate")
    if move_in:
        d = move_in.date() if hasattr(move_in, "date") else move_in
        parts.append(f"Desired move-in: {d.strftime('%m/%d/%Y')}")
    return " | ".join(parts)


def _update_prospect(prospect_id: int, prospect_row: dict, tenant_id: int,
                     row_norm: dict, db: str) -> None:
    applicant = _build_full_name(row_norm)
    business  = pick(row_norm, "businessname", "companyname", "dbaname")
    email     = pick(row_norm, "email", "businessemail", "email2")
    phone     = pick(row_norm, "phonenumber", "phone", "businessphone")
    prop_int  = pick(row_norm, "propertyofinterest", "propertyinterest")
    desired_size = pick(row_norm, "desiredsquarefootage", "desiredsqft", "squarefootage")
    move_in   = pick(row_norm, "desiredmoveindate", "moveindate")
    budget    = pick(row_norm, "monthlyrentbudget")
    now       = datetime.datetime.now()

    prospect_name = str(prospect_row.get("ProspectName") or "").strip() or business or applicant
    prop_id = (prospect_row.get("PropertyID")
               or _get_property_id_by_name(prop_int, db)
               or _get_default_property_id(db))
    current_notes = str(prospect_row.get("Notes") or "").strip()
    merged_notes  = _append_note(current_notes, "Application import", _build_import_notes(row_norm))

    run_exec(
        "UPDATE Prospects SET ProspectName=?, PropertyID=?, Phone=?, Email=?, "
        "DesiredSize=?, DesiredMoveInDate=?, BudgetRange=?, ProspectStatus=?, "
        "Notes=?, DateModified=?, ConvertedTenantID=? WHERE ProspectID=?",
        (
            prospect_name.strip(),
            int(prop_id) if prop_id else None,
            str(prospect_row.get("Phone") or "").strip() or phone,
            str(prospect_row.get("Email") or "").strip().lower() or email.lower(),
            str(prospect_row.get("DesiredSize") or "").strip() or desired_size,
            _to_date(str(prospect_row.get("DesiredMoveInDate") or "")) or _to_date(move_in),
            str(prospect_row.get("BudgetRange") or "").strip() or budget,
            "Application Submitted",
            merged_notes, now, int(tenant_id), int(prospect_id),
        ),
        db=db,
    )
