# H59 validation - 2026-09-08

H59 Steps 1-10 are implemented and acceptance sections A-D passed.

## Configuration and scope

- Four isolated subprocess checks passed: default `http://localhost:8000`,
  explicit `https://example.test`, trailing-slash removal, and preservation
  of the internal `/base` path in `https://h.test/base/`.
- Seven page modules use `state.api_base_url()` for their report/download
  links. `lease_documents.py` received only the specified comment change.
- Tenant application-report fallback now uses `PROD_DB_NAME`.
- Diff review confirms endpoint paths and query parameters are unchanged.
  No changes to SQL connection handling, PDF endpoints, or route registration.
- No `localhost:8000/api` URL construction remains in the seven edited pages,
  `state.py`, or `LucidPM.py`. Historical/orphan files are excluded as agreed.
- `git diff --check` passed.

## Browser and PDF checks

Headless Chromium inspected rendered links on both 3000/8000 and 3002/8002.
Each link's actual href was fetched and returned HTTP 200 with a valid PDF;
PDF parsing used pypdf. Both existing local app instances were available and
used for these checks; attempts to launch additional instances correctly
refused their occupied ports. Neither existing instance was stopped.

| Report/link | Port 8000 | Port 8002 | Pages |
| --- | --- | --- | --- |
| Rent Roll | Pass | Pass | 2 |
| Proforma | Pass | Pass | 1 |
| Bank Package | Pass | Pass | 3 |
| Property Financials | Pass | Pass | 1 |
| Leases Expiring (365-day window) | Pass | Pass | 1 |
| Communications (existing Test records) | Pass | Pass | 2 |
| Tenant Application Report | Pass | Pass | 2 |
| Lease package: just-generated link | Pass | Pass | 1 |
| Lease package: generated-list row | Pass | Pass | 1 |
| Lease package: selected document link | Pass | Pass | 1 |

Test -> Production -> Test switching was verified on both port pairs. Rent-roll
links retained the instance's backend port, changed their `db=` parameter
correctly, and delivered valid PDFs from both databases.

Two Test lease 4 packages were generated with the approved
`Core Lease Package - DO NOT USE` template: `H59_Test_Lease4_Port8000.pdf` and
`H59_Test_Lease4_Port8002.pdf`. Files and Test records are retained for review.
No Production records were changed; no communications were sent.

## Separate follow-ups

Both package generations reported the existing audit warning about invalid
column `LeaseDocumentSectionID`. PDF generation and all three download paths
succeeded. The warning remains outside H59, as agreed in its acceptance rules.

Azure SQL validation remains Cycle 2.2 work. Stage 3.1 must configure Reflex's
`api_url` for the browser-reachable ingress address; this change does not deploy
or configure Azure.

The orphaned communications-report module and its historical siblings are
archived in a separate commit. Bulk archival of the other touched page modules'
historical siblings is deferred to its own session, as H59 permits.
