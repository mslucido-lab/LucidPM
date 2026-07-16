"""
Tally import utility — ported from Streamlit import_tally_row() and helpers.

Handles:
  - CSV parsing with normalized column name matching
  - Prospect matching by phone/email
  - Tenant creation with Prospect status
  - Contact creation
  - Emergency contact creation/flagging from Tally application notes
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


def _note_field(label: str, *keys: str) -> tuple[str, tuple[str, ...], str]:
    """Define a normalized Notes field and the CSV keys it consumes."""
    return (label, tuple(keys), "")


def _first_nonempty_with_prefix(row_norm: dict, *prefixes: str) -> str:
    """Return a value for exact normalized keys or keys that start with a prefix."""
    for key in prefixes:
        val = row_norm.get(key, "")
        if val and str(val).strip():
            return str(val).strip()
    for key, val in row_norm.items():
        if key == "_raw":
            continue
        if any(str(key).startswith(prefix) for prefix in prefixes):
            if val and str(val).strip():
                return str(val).strip()
    return ""




def _raw_value_by_excel_column(row_norm: dict, excel_col: str) -> str:
    """Return a raw CSV value by Excel-style column letter.

    Tally exports can produce duplicate or shifting labels after normalization.
    For fields confirmed by position, use the original CSV column order.
    Example: Q/R/S = emergency contact name/phone/email.
    """
    raw = row_norm.get("_raw") or {}
    if not raw:
        return ""
    letters = str(excel_col or "").strip().upper()
    idx = 0
    for ch in letters:
        if not ("A" <= ch <= "Z"):
            return ""
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    idx -= 1
    values = list(raw.values())
    if 0 <= idx < len(values):
        return str(values[idx] or "").strip()
    return ""

def _build_address_block(row_norm: dict) -> str:
    """Build the applicant address block from the confirmed CSV columns.

    Tally column mapping confirmed by Mark:
      L = Address Line 1
      M = Address Line 2
      N = City
      O = State
      P = Zip Code

    Keep this separate from Owner 1 Address. Owner 1 Address comes from the
    owner-address fields only.
    """
    line1 = _raw_value_by_excel_column(row_norm, "L") or pick(
        row_norm, "addressline1", "address1", "streetaddress", "street"
    )
    line2 = _raw_value_by_excel_column(row_norm, "M") or pick(
        row_norm, "addressline2", "address2", "unit", "suite", "apt"
    )
    city = _raw_value_by_excel_column(row_norm, "N") or pick(row_norm, "city")
    state = _raw_value_by_excel_column(row_norm, "O") or pick(row_norm, "state")
    zip_code = _raw_value_by_excel_column(row_norm, "P") or pick(row_norm, "zipcode", "zip", "postalcode")

    city_state = ", ".join(part for part in [city, state] if part)
    city_state_zip = " ".join(part for part in [city_state, zip_code] if part).strip()
    return "\n".join(part for part in [line1, line2, city_state_zip] if part)


def _note_value(label: str, keys: tuple[str, ...], row_norm: dict) -> str:
    if label == "Emergency contact name":
        return _raw_value_by_excel_column(row_norm, "Q") or pick(row_norm, *keys)
    if label == "Emergency contact phone":
        return _raw_value_by_excel_column(row_norm, "R") or pick(row_norm, *keys)
    if label == "Emergency contact email":
        return _raw_value_by_excel_column(row_norm, "S") or pick(row_norm, *keys)
    if label == "Address":
        return _build_address_block(row_norm)
    if label == "Present address":
        return _raw_value_by_excel_column(row_norm, "U") or pick(row_norm, *keys)
    if label in {"Reference 1 name", "Reference 2 name", "Reference 3 name"}:
        n = label.split()[1]
        return _first_nonempty_with_prefix(row_norm, f"referencename{n}", f"tradereferencename{n}", f"tradereference{n}name", f"reference{n}name")
    if label in {"Reference 1 years doing business", "Reference 2 years doing business", "Reference 3 years doing business"}:
        n = label.split()[1]
        return _first_nonempty_with_prefix(row_norm, f"yearsdoingbusiness{n}", f"reference{n}years", f"yearsbusiness{n}")
    if label in {"Reference 1 phone", "Reference 2 phone", "Reference 3 phone"}:
        n = label.split()[1]
        return _first_nonempty_with_prefix(row_norm, f"referencephonenumber{n}", f"referencephone{n}", f"tradereferencephone{n}")
    return pick(row_norm, *keys)


NOTE_FIELD_DEFS: list[tuple[str, tuple[str, ...], str]] = [
    _note_field("Application date", "applicationdate", "date", "submittedat", "submissiondate"),
    _note_field("Business", "businessname", "companyname", "dbaname"),
    _note_field("Business email", "email2", "businessemail"),
    _note_field("Business phone", "businessphone"),
    _note_field("Property interest", "propertyofinterest", "propertyinterest"),
    _note_field("Desired sq ft", "desiredsquarefootage", "desiredsqft", "squarefootage"),
    _note_field("Desired move-in", "desiredmoveindate", "moveindate"),
    _note_field("Monthly budget", "monthlyrentbudget"),
    _note_field("Owner name", "nameofowner", "ownername", "ownername1"),
    _note_field("Owner 1 address", "owneraddress1", "owner1address", "owneraddress"),
    _note_field("Owner 1 phone", "ownerphone1", "owner1phone", "ownerphone"),
    _note_field("Nature of business", "natureofbusiness", "natureofthebusiness", "businessdescription"),
    _note_field("Annual sales", "annualsales", "estimatedannualsales"),
    _note_field("Bank name", "bankname", "nameofyourbank", "bank"),
    _note_field("Dun & Bradstreet", "dunandbradstreet", "dunbradstreet", "ratedindunandbradstreet", "ratedindunampbradstreet", "dunbradstreetrating"),
    _note_field("Bankruptcy", "bankruptcy", "haveyoueverfiledforbankruptcy"),
    _note_field("Remarks", "additionalremarks", "additionalremarksandinformation", "remarks", "notes"),
    _note_field("Address", "addressline1", "addressline2", "address1", "address2", "streetaddress", "city", "state", "zipcode", "zip"),
    _note_field("Present address", "presentaddress", "currentaddress", "homeaddress"),
    _note_field("City", "city2", "currentcity", "presentcity"),
    _note_field("State", "state2", "currentstate", "presentstate"),
    _note_field("Zip", "zipcode2", "zip2", "currentzip", "presentzip"),
    _note_field("Emergency contact name", "emergencycontactname", "emergencyname", "contactname"),
    _note_field("Emergency contact phone", "emergencycontactphone", "emergencyphone", "contactphone", "contactphonenumber"),
    _note_field("Emergency contact email", "emergencycontactemail", "emergencyemail", "contactemail"),
    _note_field("When established", "dateestablished", "whenestablished", "yearestablished", "businessestablished"),
    _note_field("Payment contact", "paymentcontact", "paymentcontactname", "whotocontactregardingpayment"),
    _note_field("Payment contact phone", "paymentcontactphone", "paymentphone", "paymentcontactphonenumber"),
    _note_field("Payment contact email", "paymentcontactemail", "paymentemail"),
    _note_field("Form of business", "formofbusiness", "businessform", "businesstype", "businessstructure"),
    _note_field("Business website", "website", "businesswebsite", "webaddress"),
    _note_field("Reference 1 name", "referencename1", "tradereferencename1", "tradereference1name", "reference1name"),
    _note_field("Reference 1 years doing business", "yearsdoingbusiness1", "reference1years", "yearsbusiness1"),
    _note_field("Reference 1 phone", "referencephonenumber1", "referencephone1", "tradereferencephone1"),
    _note_field("Reference 2 name", "referencename2", "tradereferencename2", "tradereference2name", "reference2name"),
    _note_field("Reference 2 years doing business", "yearsdoingbusiness2", "reference2years", "yearsbusiness2"),
    _note_field("Reference 2 phone", "referencephonenumber2", "referencephone2", "tradereferencephone2"),
    _note_field("Reference 3 name", "referencename3", "tradereferencename3", "tradereference3name", "reference3name"),
    _note_field("Reference 3 years doing business", "yearsdoingbusiness3", "reference3years", "yearsbusiness3"),
    _note_field("Reference 3 phone", "referencephonenumber3", "referencephone3", "tradereferencephone3"),
    _note_field("Personal reference 1", "personalreference1", "personalreference1name"),
    _note_field("Personal reference 2", "personalreference2", "personalreference2name"),
    _note_field("Personal reference 3", "personalreference3", "personalreference3name"),
]
# CSV fields consumed by screen fields, encrypted fields, or standardized Notes fields.
# These are not repeated in the unmapped/raw section.
HANDLED_TALLY_KEYS: set[str] = {
    "firstname", "first", "givenname", "lastname", "last", "surname", "familyname",
    "individualname", "fullname", "applicantname", "name",
    "email", "phonenumber", "phone", "cellphone",
    "socialsecurity", "socialsecuritynumber", "ssn", "socsecno",
    "driverslicense", "driverlicensenumberstate", "driverslicensenumberstate",
    "dlnumberstate", "dlnostate", "dob", "dateofbirth", "birthdate",
}
for _, keys, _ in NOTE_FIELD_DEFS:
    HANDLED_TALLY_KEYS.update(keys)


def _build_unmapped_tally_notes(row_norm: dict) -> list[str]:
    """Return original CSV fields that were not mapped elsewhere.

    Uses the original CSV headers for readability. Blank values are skipped.
    Sensitive values that are handled through encrypted fields are not duplicated here.
    """
    raw = row_norm.get("_raw") or {}
    unmapped = []
    for idx, (raw_key, raw_value) in enumerate(raw.items()):
        # Columns L-P are explicitly mapped to Applicant Address.
        # Columns Q/R/S are explicitly mapped to Emergency Contact name/phone/email.
        # Do not repeat these in the raw unmapped section.
        if idx in {11, 12, 13, 14, 15, 16, 17, 18}:
            continue
        key_norm = normalize_col(raw_key)
        value = str(raw_value or "").strip()
        if not key_norm or not value or key_norm in HANDLED_TALLY_KEYS:
            continue
        label = str(raw_key or key_norm).strip() or key_norm
        unmapped.append(f"Tally - {label}: {value}")
    return unmapped


def _build_import_notes(row_norm: dict) -> str:
    lines = []

    applicant = _build_full_name(row_norm)
    if applicant:
        lines.append(f"Applicant: {applicant}")

    for label, keys, _ in NOTE_FIELD_DEFS:
        value = _note_value(label, keys, row_norm)
        if value:
            lines.append(f"{label}: {value}")

    unmapped_lines = _build_unmapped_tally_notes(row_norm)
    if unmapped_lines:
        lines.append("Unmapped Tally fields:")
        lines.extend(unmapped_lines)

    lines.append("Imported from: Tally application")
    return "\n".join(lines)


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



# ── Emergency contact import ──────────────────────────────────────────────────

def _ensure_emergency_contact_column(db: str) -> None:
    """Ensure Contacts.IsEmergencyContact exists before Tally auto-import uses it."""
    run_exec(
        "IF COL_LENGTH('dbo.Contacts', 'IsEmergencyContact') IS NULL "
        "BEGIN "
        "ALTER TABLE dbo.Contacts ADD IsEmergencyContact BIT NOT NULL "
        "CONSTRAINT DF_Contacts_IsEmergencyContact DEFAULT 0 "
        "END",
        (),
        db=db,
    )


def _parse_notes_dict(notes: str) -> dict:
    """Parse simple key/value notes generated by _build_import_notes()."""
    result = {}
    current_key = ""
    for line in str(notes or "").split("\n"):
        raw = str(line or "").rstrip()
        if not raw.strip():
            continue
        if ":" in raw:
            key, _, value = raw.partition(":")
            current_key = key.strip().lower()
            result[current_key] = value.strip()
        elif current_key:
            existing = result.get(current_key, "")
            result[current_key] = (existing + "\n" + raw.strip()).strip() if existing else raw.strip()
    return result


def _split_name(full_name: str) -> tuple[str, str]:
    parts = [p for p in str(full_name or "").strip().split() if p]
    if not parts:
        return "", ""
    first = parts[0]
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first, last


def _contact_row_matches(contact: dict, phone: str, email: str) -> bool:
    target_phone = digits_only(phone)
    target_email = str(email or "").strip().lower()
    if target_phone:
        for key in ("WorkPhone", "HomePhone"):
            if digits_only(str(contact.get(key) or "")) == target_phone:
                return True
    if target_email:
        for key in ("Email1", "Email2"):
            if str(contact.get(key) or "").strip().lower() == target_email:
                return True
    return False


def _name_is_self_or_applicant(emergency_name: str, applicant_name: str) -> bool:
    n = str(emergency_name or "").strip().lower()
    applicant = str(applicant_name or "").strip().lower()
    if n in {"self", "same", "same as applicant", "applicant", "myself", "me"}:
        return True
    return bool(n and applicant and n == applicant)


def _import_emergency_contact_from_notes(
    tenant_id: int,
    notes: str,
    applicant_name: str,
    applicant_phone: str,
    applicant_email: str,
    db: str,
) -> str:
    """Create or flag the emergency contact created by a Tally application import.

    Rules:
    - One emergency contact per tenant.
    - Match an existing contact by phone first, then email.
    - If the Tally value is Self / Applicant, mark the existing primary/applicant contact.
    - If no match exists and no emergency contact already exists, create a new blank-role contact.
    """
    tenant_id = int(tenant_id or 0)
    if tenant_id <= 0:
        return "no_tenant"

    _ensure_emergency_contact_column(db)

    parsed = _parse_notes_dict(notes)
    emergency_name = parsed.get("emergency contact name", "")
    emergency_phone = parsed.get("emergency contact phone", "")
    emergency_email = parsed.get("emergency contact email", "")

    if not (emergency_name or emergency_phone or emergency_email):
        return "no_emergency_contact_data"

    contacts = run_query(
        "SELECT ContactID, FirstName, LastName, WorkPhone, HomePhone, Email1, Email2, "
        "IsPrimary, IsEmergencyContact "
        "FROM Contacts WHERE TenantID = ? ORDER BY IsPrimary DESC, ContactID",
        (tenant_id,),
        db=db,
    )

    existing_emergency_id = 0
    for c in contacts:
        if bool(c.get("IsEmergencyContact")):
            existing_emergency_id = int(c.get("ContactID") or 0)
            break

    match = None
    for c in contacts:
        if _contact_row_matches(c, emergency_phone, emergency_email):
            match = c
            break

    if match is None and _name_is_self_or_applicant(emergency_name, applicant_name):
        if not contacts:
            _ensure_primary_contact(tenant_id, applicant_name, applicant_email, applicant_phone, db)
            contacts = run_query(
                "SELECT ContactID, FirstName, LastName, WorkPhone, HomePhone, Email1, Email2, "
                "IsPrimary, IsEmergencyContact "
                "FROM Contacts WHERE TenantID = ? ORDER BY IsPrimary DESC, ContactID",
                (tenant_id,),
                db=db,
            )
        match = contacts[0] if contacts else None

    if match is not None:
        match_id = int(match.get("ContactID") or 0)
        if existing_emergency_id and existing_emergency_id != match_id:
            return "skipped_existing_emergency"
        run_exec(
            "UPDATE Contacts SET IsEmergencyContact = 1 WHERE ContactID = ? AND TenantID = ?",
            (match_id, tenant_id),
            db=db,
        )
        return "marked_existing"

    if existing_emergency_id:
        return "skipped_existing_emergency"

    create_name = applicant_name if _name_is_self_or_applicant(emergency_name, applicant_name) else emergency_name
    first, last = _split_name(create_name)
    run_exec(
        "INSERT INTO Contacts (TenantID, Salutation, FirstName, LastName, Title, ContactRole, "
        "WorkPhone, HomePhone, Email1, Email2, IsPrimary, IsEmergencyContact) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tenant_id,
            "",
            first,
            last,
            "",
            None,
            str(emergency_phone or "").strip(),
            "",
            str(emergency_email or "").strip().lower(),
            "",
            0,
            1,
        ),
        db=db,
    )
    return "created_new"

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
        # Even when the tenant already exists, use the current Tally row to
        # create or mark the emergency contact if possible.
        _import_emergency_contact_from_notes(
            tenant_id, notes, applicant_name, phone, email, db
        )
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

    # Create or mark the emergency contact from the imported application notes.
    _import_emergency_contact_from_notes(
        tenant_id, tenant_notes, applicant_name, phone, email, db
    )

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
