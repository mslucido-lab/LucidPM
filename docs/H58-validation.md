# H58 validation — 2026-09-07

Steps 1-6 of the revised handoff are implemented. Part A connection-plumbing
acceptance passed, with the separate package warnings below recorded for follow-up.

## Passed

- Default local Windows-auth connection reaches `TenantCRM_Test`.
- Reflex starts and compiles on frontend 3002 / backend 8002.
- Dashboard, Rent Roll, Tenants, and Lease Documents render local Test and
  Production data in headless Chromium.
- Browser toggle works Test → Production → Test, with distinct dashboard data.
- Leases-Expiring PDF endpoints return valid PDFs with the correct Test and
  Production header labels (text verified with pypdf).
- Six separate startup subprocesses reject unknown authentication, missing SQL
  credentials, non-integer and negative timeout, invalid encryption, and invalid
  certificate-trust settings with the expected named `ConfigError`.
- Isolated unit checks cover each missing credential, matching quote removal,
  unmatched quote preservation, quoted whitespace and punctuation, host-env
  precedence, Windows/SQL connection strings, password brace escaping, timeout,
  and the single-database state/toggle guard.
- With process-scoped `LUCIDPM_SINGLE_DB=TenantCRM`, Chromium shows PRODUCTION
  and no Switch button. Rent-roll PDF requests naming Production, Test, and a
  nonexistent database return identical Production report text.
- `git diff --check` passes. No dotenv dependency or persistent `.env` added.

## Lease-package acceptance

Using the user-selected `Core Lease Package - DO NOT USE` template with local
Test lease 4 succeeded: one section loaded, preview reported 14 known tokens
and zero missing tokens, and generation produced document 165 (version 44).
The standalone endpoint on port 8002 returned HTTP 200 and a valid one-page PDF
with nonempty text. The generated file and Test database record are retained
for review. No Production write was performed.

Two separate issues were observed; neither was changed in H58:

- Generation reported an audit warning: invalid column `LeaseDocumentSectionID`.
  The PDF and generated-document record were created, but the audit operation
  needs separate investigation.
- Package download links are hardcoded to port 8000 in
  `pages/lease_package_builder.py` (lines 364, 370, 1825). The standalone endpoint
  was verified directly on dev port 8002; clicking the UI link on this dev
  instance still targets port 8000.

The initial Core Lease (ALL) selection did not load a usable template. The
user supplied the working test template above, closing the generation check.
The accepted single-DB green-dot cosmetic behavior remains unchanged.

## Checklist clarifications

- A3's unmatched-quote example is inconsistent: the literal value
  `'"leadingquote` contains both leading quote characters and the approved
  loader preserves both. The test checks that exact preservation.
- The recursive Trusted_Connection search also finds historical files still in
  `LucidPM/`. The live connection helper is centralized in `state.py`; historical
  archival remains deferred until acceptance, as required by the handoff.
- No production verification query was found in the sibling `Database/`
  directory under a `*verify*` filename. No replacement query was fabricated.

## Azure / Gate 2

Part B was not run. No Azure credentials, persistent configuration, or Azure
resources were changed. Cold-resume timing and Azure read/write checks remain
Cycle 2.2 work, separate from H58 acceptance.
