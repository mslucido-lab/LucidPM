# LucidoPM — ChatGPT Handoff 59
*Env-aware API base URL — retire the hardcoded `http://localhost:8000` in PDF/report links*
*Prepared: 2026-09-07 · revised 2026-09-07 (Codex pre-impl review: `communications_report.py` is a dead orphan — dropped from edit scope; override/trailing-slash verified as an isolated subprocess check; acceptance = base+PDF, unrelated warnings recorded separately; regression grep tightened to `localhost:8000/api`)*
*Azure Migration — Stage 3 prerequisite (does not need Azure)*

---

## What This Is

Eight live page modules build absolute download URLs to the Reflex **backend**
by hardcoding `http://localhost:8000`. That string is correct only on the dev
laptop with the backend on its default port. It is wrong the moment the app
runs on any other port (`reflex run --backend-port 8002` — used for the H58
Azure smoke test) and **completely broken in a container** (Stage 3), where the
browser reaches the app through one HTTPS ingress hostname and there is no
`localhost:8000`. Every "Download PDF" / "Open report" link 404s.

*(A ninth file, `pages/communications_report.py`, has the same literal but is a
dead orphan — not imported, not routed, no `@rx.page`; `/communications` and
`/communications-report` are both served by `pages/communications.py`. It is
**not** edited here; it goes to `Archived Versions/` in the housekeeping step.)*

This handoff replaces the literal with a one-line helper that reads Reflex's
own `api_url` config. **With no configuration, the helper returns
`http://localhost:8000` — byte-identical to today.** `reflex run --backend-port
N` makes it `http://localhost:N` automatically. A deployment points it at the
real hostname via `REFLEX_API_URL` (or `rxconfig.py`) — that deployment wiring
is **Stage 3.1's job, not this handoff's**.

This came out of the Handoff 58 review (findings 2 + 4). Finding 2 — a stale
`"TenantCRM"` literal in the same `tenants.py` var — is folded in here since the
file is already being touched.

### Scope constraint

**URL construction only.** This handoff does **not**:

- Set `api_url` / `REFLEX_API_URL` for any deployment, or touch `rxconfig.py`
  — Stage 3.1.
- Change the PDF endpoints themselves (`LucidPM.py` `@api.get("/api/...")`),
  their query params, or any generated PDF.
- Change which database a link targets — the `&db=` param is passed through
  unchanged (except the `tenants.py` literal swap in Step 10, which is a no-op
  today).
- Touch any `_vN` / numbered sibling file (`proforma_6_4.py`,
  `rent_roll_8_FIXED.py`, …). Live files only. Sibling archival is optional
  housekeeping — see *How to Deliver*.
- Convert these to relative URLs. Reflex serves frontend and backend from
  different origins in dev; an absolute backend URL is required. The helper
  keeps them absolute, just not hardcoded.

**Files that change:** `LucidPM/state.py` (+1 helper) and 8 live page modules
under `LucidPM/pages/` (import + f-string swaps, ~11 lines total), plus a
comment-only touch in `pages/lease_documents.py`.

---

## The Current State

`grep -rn "http://localhost:8000" LucidPM/pages/*.py` on the live files:

| File | Line(s) | `@rx.var` | Endpoint | In scope |
|---|---|---|---|---|
| `pages/communications.py` | 1694 | `pdf_url` | `/api/communications-pdf` | ✅ Step 2 |
| `pages/leases_expiring.py` | 539 | `pdf_url` | `/api/leases-expiring-pdf` | ✅ Step 3 |
| `pages/lease_package_builder.py` | 364, 370 | `generated_download_url`, `selected_generated_download_url` | `/api/lease-generated-pdf` | ✅ Step 4 |
| `pages/lease_package_builder.py` | 1825 | (row build in `_load_generated_packages`) | `/api/lease-generated-pdf` | ✅ Step 4 |
| `pages/proforma.py` | 85, 93 | `pdf_download_url`, `bank_package_url` | `/api/proforma-pdf`, `/api/bank-package-pdf` | ✅ Step 5 |
| `pages/property_financials.py` | 91 | `pdf_download_url` | `/api/property-financials-pdf` | ✅ Step 6 |
| `pages/rent_roll.py` | 336 | `pdf_download_url` | `/api/rent-roll-pdf` | ✅ Step 7 |
| `pages/tenants.py` | 704 | `application_report_url` | `/api/application-report-pdf` | ✅ Steps 8 + 10 |
| `pages/communications_report.py` | 321 | `pdf_url` | `/api/communications-pdf` | ❌ dead orphan → archive (housekeeping) |

