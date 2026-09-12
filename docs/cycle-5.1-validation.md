# Cycle 5.1 - Production source PDF Blob migration

**Result: PASSED for `TenantCRM` on 2026-09-12.**

H69 migrated Production source PDFs and PDF-backed lease sections to Azure Blob. The deployed
Container App remains intentionally locked to `TenantCRM_Test`; Production was validated through the
local app.

## Path-repair detour

The original bulk stale-path repair incorrectly assumed the OneDrive backup was newer than the live
`C:\Dell Inspirion` document root. A fresh comparison of all 17 rewritten Production rows found:

- 8 files only in the OneDrive backup;
- 3 copies present at both roots with identical SHA-256 hashes; and
- 6 newer files only at `C:\Dell Inspirion`.

The six Dell-only rows (source IDs 7-8; section IDs 51-52 and 62-63) were restored with guarded SQL
updates. The guard required each row still to reference the OneDrive root and updated exactly 2 source
and 4 section rows. No files were deleted.

## Migration and verification

- The maintenance window contained the comparison, guarded path repair, dry run, migration, and local
  validation.
- The H69 dry run found **17 readable local rows**, no existing Blob identifiers, and no fallback
  bucket rows.
- The committed migration uploaded all 17 PDFs, updated the matching `TenantCRM` rows to `azblob:`
  identifiers, and produced ignored H69 manifest and rollback files.
- Every manifest entry reached `migrated`; every Blob SHA-256 hash matched its original local file;
  every original local file remained present.

## Local Production validation

With the local process scoped to `LUCIDPM_SINGLE_DB=TenantCRM` and
`LUCIDPM_STORAGE_BACKEND=azure_blob`, Mark generated and downloaded the **4C's Option Extension
Agreement with a dual signature page**. This specifically exercises the previously Dell-only PDF-backed
path and confirms the generated package works from Blob storage.

## Remaining scope

The Container App remains Test-only until the separate Stage 5.3 production exposure and Entra work.
The storage-root admin UI redesign remains outside Cycle 5.1.
