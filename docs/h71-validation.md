# H71 validation - storage display and Production POC cleanup

Validated 2026-09-12.

## Storage display and deployment

The document-storage display now resolves the backend in Reflex state at runtime. This matters because Reflex creates the browser bundle during the Docker build, before Container App environment variables exist. A module-level Python environment check would therefore be baked with the build environment's value.

- Local and Blob-mode imports passed, and the production Reflex frontend export completed.
- The initial H71 deployment exposed that build-time issue. Revision `lucidpm--0000006` corrected the runtime state branch.
- The first image rebuild omitted the `REFLEX_API_URL` build argument, causing package download links to target `localhost`. Revision `lucidpm--0000007` uses `ghcr.io/mslucido-lab/lucidpm:0.4.2`, built with `REFLEX_API_URL=https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io`.
- Mark verified the deployed Admin Settings page shows `Azure Blob Storage (lucidpm-documents)` and has no editable local storage-root input.
- The deployed Lease Package download succeeds after the public API URL correction.
- The Container App remains Test-locked and retains both Office and Home ingress restrictions.

## Production POC cleanup

`db/data_updates/2026-09-12_h71_remove_prod_poc_test_packages.py` uses an explicit ID set: 2111 through 2116. Its dry run connected to Azure `TenantCRM`, wrote the ignored full-row manifest and rollback SQL, and found exactly six parent rows and 24 child rows. The commit deleted exactly those counts in one transaction.

| Table | Before | After |
| --- | ---: | ---: |
| `LeaseGeneratedDocuments` | 150 | 144 |
| `LeasePackageSections` | 2,591 | 2,567 |

A read-only post-check confirmed zero remaining approved parent or child rows. The cleanup script's database guard, manifest column coverage, `IDENTITY_INSERT` rollback SQL, Python compilation, and Reflex export were also checked.

The local, gitignored recovery artifacts remain at:

- `db/data_updates/h71_prod_package_cleanup_manifest.json`
- `db/data_updates/h71_prod_package_cleanup_manifest.rollback.sql`
