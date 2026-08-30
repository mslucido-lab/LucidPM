# LucidoPM — ChatGPT Handoff 55

## Merge-Token Catalog — Phase 1 (data-driven resolver + picker)

---

## What This Is

Merge tokens (`{{TenantName}}`, `{{ExtensionRentWords}}`, …) are defined in **two hand-maintained places that have drifted apart**:

1. `LucidPM/lease_merge.py` → `get_lease_merge_context()` — a ~121-entry Python dict, the resolver.
2. `LucidPM/pages/lease_documents.py` → `_available_token_buttons_panel()` — 9 hardcoded `_token_group(...)` lists, 86 `"{{Token}}"` strings, the author-facing picker.

The picker is a subset of the resolver and **~35 real tokens are missing from it**; there are no per-token descriptions.

**Phase 1 introduces `dbo.MergeTokenCatalog`** — one table, both DBs — as the single source of truth. The picker reads it. The resolver reads it for *simple field tokens* (column → format) so adding one becomes a table row, not a code change. Everything already working keeps working, unchanged, because a seed script reproduces today's token set exactly.

### Scope constraint — Phase 1 ONLY

- **No admin UI.** Catalog rows are edited via a `db/data_updates/` script or SSMS for now. The `/admin/merge-tokens` page is Phase 2 (sketched at the end, do not build it here).
- **No new token behaviour.** Do not add, rename, retire, or re-group any token. The seeded catalog must render an identical picker and identical merge output to `main` today.
- **No formula language.** `field` tokens are `SourceObject.SourceColumn` + a fixed `Format` enum. Nothing conditional. Everything conditional stays `computed` (Python).
- **One schema script, one seed script, edits to two `.py` files.** Nothing else.

---

## Current State (real references)

### `lease_merge.py`

- `from LucidPM.state import run_query, run_exec, TEST_DB_NAME` (line 32).
- `TOKEN_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_\.\-]+)\s*\}\}")` (line 34).
- `_table_exists(table_name, db) -> bool` (line 281) and `_get_table_columns(table_name, db) -> set[str]` (line 271) — **use these for graceful degradation**, same as `_rent_schedule_summary` does at line 291.
- Formatters already present: `fmt_date` (`%m/%d/%Y`, line 82), `fmt_iso_date` (line 87), `fmt_money` (line 92), `fmt_number` (line 100), `number_to_words` (line 390), `_ordinal` (line 244), `_long_date` (line 261), `_short_date_no_leading_zero` (line 266).
- `get_lease_merge_context(tenant_id, lease_id, db) -> dict[str, str]` (line 614):
  - Builds one big joined `lease` row (lines 620–641): `Leases l` LEFT JOIN `Tenants t`, `Properties p`, `PropertySuites ps`, `LeaseTypes lt`, `LeaseTermTypes ltt`. So property/suite/tenant/leasetype columns are all already on `lease`.
  - Also loads: `contact` (tenant primary contact row), `parent_lease` (lines 648–653: `LeaseStart, LeaseEnd, ExecutionDate, LeaseTypeName` when `ParentLeaseID` set).
  - `context = { … }` literal (line 778 → 935), then ~40 more `context["X"] = …` lines (938 → 1008), then `return context` (line 1010).
- `render_text_template(template_text, context)` (line 1013) — `TOKEN_PATTERN.sub`, unknown token → left verbatim + reported. **Do not change.**

### `lease_documents.py`

- `_token_group(label, tokens, target_id)` (line 3290) — renders one titled row of `_token_insert_button`s.
- `_token_insert_button(token, target_id)` (line 3280) — purple button, `on_click=rx.call_script(_insert_token_at_cursor_script(token, target_id))`. **The insert-at-cursor JS (line 3250) is unchanged.**
- `_available_token_buttons_panel(target_id)` (line 3304) — the `rx.box` with 9 hardcoded `_token_group(...)` calls (Header / Clause Numbering / Tenant / Property-Suite / Lease Dates-Term / Rent-Payment / Options-Other / Amendment-Renewal) + two `rx.text` help captions. Called from the section editor, the create-text body, and the create-bulk body (3 call sites, all pass a textarea `id`).
- State class: `LeaseDocumentState(AppState)` — same file. `run_query` / `run_exec` already imported; `self.db` is the active DB.

### `db/` conventions (see `docs/Database.md`)

