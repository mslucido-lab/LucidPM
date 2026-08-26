# LucidoPM — ChatGPT Handoff 51
*Tenant DBA Flag — Schema Column + Merge Token Wiring*
*Prepared: 2026-08-26*

---

## What This Is

Two merge tokens, `{{DBAName}}` and `{{TenantNameWithDBA}}`, have existed in `lease_merge.py` and the Section Library's "Tenant" token-picker group since before this session — but `DBAName` is hardcoded to always return `""`. There is no DBA (`d.b.a.` / trade name) concept anywhere in the data model, so these tokens have never been able to resolve to a real value. This handoff wires them up properly.

**Design, finalized with Mark before writing this handoff — read this before implementing, it is not the obvious/naive design:**

- `Tenants.TenantName` is always the business/trade name, regardless of entity type (`TenantTypeID` — Individual, LLC, Corporation, Partnership, Sole Proprietorship, etc. — already exists and is untouched by this handoff).
- A new **boolean flag**, `Tenants.IsDBA`, is the trigger — not a free-text "DBA name" field. There is no separate DBA name to store: legally, a d.b.a. situation is an *individual* (or individuals, as a partnership) operating under a business name without a separate legal entity. The business name **is** `TenantName`; the flag just says "the party behind this name is an individual/partnership operating under it, not the name of a legal entity in its own right."
- The individual name(s) printed before "d.b.a." come from **`Contacts` where `ContactRole = 'Guarantor'`** — deliberately, not a new `'Owner'` role (that was floated and rejected). Reasoning: in a genuine DBA/sole-proprietorship arrangement there is no separate legal entity shielding the individual, so "who is ultimately responsible for this lease" (the guarantor concept) and "who is the DBA party" are the same person(s) by definition. This also means **no new Contacts data entry is needed** for tenants that already have Guarantor contacts on file — this handoff is purely additive on top of the guarantor-name-joining fix already shipped this session (see `TenantNameWithGuarantor`, `lease_merge.py:743-747`).
- The flag is **fully independent of `TenantTypeID`** — the system does not gate or infer it from entity type. It is a manual, per-tenant decision made by whoever enters the tenant, exactly like every other boolean flag in this schema (`IsActive`, `IsReusable`, etc.).

**Known real-world data problem, explicitly NOT part of this handoff:** tenant "4C's Mechanical, LLC" (`TenantID` 40) currently has `TenantTypeID = LLC` and `TenantName = "4C's Mechanical, LLC"`, but its actual signed lease names the tenant as "Carlos Cruz and Christopher Carter d.b.a. 4C's Mechanical" — no LLC at all. Cleaning up that specific tenant's `TenantName`/`TenantTypeID`/`IsDBA` is a data-entry task for Mark to do himself (via the UI this handoff builds), not a script or migration in this handoff. Do not "fix" this tenant's data as part of implementing this — just build the mechanism.

**Two files/targets change: a new `db/history/` migration script (run against both `TenantCRM_Test` and `TenantCRM`), `LucidPM/pages/tenants.py`, and `LucidPM/lease_merge.py`. No changes to the PDF renderer or the token picker — `{{DBAName}}`/`{{TenantNameWithDBA}}` are already listed there (`lease_documents.py`, "Tenant" token group).**

---

## Current State

### Schema

`dbo.Tenants` columns are identical in both databases today (confirmed via `INFORMATION_SCHEMA.COLUMNS`): `TenantID, TenantName, Notes, TenantTypeID, TenantStatusID, PropertyID, Suite, ProspectID, SuiteID`. No DBA-related column exists. `TenantTypes` (already populated, unchanged by this handoff): Individual, LLC, Corporation, Partnership, Nonprofit, Government, Sole Proprietorship, PLLC.

### Dead tokens

`LucidPM/lease_merge.py`, in `get_lease_merge_context()`:

```python
"DBAName": "",
"TenantNameWithDBA": _s(lease.get("TenantName")),
```
(lines 769-770)

