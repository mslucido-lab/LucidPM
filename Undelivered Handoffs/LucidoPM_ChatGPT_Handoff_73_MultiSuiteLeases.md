# LucidoPM — ChatGPT Handoff 73
*Multi-suite leases — one lease covering two or more suites*
*Prepared: 2026-10-05*

---

## What This Is

Today a lease points at **one** suite (`Leases.SuiteID`). When a tenant leases
two adjacent suites under one lease (e.g. Broadway `1614-1 # 100` +
`1614-1 # 102`), there is no way to record it. The only workaround in the data
is Walnut's permanently-merged suite records (`1 & 2`, `3 & 4`, `5 & 6`). That
works only for merges that never change.

This handoff lets a lease cover **N suites** and makes the multi-suite lease
show up correctly everywhere a lease and a suite meet:

| Surface | Required behavior (Mark's calls, 2026-10-05) |
|---|---|
| **Rent Roll** (page + PDF) | **One combined row per lease.** The label lists every suite, primary first. SF is summed and the full lease rent is shown once. The bank reads the rent roll by tenant. |
| **Proforma** (one column per suite) | **Rent tracked per suite.** Each suite column gets that suite's share of the lease's rent every month. |
| **Dashboard** | Every linked suite counts as occupied. Monthly rent is counted **once per lease**. |
| **Leases Expiring** | Two leases are "the same suite" if they share **any** suite. |
| **Lease documents** | **One combined rent amount** and **all suite numbers**, primary first ("1614-2 # 200 and 1614-1 # 110"). SF is summed, and the premises/legal descriptions cover every suite. |
| **Tenant → Lease form** | The Suite dropdown becomes a **checkbox dropdown** listing the property's suites. With 2+ checked, a rent table above Monthly rent takes **each suite's monthly rent in dollars** and marks the primary. The lease rent is their sum, and the % share is derived and stored. |

The acceptance test is the real Dallas Pro Paint & Drywall expansion. See
**Worked Example** below. Every phase's validation includes it.

### Design in one paragraph

A new junction table `dbo.LeaseSuites (LeaseID, SuiteID, IsPrimary,
RentAllocationPct)` holds a lease's suites. Each existing lease that has a
`SuiteID` gets a backfilled row (`IsPrimary=1`, `100%`). **`Leases.SuiteID` is
kept and always equals the primary suite.** As a result, single-suite leases and any code
this handoff does not touch keep working unchanged. Mark **enters** allocations in
dollars per suite, but they are **stored as a percentage** of the lease rent (6 decimal
places). If the lease's rent schedule steps up mid-term, each suite's share steps up
with it, and the suite amounts can never drift out of sum with the lease rent. (Mark's
practice is one lease record per term, so each new term re-enters per-suite dollars.
Different escalations per suite *within* one term are out of scope.) All
suite↔lease matching moves into one new module,
`LucidPM/lease_suites.py`. That module replaces the four copy-pasted `find_lease` cascades.

### Scope constraint

- **No change to how rent itself is computed.** `LeaseRentSchedule` stays
  per-lease. Allocation only *splits* the lease's rent where a per-suite view needs it.
- **`Tenants.SuiteID` / `Tenants.Suite` are untouched.** They remain the tenant's
  "home" suite, used as a fallback only for legacy leases with no `SuiteID`.
- **No Walnut data migration.** Mark will split the Walnut suites by hand through the
  UI (see "Operator note" under Validation).
- **No per-suite rent schedules, no cross-property leases.** All of a lease's
  suites must belong to the lease's `PropertyID`.
- `Leases.SuiteID` is **not** dropped or deprecated in this handoff.

---

## Worked Example — Dallas Pro Paint & Drywall (Prod, TenantID 11)

**Today.** Each term is its own lease record. The current one is **Lease 73**:
`1614-2 # 200` (SuiteID 16, 850 SF), 2026-01-01 → 2026-12-31, $975/mo,
"Renewal Option". Earlier terms are Leases 11, 62, and 61. `1614-1 # 110` is held by
Orbit Distribution, **Lease 85**: month-to-month (option not exercised). Orbit has
given notice, so `LeaseEnd` = **2026-10-31** (Prod, confirmed 2026-10-05).

**The plan (Mark, 2026-10-05):**
1. **Early-terminate Lease 73:** `LeaseStatus = 'Terminated'`,
   `LeaseTerminationDate = 2026-10-31`. `LeaseEnd` stays 2026-12-31.
2. **New lease from 2026-11-01**, Parent = 73, covering both suites:

| Suite | SuiteID | SF | Monthly rent entered | Stored % |
|---|---|---|---|---|
| `1614-2 # 200` (**primary**) | 16 | 850 | $1,025.00 | 45.054945 |
| `1614-1 # 110` | 15 | 1,080 | $1,250.00 | 54.945055 |
| **Lease** | | **1,930** | **$2,275.00** (= `Leases.RentAmount`, base schedule row) | 100 |

(Splitting by SF would give $1,001.94 / $1,273.06. That is why the form takes dollars.)

**Expected results:**

- **Rent Roll as of 2026-10-31:** `1614-2 # 200` = Dallas Pro, Lease 73, $975.
  `1614-1 # 110` = Orbit, $1,250.
- **Rent Roll as of 2026-11-01 or later:** one row at #200's position:
  `1614-2 # 200 / 1614-1 # 110 · 1,930 · Occupied · Dallas Pro Paint & Drywall · $2,275.00`.
  `1614-1 # 110` does **not** appear separately. This lease's PSF = $2,275 × 12 ÷ 1,930 = **$14.15/sf**.
  **Lease 73 must not match**, even though its `LeaseEnd` (12/31) is later than the as-of date.
  It is Terminated as of 10/31. See "Early-termination fix" in Phase 2. Today's code
  would show Lease 73 at $975 here.
- **Proforma** (Broadway 2026): Jan–Oct unchanged ($975 on #200 from Lease 73; Orbit
  on #110). **Nov–Dec:** #200 = **$1,025.00**, #110 = **$1,250.00**. Proforma 2027: the
  same split every month. Proforma already handles Lease 73's termination correctly.
- **Dashboard (on/after 11/1):** both suites occupied, and $2,275 is counted once.
- **Leases Expiring:** Lease 73 is **not** listed as expiring 2026-12-31, because it is
  terminated 10/31. Orbit's Lease 85 is listed as ending 2026-10-31. The new lease is
  recognised as Lease 73's successor (they share #200).
- **Lease document:** `{{SuiteLabel}}` = "1614-2 # 200 and 1614-1 # 110". Rent tokens = $2,275.00.
  `{{SuiteFullAddress}}` = "Bldg. 1614-2, Suite 200 and Bldg. 1614-1, Suite 110, 1614 S. Broadway, Carrollton, …".
  `{{SuiteLegalDescription}}` = "Bldg. 1614-2, Suite 200 and Bldg. 1614-1, Suite 110, 1614 S. Broadway
  Street, being Lot 2b Block 1, of I-35 Marchant Addition, City of Carrollton, Texas 75006"
  (shared tail factored out; see Phase 4).
- **No overlap warning** when saving the new lease: Orbit ends 10/31, and Lease 73
  is terminated 10/31. The overlap check must use the termination date for a Terminated lease.
  If Lease 73 is entered as terminated *after* the new lease is saved, the warning
  names Lease 73. That is expected and non-blocking.

**Deadline.** The lease document must be generated and signed before **2026-11-01**.
That is why Mark set the delivery order to Phase 1 → 4 → 2 → 3 (see "The Fix").

---

## The Current State

### Schema (`db/baseline_schema.sql`)

- `Leases` (line 218): `SuiteID INT NULL`. FK `FK_Leases_PropertySuites` (line 633),
  index `IX_Leases_SuiteID` (line 689).
- `PropertySuites` (line 344): `SuiteID, PropertyID, SuiteLabel, SquareFeet,
  SortOrder, IsActive, SuiteUseType, UnderwritingRent, SuiteLegalDescription,
  SuitePremisesDescription, SuiteAddressOverride`.
- `Tenants` (line 446): `Suite NVARCHAR(50)`, `SuiteID INT`.
- Data (2026-10-05): Prod has 93 leases (19 with no `SuiteID`) and 24 suites. Test has 75 leases (19 with no `SuiteID`) and 23 suites.
  No tenant currently has two concurrently-active leases on different suites.
- The H70 DDL trigger `trg_LogSchemaChanges` logs schema changes automatically,
  so **no manual `SchemaChangeLog` insert is needed** in the new script.

### The duplicated suite→lease matching cascade

There are four copies of the same three-step cascade: (1) `Leases.SuiteID`, (2) `Tenants.SuiteID` +
PropertyID, (3) `Tenants.Suite` text = `SuiteLabel`. Each one assumes one suite per lease:

| File | Lines | Notes |
|---|---|---|
| `pages/rent_roll.py` | `find_lease` 191–206, row build 208–289 | Uses scheduled `EffectiveRent` (`LeaseRentSchedule`), holdover via `TenantSuite` + fixed-term check |
| `LucidPM.py` | `_build_rent_roll_pdf_bytes` 55–200, `find_lease` 114–127 | **Has drifted from the page:** uses `l.RentAmount`, not scheduled rent, and a separate holdover SQL |
| `pages/dashboard.py` | `_load_rent_roll_summary` 100–211, `find_lease` 151–164 | Sums `RentAmount` **per suite**, so a 2-suite lease would be counted twice |
| `pages/proforma.py` | lease load 348–357, `suite_leases` 420–430 | Keys suites by **label**. Picks leases by `COALESCE(ps.SuiteLabel, t.Suite)` |

Single-suite consumers:

| File | Lines | Use |
|---|---|---|
| `pages/leases_expiring.py` | 140–158 (`_successor…`), 161–178 `_same_suite`, 468–470 lease SQL | Compares `SuiteID` equality |
| `lease_merge.py` | 618–640 base SELECT (`LEFT JOIN PropertySuites ps ON l.SuiteID = ps.SuiteID`), 767 `suite_label`, 146–158 `_suite_full_address`, 879–890 tokens | Single suite's label/SF/descriptions |
| `pages/lease_package_builder.py` | 554–561, 591 (lease picker label); 669–674, 701 | Single `SuiteLabel` |
| `pages/tenants.py` | `_load_suite_options` 890–903; `load_leases` 3004–3040; `select_lease` 3043–3094; `save_lease` 3127–3229; delete 3248–3250; form UI 4416–4426 | One `rx.select` for suite; writes `Leases.SuiteID` |
| `pages/suites.py` | `delete_suite` 268–274 | Delete guard checks `Leases.SuiteID` only |

`run_exec` (`state.py:255`) opens one connection per statement. There is no
multi-statement transaction helper.

### Related undelivered handoffs

- **H57 (Suite Rent PSF tab)** reuses the `rent_roll.find_lease` cascade. If H57
  lands after this handoff, it should call `lease_suites.match_suite_to_lease`
  and take the per-suite rent from `split_amount`. If H57 lands first,
  update its matcher as part of Phase 2 here.
- **H55 (Merge-token catalog)**. If H55 lands first, the two new tokens in Phase 4
  (`SuiteWord`, `SuiteCount`) need catalog seed rows (`Kind='computed'`).

---

## The Fix

Four phases, **one commit each**. **Delivery order: Phase 1 → Phase 4 → Phase 2 →
Phase 3** (Mark, 2026-10-05). The Dallas Pro lease document is needed before 11/1.
Phase 4 depends only on Phase 1 (`lease_suites.py` + the `LeaseSuites` data), so
it must not use anything introduced in Phase 2 or 3. After every phase the app must
run correctly. Phase 1 alone changes no report output, because every lease still has at
most one suite until someone adds a second one in the form.

**Expected interim state (after 1 + 4, before 2 + 3):** a multi-suite lease is entered,
saved, and generates correct documents. The reports still behave the old way: Rent Roll
and Dashboard show the lease on its primary suite only, with the other suite Vacant, and
Proforma shows the full rent on the primary suite. Worse, for Dallas Pro specifically:
until Phase 2's termination fix, the Rent Roll from 11/1 will most likely still show
**Lease 73 at $975** on #200, because it is the older matching lease. Proforma is
correct for #200. This is known and accepted. Phases 2 and 3 close it, so Phase 2
should follow Phase 4 promptly.

**Environment (confirmed by Mark 2026-10-05): Azure SQL is the only database.** The
local SQL Server copies are retired. Local development (`reflex run` on Mark's PC, `.env`)
and the deployed Container App connect to the **same** Azure SQL server
(`lucidpm-sql-24899`), databases `TenantCRM_Test` and `TenantCRM`. As a result:
- "Testing locally" means local **code** against the **Azure `TenantCRM_Test`** database.
  Keep the app toggled to Test throughout development. Never point unreleased code at `TenantCRM`.
- A schema change is live for the deployed app the moment the script runs. The 014 script
  is purely additive (new table + backfill; no existing column changes), so the currently
  deployed image (`0.4.3`) is unaffected by it.
- Data entered through either the local or the deployed app lands in the same place.

**Deployment order.** The Phase 1 code queries `dbo.LeaseSuites`, so the table must exist
in a database before Phase 1 code runs against it:
1. Run the 014 script on Azure `TenantCRM_Test` before Codex starts Phase 1 testing.
2. Develop and verify P1 + P4 locally against Azure Test.
3. Mark runs the 014 script on Azure `TenantCRM`.
4. Release image `0.5.0` to the Container App (see "Release to Azure" under How to Deliver).
   Until then, `lucidpm.lucidoproperties.net` keeps running `0.4.3`.

Steps 3–4 repeat (without the script) for the P2 and P3 releases.

**Shared rule: a lease's effective end.** Phases 1, 2 and 3 all use this rule, so put it
in `lease_suites.py` (Phase 1). It is the same rule `proforma._build_segments`
(lines 177–184) already applies:

```python
def effective_end(lease: dict) -> datetime.date | None:
    """LeaseEnd, cut short to LeaseTerminationDate when LeaseStatus = 'Terminated'.
    None = open-ended."""
    end = _to_date(lease.get("LeaseEnd"))
    if str(lease.get("LeaseStatus") or "").strip() == "Terminated":
        term = _to_date(lease.get("LeaseTerminationDate"))
        if term is not None:
            end = term if end is None else min(end, term)
    return end
```

(`_to_date` = the usual datetime→date helper. Add it to the module.)

### Phase 1 — Schema, shared helper, lease form

#### 1a. Schema script `db/history/014_2026-10-05_<HHMM>_lease_suites.sql`

Idempotent. Run on Azure `TenantCRM_Test` → verify → Azure `TenantCRM`. Use SSMS or
`sqlcmd` connected to `lucidpm-sql-24899.database.windows.net`, as the admin login, because
the app's `lucidpm_app` user has only `db_datareader`/`db_datawriter` and cannot run DDL.
**Mark runs the `TenantCRM` (Prod) run.** The H70 DDL trigger is installed on both Azure DBs
and logs the change automatically.

```sql
-- Multi-suite leases (Handoff 73). One row per suite a lease covers.
-- Leases.SuiteID is retained and must always equal the IsPrimary=1 row's SuiteID.
-- RentAllocationPct: share (0-100) of the lease's rent attributed to this suite
-- for per-suite views (Proforma). Rows for one lease sum to 100.
-- Run against TenantCRM_Test first. Verify. Then run against TenantCRM.

IF OBJECT_ID('dbo.LeaseSuites', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeaseSuites (
        LeaseSuiteID      INT IDENTITY(1,1) NOT NULL,
        LeaseID           INT NOT NULL,
        SuiteID           INT NOT NULL,
        IsPrimary         BIT NOT NULL CONSTRAINT DF_LeaseSuites_IsPrimary DEFAULT (0),
        RentAllocationPct DECIMAL(9,6) NOT NULL CONSTRAINT DF_LeaseSuites_Pct DEFAULT (100),
        CreatedDate       DATETIME NOT NULL CONSTRAINT DF_LeaseSuites_Created DEFAULT (GETDATE()),
        CONSTRAINT PK_LeaseSuites PRIMARY KEY CLUSTERED (LeaseSuiteID),
        CONSTRAINT FK_LeaseSuites_Leases FOREIGN KEY (LeaseID)
            REFERENCES dbo.Leases (LeaseID) ON DELETE CASCADE,
        CONSTRAINT FK_LeaseSuites_PropertySuites FOREIGN KEY (SuiteID)
            REFERENCES dbo.PropertySuites (SuiteID),
        CONSTRAINT CK_LeaseSuites_Pct CHECK (RentAllocationPct >= 0 AND RentAllocationPct <= 100)
    );
    CREATE UNIQUE INDEX UX_LeaseSuites_Lease_Suite ON dbo.LeaseSuites (LeaseID, SuiteID);
    CREATE UNIQUE INDEX UX_LeaseSuites_OnePrimary ON dbo.LeaseSuites (LeaseID) WHERE IsPrimary = 1;
    CREATE INDEX IX_LeaseSuites_SuiteID ON dbo.LeaseSuites (SuiteID) INCLUDE (LeaseID, RentAllocationPct);
END;

-- Backfill: every lease with a SuiteID gets its primary row at 100%.
INSERT INTO dbo.LeaseSuites (LeaseID, SuiteID, IsPrimary, RentAllocationPct)
SELECT l.LeaseID, l.SuiteID, 1, 100
FROM dbo.Leases l
WHERE l.SuiteID IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dbo.LeaseSuites x WHERE x.LeaseID = l.LeaseID);
```

Verification queries (put them in the script as a commented block):

```sql
-- Expect 0: every SuiteID'd lease has exactly one primary row matching it
SELECT COUNT(*) FROM dbo.Leases l
LEFT JOIN dbo.LeaseSuites ls ON ls.LeaseID = l.LeaseID AND ls.IsPrimary = 1
WHERE l.SuiteID IS NOT NULL AND (ls.SuiteID IS NULL OR ls.SuiteID <> l.SuiteID);
-- Expect 0: allocations sum to 100
SELECT LeaseID FROM dbo.LeaseSuites GROUP BY LeaseID HAVING ABS(SUM(RentAllocationPct) - 100) > 0.01;
```

Afterwards, regenerate `db/baseline_schema.sql` with `db/generate_baseline_schema.py`. Add a
row to `db/history/CHANGELOG.md`, and add `LeaseSuites` to `docs/Database.md`.

#### 1b. New module `LucidPM/lease_suites.py`

This module is the **only** place suite↔lease matching and labeling logic lives.
Pure functions plus two DB helpers. No Reflex imports.

```python
"""
Multi-suite lease helpers (Handoff 73).

A lease covers one or more suites via dbo.LeaseSuites. Leases.SuiteID is kept
equal to the primary suite. Leases with no LeaseSuites rows (legacy, no
SuiteID) fall back to the Tenants.SuiteID / Tenants.Suite cascade that every
report used before this module existed.
"""

import datetime
from decimal import Decimal, ROUND_HALF_UP

from LucidPM.state import get_conn, run_query

# NOTE: lease-row dicts from the Rent Roll PDF / Dashboard queries alias Leases.SuiteID
# as "LeaseSuiteID". That alias is unrelated to the LeaseSuites.LeaseSuiteID primary
# key, and this module never reads the PK.

_BATCH = 100


def load_lease_suites(lease_ids, db: str) -> dict[int, list[dict]]:
    """LeaseID -> [{SuiteID, SuiteLabel, SquareFeet, SortOrder, IsPrimary,
    RentAllocationPct, PropertyID}] ordered primary first, then SortOrder, SuiteLabel."""
    ids = sorted({int(i) for i in lease_ids if i is not None})
    out: dict[int, list[dict]] = {}
    for i in range(0, len(ids), _BATCH):
        batch = ids[i:i + _BATCH]
        ph = ",".join(["?"] * len(batch))
        rows = run_query(
            "SELECT ls.LeaseID, ls.SuiteID, ls.IsPrimary, ls.RentAllocationPct, "
            "ps.SuiteLabel, ps.SquareFeet, ps.SortOrder, ps.PropertyID, "
            "ISNULL(ps.SuitePremisesDescription,'') AS SuitePremisesDescription, "
            "ISNULL(ps.SuiteLegalDescription,'') AS SuiteLegalDescription "
            "FROM LeaseSuites ls INNER JOIN PropertySuites ps ON ps.SuiteID = ls.SuiteID "
            f"WHERE ls.LeaseID IN ({ph}) "
            "ORDER BY ls.LeaseID, ls.IsPrimary DESC, ps.SortOrder, ps.SuiteLabel",
            tuple(batch), db=db,
        )
        for r in rows:
            out.setdefault(int(r["LeaseID"]), []).append(r)
    return out


def suite_ids_for(lease: dict, lease_suites: dict[int, list[dict]]) -> set[int]:
    """Suites a lease covers. Falls back to the lease's own SuiteID column
    (any alias: SuiteID / LeaseSuiteID) when no LeaseSuites rows exist."""
    rows = lease_suites.get(int(lease["LeaseID"]))
    if rows:
        return {int(r["SuiteID"]) for r in rows}
    for key in ("SuiteID", "LeaseSuiteID"):
        if lease.get(key) is not None:
            return {int(lease[key])}
    return set()


def allocation_pct(lease_id: int, suite_id: int, lease_suites: dict[int, list[dict]]) -> float:
    """Percent (0-100) of the lease's rent attributed to suite_id. 100 when unlinked/legacy."""
    for r in lease_suites.get(int(lease_id), []):
        if int(r["SuiteID"]) == int(suite_id):
            return float(r["RentAllocationPct"] or 0)
    return 100.0


def match_suite_to_lease(suite_id: int, prop_id: int, suite_label: str,
                         pool: list[dict], lease_suites: dict[int, list[dict]]) -> dict | None:
    """Drop-in replacement for the old per-page find_lease cascade.
    Pass 1 uses LeaseSuites membership (identical to the old Leases.SuiteID test
    for single-suite leases); passes 2-3 are the old Tenants fallbacks, unchanged."""
    for l in pool:
        if suite_id in suite_ids_for(l, lease_suites):
            return l
    for l in pool:
        tsid = l.get("TenantSuiteID")
        if tsid is not None and int(tsid) == suite_id and int(l.get("PropertyID", -1)) == prop_id:
            return l
    for l in pool:
        if (int(l.get("PropertyID", -1)) == prop_id and
                str(l.get("TenantSuite") or "").strip().upper() == suite_label.upper()):
            return l
    return None


def join_labels(labels: list[str], conjunction: str = "and") -> str:
    """['A'] -> 'A'; ['A','B'] -> 'A and B'; ['A','B','C'] -> 'A, B and C'."""
    labels = [s for s in (str(x).strip() for x in labels) if s]
    if len(labels) <= 1:
        return labels[0] if labels else ""
    return f"{', '.join(labels[:-1])} {conjunction} {labels[-1]}"


def report_label(labels: list[str]) -> str:
    """Compact label for tables / PDFs: 'A / B'. Callers pass labels in lease
    order (primary first), as returned by load_lease_suites."""
    return " / ".join(s for s in (str(x).strip() for x in labels) if s)


_PCT_Q = Decimal("0.000001")   # matches DECIMAL(9,6)
_CENT = Decimal("0.01")


def pcts_from_amounts(amounts: list[Decimal]) -> list[Decimal]:
    """Per-suite monthly dollars (primary first) -> stored percentages summing to
    exactly 100. Remainder goes to the primary. All-zero -> equal split."""
    n = len(amounts)
    if n == 0:
        return []
    total = sum(amounts)
    if total <= 0:
        amounts, total = [Decimal(1)] * n, Decimal(n)
    pcts = [(a * 100 / total).quantize(_PCT_Q, rounding=ROUND_HALF_UP) for a in amounts]
    pcts[0] += Decimal(100) - sum(pcts)
    return pcts


def split_amount(total: Decimal, pcts: list[Decimal]) -> list[Decimal]:
    """Split a lease-level dollar amount into per-suite cents that sum EXACTLY to
    total (remainder cent(s) to the primary). Used by the form and Proforma."""
    if not pcts:
        return []
    parts = [(total * p / 100).quantize(_CENT, rounding=ROUND_HALF_UP) for p in pcts]
    parts[0] += total.quantize(_CENT) - sum(parts)
    return parts


def sf_amounts(total: Decimal, suites: list[dict]) -> list[Decimal]:
    """Optional 'Split by SF' helper for the form: total dollars pro-rata by
    SquareFeet (equal split if any suite lacks SF)."""
    try:
        sfs = [Decimal(str(s.get("SquareFeet"))) for s in suites]
        if any(sf <= 0 for sf in sfs):
            raise ValueError
    except Exception:
        sfs = [Decimal(1)] * len(suites)
    return split_amount(total, pcts_from_amounts(sfs))


def combine_descriptions(premises: list[str], full: list[str]) -> str:
    """Combine per-suite descriptions for a multi-suite lease (primary first).
    If every full[i] starts with premises[i] and the remaining tails are identical
    (the normal case: same building lot), return
    'P1 and P2<shared tail>'. Otherwise join the full texts with '; and '."""
    pairs = [(_s(p), _s(f)) for p, f in zip(premises, full)]
    if pairs and all(p and f.startswith(p) for p, f in pairs):
        tails = {f[len(p):] for p, f in pairs}
        if len(tails) == 1:
            return join_labels([p for p, _ in pairs]) + tails.pop()
    texts = [f for _, f in pairs if f]
    return "; and ".join(texts) if len(texts) > 1 else (texts[0] if texts else "")


def _s(v) -> str:
    return str(v or "").strip()


def save_lease_suites(lease_id: int, rows: list[tuple[int, bool, Decimal]], db: str) -> None:
    """Replace a lease's LeaseSuites rows and sync Leases.SuiteID in ONE transaction.
    rows = [(SuiteID, IsPrimary, RentAllocationPct)]. Empty rows -> lease has no suite."""
    conn = get_conn(db)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM LeaseSuites WHERE LeaseID = ?", (lease_id,))
        primary = None
        for suite_id, is_primary, pct in rows:
            cur.execute(
                "INSERT INTO LeaseSuites (LeaseID, SuiteID, IsPrimary, RentAllocationPct) "
                "VALUES (?, ?, ?, ?)",
                (lease_id, suite_id, 1 if is_primary else 0, pct),
            )
            if is_primary:
                primary = suite_id
        cur.execute("UPDATE Leases SET SuiteID = ? WHERE LeaseID = ?", (primary, lease_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

> `state.get_conn` leaves pyodbc's default `autocommit=False` (verified
> 2026-10-05; `run_exec` commits explicitly), so the commit/rollback above is a
> real single transaction. Do not change `get_conn`.

#### 1c. `pages/tenants.py` — lease form

**State (near line 501 / 523):** add

```python
    l_suites: list[str] = []                # checked suite labels, in check order
    l_primary_suite: str = ""               # one of l_suites
    l_suite_amounts: dict[str, str] = {}    # label -> monthly $ as typed (multi-suite only)
    suite_sqft: dict[str, str] = {}         # label -> SquareFeet, filled by _load_suite_options
```

`l_suite` (single string) is retired from the form. Keep the field so nothing else
breaks, and set it to `l_primary_suite` on every change.

Mark thinks in **dollars per suite** (e.g. #200 at $1,025 and #110 at $1,250 →
$2,275). The form takes dollars. Percentages are derived and are only for display and storage.

**Layout (Mark's design, 2026-10-05).** Two pieces, each where it belongs. Choosing
**which** suites happens in a checkbox dropdown that replaces today's Suite select.
Splitting **rent** happens in a table directly above Monthly rent, shown only when
two or more suites are checked:

```
Row 1:  Property *      Suite(s)                           Lease type *    Term type
        [Broadway ▾]    [1614-2 # 200, 1614-1 # 110  ▾]   [Amendment ▾]   [Fixed Term ▾]
                         ┌───────────────────────────┐
                         │ ☐ 1612-1 # 100            │   (popover, opens on click,
                         │ ☑ 1614-1 # 110            │    property's active suites,
                         │ ☑ 1614-2 # 200            │    SortOrder then label)
                         │ ☐ 1614-2 # 202  ...       │
                         └───────────────────────────┘
Row 1b: status / termination date        (unchanged)
Row 2:  start / end / execution / amends (unchanged)

Row 2a (only when 2+ suites checked):
        Suite              SF      Monthly rent    Share    Primary
        1614-2 # 200       850     [ 1,025.00 ]    45.05%     (●)
        1614-1 # 110       1,080   [ 1,250.00 ]    54.95%     ( )
        Total              1,930      $2,275.00    100%            Split total by SF

Row 2b: Monthly rent ($)   Deposit ($)
        [ 2,275.00 🔒 ]    [ ... ]     ← read-only total while 2+ suites are checked
```

- `_load_suite_options` (890–903): also SELECT `SquareFeet` and fill `suite_sqft`.
  Drop the `"(No suite)"` sentinel from the options used by this control. Zero checked
  means no suite.
- **Suite(s) control (replaces the `rx.select` at 4416–4426).** An `rx.popover.root`.
  The trigger is styled like the neighbouring `rx.select` (same height, border, chevron) and
  shows the checked labels joined with ", ", or "(No suite)" when none are checked. The
  content is an `rx.foreach` of `rx.checkbox` rows over the property's suites, scrollable
  if long. (No popover is used in the codebase yet. Reflex 0.8.9's `rx.popover` +
  `rx.checkbox` are sufficient; do not add a dependency.) Label the field "Suite(s)".
- **Primary:** the first suite checked becomes primary. With 2+ checked, the
  Primary radio in Row 2a lets Mark change it. Unchecking the primary promotes the next
  checked suite. The trigger lists the primary first.
- **One suite checked:** Row 2a is hidden. Monthly rent is editable exactly as today.
  This path must feel unchanged.
- **Second suite checked:** Row 2a appears. Pre-fill the primary's amount with the
  current Monthly rent; the new suite's amount starts empty. Each further suite starts empty.
- **Back to one suite:** Row 2a hides. Monthly rent becomes editable again and keeps its current total.
- Row 2a: Share % is read-only (`pcts_from_amounts`). **"Split total by SF"** fills the
  amounts from the current total using `sf_amounts`. Monthly rent (Row 2b) shows the live sum
  read-only. `l_rent` is set from that sum, so the existing save path (`RentAmount` + Base
  rent-schedule row) is unchanged.
- Changing property (`set_l_property`, ~3123) clears `l_suites`, `l_primary_suite`,
  and `l_suite_amounts`.
- Reflex note: drive Row 2a's `rx.foreach` from a computed `@rx.var` that returns
  `list[dict[str, str]]` (label, sqft, amount, share, is_primary) built from the state
  above. Do not iterate the dict directly. Each amount input's `on_change` calls a
  handler with the row label. Follow the existing "State, not module constants" rule in
  CLAUDE.md Watch-fors.

**`select_lease` (3043–3094):** after the existing load, call
`load_lease_suites([lease_id], self.db)`. Set `l_suites` (primary first),
`l_primary_suite`, and, when 2+, fill `l_suite_amounts` with
`split_amount(RentAmount, stored pcts)`. This gives back exactly the dollars Mark
entered (e.g. $1,025.00 / $1,250.00). For a legacy lease with no rows but a `SuiteID`,
set `l_suites = [that label]`.

**`save_lease` (3127–3229):**
1. Validation, added after the suite resolution (3135–3138):
   - With 2+ suites, every suite amount must be a number > 0. Error:
     `"Enter a monthly rent for each suite."`
   - Suite resolution reads `l_primary_suite` (not the old `l_suite` select) to get `suite_id`.
   - Stored rows = primary first, then the rest in SortOrder. 2+ suites: `pcts_from_amounts(amounts)`,
     which always sum to exactly 100. One suite: `[(id, True, 100)]`. None: `[]`.
   - **Overlap warning (non-blocking):** if any chosen suite is in another lease
     (any tenant) whose date range overlaps this one, set `lease_form_success` to
     `"Saved. Note: Suite X is also on <TenantName> Lease #N (<start>–<end>)."`.
     A NULL `LeaseEnd` counts as open-ended, so it overlaps, and `<end>` shows
     `"open-ended / month-to-month"`. Use `effective_end()` for both leases, so a
     terminated lease ends on its `LeaseTerminationDate`. This is the normal case for an expansion into a suite
     whose month-to-month tenant hasn't had an end date entered yet. The
     message tells Mark which lease to close out. It must not block the save.
2. Keep the existing `UPDATE` / `INSERT` exactly as written. They still write `SuiteID`
   (the primary), which keeps the legacy column in sync for the moment between statements.
3. Immediately after the `UPDATE` (edit) or after resolving `new_id` (insert),
   call `save_lease_suites(lease_id, rows, self.db)`. `rows` is primary first,
   then extras in `SortOrder`. For a single suite that is `[(primary, True, 100)]`, and
   for no suite it is `[]`. **Note:** the insert branch resolves `new_id` only inside
   `if id_rows and lease_start:`. Restructure so `new_id` is resolved whenever
   `id_rows` is non-empty, and call `save_lease_suites` there. Leave the rent-schedule
   insert's `lease_start` condition unchanged.

**`load_leases` (3004–3040):** the lease list shows `suite_label`. Use
`report_label` of all the lease's suites. Call `load_lease_suites` for the loaded
IDs and fall back to `ps.SuiteLabel` when there are no rows.

**Delete (3248–3250):** no code change. `ON DELETE CASCADE` removes the
`LeaseSuites` rows. Add a one-line comment noting this.

#### 1d. `pages/suites.py` — delete guard (268–274)

Extend the lease check so a suite linked only as an *additional* suite is also
protected:

```python
        leases_in_use = run_query(
            "SELECT TOP 1 LeaseID FROM Leases WHERE SuiteID = ? "
            "UNION SELECT TOP 1 LeaseID FROM LeaseSuites WHERE SuiteID = ?",
            (self.selected_suite_id, self.selected_suite_id), db=self.db,
        )
```

---

### Phase 2 — Rent Roll (page + PDF) and Dashboard

#### 2a. One shared Rent Roll builder

The page (`rent_roll.py` 100–331) and the PDF (`LucidPM.py` 55–200) have
**drifted apart**: the PDF ignores `LeaseRentSchedule` and uses a different
holdover query. Both need the same multi-suite change, so converge them. Move the
page's `_do_compute` data logic (suite SQL, lease SQL with `EffectiveRent`,
active/holdover categorization, row build, stats) into a function in
`lease_suites.py`:

```python
def build_rent_roll(as_of: datetime.date, prop_filter: str, basis: str, db: str) -> dict:
    """Returns {"rows": [dict...], "total_rentable": float, "total_occupied": float,
    "vacancy_rate": float, "avg_annual_psf": float | None}.
    Row dict keys = RentRollRow fields."""
```

- `RentRollState._do_compute` calls it and maps rows into `RentRollRow`. Its formatting stays where it is.
- `_build_rent_roll_pdf_bytes` calls it and drops its own queries and `find_lease`.
  It keeps its own `prop_detail_rows` / PDF layout code (from line ~200 onward)
  unchanged, apart from reading totals from the dict.
- **The page's current behavior is the reference.** Expected, intentional
  PDF differences: rent now comes from the rent schedule as of the date (as on the page).
  Holdover detection now matches the page. Record any rows that differ in the
  validation notes.

**Multi-suite row building** inside `build_rent_roll`. This replaces the per-suite
loop (`rent_roll.py` 211–262):

Two passes. Match every suite first, then emit rows, so a combined row can sit at its
**primary** suite's position with the label in lease order (primary first). For
Dallas Pro Paint, the row is `1614-2 # 200 / 1614-1 # 110` among the 1614-2 suites,
even though `1614-1 # 110` sorts earlier.

```python
        lease_suites = load_lease_suites([l["LeaseID"] for l in active_leases + holdover_leases], db)
        report_ids = {int(s["SuiteID"]) for s in suites}

        # Pass 1: match
        match_by_suite: dict[int, tuple[dict, bool]] = {}   # sid -> (lease, is_holdover)
        for s in suites:
            sid, prop_id, label = int(s["SuiteID"]), int(s["PropertyID"]), str(s.get("SuiteLabel") or "").strip()
            am = match_suite_to_lease(sid, prop_id, label, active_leases, lease_suites)
            hm = match_suite_to_lease(sid, prop_id, label, holdover_leases, lease_suites) if am is None else None
            if am is not None or hm is not None:
                match_by_suite[sid] = (am or hm, am is None)

        def anchor_suite(lease) -> int | None:
            """Where a lease's row goes: its first LeaseSuites row (the primary) that is
            in this report, else the first member in report order."""
            for r in lease_suites.get(int(lease["LeaseID"]), []):
                if int(r["SuiteID"]) in report_ids:
                    return int(r["SuiteID"])
            return None

        # Pass 2: emit, in report order
        for s in suites:
            sid = int(s["SuiteID"])
            if sid not in match_by_suite:
                # ... Vacant / Owner Occupied row, unchanged ...
                continue
            lease, is_holdover = match_by_suite[sid]
            anchor = anchor_suite(lease)
            if anchor is not None and anchor != sid:
                continue                         # emitted at the anchor's position
            ls_rows = [r for r in lease_suites.get(int(lease["LeaseID"]), [])
                       if int(r["SuiteID"]) in report_ids]
            if len(ls_rows) <= 1:
                row_label = str(s.get("SuiteLabel") or "").strip()      # identical to today
                row_sqft  = s.get("SquareFeet")
            else:
                row_label = report_label([r["SuiteLabel"] for r in ls_rows])
                row_sqft  = sum(float(r.get("SquareFeet") or 0) for r in ls_rows)
            # ... emit ONE row exactly as today (active or holdover variant),
            #     with suite=row_label, sq_ft=row_sqft, full EffectiveRent ...
```

- Vacant and Owner-Occupied rows are unchanged.
- A lease must never be emitted twice. Add a defensive `emitted_lease_ids` set. This
  covers a legacy lease matched to two suites by the Tenants fallback. Today that case would
  emit twice, so behavior changes only in that already-broken case. Note it if it occurs.
- The "unlinked" pass (264–287) skips a lease if **any** of
  `suite_ids_for(l, lease_suites)` is in `report_ids`. This replaces the single-`SuiteID` check.
- Stats: total rentable is still summed per suite. Occupied SF and PSF now come from the
  combined row's summed SF and full rent, which gives the correct weighted PSF.

**Early-termination fix (existing bug, folded in by Mark 2026-10-05).** Today the Rent
Roll page (`rent_roll.py` 150–170), the PDF (`LucidPM.py` 72–111, where the cutoff is in SQL),
and the Dashboard (`dashboard.py` 115–148, also in SQL) decide "active" from `LeaseEnd` only.
They ignore `LeaseStatus = 'Terminated'` / `LeaseTerminationDate`. Only Proforma honors
them. Real trigger: Dallas Pro's Lease 73 is terminated 10/31/2026 with `LeaseEnd`
12/31/2026. From 11/1, both Lease 73 and the new lease match #200, and the older one
wins (no `ORDER BY`), so the report shows $975.

**This bug is already live in Prod (found 2026-10-05).** Bamm Bamm Services' Lease 49 on
`1612-1 # 102` (SuiteID 7) is Terminated 2026-05-15 with `LeaseEnd` 2026-12-31. Pioneer
Insurance & Tax's Lease 1087 has held #102 since 2026-07-01. Both pass the active test,
and with no `ORDER BY` the lower LeaseID (49, Bamm Bamm) most likely wins. Rent is
$1,250 either way, so the totals are right, but the occupant shown is probably wrong.
After the fix, the Rent Roll page, PDF and Dashboard must show Pioneer on #102.

In `build_rent_roll`:
- Add `l.LeaseStatus, l.LeaseTerminationDate` to the lease SELECT.
- Active test: `start <= as_of and (eff_end is None or eff_end >= as_of)`, where
  `eff_end = effective_end(l)` and replaces the raw `end`.
- **A Terminated lease is never a holdover.** Skip it in the holdover branch, because the
  tenant left on purpose.
- Add `ORDER BY l.LeaseStart DESC, l.LeaseID DESC` to the lease SELECT. If two leases
  still match one suite, the newer one wins. That is deterministic, and it is the right tie-break.
- The PDF inherits all of this through `build_rent_roll`.

#### 2b. `pages/dashboard.py` `_load_rent_roll_summary` (100–211)

- Add `l.LeaseID` to both lease SELECTs if missing (the active query already has it).
- Replace the local `find_lease` with `match_suite_to_lease`. Load `lease_suites`
  once for active + holdover lease IDs.
- Occupancy stays **per suite**: each linked suite counts as occupied.
- **Rent is counted once per lease.** Keep a `counted_lease_ids: set[int]` and
  only add `RentAmount` the first time a lease is matched.
- Leave the dashboard on `RentAmount` (not scheduled rent). That is its current
  behavior, and convergence is out of scope here.
- **Early-termination fix:** add to the active-lease WHERE (line ~126)
  `AND NOT (l.LeaseStatus = 'Terminated' AND l.LeaseTerminationDate IS NOT NULL AND l.LeaseTerminationDate < ?)`
  (param `today`). Add `AND ISNULL(l.LeaseStatus, '') <> 'Terminated'` to the holdover
  WHERE (line ~144). Add `ORDER BY l.LeaseStart DESC, l.LeaseID DESC` to both queries.

---

### Phase 3 — Proforma and Leases Expiring

#### 3a. `pages/proforma.py`

Suites are keyed by `SuiteLabel` throughout. Keep that, but resolve membership by ID:

1. Suite query (316–320): add `SuiteID`. Build `suite_id_by_label`.
2. After loading `lease_rows` (348–357), `lease_suites = load_lease_suites(...)`.
3. Replace the `suite_leases` selection (420–430):

```python
                sid = suite_id_by_label[suite]
                suite_leases = [
                    l for l in lease_rows
                    if sid in suite_ids_for(l, lease_suites)
                ]
                # Fallback for legacy leases with no SuiteID / LeaseSuites rows (unchanged)
                legacy = [l for l in lease_rows
                          if not suite_ids_for(l, lease_suites)
                          and str(l.get("TenantSuite") or "").strip() == suite]
                suite_leases += legacy
                if not suite_leases and tenant_ids:
                    suite_leases = [l for l in lease_rows if int(l["TenantID"]) in tenant_ids]
```

   `suite_ids_for` reads `SuiteID`, so add `l.SuiteID` to the lease SELECT (348–357).
4. Rent allocation. In the `controlling_leases` loop (~470–478), take this suite's
   share of the month's lease amount with `split_amount`. Do not multiply by a float,
   because the suite columns must add up **to the cent** to the lease amount
   (Dallas Pro Paint: $1,025.00 + $1,250.00 = $2,275.00). Import `Decimal` and
   `split_amount` / `load_lease_suites` / `suite_ids_for` at the top of `proforma.py`:

```python
                    lease_month = self._calc_month_amount(segs, year, month_num,
                                                          lease_start=ls, rent_due_day=due_day)
                    rows_ls = lease_suites.get(lid, [])
                    if len(rows_ls) > 1:
                        parts = split_amount(Decimal(str(lease_month)),
                                             [Decimal(str(r["RentAllocationPct"])) for r in rows_ls])
                        idx = [int(r["SuiteID"]) for r in rows_ls].index(sid)
                        amount += float(parts[idx])
                    else:
                        amount += lease_month                      # unchanged path
```

5. `last_known_rent` (365–375) is currently keyed by `TenantSuite` label. Rebuild
   it per suite membership: for each lease and each of its suites, the stored value =
   `last_seg rent × allocation_pct`. A vacant suite's recommended rent then reflects
   that suite's share, not the whole combined lease.
6. Changed-cell / tenant-change detection (~500+) is unchanged. It keys by suite
   and tenant, both of which still apply.

Single-suite check: `allocation_pct` returns 100 for single-suite and legacy leases,
so every existing proforma must be **numerically identical**.

#### 3b. `pages/leases_expiring.py`

- Add `l.LeaseID` (already present) and load `lease_suites` once next to the lease
  query (468–470). Pass it into `_build_events` and down to the two helpers. Thread
  it as a parameter; do not use a module global.
- `_same_suite(a, b)` (161–178): first compare
  `suite_ids_for(a, ls) & suite_ids_for(b, ls)`. A non-empty overlap means the same suite.
  Keep the existing `TenantSuiteID` / label fallbacks after that.
- Successor lookup (140–158): replace `l.get("SuiteID") == suite_id` with
  `_same_suite(this_lease, l, lease_suites)`.
- Wherever an event displays a suite label, use `report_label` of the lease's suites.
- **Early-termination fix:** add `l.LeaseStatus, l.LeaseTerminationDate` to the lease
  SELECT (468–470). In `_build_events` and in the current/successor date tests (140–215),
  use `effective_end(l)` instead of raw `LeaseEnd`. A Terminated lease's expiration event
  is dated at its termination date. If that date is already past, the lease drops off
  the list like any other past expiration. Do not change the event-type wording.

---

### Phase 4 — Lease documents

#### 4a. `lease_merge.py` `get_lease_merge_context`

Prod templates today use three suite tokens: `{{SuiteLabel}}` (twice, in insurance
clauses), `{{SuiteFullAddress}}` ("Premises: …"), and `{{SuiteLegalDescription}}` (bold
legal description). **All three must cover every suite.** Taking only the primary suite's
description would silently drop Suite 110 from the Dallas Pro Paint legal description.

Keep the base SELECT (618–640) as is. It joins the **primary** suite, which remains the
source for `SuiteUseType` and `SuiteAddressOverride`. `load_lease_suites` (Phase 1)
already returns `SuitePremisesDescription` and `SuiteLegalDescription`. After the
lease row loads:

```python
    ls_rows = load_lease_suites([lease_id], db).get(int(lease_id), [])
    multi = len(ls_rows) > 1
    if multi:
        suite_label = join_labels([r["SuiteLabel"] for r in ls_rows])          # "A and B", primary first
        total_sf    = sum(float(r.get("SquareFeet") or 0) for r in ls_rows)
        premises    = combine_descriptions([r.get("SuitePremisesDescription") for r in ls_rows],
                                           [r.get("SuitePremisesDescription") for r in ls_rows])
        suite_legal = combine_descriptions([r.get("SuitePremisesDescription") for r in ls_rows],
                                           [r.get("SuiteLegalDescription") for r in ls_rows])
    else:
        suite_label = _s(lease.get("SuiteLabel")) or _s(lease.get("TenantSuiteText"))   # unchanged (line 767)
        total_sf    = lease.get("SquareFeet")
        premises    = _s(lease.get("SuitePremisesDescription"))
        suite_legal = _s(lease.get("SuiteLegalDescription"))
```

Then, with the single-suite values identical to today:
- `Suite` / `SuiteLabel` / `SuiteName` → `suite_label`
- `SuiteSquareFeet` → `fmt_number(total_sf, 0)`
- `SuitePremisesDescription` → `premises`. `SuiteLegalDescription` → `suite_legal`.
  `legal_description` (773) → `suite_legal or PropertyLegalDescription`.
- `_suite_full_address(row, suite_label)` (146–158) reads premises from `row`. For a multi-suite
  lease, pass a copy of `lease` with `SuitePremisesDescription = premises`. If the primary
  suite has a `SuiteAddressOverride`, **ignore it when multi** (an override names one
  suite) and note this in a code comment. In the bare-label branch, use `"Suites"`
  instead of `"Suite"` when multi.
- `UnderwritingRent` → sum across suites when multi.
- **New tokens:** `SuiteWord` (`"Suite"` / `"Suites"`) and `SuiteCount`. No current Prod template
  hard-codes "Suite {{Suite…", so nothing breaks without them. They are for future templates.
  Add them to the picker in `_available_token_buttons_panel` (`pages/lease_documents.py`),
  or to the catalog seed if H55 has landed.
- Rent tokens are already lease-level ($2,275 for the example). No change.

Expected Dallas Pro Paint output (verified against Prod descriptions 2026-10-05):

```
SuiteLabel            1614-2 # 200 and 1614-1 # 110
SuiteFullAddress      Bldg. 1614-2, Suite 200 and Bldg. 1614-1, Suite 110, 1614 S. Broadway, Carrollton, …
SuiteLegalDescription Bldg. 1614-2, Suite 200 and Bldg. 1614-1, Suite 110, 1614 S. Broadway Street, being
                      Lot 2b Block 1, of I-35 Marchant Addition, City of Carrollton, Texas 75006
SuiteSquareFeet       1,930
```

#### 4b. `pages/lease_package_builder.py`

Lease picker labels (554–591) and the selected-lease suite label (669–701): use
`report_label` of the lease's suites, falling back to the current `SuiteLabel`.

---

## Do Not Touch

- `LeaseRentSchedule` structure and every rent calculation outside the allocation multiply in Proforma.
- `Tenants.SuiteID` / `Tenants.Suite`, and the tenant form's suite field (1892–1926).
- Dropping or renaming `Leases.SuiteID`, or its FK and index.
- The Walnut combined suite records (`1 & 2`, `3 & 4`, `5 & 6`) and any other suite/lease data.
- Section Library content (template wording changes are Mark's call).
- `property_financials_analytics.py`, except the H57 note above.
- Rent Roll PDF layout / styling code (`rent_roll_pdf.py`, and the PDF table code below line ~200 in `LucidPM.py`).
- `_vN` siblings. Archive only the siblings of files this handoff edits, after verification, per CLAUDE.md
  (`rent_roll_*.py`, `dashboard_*.py`, `proforma_*.py`, `leases_expiring_*.py`, `suites_*.py`, `tenants_*.py`).

---

## Validation Checklist

Run with the **local app (`reflex run`) toggled to Test, i.e. Azure `TenantCRM_Test`**,
unless stated otherwise. The worked-example setup edits Test data only. Never edit
Dallas Pro or Orbit in `TenantCRM`.

**Before any code change:** save a baseline. Capture the Rent Roll rows (All properties,
today, Tax and Bank), the Rent Roll PDF, the Dashboard tiles, the Proforma for each property
(current year, both bases), and the Leases Expiring list.

Phase 1
- [ ] Script runs twice on Azure `TenantCRM_Test` without error (idempotent). Both verification queries return 0.
- [ ] The deployed app (still `0.4.3`) works normally against Test after the script ran. Open a tenant's leases and the Rent Roll.
- [ ] Row count in `LeaseSuites` = count of leases with non-null `SuiteID`.
- [ ] Edit an existing single-suite lease and save without changes. Its `LeaseSuites` row is unchanged (100%, primary).
- [ ] **Worked example on Test.** First mirror the Prod setup on Test: Dallas Pro's current
      #200 lease is Terminated with `LeaseTerminationDate` 2026-10-31, and the #110 holder's lease
      ends 2026-10-31. Then create the expansion lease (start 2026-11-01, Parent = the
      terminated lease; primary `1614-2 # 200` at $1,025, add `1614-1 # 110` at $1,250). No overlap warning.
      Rent field shows $2,275.00 read-only. After saving, DB has 2 rows: 45.054945 (primary) +
      54.945055 = 100, `Leases.SuiteID` = #200's ID, `RentAmount` = 2275, and the Base schedule row = 2275.
      Re-open the lease: the amounts show $1,025.00 / $1,250.00 exactly.
- [ ] "Split total by SF" on $2,275 fills $1,001.94 / $1,273.06.
- [ ] A missing or zero suite amount → error and nothing saved.
- [ ] Use the Primary radio to make #110 primary and save. Flags swap, and `Leases.SuiteID` follows.
      The trigger and the lease list now show #110 first.
- [ ] Uncheck the primary in the dropdown. The next checked suite becomes primary.
- [ ] Single-suite flow: check one suite. Row 2a never appears, and Monthly rent is editable as today.
      Check a second suite: the primary's amount is pre-filled with the current rent.
      Uncheck it again: the total is kept and Monthly rent is editable again.
- [ ] Dropdown trigger matches the neighbouring selects visually, and long suite lists scroll inside the popover.
- [ ] Remove all suites and save. Zero rows, `Leases.SuiteID` NULL.
- [ ] Overlap warning appears when a chosen suite is on another live lease with overlapping dates.
- [ ] Delete the test lease. `LeaseSuites` rows are gone (cascade).
- [ ] Suites admin: deleting a suite used only as a non-primary suite is blocked.
- [ ] With the worked-example lease deleted, every report matches the baseline exactly.

Phase 4 (delivered second, right after Phase 1)
- [ ] Generate a package for the worked-example lease. `{{SuiteLabel}}`, `{{SuiteFullAddress}}`,
      `{{SuiteLegalDescription}}`, and `{{SuiteSquareFeet}}` match the expected output in 4a exactly.
      Rent tokens = $2,275.00. `{{SuiteWord}}` = "Suites".
- [ ] Generate a package for a single-suite lease. The output is byte-identical to one generated before this phase.
- [ ] `combine_descriptions` fallback: with mismatched legal-description tails (Test data only),
      the output is the full texts joined with "; and ".
- [ ] Lease package builder picker shows "1614-2 # 200 / 1614-1 # 110" for the test lease.
- [ ] Phase 4 code imports nothing introduced in Phase 2 or 3.
- [ ] **Ship gate:** after P1 + P4 are verified on Test, Mark runs the schema script on Azure
      `TenantCRM` and releases image `0.5.0` ("Release to Azure"). He then enters the real Dallas Pro lease
      and generates its documents before 11/1, from either the deployed or the local app.

Phase 2 (with the worked-example lease in place)
- [ ] Rent Roll page as of 2026-10-31: #200 = Lease 73 at $975; #110 = Orbit at $1,250.
- [ ] Rent Roll page as of 2026-11-01: exactly one row
      `1614-2 # 200 / 1614-1 # 110 · 1,930 · Dallas Pro Paint & Drywall · $2,275.00`, positioned among the
      1614-2 suites. `1614-1 # 110` does not appear on its own. The terminated lease does not appear.
- [ ] A Terminated lease past its termination date is not shown as a holdover.
- [ ] Prod spot-check: `1612-1 # 102` shows **Pioneer Insurance & Tax** (Lease 1087), not Bamm Bamm (Lease 49).
- [ ] Vacancy %, occupied SF, and avg PSF are correct by hand calculation.
- [ ] Rent Roll PDF shows the same rows and totals as the page.
- [ ] With the worked-example lease deleted, the Rent Roll page matches the baseline **except** for
      rows involving Terminated leases (termination fix). List every such row for Mark.
      Run `SELECT LeaseID, LeaseEnd, LeaseTerminationDate FROM Leases WHERE LeaseStatus='Terminated'`
      first to know what to expect. PDF differences beyond that come only from the scheduled-rent / holdover
      convergence. List them too.
- [ ] Dashboard on/after 11/1: occupied count includes both suites, monthly rent includes $2,275 once,
      and the terminated lease's $975 is not counted.

Phase 3
- [ ] Proforma Broadway 2026: Jan–Oct unchanged from the baseline. Nov and Dec: `1614-2 # 200` = $1,025.00 and
      `1614-1 # 110` = $1,250.00. Proforma 2027: the same split every month of the term.
- [ ] A rent-schedule step-up added mid-term (Test only, e.g. to $2,350) splits $1,058.79 / $1,291.21. Columns sum to the cent.
- [ ] A partial first month (proration) still sums to the cent across the two columns.
- [ ] Without the test lease, every Proforma matches the baseline exactly.
- [ ] Leases Expiring: a renewal of the 2-suite lease sharing either suite is recognised as the successor.
- [ ] Leases Expiring: the terminated lease is not listed as expiring 2026-12-31. The #110 holder's
      lease is listed as ending 2026-10-31.

After each release: spot-run the phase's key checks on the **deployed** app
(`https://lucidpm.lucidoproperties.net`), first toggled to Test, then Prod.

**Operator note for splitting Walnut (Mark, by hand, after Phase 3):** for each
combined record (e.g. `1 & 2`):
1. Create suite records `1` and `2` with their own SF.
2. On the current lease, set primary = `1`, add `2`, and check the allocation.
3. Mark `1 & 2` **inactive**. Do not delete it, because historical leases still point at it.
   An active, unleased `1 & 2` would show up as a Vacant row and inflate rentable SF.

---

## How to Deliver This

One commit per phase, **in the order P1 → P4 → P2 → P3**, each verified before the next.
**P1 + P4 are due in time for Mark to generate the Dallas Pro lease before 2026-11-01**
(target: verified on Test by ~2026-10-19). Suggested messages:
`H73 P1: LeaseSuites table, lease_suites helper, multi-suite lease form` ·
`H73 P4: Multi-suite lease merge tokens + package builder labels` ·
`H73 P2: Rent Roll + Dashboard multi-suite and early-termination fix; converge Rent Roll PDF on page logic` ·
`H73 P3: Proforma per-suite allocation; Leases Expiring multi-suite + termination`.
Then a separate commit archives `_vN` siblings of the edited files.

Codex's job ends at verified local commits. **Release to Azure is Mark's step** (or Claude
at Mark's request). It is the first code release since the Entra/custom-domain cutover.

### Release to Azure

Live as of 2026-10-05: Container App `lucidpm` (RG `Lucido-Apps-RG`), image
`ghcr.io/mslucido-lab/lucidpm:0.4.3`, revision `lucidpm--0000009`, `minReplicas 0`,
custom domain `lucidpm.lucidoproperties.net`. Versions for this handoff:
P1+P4 → **`0.5.0`**, P2 → `0.5.1`, P3 → `0.5.2`.

From the repo root (PowerShell), with Docker Desktop running and the release commit
checked out with a clean working tree (`git status`). The build copies the working directory,
so uncommitted files would ship.

```powershell
# 1. Build. REFLEX_API_URL is baked into the frontend bundle at build time (H64/H71 lesson:
#    omitting it pointed download links at localhost). Use the custom domain so browser
#    API calls are same-origin; this also closes the Cycle 5.4 optional follow-up.
docker build --build-arg REFLEX_API_URL=https://lucidpm.lucidoproperties.net `
  -t ghcr.io/mslucido-lab/lucidpm:0.5.0 .

# 2. Push (docker login ghcr.io first if needed; a token with write:packages).
docker push ghcr.io/mslucido-lab/lucidpm:0.5.0

# 3. Point the Container App at it. This creates a new revision; env vars, secrets, auth,
#    domain and scale settings carry over (update merges, it does not replace).
az containerapp update -n lucidpm -g Lucido-Apps-RG --image ghcr.io/mslucido-lab/lucidpm:0.5.0

# 4. Confirm the new revision is running and healthy.
az containerapp revision list -n lucidpm -g Lucido-Apps-RG -o table
```

**Verify on `https://lucidpm.lucidoproperties.net`:** the sign-in works. The lease form
shows the Suite(s) dropdown. A Rent Roll PDF opens and a lease package downloads. Those two
are the links that break if `REFLEX_API_URL` is wrong. Run the Phase key checks, Test then Prod.

**Rollback** (if the new revision misbehaves):
`az containerapp update -n lucidpm -g Lucido-Apps-RG --image ghcr.io/mslucido-lab/lucidpm:0.4.3`.
The 014 table can stay. `0.4.3` ignores it. Note: a lease saved with two suites under
`0.5.0` will show only its primary suite under `0.4.3`, which is harmless. No data is lost.

---

## File Locations

| File | Phase | Change |
|---|---|---|
| `db/history/014_2026-10-05_<HHMM>_lease_suites.sql` | 1 | **New.** Table, indexes, backfill |
| `db/baseline_schema.sql`, `db/history/CHANGELOG.md`, `docs/Database.md` | 1 | Regenerate / document |
| `LucidPM/lease_suites.py` | 1, 2 | **New.** Shared helpers; `build_rent_roll` added in P2 |
| `LucidPM/pages/tenants.py` | 1 | Lease form multi-suite + allocation, save/load/list |
| `LucidPM/pages/suites.py` | 1 | Delete guard |
| `LucidPM/pages/rent_roll.py` | 2 | Use `build_rent_roll` |
| `LucidPM/LucidPM.py` | 2 | `_build_rent_roll_pdf_bytes` uses `build_rent_roll` |
| `LucidPM/pages/dashboard.py` | 2 | Shared matcher; rent once per lease |
| `LucidPM/pages/proforma.py` | 3 | Membership by SuiteID, allocated rent |
| `LucidPM/pages/leases_expiring.py` | 3 | Suite-overlap matching |
| `LucidPM/lease_merge.py` | 4 | Combined suite label/SF, `SuiteWord`/`SuiteCount` |
| `LucidPM/pages/lease_documents.py` | 4 | Token picker entries |
| `LucidPM/pages/lease_package_builder.py` | 4 | Combined labels |