All eight in-scope files already have `import reflex as rx` and a
`from LucidPM.state import …`. Each site is a plain Python f-string inside an
`@rx.var` body — evaluated on the backend, rendered by the frontend as an `href`.

**`pages/communications_report.py` is dead code.** Nothing imports it; it has no
`@rx.page`, `add_page`, or `route=`. `LucidPM.py` registers **both**
`/communications` (line 989) and `/communications-report` (line 991) with
`communications_page` / `CommunicationsState` from `pages/communications.py`.
Editing this module would change nothing a user can reach. Do **not** apply the
URL fix to it; move it to `Archived Versions/` in the housekeeping step instead.

Reflex 0.8.9 (`reflex.config.Config`):
- `api_url` default = `f"http://localhost:{DefaultPorts.BACKEND_PORT}"` → `http://localhost:8000`.
- `_replace_defaults()` rewrites it to `http://localhost:<port>` when `backend_port` is passed (i.e. `reflex run --backend-port 8002`), **unless** `api_url` was set explicitly.
- Any field is overridable by a `REFLEX_`-prefixed env var → `REFLEX_API_URL`.

`rxconfig.py` is currently bare (`rx.Config(app_name="LucidPM")`), so `api_url`
is the default today.

Two comments also name the hardcoded port and should be corrected:
- `pages/rent_roll.py:334` — `@rx.var` docstring "…pointing to the Reflex backend on port 8000."
- `pages/lease_documents.py:206` — header-comment line "PDF download URLs must target localhost:8000 explicitly…"

---

## The Fix

### Step 1 — `state.py`: add `api_base_url()`

`LucidPM/state.py` already has `import reflex as rx` (line 10). Add this helper
next to `get_conn` (anywhere at module scope after the imports is fine; put it
just below `_odbc_brace` / `get_conn`):