```python
context["TenantNameWithDBAUpper"] = context.get("TenantNameWithDBA", "").upper()
```
(line 900 — needs no change, it derives from `TenantNameWithDBA` and will pick up the real value automatically)

The guarantor name(s), already correctly joined this session (multiple guarantors handled, e.g. `"Chris Carter and Carlos Cruz"`), are already computed as the local variable `guarantor_name` earlier in this same function (`lease_merge.py`, the guarantor lookup block a few lines above the `context = {` dict literal). This handoff reuses that value directly — no new lookup or joining logic needed.

Both `{{DBAName}}` and `{{TenantNameWithDBA}}` are already listed in the "Tenant" token-picker group in `LucidPM/pages/lease_documents.py` — no picker changes needed here.

### Tenant edit form

`LucidPM/pages/tenants.py`, class `TenantState`:

- Display fields loaded by `_load_tenant_detail()` (lines 966-1010) from a single `SELECT` (lines 967-976) — e.g. `self.tenant_notes = str(r.get("Notes") or "")` at line 989.
- Edit-form fields (`f_tenant_*`) declared at lines 392-400, populated from the display fields in `start_edit_tenant()` (lines 1816-1829) and reset to blank in `start_new_tenant()` (lines 1831-1845).
- Explicit setters declared at lines 1852-1855 (e.g. `def set_f_tenant_notes(self, v: str): self.f_tenant_notes = v`).
- Save happens via plain `INSERT`/`UPDATE` against `Tenants` (lines 1895-1901 and 1914-1920).
- Boolean flags elsewhere in this same file are edited with `rx.switch(checked=..., on_change=...)` (e.g. line 4022) — that's the existing convention to follow, not a checkbox.

---

## The Fix

### Part A — Schema migration