- Schema change → a script in `db/history/`, named `NNN_YYYY-MM-DD_HHMM_short_description.sql`, **idempotent guards**, and an `INSERT INTO dbo.SchemaChangeLog` block (template: `db/history/012_2026-08-25_2326_add_tenant_isdba_flag.sql`). Last number is **012**, so this is **013**.
- Data seed → a script in `db/data_updates/`, `YYYY-MM-DD_<desc>.py`, connects via `LucidPM.state.get_conn`, **dry-run by default**, `--commit` to write, prints a recovery copy first (template: `db/data_updates/2026-08-27_handoff_52_dynamic_clause_numbering.py`).
- Run everything against `TenantCRM_Test` first, verify, then `TenantCRM`.

---

## The Fix — Phase 1

### 1. Schema — `db/history/013_<date>_<time>_merge_token_catalog.sql`

Create `dbo.MergeTokenCatalog` (idempotent — `IF OBJECT_ID('dbo.MergeTokenCatalog','U') IS NULL`):

| Column | Type | Notes |
|---|---|---|
| `MergeTokenID` | `INT IDENTITY(1,1) PRIMARY KEY` | |
| `TokenName` | `NVARCHAR(100) NOT NULL` | no braces, e.g. `TenantContactEmail`. `UNIQUE`. |
| `DisplayName` | `NVARCHAR(200) NOT NULL` | picker label |
| `GroupName` | `NVARCHAR(60) NOT NULL` | picker section header |
| `Description` | `NVARCHAR(500) NULL` | what it resolves to / when blank |
| `Kind` | `VARCHAR(20) NOT NULL` | `CHECK (Kind IN ('field','computed'))` |
| `SourceObject` | `NVARCHAR(40) NULL` | `field` only — whitelisted (see §3) |
| `SourceColumn` | `NVARCHAR(128) NULL` | `field` only |
| `Format` | `VARCHAR(20) NULL` | `field` only — enum (see §3); `NULL`/`raw` = passthrough |
| `SortOrder` | `INT NOT NULL DEFAULT 100` | within group |
| `IsActive` | `BIT NOT NULL DEFAULT 1` | hide from picker without deleting |
| `ExampleValue` | `NVARCHAR(200) NULL` | optional "e.g. March 1, 2026" |
| `UpdatedOn` | `DATETIME2 NOT NULL DEFAULT SYSDATETIME()` | |

Add the `SchemaChangeLog` INSERT block. **Run Test, verify, then Prod** — commit the script either way (it is the record).

### 2. Resolver — `lease_merge.py`

**2A. A whitelisted source-object map.** Near the end of `get_lease_merge_context()`, *before* `return context`, assemble the dict of rows a `field` token may read from. Start with exactly:

```python
catalog_sources = {
    "lease": lease,            # the big joined row — has Lease/Tenant/Property/Suite/LeaseType cols
    "contact": contact,
    "parent_lease": parent_lease,
}
```

Add clean `"tenant"` / `"property"` / `"suite"` sub-dicts **only if** it removes real ambiguity — `lease` already carries those columns, so it is acceptable to ship with just the three above. This set is the **entire** allowed surface; a catalog row naming anything else resolves blank (and should be flagged by the Phase 1 validation check below).

**2B. A fixed formatter registry:**

```python
_TOKEN_FORMATTERS = {
    "raw":        lambda v: _s(v),
    "money":      lambda v: fmt_money(v) if v is not None and str(v) != "" else "",
    "number0":    lambda v: fmt_number(v, 0) if v is not None and str(v) != "" else "",
    "number2":    lambda v: fmt_number(v, 2) if v is not None and str(v) != "" else "",
    "date":       lambda v: fmt_date(v),          # m/d/Y
    "date_iso":   lambda v: fmt_iso_date(v),
    "date_long":  lambda v: _long_date(_date(v)) if _date(v) else "",
    "ordinal":    lambda v: _ordinal(int(v)) if str(v or "").strip().isdigit() else "",
    "words":      lambda v: number_to_words(v) if v is not None and str(v) != "" else "",
    "upper":      lambda v: _s(v).upper(),
}
```

`None`/unknown `Format` → treat as `raw`.

