# Cycle 5.1-early - source PDF Blob migration

**Result: PASSED for `TenantCRM_Test` on 2026-09-12.**

This early Stage 5.1 work fixed the Container App failure for lease packages that contain PDF-backed
sections. It does not migrate production (`TenantCRM`).

## Implementation

- Source PDFs and split PDF sections now use `DocumentStorage`.
- Blob-backed identifiers use the self-describing `azblob:` prefix, so rows backed by Blob and legacy
  local paths can coexist regardless of the configured write backend.
- Local source-document behavior remains rooted at the document root (`Admin/...` and `Sections/...`),
  separate from generated packages' `Generated/...` root.
- Package generation and PDF splitting resolve either a local path or an `azblob:` identifier. Rendered
  text sections remain temporary local files during the merge.

## Test data migration

- The Test stale-path prerequisite was resolved first. All 25 source/section PDF rows were readable.
- The migration ran in dry-run mode before committing. It directly constructed the Blob writer, rather
  than using `LUCIDPM_STORAGE_BACKEND`.
- **25 `TenantCRM_Test` rows** were migrated to Blob. Object hashes matched their local originals and
  local files were retained.
- The ignored migration manifest and reviewed rollback SQL were produced under `db/data_updates/`.
- No `TenantCRM` rows were read or modified.

## Deployed validation

- Image `ghcr.io/mslucido-lab/lucidpm:0.3.0` was built and pushed with the source-PDF support.
- Container App revision `lucidpm--0000004` reached **Healthy** and received 100% of traffic.
- Mark generated the formerly failing **Lease Package #2** in the live Test-only Container App. The
  General Lease PDF was retrieved from Blob, generation succeeded, and the resulting package opened
  correctly after download.

## Remaining scope

Production source/section PDFs remain unchanged. Their migration requires a separate reviewed handoff
after the Test result is accepted. The storage-root admin UI redesign is also outside this work.