New file: `db/history/012_2026-08-26_add_tenant_isdba_flag.sql` (adjust the timestamp in the filename to when it's actually run, per the `db/history/CHANGELOG.md` naming convention). Follow the exact idempotent-guard + `SchemaChangeLog` idiom used by every other script in `db/history/` (e.g. `011_2026-05-01_0918_phase5_sprint2_nullable_source_document.sql`):

```sql
-- Add IsDBA flag to Tenants: marks a tenant as an individual/partnership
-- operating under TenantName as a d.b.a. (trade name), rather than TenantName
-- being that individual's/entity's own legal name. Drives the
-- DBAName/TenantNameWithDBA merge tokens in lease_merge.py.
-- Run against TenantCRM_Test first. Verify in SSMS. Then run against TenantCRM.

IF COL_LENGTH('dbo.Tenants', 'IsDBA') IS NULL
BEGIN
    ALTER TABLE dbo.Tenants ADD IsDBA BIT NOT NULL DEFAULT 0;
END;

IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM dbo.SchemaChangeLog
        WHERE ScriptName = 'add_tenant_isdba_flag.sql'
    )
BEGIN
    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    VALUES (
        'add_tenant_isdba_flag.sql',
        GETDATE(),
        SUSER_SNAME(),
        'Added Tenants.IsDBA (bit, default 0) so the existing DBAName/TenantNameWithDBA merge tokens can resolve to real d.b.a. phrasing instead of always being blank/plain tenant name.'
    );
END;
```

Run against `TenantCRM_Test` first, confirm via SSMS, then run the identical script against `TenantCRM`. Update `db/history/CHANGELOG.md` with the new entry once applied, and add `IsDBA` to `db/baseline_schema.sql`'s `Tenants` table definition so the regeneratable baseline stays accurate.

---

### Part B — Tenant edit form

`LucidPM/pages/tenants.py`, class `TenantState`.

#### B1. Add the display and edit-form fields

**Current** (line 383-384):

```python
    tenant_notes: str = ""
    tenant_initials: str = ""
```

**Replace** with:

```python
    tenant_notes: str = ""
    tenant_is_dba: bool = False
    tenant_initials: str = ""
```

**Current** (line 400):

```python
    f_tenant_notes: str = ""
```

**Replace** with:

```python
    f_tenant_notes: str = ""
    f_tenant_is_dba: bool = False
```

#### B2. Load it in `_load_tenant_detail`

**Current** (lines 967-976):

```python
        rows = run_query(
            "SELECT t.TenantID, t.TenantName, s.TenantStatusName, tt.TenantTypeName, "
            "ps.SuiteLabel, p.PropertyName, t.Notes "
            "FROM Tenants t "
            "LEFT JOIN TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
            "LEFT JOIN TenantTypes tt ON t.TenantTypeID = tt.TenantTypeID "
            "LEFT JOIN PropertySuites ps ON t.SuiteID = ps.SuiteID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            "WHERE t.TenantID = ?",
            (tenant_id,), db=self.db,
        )
```

**Replace** with:

```python
        rows = run_query(
            "SELECT t.TenantID, t.TenantName, s.TenantStatusName, tt.TenantTypeName, "
            "ps.SuiteLabel, p.PropertyName, t.Notes, t.IsDBA "
            "FROM Tenants t "
            "LEFT JOIN TenantStatuses s ON t.TenantStatusID = s.TenantStatusID "
            "LEFT JOIN TenantTypes tt ON t.TenantTypeID = tt.TenantTypeID "
            "LEFT JOIN PropertySuites ps ON t.SuiteID = ps.SuiteID "
            "LEFT JOIN Properties p ON t.PropertyID = p.PropertyID "
            "WHERE t.TenantID = ?",
            (tenant_id,), db=self.db,
        )
```

**Current** (line 989):

```python
        self.tenant_notes          = str(r.get("Notes") or "")
```

**Replace** with:

```python
        self.tenant_notes          = str(r.get("Notes") or "")
        self.tenant_is_dba         = bool(r.get("IsDBA"))
```

#### B3. Populate/reset it in the edit form open/close handlers

**Current** (`start_edit_tenant`, lines 1822-1827):

```python
        self.f_tenant_name     = self.selected_tenant_name
        self.f_tenant_status   = self.tenant_status
        self.f_tenant_type     = self.tenant_type
        self.f_tenant_property = self.tenant_property
        self.f_tenant_suite    = self.tenant_suite
        self.f_tenant_notes    = self.tenant_notes
```

**Replace** with:

```python
        self.f_tenant_name     = self.selected_tenant_name
        self.f_tenant_status   = self.tenant_status
        self.f_tenant_type     = self.tenant_type
        self.f_tenant_property = self.tenant_property
        self.f_tenant_suite    = self.tenant_suite
        self.f_tenant_notes    = self.tenant_notes
        self.f_tenant_is_dba   = self.tenant_is_dba
```

**Current** (`start_new_tenant`, lines 1838-1843):

```python
        self.f_tenant_name     = ""
        self.f_tenant_status   = self.status_names[0] if self.status_names else ""
        self.f_tenant_type     = self.type_names[0] if self.type_names else ""
        self.f_tenant_property = self.property_names[0] if self.property_names else ""
        self.f_tenant_suite    = "(No suite)"
        self.f_tenant_notes    = ""
```

**Replace** with:

```python
        self.f_tenant_name     = ""
        self.f_tenant_status   = self.status_names[0] if self.status_names else ""
        self.f_tenant_type     = self.type_names[0] if self.type_names else ""
        self.f_tenant_property = self.property_names[0] if self.property_names else ""
        self.f_tenant_suite    = "(No suite)"
        self.f_tenant_notes    = ""
        self.f_tenant_is_dba   = False
```

#### B4. Add the setter

**Current** (line 1855):

```python
    def set_f_tenant_notes(self, v: str):    self.f_tenant_notes = v
```

**Replace** with:

```python
    def set_f_tenant_notes(self, v: str):    self.f_tenant_notes = v
    def set_f_tenant_is_dba(self, v: bool):  self.f_tenant_is_dba = v
```

#### B5. Add the switch to the form

Add near the existing Tenant Name / Notes fields in the tenant edit form's `rx.vstack`/`rx.grid` (find the render code for the edit form fields declared above, use the same `rx.switch` pattern already established at line 4022):

```python
rx.hstack(
    rx.text("Doing Business As (d.b.a.)", size="1", color="#666"),
    rx.switch(checked=TenantState.f_tenant_is_dba, on_change=TenantState.set_f_tenant_is_dba),
    spacing="2",
    align="center",
),
```

Consider a short caption near it, e.g. *"Tenant Name is the trade name this individual/partnership operates under."*

#### B6. Save it

**Current** (lines 1895-1901, new-tenant insert):

```python
        if self.tenant_is_new:
            run_exec(
                "INSERT INTO Tenants (TenantName, TenantStatusID, TenantTypeID, "
                "PropertyID, Suite, SuiteID, Notes) VALUES (?,?,?,?,?,?,?)",
                (self.f_tenant_name.strip(), status_id, type_id,
                 prop_id, suite_label, suite_id, self.f_tenant_notes),
                db=self.db,
            )
```

**Replace** with:

```python
        if self.tenant_is_new:
            run_exec(
                "INSERT INTO Tenants (TenantName, TenantStatusID, TenantTypeID, "
                "PropertyID, Suite, SuiteID, Notes, IsDBA) VALUES (?,?,?,?,?,?,?,?)",
                (self.f_tenant_name.strip(), status_id, type_id,
                 prop_id, suite_label, suite_id, self.f_tenant_notes,
                 self.f_tenant_is_dba),
                db=self.db,
            )
```

**Current** (lines 1914-1920, existing-tenant update):

```python
            run_exec(
                "UPDATE Tenants SET TenantName=?, TenantStatusID=?, TenantTypeID=?, "
                "PropertyID=?, Suite=?, SuiteID=?, Notes=? WHERE TenantID=?",
                (self.f_tenant_name.strip(), status_id, type_id,
                 prop_id, suite_label, suite_id, self.f_tenant_notes,
                 self.tenant_id),
                db=self.db,
            )
```

**Replace** with:

```python
            run_exec(
                "UPDATE Tenants SET TenantName=?, TenantStatusID=?, TenantTypeID=?, "
                "PropertyID=?, Suite=?, SuiteID=?, Notes=?, IsDBA=? WHERE TenantID=?",
                (self.f_tenant_name.strip(), status_id, type_id,
                 prop_id, suite_label, suite_id, self.f_tenant_notes,
                 self.f_tenant_is_dba,
                 self.tenant_id),
                db=self.db,
            )
```

---

### Part C — Wire the merge tokens to real data

`LucidPM/lease_merge.py`.

#### C1. Select the new column

**Current** (line 612):

```python
        "t.TenantName, t.Suite AS TenantSuiteText, "
```

**Replace** with:

```python
        "t.TenantName, ISNULL(t.IsDBA, 0) AS IsDBA, t.Suite AS TenantSuiteText, "
```

#### C2. Resolve the tokens from it

**Current** (lines 769-770):

```python
        "DBAName": "",
        "TenantNameWithDBA": _s(lease.get("TenantName")),
```

**Replace** with:

```python
        "DBAName": _s(lease.get("TenantName")) if lease.get("IsDBA") else "",
        "TenantNameWithDBA": (
            f"{guarantor_name} d.b.a. {_s(lease.get('TenantName'))}"
            if lease.get("IsDBA") and guarantor_name
            else _s(lease.get("TenantName"))
        ),
```

`guarantor_name` is the same local variable already computed a few lines above for `GuarantorName`/`TenantNameWithGuarantor` — this reuses it as-is, no new lookup. `{{DBAName}}` becomes "the trade name, only when this really is a DBA situation" (distinct from `{{TenantName}}`, which is always the business name regardless) — useful for a clause that specifically wants to say "operating under the trade name ___" only when applicable.

`TenantNameWithDBAUpper` (line 900) needs no change — it already derives from `TenantNameWithDBA`.

---

## Do Not Touch

| What | Why |
|---|---|
| `TenantNameWithGuarantor` / the guarantor-joining logic from earlier this session | Reused as-is by `TenantNameWithDBA`, not duplicated or modified. |
| `Contacts.ContactRole` values, the `'Guarantor'` role itself | Deliberately reused as the DBA-party source — see "What This Is" for the reasoning. No new `ContactRole` value is being introduced. |
| `TenantTypeID` / `TenantTypes` | Untouched, and deliberately not read by the new `IsDBA` logic — the flag is independent of entity type by design. |
| Tenant "4C's Mechanical, LLC" (`TenantID` 40)'s actual data | Its `TenantName`/`TenantTypeID`/`IsDBA` cleanup is a manual data-entry task for Mark using the UI this handoff builds — not a script, not part of this handoff. |
| The token-picker entries in `lease_documents.py` | `{{DBAName}}`/`{{TenantNameWithDBA}}` are already listed in the "Tenant" group — no picker changes needed. |
| Any other `Tenants` column or the `Contacts` table structure | Out of scope. |

---

## Validation Checklist

- [ ] Migration script runs cleanly against `TenantCRM_Test`, confirmed via SSMS (`IsDBA` column exists, `BIT`, `NOT NULL`, default `0`)
- [ ] Same script runs cleanly against `TenantCRM`
- [ ] `db/history/CHANGELOG.md` and `db/baseline_schema.sql` updated to reflect the new column
- [ ] Tenant edit form shows a "Doing Business As (d.b.a.)" switch; toggling it and saving persists and reloads correctly on both new-tenant creation and existing-tenant edit
- [ ] For a tenant with `IsDBA = false` (the default for every existing tenant today), `{{DBAName}}` is `""` and `{{TenantNameWithDBA}}` equals plain `{{TenantName}}` — i.e. **zero behavior change for every tenant that existed before this migration**
- [ ] For a tenant with `IsDBA = true` and one or more Guarantor contacts, `{{DBAName}}` equals `{{TenantName}}`, and `{{TenantNameWithDBA}}` renders as `"{Guarantor name(s)} d.b.a. {TenantName}"`
- [ ] For a tenant with `IsDBA = true` but **no** Guarantor contacts, `{{TenantNameWithDBA}}` falls back to plain `{{TenantName}}` (no crash, no dangling "d.b.a." with nothing after it)
- [ ] `{{TenantNameWithDBAUpper}}` correctly upper-cases the new composed value
- [ ] All 17 previously-registered pages still compile and the app still runs (`reflex run --backend-only`)

---

## How to Deliver This

Per `CLAUDE.md`: edit files in place, no new versioned files (except the new, additive `db/history/` migration script, which is expected to be a new file per the DB-history convention).

1. Apply Part A: run the migration against `TenantCRM_Test`, verify, then `TenantCRM`. Update `CHANGELOG.md`/`baseline_schema.sql`.
2. Apply Part B (B1-B6) to `LucidPM/pages/tenants.py`.
3. Apply Part C (C1-C2) to `LucidPM/lease_merge.py`.
4. Verify against the checklist above.
5. Commit with a descriptive message (e.g. "Add Tenants.IsDBA flag and wire DBAName/TenantNameWithDBA merge tokens").

Cleaning up "4C's Mechanical, LLC"'s own data (dropping ", LLC" from its name, changing its `TenantTypeID`, setting its `IsDBA`) is a separate follow-up Mark will do himself in the UI once this ships — not part of this delivery.

---

## File Locations

```
C:\Inspirion\Dev\TenantCRM\LucidPM\
  db\history\012_...add_tenant_isdba_flag.sql   ← Part A (new file)
  db\baseline_schema.sql                         ← Part A (update Tenants definition)
  db\history\CHANGELOG.md                        ← Part A (log entry)
  LucidPM\pages\tenants.py                       ← Part B
  LucidPM\lease_merge.py                         ← Part C

Frontend: http://localhost:3000
Backend:  http://localhost:8000
Test DB: green banner | Prod DB: red banner
```

---

*One schema column (a boolean, not a text field), one form switch, two dead tokens brought to life — reusing the guarantor-name logic already shipped this session rather than introducing a new Contact role or a new name-joining code path. "4C's Mechanical"'s own bad data is explicitly a follow-up for Mark, not part of this delivery.*
