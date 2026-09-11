# Cycle 4.1 - Generated package storage abstraction

**Goal:** validate the new generated-lease-package storage abstraction locally against both the existing filesystem behavior and the private Azure Blob container.

- Storage account: `lucidpmdocs24899` in `Lucido-Apps-RG`, West US 3.
- Container: private `lucidpm-documents`.
- Scope: generated lease packages only. Source PDFs, upload, splitting, and schema remain unchanged.
- The full Storage Account connection string was used only from ignored local `.env`; it is not committed or deployed.

## A. Local filesystem regression

- [x] With the local backend, an isolated one-page PDF round trip wrote under a flat `Generated` folder, preserving the existing filename behavior.
- [x] A duplicate filename used the original `_2` suffix rather than overwriting the first package.
- [x] The local stored bytes were read back unchanged.

## B. Blob Storage write and read

- [x] With `LUCIDPM_STORAGE_BACKEND=azure_blob`, a generated package appeared in the private `lucidpm-documents` container.
- [x] The Blob key uses the generated-package namespace and lease-specific collision-resistant identifier.
- [x] The generated package downloaded successfully from the LucidPM app.
- [x] The same PDF was also downloaded successfully from Azure Storage.
- [x] Package-history status, Review, and Download all report and retrieve Blob-backed packages correctly. Live validation found that the history status used a direct `os.path.isfile()` check; H66 corrected it to use the storage backend before this verification.

## C. Regeneration

- [x] Regeneration produced a second package record and a second Blob object.
- [x] Both the original and regenerated package remain available and report `File OK`.

## D. Configuration and import checks

- [x] Missing `LUCIDPM_BLOB_CONNECTION_STRING` with the Blob backend raises a clear `RuntimeError`; it never falls back to local storage.
- [x] `azure-storage-blob==12.30.1` and locked transitive dependencies were added to the runtime dependency set.
- [x] Python compile checks and `import LucidPM.LucidPM` passed. The existing sitemap-plugin warning remains non-fatal.

## Result: Cycle 4.1 COMPLETE - Date: 2026-09-11

The generated-package read/write pair works with both storage backends. The deployed Container App has not changed in this cycle. Cycle 4.2 must rebuild and deploy the image, replace the local account-key connection string with a scoped SAS token or managed identity, then prove a generated package survives Container Apps scale-to-zero. That is Gate 4 and POC completion.