```python
def api_base_url() -> str:
    """Browser-reachable base URL of the Reflex backend API, no trailing slash.

    Replaces the `http://localhost:8000` literal that every PDF/report download
    link used to hardcode. Reads Reflex's own `api_url` config:
      * unset            -> "http://localhost:8000" (local behaviour unchanged)
      * --backend-port N  -> "http://localhost:N" (Reflex rewrites api_url)
      * deployed          -> whatever REFLEX_API_URL / rxconfig.py sets
    """
    return rx.config.get_config().api_url.rstrip("/")
```

### Steps 2–8 — the 8 live page modules

For each file: (a) add `api_base_url` to its `from LucidPM.state import …`
line/block, (b) replace `http://localhost:8000` with `{api_base_url()}` in the
f-string(s), converting `"..." + params` to an f-string where needed. The
`/api/...` path and every query param stay exactly as they are.

---

**Step 2 — `pages/communications.py`**

Import (line ~21):
```python
from LucidPM.state import (
    AppState, run_query, run_exec, decrypt_value, resolve_upload_filename,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES,
)
```
→ add `api_base_url`:
```python
from LucidPM.state import (
    AppState, run_query, run_exec, decrypt_value, resolve_upload_filename,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES, api_base_url,
)
```
Line 1694:
```python
            f"http://localhost:8000/api/communications-pdf"
```
→
```python
            f"{api_base_url()}/api/communications-pdf"
```

---

**Step 3 — `pages/leases_expiring.py`**

Import (line 24):
```python
from LucidPM.state import AppState, run_query, BRAND_PRIMARY, BRAND_DARK
```
→
```python
from LucidPM.state import AppState, run_query, BRAND_PRIMARY, BRAND_DARK, api_base_url
```
Line 539:
```python
            f"http://localhost:8000/api/leases-expiring-pdf"
```
→
```python
            f"{api_base_url()}/api/leases-expiring-pdf"
```

---

**Step 4 — `pages/lease_package_builder.py`**

Import (line 67):
```python
from LucidPM.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
```
→
```python
from LucidPM.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY, api_base_url
```
Line 364:
```python
        return f"http://localhost:8000/api/lease-generated-pdf?generated_id={self.last_generated_document_id}&db={self.db}"
```
→
```python
        return f"{api_base_url()}/api/lease-generated-pdf?generated_id={self.last_generated_document_id}&db={self.db}"
```
Line 370:
```python
        return f"http://localhost:8000/api/lease-generated-pdf?generated_id={self.selected_generated_id}&db={self.db}"
```
→
```python
        return f"{api_base_url()}/api/lease-generated-pdf?generated_id={self.selected_generated_id}&db={self.db}"
```
Line 1825:
```python
                download_url=f"http://localhost:8000/api/lease-generated-pdf?generated_id={generated_id}&db={self.db}",
```
→
```python
                download_url=f"{api_base_url()}/api/lease-generated-pdf?generated_id={generated_id}&db={self.db}",
```

---

**Step 5 — `pages/proforma.py`**

Import (line 30):
```python
from LucidPM.state import AppState, run_query, BRAND_DARK, BRAND_PRIMARY
```
→
```python
from LucidPM.state import AppState, run_query, BRAND_DARK, BRAND_PRIMARY, api_base_url
```
Line 85:
```python
            f"http://localhost:8000/api/proforma-pdf"
```
→
```python
            f"{api_base_url()}/api/proforma-pdf"
```
Line 93:
```python
            f"http://localhost:8000/api/bank-package-pdf"
```
→
```python
            f"{api_base_url()}/api/bank-package-pdf"
```

---

**Step 6 — `pages/property_financials.py`**

Import (line 17):
```python
from LucidPM.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY
```
→
```python
from LucidPM.state import AppState, run_query, run_exec, BRAND_DARK, BRAND_PRIMARY, api_base_url
```
Line 91:
```python
            f"http://localhost:8000/api/property-financials-pdf"
```
→
```python
            f"{api_base_url()}/api/property-financials-pdf"
```

---

**Step 7 — `pages/rent_roll.py`**

Import (line ~19): add `api_base_url` to the block (currently
`AppState, run_query,` / `BRAND_PRIMARY, BRAND_DARK,`).

Line 334 docstring:
```python
        """Builds the PDF endpoint URL pointing to the Reflex backend on port 8000."""
```
→
```python
        """Builds the PDF endpoint URL pointing to the Reflex backend (see state.api_base_url)."""
```
Line 336:
```python
        return "http://localhost:8000/api/rent-roll-pdf" + params
```
→
```python
        return f"{api_base_url()}/api/rent-roll-pdf" + params
```

---

**Step 8 — `pages/tenants.py`**

Import (line ~74):
```python
from LucidPM.state import (
    AppState, run_query, run_exec, fmt_date, resolve_upload_filename,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES, TEST_DB_NAME,
)
```
→ add `PROD_DB_NAME` (Step 10) **and** `api_base_url`:
```python
from LucidPM.state import (
    AppState, run_query, run_exec, fmt_date, resolve_upload_filename,
    BRAND_PRIMARY, BRAND_DARK, METHOD_CHOICES, TEST_DB_NAME, PROD_DB_NAME,
    api_base_url,
)
```

### Step 9 — `pages/lease_documents.py` comment only

Line ~206, header comment:
```python
#   - PDF download URLs must target localhost:8000 explicitly (frontend on 3000, backend 8000).
```
→
```python
#   - PDF download URLs come from state.api_base_url() (Reflex api_url); local default is backend :8000.
```
No code in this file changes.

### Step 10 — `pages/tenants.py`: the two-line var (H58 review finding 2)

`application_report_url` (lines ~700–704):

**Current:**
```python
    @rx.var
    def application_report_url(self) -> str:
        if self.tenant_id <= 0:
            return "#"
        db_name = self.db or "TenantCRM"
        return f"http://localhost:8000/api/application-report-pdf?tenant_id={self.tenant_id}&db={db_name}"
```

**Replace with:**
```python
    @rx.var
    def application_report_url(self) -> str:
        if self.tenant_id <= 0:
            return "#"
        db_name = self.db or PROD_DB_NAME
        return f"{api_base_url()}/api/application-report-pdf?tenant_id={self.tenant_id}&db={db_name}"
```

`self.db` (inherited from `AppState`) is always a non-empty string today, so
`or PROD_DB_NAME` is a defensive no-op — it just stops the fallback from being
pinned to the literal `"TenantCRM"` if `LUCIDPM_PROD_DB` is ever overridden.

---

## Do Not Touch

| What | Why |
|---|---|
| `rxconfig.py` | Setting `api_url` for a deployment is Stage 3.1 |
| `pages/communications_report.py` (edit it) | Dead orphan — not imported, not routed. Do not apply the URL fix; archive it in the housekeeping step |
| Route registration in `LucidPM.py` (lines 989 / 991) | `/communications` and `/communications-report` stay pointed at `communications_page` |
| The `@api.get("/api/...")` endpoints in `LucidPM.py` | Endpoints, params, and PDFs are unchanged — only the caller's base URL |
| The `&db=` / `?tenant_id=` / every other query param | Passed through verbatim |
| Any `_vN` / numbered sibling (`proforma_6_4.py`, `rent_roll_8_FIXED.py`, `tenants_23.py`, …) | Live files only; siblings are archive-pending |
| `deploy_url` (the frontend URL) | Not used by any of these links |
| `AppState.db` / `use_test_db` / the toggle | Untouched; `db_name` still resolves from `self.db` |
| `state.get_conn` and everything H58 added | Unrelated |

---

## Validation Checklist

### A — `api_base_url()` in isolation (no browser, no websocket)

Run these as one-off subprocesses (like H58's `ConfigError` checks). Setting
`REFLEX_API_URL` in a live `reflex run` also redirects the frontend↔backend
websocket, so the app never finishes loading and the links can't be inspected
in a browser — so verify the override **here**, not in the running app.

- [ ] `python -c "import LucidPM.state as s; print(s.api_base_url())"` →
      `http://localhost:8000` (unset default, unchanged).
- [ ] Same with `REFLEX_API_URL=https://example.test` → `https://example.test`.
- [ ] Same with `REFLEX_API_URL=https://example.test/` → `https://example.test`
      (one trailing slash stripped, exactly one).
- [ ] Same with `REFLEX_API_URL=https://h.test/base/` → `https://h.test/base`
      (only the trailing slash goes; an internal path segment is preserved).

### B — browser checks on real ports (default 3000/8000)

- [ ] `reflex run` compiles; no import error for the new `api_base_url` symbol
      in any of the 8 pages.
- [ ] Rent Roll → "Download PDF" opens the rent-roll PDF; the URL bar shows
      `http://localhost:8000/api/rent-roll-pdf?...` — character-for-character
      what it was before this handoff.
- [ ] Repeat for: Proforma (PDF **and** Bank Package), Property Financials,
      Leases Expiring, the Communications report (`/communications` route), a
      Tenant's Application Report, and a generated Lease Package download — both
      the just-generated link and a row in the generated-packages list.

### C — browser checks on a non-default backend port (proves the fix)

- [ ] `reflex run --frontend-port 3002 --backend-port 8002`, open the app on
      3002. Every link from section B now points at `http://localhost:8002/...`
      and returns the PDF. (Before this handoff they pointed at `:8000` and
      failed on a 3002/8002 instance — the exact wart noted in the H58
      validation.)

### D — regression

- [ ] Toggle Test/Prod, re-open one report — the `&db=` value in the URL still
      follows the toggle.
- [ ] `grep -rn "localhost:8000/api" LucidPM/` returns **only** `_vN` / numbered
      siblings — zero hits in `state.py`, `LucidPM.py`, or the 8 live pages.
      (Plain `"localhost:8000"` without `/api` still legitimately appears once,
      in `state.api_base_url`'s docstring — that's the allowed documented
      default, not URL construction.)

### Acceptance

H59 is done when **A–D pass**: every download link resolves to the correct
base for the port/config, and the PDF is delivered. Pre-existing unrelated
warnings surfaced while testing (e.g. the lease-package generation "invalid
column `LeaseDocumentSectionID`" audit warning that H58 also hit) are
**recorded in the delivery notes, not fixed here** and do not block acceptance.
For the lease-package link test, reuse the known-working
`Core Lease Package - DO NOT USE` template on Test lease 4 (same as H58) rather
than hunting for a fresh template.

---

## How to Deliver This

Per `CLAUDE.md`: edit the live files in place, no `_vN` copies.

1. Apply Steps 1–10.
2. Run checklist section **A** (isolated), then **B** (default ports — the "did
   we change local behaviour" gate; URLs must be character-for-character the
   same).
3. Then **C** (non-default port) and **D** (regression + grep).
4. Commit — e.g. `Env-aware API base URL: retire hardcoded localhost:8000 (H59)`.
5. Move this doc to `Completed Handoffs/`.

### Then (housekeeping, separate commit(s) — per the incremental cleanup rule)

- **`pages/communications_report.py` → `Archived Versions/`.** It is a dead
  orphan (see *Current State*); this handoff establishes that. Move it and
  commit separately, e.g. `Archive orphaned communications_report.py (dead route)`.
- **`_vN` siblings of the 8 touched files → `Archived Versions/`.** Large sibling
  sets under `LucidPM/pages/` (`proforma_1.py … proforma_6_6.py`,
  `rent_roll_3.py … rent_roll_8_FIXED.py`, `property_financials_8.py`,
  `property_financials _7.py` (note the space), `leases_expiring_4.py … _7.py`,
  `tenants_1.py … tenants_24.py`, `lease_package_builder_*`,
  `communications_report_1.py`/`_2.py`). Move each touched file's siblings and
  commit separately (one commit, or one per file — mirror how H58 split
  `b47b6f8` from `d18a256`). Bulky; fine to defer to its own session — do
  **not** let it hold up the URL fix.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\state.py                          ← Step 1 (helper)
  LucidPM\pages\communications.py           ← Step 2
  LucidPM\pages\leases_expiring.py          ← Step 3
  LucidPM\pages\lease_package_builder.py    ← Step 4  (3 sites)
  LucidPM\pages\proforma.py                 ← Step 5  (2 sites)
  LucidPM\pages\property_financials.py      ← Step 6
  LucidPM\pages\rent_roll.py                ← Step 7  (+ docstring)
  LucidPM\pages\tenants.py                  ← Steps 8 + 10
  LucidPM\pages\lease_documents.py          ← Step 9 (comment only)
  LucidPM\pages\communications_report.py    ← NOT edited; archive (housekeeping)

Dev app: http://localhost:3000 (frontend) / :8000 (backend)  — api_base_url() = http://localhost:8000
```

---

*One helper in `state.py`, an import line + an f-string swap in 8 live pages,
one comment, one bonus literal fix; one dead orphan dropped from scope. Local
behaviour byte-identical (Reflex's `api_url` default is the same string that was
hardcoded). Unblocks Stage 3.1 — a containerised app can point every download
link at its real ingress host with one env var.*