**2C. Merge catalog `field` tokens into the context — BEFORE the hand-written entries win.** The cleanest way: resolve them into a local dict and lay it down **first**, so any hand-written `context["X"]` later in the function overrides a same-named catalog row (migration safety — if a token is both seeded as `field` and still computed in code, code wins and output is unchanged):

```python
# near the TOP of the context dict assembly, e.g. right after `context = {`
# ...actually simplest: build catalog dict, then `context = {**_catalog_field_context(...), **context_literal}`
```

Recommended shape — a module-level helper:

```python
def _catalog_field_context(db: str, sources: dict[str, dict]) -> dict[str, str]:
    if not _table_exists("MergeTokenCatalog", db):
        return {}
    rows = run_query(
        "SELECT TokenName, SourceObject, SourceColumn, Format "
        "FROM dbo.MergeTokenCatalog WHERE Kind = 'field' AND IsActive = 1",
        db=db,
    )
    out: dict[str, str] = {}
    for r in rows:
        src = sources.get(str(r["SourceObject"] or ""))
        if src is None:
            continue  # unknown source object — leave unresolved
        fmt = _TOKEN_FORMATTERS.get(str(r["Format"] or "raw"), _TOKEN_FORMATTERS["raw"])
        try:
            out[str(r["TokenName"])] = fmt(src.get(str(r["SourceColumn"] or "")))
        except Exception:
            out[str(r["TokenName"])] = ""
    return out
```

Then in `get_lease_merge_context`, once `lease` / `contact` / `parent_lease` exist and the `catalog_sources` map is built:

```python
_catalog_fields = _catalog_field_context(db, catalog_sources)
# ... build the big `context = { ... }` literal ...
context = {**_catalog_fields, **context}   # hand-written entries always win
```

**Do not** call `_catalog_field_context` after the aliases block — it must not clobber `context["Landlord"]` etc.

**2D. Nothing else in `lease_merge.py` changes.** `render_text_template`, `apply_clause_numbering`, every existing computed entry: untouched.

### 3. Whitelist + format enum — write these into the seed as the contract

- **`SourceObject` ∈ `{lease, contact, parent_lease}`** (plus `tenant`/`property`/`suite` iff you added them in 2A).
- **`Format` ∈ `{raw, money, number0, number2, date, date_iso, date_long, ordinal, words, upper}`** or `NULL`.
- A `field` row MUST have `SourceObject` + `SourceColumn`. A `computed` row MUST leave all three of `SourceObject`/`SourceColumn`/`Format` `NULL`.

### 4. Seed — `db/data_updates/<date>_seed_merge_token_catalog.py`

One row per token that exists on `main` today. Build the list by walking **both** current sources:

1. Every key in the `get_lease_merge_context` return dict (the literal + the `context["X"] = …` lines + the aliases). That is the full ~121.
2. Every `"{{Token}}"` string in `_available_token_buttons_panel` (the 86) — these carry the **GroupName** (the `_token_group` label) and rough ordering.

For each token:

- **`GroupName`** — from the `_token_group` it is in. Tokens in the resolver but **not** in any picker group → put in a new group **`"Uncategorized"`** (surfacing the drift is a feature; Mark re-groups later via Phase 2).
- **`Kind`** — classify by inspecting the resolver line:
  - `field` **only if** the value is a single `sources-object` column read through at most one formatter and nothing else. Concretely: `_s(lease.get("PropertyCity"))` → `field / lease / PropertyCity / raw`. `fmt_money(lease.get("DepositAmount"))` → `field / lease / DepositAmount / money`. `_s(contact.get("Title"))` → `field / contact / Title / raw`.
  - `computed` for **everything else** — any `or` fallback (`_s(a) or _s(b)`), any f-string, any conditional (`… if parent_lease_id else ""`), any `.title()`/`.upper()` chained on another token, any helper (`_property_full_address`, `_lease_term_description`, `number_to_words` on a derived value, `_payment_schedule_block`, …), and every alias assigned from another `context[...]`.
  - When unsure → `computed`. A token wrongly marked `computed` still works (code resolves it); a token wrongly marked `field` may resolve blank. Bias to `computed`.
- **`DisplayName`** — humanize `TokenName` (`TenantContactEmail` → "Tenant contact email"); tighten obvious ones.
- **`Description`** — one line. For the ~15 tokens whose git commit message explains them (`AsAmendedPhrase`, `OriginalOptionRent[Words]`, `OriginalLease*`, `DBAName`, `TenantNameWithDBA`, `BaseRentWordsTitle`, `PriorAmendmentsClause`, `LeaseTermBlock`, `AmendmentTermBlock`), lift a sentence from there. Otherwise a plain description is fine.
- **`SortOrder`** — 10, 20, 30, … in current picker order within the group; 100 for Uncategorized.
- **`ExampleValue`** — optional, only where cheap and useful.

Script mechanics per `docs/Database.md`: `get_conn`, dry-run prints the full INSERT set + a row count, `--commit` writes, refuses to run if `MergeTokenCatalog` already has rows (so it is not double-seeded). Idempotency: `WHERE NOT EXISTS (SELECT 1 FROM dbo.MergeTokenCatalog WHERE TokenName = ?)` per row. **Test first, verify picker + a package generation, then Prod.**

### 5. Picker — `lease_documents.py`

**5A. Load the catalog into state.** Add to `LeaseDocumentState`:

```python
merge_token_catalog: list[dict] = []   # [{name, group, description, example}]

def _load_merge_token_catalog(self):
    try:
        rows = run_query(
            "SELECT TokenName, GroupName, Description, ExampleValue "
            "FROM dbo.MergeTokenCatalog WHERE IsActive = 1 "
            "ORDER BY GroupName, SortOrder, TokenName",
            db=self.db,
        )
    except Exception:
        rows = []
    self.merge_token_catalog = [
        {"name": r["TokenName"], "group": r["GroupName"],
         "description": r.get("Description") or "", "example": r.get("ExampleValue") or ""}
        for r in rows
    ]
```

Call it wherever the tab data loads (alongside `_load_all_sections()` / on tab entry) and on DB toggle. If the query fails or returns nothing (table not yet seeded), **fall back to the current hardcoded lists** so the editor is never tokenless — keep the existing `_token_group` literal as `_LEGACY_TOKEN_GROUPS` and render it when `merge_token_catalog` is empty.

**5B. Render from data.** `_available_token_buttons_panel(target_id)` groups `merge_token_catalog` by `group` (preserving query order) and renders one `_token_group`-style block per group, each button `{{name}}`. Keep the Clause Numbering caption (those 3 tokens are seeded too — `ClauseNumber`, `ClauseNumber:Anchor`, `ClauseRef:Anchor`, group "Clause Numbering", `computed`). Show `description` as a tooltip (`title=`) or a small muted line under each group — your call, keep it compact; the panel already lives in a scroll box.

**5C. Reflex note.** `rx.foreach` over a `list[dict]` of plain str values is fine. If nested `rx.foreach` (groups → tokens) fights the compiler, pre-shape in Python into `list[{"group": str, "tokens": list[str], "descriptions": list[str]}]` via a `@rx.var` and foreach that.

### Phase 1 checklist

- [ ] `013_…merge_token_catalog.sql` creates the table on Test and Prod; `SchemaChangeLog` row written on both.
- [ ] Seed script: dry-run shows ~121 rows, refuses double-seed; `--commit` populates Test then Prod.
- [ ] Every token in `_LEGACY_TOKEN_GROUPS` is present in the catalog with the same group.
- [ ] `git grep` count: catalog row count ≥ resolver key count (nothing dropped).
- [ ] Picker renders from the catalog; every button still inserts `{{Name}}` at the cursor.
- [ ] With the table absent (rename it locally), picker falls back to legacy list and `get_lease_merge_context` still returns — no crash.
- [ ] **Generate a real package on Test that exercised several tokens — output byte-identical to a pre-change generation of the same package.** (The core acceptance test.)
- [ ] Add a throwaway `field` row by hand (`INSERT … 'TestPokeToken','lease','PropertyCity','raw'`), regenerate a preview with `{{TestPokeToken}}` in a section → resolves to the city. Delete the row.
- [ ] `import LucidPM.LucidPM` builds; `reflex run` console clean.

---

## Do Not Touch

| What | Why |
|---|---|
| `render_text_template`, `TOKEN_PATTERN`, `apply_clause_numbering` | The render path is not changing — only how the context dict is populated. |
| Any existing `context["X"] = …` / dict-literal entry in `get_lease_merge_context` | They must keep resolving exactly as today. Catalog `field` values are laid down *under* them. |
| `_insert_token_at_cursor_script`, `_token_insert_button` | Button behaviour unchanged. |
| `lease_package_builder.py` | Consumes the context; Phase 3 territory (unknown-token report). Not now. |
| `DOCUMENT_LEVEL_TOKENS` / `_drop_document_level_tokens` (`lease_package_builder.py:102`) | Clause-numbering plumbing from Handoff 52. Unrelated. |
| The `/admin/lease-templates` tabs | The catalog admin is its own page (Phase 2). |

---

## Gotchas

- `get_lease_merge_context` raises `ValueError` if the lease is not found — keep the catalog call *after* that guard.
- The `lease` row has **COALESCE'd / aliased** columns (`ISNULL(p.LandlordEntityName,'') AS LandlordEntityName`). A `field` token reading `lease.LandlordEntityName` gets `''` not `NULL` when unset — fine, `raw` handles it. But `LandlordEntity` itself is `computed` (`_s(...) or _property_owner(...)`).
- `contact` may be `{}` (no primary contact) — `.get()` returns `None` → formatters must no-op on `None` (they do, as written).
- `parent_lease` is `{}` on a base lease — every `parent_lease` `field` token then resolves blank, which matches the current `… if parent_lease_id else ""` behaviour. Good.
- Do not seed the `context[...]` **aliases** (`Landlord`, `Premises`, `MonthlyRent`, `RentAmount`, `LeaseStart`, …) as `field` — they are assigned from other context keys, so they are `computed`. Seed them so the picker lists them, `Kind = computed`, group "Aliases" or their natural group.
- Reflex `rx.select`/state list rendering: if the picker was previously all module-level (no state), you are now adding a state read — make sure the panel's 3 call sites are all inside components that can see `LeaseDocumentState`. They are (same file), but the panel currently takes no state — wire `merge_token_catalog` through.

---

## Deferred (explicitly out of Phase 1)

- **Phase 2 — `/admin/merge-tokens` page.** Standalone route (Mark's call, 2026-08-29). Left list grouped by `GroupName`, right detail form. `field` rows: `SourceObject` dropdown (the whitelist), `SourceColumn` free text or a dropdown from `INFORMATION_SCHEMA` for the picked object, `Format` dropdown, live preview against a chosen sample lease (call `get_lease_merge_context` and show the one value). `computed` rows: `DisplayName`/`GroupName`/`Description`/`SortOrder`/`IsActive`/`ExampleValue` editable, the rest read-only with a "resolved in code" note. New-token flow with Kind picker. List/detail pattern per every other admin module.
- **Phase 3 (optional) — unknown-token report.** In `lease_package_builder`'s generate/preview, diff `extract_tokens(section_text)` against `MergeTokenCatalog` + the live context; surface "used but not in catalog" and "in catalog but never resolves" as a soft warning. Deprecation flow (`IsActive = 0` hides from picker but still resolves).
- **Re-grouping / renaming / retiring any current token** — Mark does this through the Phase 2 UI once it exists.
- **Formula language for computed tokens** — considered and rejected (see `project_token_catalog_idea` memory). Not happening.

---

## File Locations

```
db/history/013_<date>_<time>_merge_token_catalog.sql          ← new (schema, both DBs)
db/data_updates/<date>_seed_merge_token_catalog.py            ← new (seed, both DBs)
LucidPM/lease_merge.py
  _TOKEN_FORMATTERS, _catalog_field_context                   ← new module-level
  get_lease_merge_context(): catalog_sources map + merge      ← ~line 760 / ~line 778
LucidPM/pages/lease_documents.py
  LeaseDocumentState.merge_token_catalog / _load_…            ← new state
  _available_token_buttons_panel(): render from state         ← line 3304
  _LEGACY_TOKEN_GROUPS (kept as fallback)                     ← from the current literal

Templates to copy:
  db/history/012_2026-08-25_2326_add_tenant_isdba_flag.sql
  db/data_updates/2026-08-27_handoff_52_dynamic_clause_numbering.py
```

---

*Phase 1 makes the catalog real and authoritative without changing a single rendered character: the seed reproduces today's tokens, the resolver lays catalog `field` values *under* the hand-written ones, and the picker reads the table with the old hardcoded lists as a fallback. The payoff is immediate for the picker (one list, descriptions, drift gone) and for future simple tokens (a row, not a diff). Computed tokens stay in Python — catalogued, not migrated.*
