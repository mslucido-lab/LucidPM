# LucidoPM — ChatGPT Handoff 66
*Storage abstraction for generated lease package PDFs: local filesystem today, Azure Blob as a second
implementation — proves the round-trip Cycle 4.2 needs*
*Prepared: 2026-09-11 · revised 2026-09-11 (Codex pre-implementation review, 3 questions + 2*
*corrections, all accepted):*
*(1) Collision-proof blob keys — confirmed real: `Generated/<filename>` + `overwrite=True` would let a*
*same-named later package silently replace an earlier one's actual blob content while the earlier*
*`LeaseGeneratedDocuments` row still points at that now-wrong content. Fixed: the key now bakes in*
*lease ID + timestamp + a short UUID, built once before persisting — see the redesigned Step 2. (2)*
*Regeneration — confirmed and a real miss: `merge_pdf_files()` is also called from the regeneration*
*path (`lease_package_builder.py` ~2282), not just first generation (~1581), and that second call site*
*has the identical disk-based `os.path.isfile`/`os.path.getsize`/`page_count(path)` post-write*
*validation that breaks under the Blob backend — the original draft only looked at the first call*
*site. Both are now in scope, sharing one new helper. (3) Storage-account connection string —*
*confirmed as intended: local Cycle 4.1 validation only, gitignored `.env`; Cycle 4.2 moves the*
*deployed app to a scoped SAS token or managed identity before the account key ever reaches the*
*Container App — stated explicitly now rather than left as a soft aside.*
*Two corrections folded in: the local backend was hardcoding `DEFAULT_DOCUMENT_ROOT`, silently*
*ignoring a caller's configured `LeaseDocumentStorageRoot` (`storage_root` parameter) — not*
*byte-identical to today. And the callers' own disk-based post-write validation*
*(`os.path.isfile`/`os.path.getsize`/`page_count`) needed to go — `merge_pdf_files()` now validates the*
*merged PDF itself, on the in-memory `PdfWriter`/bytes, before either backend ever sees it, and both*
*call sites' now-redundant (and Blob-broken) validation blocks are deleted.*
*Also folds in: `docs/Deployment.md` still describes Cycle 3.2 as not-yet-done (no image pushed, no*
*Container App) — stale since Gate 3 passed; corrected as part of this handoff (Step 6).*
*Revised again 2026-09-11 (Codex pre-implementation review, round 2 — 2 details, both accepted): (1)*
*`get_document_storage()`'s local branch called `generated_folder(...)`, which already appends*
*"Generated" — and `save_generated_package()`'s key ALSO starts with "Generated/", so the two stacked*
*into `...\Generated\Generated\<lease-id>\...` instead of `...\Generated\<lease-id>\...`, breaking the*
*byte-identical-default-path constraint. Fixed: the local branch now uses `normalize_storage_root(...)`*
*(the bare configured root) instead of `generated_folder(...)` — the single "Generated/" prefix in the*
*key is the only place that segment gets added, for both backends uniformly. (2)*
*`uuid.uuid4().hex[:8]` is only 32 bits, paired with `overwrite=True` on the blob upload — an*
*(astronomically unlikely, but nonzero) collision would have silently replaced an existing package's*
*actual content rather than erroring. Fixed: the full 128-bit `uuid.uuid4().hex`, not truncated, and*
*`overwrite=False` on the blob upload (the SDK's own default — the prior draft had actively opted out*
*of it) so a collision fails loudly. Extended the same fail-loud posture to the local backend's*
*`save()`, which had the identical silent-overwrite exposure via a plain `open(..., "wb")` — not*
*explicitly asked, but the same bug class in the other implementation of the same interface contract.*
*Azure Migration — Stage 4, Cycle 4.1. Low/medium risk — narrow, additive, no behavior change on the
default path.*

---

## What This Is

Roadmap **Cycle 4.1** (`Undelivered Handoffs/Azure Migration Roadmap.md`, Stage 4 — the last stage
before **POC COMPLETE**). Introduce a small storage interface with two implementations — local
filesystem (today's behavior, unchanged) and Azure Blob (new) — selected by an env var, and route
**one** read/write pair through it: generating a lease package PDF, and downloading it back. That
pair is exactly what Cycle 4.2's proof needs (*"generate/upload a lease PDF → scale the container to
zero and back → download it intact"*), and it's the narrowest real round-trip in the app to prove it
with.

**Scope constraint — deliberately narrow:**
- Only the **generated lease package** write/read pair is touched (`merge_pdf_files()` /
  `/api/lease-generated-pdf`). **Not** source-PDF upload (`save_uploaded_pdf`), **not** PDF splitting
  (`split_pdf_pages`), **not** the `storage_root` / `LeaseDocumentStorageRoot` admin-settings screen.
  Those all stay on local disk, exactly as today. Migrating them is Cycle 5.1 (the full production
  data migration, already scoped in the roadmap as its own, larger, higher-risk cycle tangled with the
  standing stale-`StoredFilePath` cleanup).
- No schema change. `LeaseGeneratedDocuments.StoredFilePath` keeps its name and column type — its
  *meaning* becomes backend-dependent (a real filesystem path for local, a blob identifier for Azure),
  same pattern as every other env-driven config in this repo.
- No container/deployment change. This cycle is pure application code, tested locally against a real
  (already-created) Azure Blob container. Deploying the updated image and doing the actual
  restart-survival proof against the live Container App is Cycle 4.2 — a separate, follow-on handoff.
- Default behavior (env var unset) must be byte-identical to today — same as every H58/H60/H63-style
  env-driven change already in this codebase.

**Azure resources already created this session** (prerequisites, not part of this handoff's own
scope):
- `Microsoft.Storage` resource provider registered on the subscription (was `NotRegistered` — same
  class of one-time gap `Microsoft.Sql` had at Stage 1).
- Storage account **`lucidpmdocs24899`** (Resource Group `Lucido-Apps-RG`, **westus3**,
  `Standard_LRS`, `StorageV2`, public blob access **disabled**, min TLS 1.2).
- Blob container **`lucidpm-documents`** (private, no public access).

---

## Current State

**The write side** — `merge_pdf_files()`, `LucidPM/pages/lease_documents_pdf.py:1173-1199`:
```python
def merge_pdf_files(section_paths: Iterable[str], output_name: str, storage_root: str | None = None) -> str:
    folder = generated_folder(storage_root or DEFAULT_DOCUMENT_ROOT)
    ensure_folder(folder)
    ...
    writer = PdfWriter()
    for path in paths:
        reader = PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)
    filename = safe_pdf_filename(output_name)
    target = os.path.join(folder, filename)
    ...
    with open(target, "wb") as f:
        writer.write(f)
    return target
```
**Two call sites, not one** — the first draft only accounted for the first:
- **First generation**, `lease_package_builder.py:1581`: `output_path = merge_pdf_files(pdf_paths_to_merge, self.package_name.strip(), root)`,
  then `os.path.isfile(output_path)` / `os.path.getsize(output_path)` / `page_count(output_path)`
  (lines 1582–1589), then `filename = os.path.basename(output_path)` (1591), then INSERT into
  `LeaseGeneratedDocuments` (1595–1600).
- **Regeneration**, `lease_package_builder.py:2282`: identical shape —
  `output_path = merge_pdf_files(pdf_paths_to_merge, regen_name, root)`, then the same
  `os.path.isfile`/`os.path.getsize`/`page_count` block (2284–2288), then `filename =
  os.path.basename(output_path)` (2290), then INSERT (2296–2308). `source_lease_id` is in scope here,
  same as `self.selected_lease_id` is at the first site.

Both sites' post-write validation calls real filesystem functions (`os.path.isfile`, `os.path.getsize`,
`PdfReader(path)` inside `page_count`) directly on whatever `merge_pdf_files()` returns. Under the
Blob backend that return value is a blob key string, not a real path — every one of those calls would
fail or behave wrong. **Both sites' validation blocks must be deleted, not made storage-aware** — see
Step 2, which moves equivalent (better) validation inside `merge_pdf_files()` itself, using the
in-memory `PdfWriter`, before either backend ever gets involved.

Both sites also do `filename = os.path.basename(output_path)` for `GeneratedFileName` — under the new
key shape (see Step 2) that would extract the collision-proofing stamp, not the friendly name. Fixed
by returning the friendly filename separately, computed once, rather than derived from the identifier.

**The read side** — `LucidPM/LucidPM.py:787-822`, the `/api/lease-generated-pdf` endpoint:
```python
row = rows[0]
file_path = str(row.get("StoredFilePath") or "").strip()
...
if not file_path or not os.path.isfile(file_path):
    msg = f"Generated PDF file not found on disk: {file_path}"
    return Response(content=msg.encode("utf-8"), status_code=404)
with open(file_path, "rb") as f:
    pdf_bytes = f.read()
return Response(content=pdf_bytes, media_type="application/pdf", ...)
```

Both sides do raw `os.path`/`open()` calls directly against `StoredFilePath` — there's no
intermediate layer to swap today.

**Adjacent, unrelated system:** `pdf_paths_to_merge.append(p.file_path)`
(`lease_package_builder.py:1573`) reads *source* section PDFs — sections whose own
`StoredFilePath` still points at the stale `C:\Dell Inspirion\...` root (standing TOP-PRIORITY item)
will make package generation fail **before** this cycle's code is ever reached, for a reason that has
nothing to do with this change. **Use a template with text-only sections to validate this cycle** —
same workaround already used in the Cycle 2.2 and 3.2 validation docs.

**No existing storage abstraction, no `azure-storage-blob` dependency** — confirmed, nothing in
`requirements.txt`/`pyproject.toml` today handles Blob Storage.

---

## The Fix

### Step 1 — new module `LucidPM/document_storage.py`

```python
"""Storage backend for generated lease package PDFs (Cycle 4.1 — narrow scope,
see Handoff 66). Selected by LUCIDPM_STORAGE_BACKEND: "local" (default, today's
behavior, unchanged) | "azure_blob". Only wired into the generated-package
write/read pair — source PDFs, uploads, and splits are untouched this cycle.
"""
from __future__ import annotations

import os
from typing import Protocol


class DocumentStorage(Protocol):
    def save(self, relative_key: str, data: bytes) -> str:
        """Persist data under relative_key. Returns the identifier to store as StoredFilePath."""

    def read(self, identifier: str) -> bytes:
        """Return the raw bytes for a previously-saved identifier."""

    def exists(self, identifier: str) -> bool:
        """Whether identifier currently resolves to stored content."""


class LocalFilesystemStorage:
    """Today's behavior, unchanged. identifier == an absolute local path, exactly
    like the current StoredFilePath values."""

    def __init__(self, root: str):
        self._root = root

    def save(self, relative_key: str, data: bytes) -> str:
        target = os.path.join(self._root, relative_key)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target):
            # Same fail-loud posture as the Blob backend below: with a full
            # uuid4 in the key (Step 2), a real collision should be
            # cryptographically implausible — so treat one as an error, not
            # something to silently overwrite.
            raise RuntimeError(f"Storage key already exists, refusing to overwrite: {target}")
        with open(target, "wb") as f:
            f.write(data)
        return target

    def read(self, identifier: str) -> bytes:
        with open(identifier, "rb") as f:
            return f.read()

    def exists(self, identifier: str) -> bool:
        return bool(identifier) and os.path.isfile(identifier)


class AzureBlobStorage:
    """identifier == the blob name within the fixed container (not a URL, not a
    local path) — e.g. "Generated/2026-lease-package.pdf"."""

    def __init__(self, connection_string: str, container: str):
        from azure.storage.blob import BlobServiceClient  # deferred: only needed for this backend

        self._container = BlobServiceClient.from_connection_string(
            connection_string
        ).get_container_client(container)

    def save(self, relative_key: str, data: bytes) -> str:
        # overwrite=False is the SDK's own default, kept explicit here: with a
        # full uuid4 in the key (Step 2), a real collision should be
        # cryptographically implausible — so a collision raises
        # azure.core.exceptions.ResourceExistsError rather than silently
        # replacing an existing package's actual content.
        self._container.upload_blob(name=relative_key, data=data, overwrite=False)
        return relative_key

    def read(self, identifier: str) -> bytes:
        return self._container.download_blob(identifier).readall()

    def exists(self, identifier: str) -> bool:
        if not identifier:
            return False
        return self._container.get_blob_client(identifier).exists()


_BLOB_STORAGE: DocumentStorage | None = None


def get_document_storage(storage_root: str | None = None) -> DocumentStorage:
    """local backend: a fresh LocalFilesystemStorage per call, rooted at the
    caller's storage_root (falls back to DEFAULT_DOCUMENT_ROOT) — this must
    NOT be cached across calls, since storage_root reflects the admin-
    configurable LeaseDocumentStorageRoot setting and can differ by caller.
    Constructing it is cheap (no I/O), so no caching is needed or wanted.

    azure_blob backend: a cached singleton instead — storage_root is
    irrelevant to it (the blob container is fixed by LUCIDPM_BLOB_CONTAINER,
    not by the local-disk setting), and constructing a BlobServiceClient has
    real per-call overhead worth avoiding.
    """
    backend = os.getenv("LUCIDPM_STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        from LucidPM.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT, normalize_storage_root

        # normalize_storage_root(), NOT generated_folder() — save_generated_package()'s
        # key already starts with "Generated/"; generated_folder() also appends
        # "Generated", and stacking both would double it
        # (...\Generated\Generated\<lease-id>\... instead of ...\Generated\<lease-id>\...).
        return LocalFilesystemStorage(normalize_storage_root(storage_root or DEFAULT_DOCUMENT_ROOT))
    if backend == "azure_blob":
        global _BLOB_STORAGE
        if _BLOB_STORAGE is None:
            conn_str = os.getenv("LUCIDPM_BLOB_CONNECTION_STRING", "")
            container = os.getenv("LUCIDPM_BLOB_CONTAINER", "lucidpm-documents")
            if not conn_str:
                raise RuntimeError(
                    "LUCIDPM_STORAGE_BACKEND=azure_blob requires LUCIDPM_BLOB_CONNECTION_STRING."
                )
            _BLOB_STORAGE = AzureBlobStorage(conn_str, container)
        return _BLOB_STORAGE
    raise RuntimeError(f"LUCIDPM_STORAGE_BACKEND={backend!r} is not valid — use 'local' or 'azure_blob'.")
```

Follow the `state.py` fail-fast convention (H58/H60/H63 precedent): an invalid/incomplete config
raises immediately with a named error, never silently degrades. This one raises `RuntimeError` at
first use rather than `ConfigError` at import time — it's genuinely lazy (matches `get_fernet()`'s
laziness, H63) since most of the app never touches document storage at all.

### Step 2 — split `merge_pdf_files()`, add `save_generated_package()`, fix both call sites

Current `merge_pdf_files()` (lines 1173–1199, see Current State above) does three things in one
function: merge pages, write to a real local path, return that path. Split it: merging+validating
(pure, storage-agnostic) separate from persisting (needs a `lease_id` for the collision-proof key,
which only the callers have in scope).

**Replace `merge_pdf_files()` entirely with:**
```python
def merge_pdf_files(section_paths: Iterable[str]) -> bytes:
    """Merge the given PDF files in page order. Returns the merged PDF's bytes.
    Validates internally (non-empty input, non-zero resulting page count) so
    callers no longer need their own post-merge disk-based checks — those
    broke under a non-filesystem storage backend anyway."""
    paths = list(section_paths or [])
    missing = [p for p in paths if not p or not os.path.isfile(p)]
    if missing:
        raise ValueError(f"Missing section file(s): {missing}")
    if not paths:
        raise ValueError("Select at least one PDF section.")

    writer = PdfWriter()
    for path in paths:
        reader = PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)
    if len(writer.pages) <= 0:
        raise RuntimeError("Merged PDF has no pages.")

    buffer = io.BytesIO()
    writer.write(buffer)
    data = buffer.getvalue()
    if not data:
        raise RuntimeError("Merged PDF produced no bytes.")
    return data


def save_generated_package(
    data: bytes, lease_id: int, output_name: str, storage_root: str | None = None
) -> tuple[str, str]:
    """Persist merged package bytes. Returns (identifier_for_StoredFilePath,
    friendly_filename_for_GeneratedFileName) — kept separate because the
    identifier is now collision-proof (not human-friendly) under either
    backend, so it can no longer double as the display filename the way
    os.path.basename(output_path) used to."""
    from LucidPM.document_storage import get_document_storage

    filename = safe_pdf_filename(output_name)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex  # full 128-bit UUID — not truncated. A collision
    # needs to be cryptographically implausible, not just "unlikely enough to
    # overwrite" — that's what justifies both save() implementations failing
    # loudly on a collision (above) instead of needing a retry loop.
    key = f"Generated/{lease_id}/{stamp}_{unique}_{filename}"
    identifier = get_document_storage(storage_root).save(key, data)
    return identifier, filename
```

**Call site 1 — first generation, `lease_package_builder.py:1577–1600`.** Current:
```python
            if not pdf_paths_to_merge:
                self.form_error = "No valid sections to merge."
                return

            output_path = merge_pdf_files(pdf_paths_to_merge, self.package_name.strip(), root)
            if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError(f"Merged PDF was not created or is empty: {output_path}")
            try:
                merged_page_count = page_count(output_path)
            except Exception as page_ex:
                raise RuntimeError(f"Merged PDF could not be opened for validation: {page_ex}")
            if merged_page_count <= 0:
                raise RuntimeError(f"Merged PDF has no pages: {output_path}")

            filename = os.path.basename(output_path)
            now = datetime.datetime.now()
            notes = self.package_notes.strip()

            run_exec(
                "INSERT INTO LeaseGeneratedDocuments (LeaseID, TenantID, GeneratedFileName, StoredFilePath, GeneratedOn, PackageNotes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.selected_lease_id, tenant_id if tenant_id > 0 else None, filename, output_path, now, notes),
                db=self.db,
            )
```
Replace with:
```python
            if not pdf_paths_to_merge:
                self.form_error = "No valid sections to merge."
                return

            merged_bytes = merge_pdf_files(pdf_paths_to_merge)
            output_path, filename = save_generated_package(
                merged_bytes, self.selected_lease_id, self.package_name.strip(), root
            )
            now = datetime.datetime.now()
            notes = self.package_notes.strip()

            run_exec(
                "INSERT INTO LeaseGeneratedDocuments (LeaseID, TenantID, GeneratedFileName, StoredFilePath, GeneratedOn, PackageNotes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self.selected_lease_id, tenant_id if tenant_id > 0 else None, filename, output_path, now, notes),
                db=self.db,
            )
```
(the `os.path.isfile`/`os.path.getsize`/`page_count` block and the `filename = os.path.basename(...)`
line are both deleted — `merge_pdf_files()` now validates internally, and `save_generated_package()`
returns the friendly filename directly.)

**Call site 2 — regeneration, `lease_package_builder.py:2279–2308`.** Current:
```python
            root = normalize_storage_root(self.output_storage_root)
            next_version_number = self._next_generated_version_number(source_lease_id)
            regen_name = self._build_versioned_package_filename(next_version_number)
            output_path = merge_pdf_files(pdf_paths_to_merge, regen_name, root)

            if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError(f"Regenerated PDF was not created or is empty: {output_path}")
            merged_page_count = page_count(output_path)
            if merged_page_count <= 0:
                raise RuntimeError(f"Regenerated PDF has no pages: {output_path}")

            filename = os.path.basename(output_path)
            now = datetime.datetime.now()
```
Replace with:
```python
            root = normalize_storage_root(self.output_storage_root)
            next_version_number = self._next_generated_version_number(source_lease_id)
            regen_name = self._build_versioned_package_filename(next_version_number)
            merged_bytes = merge_pdf_files(pdf_paths_to_merge)
            output_path, filename = save_generated_package(merged_bytes, source_lease_id, regen_name, root)
            now = datetime.datetime.now()
```
This was the call site the original draft missed entirely — it has the identical
disk-based-validation-then-basename pattern as call site 1, and would have broken under the Blob
backend in exactly the same way, undetected until someone tried to regenerate a package.

Add `import io` and `import uuid` near the top of `lease_documents_pdf.py`.

### Step 3 — wire the read side: `LucidPM.py`, `/api/lease-generated-pdf`

Current (lines 809–817):
```python
    file_path = str(row.get("StoredFilePath") or "").strip()
    filename = str(row.get("GeneratedFileName") or os.path.basename(file_path) or "lease_package.pdf").strip()

    if not file_path or not os.path.isfile(file_path):
        msg = f"Generated PDF file not found on disk: {file_path}"
        return Response(content=msg.encode("utf-8"), status_code=404)

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()
```
Replace with:
```python
    from LucidPM.document_storage import get_document_storage
    # No storage_root here: reads don't know or care which LeaseDocumentStorageRoot
    # a generation call used — under "local", get_document_storage() falls back to
    # DEFAULT_DOCUMENT_ROOT when storage_root is None, same as the write side did
    # before any custom root was configured. If a deployment has ever changed
    # LeaseDocumentStorageRoot, existing local-path StoredFilePath values already
    # encode the absolute path they were written under, so this read doesn't need
    # to reconstruct the root at all — only the write side does.
    storage = get_document_storage()

    file_path = str(row.get("StoredFilePath") or "").strip()
    filename = str(row.get("GeneratedFileName") or os.path.basename(file_path) or "lease_package.pdf").strip()

    if not file_path or not storage.exists(file_path):
        msg = f"Generated PDF not found in storage: {file_path}"
        return Response(content=msg.encode("utf-8"), status_code=404)

    pdf_bytes = storage.read(file_path)
```
The `os.path.basename(file_path)` filename fallback only fires when `GeneratedFileName` is somehow
empty — with `save_generated_package()` always populating it now, this is dead-but-harmless defensive
code either way; leave it as-is.

### Step 4 — dependency

Add `azure-storage-blob` to `requirements.txt` and `pyproject.toml`'s `[project.dependencies]`
(mirrors the H61 pattern — pin the exact version in both, keep them in sync). **Verify the current
stable release at implementation time** rather than trusting a version number drafted here — same
hedge as Caddy's version in Handoff 64.

### Step 5 — `.env.example`

Document the two new vars, inert by default:
```
# --- Generated lease package storage (Handoff 66, Cycle 4.1) ------------------
# "local" (default) = unchanged behavior, writes under the existing
# LeaseDocumentStorageRoot\Generated folder. "azure_blob" = Azure Blob Storage.
#LUCIDPM_STORAGE_BACKEND=local
#LUCIDPM_BLOB_CONNECTION_STRING=<storage account connection string — azure_blob only>
#LUCIDPM_BLOB_CONTAINER=lucidpm-documents
```

### Step 6 — `docs/Deployment.md` reconcile (small, unrelated to the code above — do anyway while touching this doc)

Current (`docs/Deployment.md:5`):
```
LucidPM has a Docker image definition for local container validation. ... The image has not been pushed to a registry and no Azure Container App exists yet.
```
Stale since Gate 3 passed (2026-09-11, commit `9a9fb79`). Replace with something like:
```
LucidPM runs as the `lucidpm` Azure Container App (`lucido-apps-env`, westus3), image
`ghcr.io/mslucido-lab/lucidpm:0.1.0` on private GHCR. Ingress is restricted to Mark's Office/Home IPs
(no Microsoft Entra yet — Stage 5.3) and the app is locked to `TenantCRM_Test` only
(`LUCIDPM_SINGLE_DB`). `minReplicas: 0` — the app scales to zero on idle; a cold request takes
roughly one minute (container scale-up plus any Azure SQL serverless resume). See
`docs/cycle-3.2-validation.md` for the full Gate 3 record.
```
Also fix line 21, which describes the absolute-URL question as still-open for "Cycle 3.2" — Cycle 3.2
resolved it (rebuilt with the real FQDN baked in via `--build-arg`, since the environment's domain
suffix is fixed and was already known before the app was created) — reword to say so, and note the
same question returns for Stage 5.4's custom domain.

---

## Do Not Touch

- **Source-PDF upload/copy/split** (`save_uploaded_pdf`, `copy_existing_pdf`, `split_pdf_pages`,
  `lease_documents_pdf.py`) — untouched. Stays on local disk. Cycle 5.1's job, not this one's.
- **The `storage_root` / `LeaseDocumentStorageRoot` admin-settings screen**
  (`pages/lease_documents.py` ~883–886, ~3470) — untouched. It still governs source-PDF storage,
  which this cycle doesn't move.
- **The stale-`StoredFilePath` data issue** — unrelated; test with text-only-section templates so it
  doesn't get conflated with this cycle's actual change (see Current State).
- **Schema** — no migration, no new columns. `StoredFilePath` keeps its name; only its *meaning*
  becomes backend-dependent, exactly like `LUCIDPM_SQL_*`/`LUCIDPM_FERNET_KEY` already work.
- **Cycle 4.2** — no container image rebuild, no deployment, no actual restart-survival test against
  the live `lucidpm` Container App. This handoff is local-only.
- **The Azure Blob account key beyond this cycle.** The connection string (full account-key access)
  is for **local Cycle 4.1 validation only**, in a gitignored `.env` — never committed, never baked
  into the image. **Cycle 4.2 must not deploy the account-key connection string into the Container
  App.** Before that cycle runs, switch to a container-scoped SAS token (read+write+list on
  `lucidpm-documents` only) or a user-assigned managed identity with `Storage Blob Data Contributor`
  scoped to just that container — the same least-privilege progression the SQL user
  (`lucidadmin` → `lucidpm_app`) and GHCR tokens (write → read-only) already went through. This is
  Cycle 4.2's problem to solve, not this one's, but it's a firm requirement, not a soft suggestion.

---

## Validation Checklist

- [ ] `LUCIDPM_STORAGE_BACKEND` unset (or `local`) — generate a lease package from a **text-only**
      template (avoids the unrelated stale-path issue), confirm it downloads correctly via
      `/api/lease-generated-pdf`. **Check the file actually landed at
      `<root>\Generated\<lease-id>\<timestamp>_<uuid>_<filename>.pdf`** — a single `Generated`
      segment, not `Generated\Generated\...` (the exact bug this revision fixed).
- [ ] **Regeneration, local backend** — regenerate that same package (the second call site,
      `lease_package_builder.py` ~2279). This is the path the original draft missed; confirm it still
      works and produces a new `LeaseGeneratedDocuments` row with its own correct file.
- [ ] **Custom `LeaseDocumentStorageRoot`, local backend** — set a non-default storage root in Admin
      Settings, generate a package, confirm it's written under *that* root, not
      `DEFAULT_DOCUMENT_ROOT` — this is the byte-identical-behavior regression the original draft
      would have broken.
- [ ] `LUCIDPM_STORAGE_BACKEND=azure_blob` + `LUCIDPM_BLOB_CONNECTION_STRING` pointed at the real
      `lucidpmdocs24899` account — generate a package.
      - [ ] Confirm the blob landed at the expected collision-proof key shape:
            `az storage blob list --account-name lucidpmdocs24899 --container-name lucidpm-documents --auth-mode login -o table`
            (expect `Generated/<lease-id>/<timestamp>_<uuid>_<filename>.pdf`, not a bare
            `Generated/<filename>.pdf`)
      - [ ] Confirm `/api/lease-generated-pdf` retrieves and serves it correctly — byte-identical PDF
            to the local-backend run.
      - [ ] Confirm `GeneratedFileName` in the DB is the friendly name (e.g. `MyPackage.pdf`), not the
            collision-proofed key or its basename.
      - [ ] **Regenerate under the blob backend too** — confirm the second call site works here as
            well, and that the original package's blob is untouched (two distinct blobs, two distinct
            `LeaseGeneratedDocuments` rows).
- [ ] Switching back to `local` afterward still works (no state leaked between backends via the
      lazy-singleton pattern — restart the process between backend switches, don't expect a live
      env-var change mid-run to take effect, same as every other env-driven config in this app).
- [ ] `get_document_storage()` fails fast with a clear error when `LUCIDPM_STORAGE_BACKEND=azure_blob`
      and `LUCIDPM_BLOB_CONNECTION_STRING` is missing — don't let it silently fall back to local.
- [ ] `import LucidPM.LucidPM` still exits 0 (the standard post-change import check this repo uses).
- [ ] `docs/Deployment.md` reconciled (Step 6).
- [ ] **Fail-loud collision check (either backend)** — manually call `save()` twice with the *same*
      key (e.g. in a scratch script) and confirm the second call raises (`RuntimeError` for local,
      `azure.core.exceptions.ResourceExistsError` for blob) rather than silently replacing the first
      write. Doesn't need to happen through the real UI — this is checking the interface contract, not
      a real generation flow (a genuine key collision shouldn't occur in normal use with a full uuid4).

**Done when:** both backends work locally, proven with a real write + read against the actual Azure
Blob container. Cycle 4.2 (deploy the updated image, generate a PDF in the live Container App, scale
to zero and back, confirm it survived) is next — and is **Gate 4**, the actual POC-complete decision
point.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\document_storage.py            ← new, Step 1
  LucidPM\pages\lease_documents_pdf.py    ← Step 2 (merge_pdf_files split + save_generated_package,
                                              + `import io` + `import uuid`)
  LucidPM\pages\lease_package_builder.py  ← Step 2 (both call sites: ~1577-1600 and ~2279-2308)
  LucidPM\LucidPM.py                      ← Step 3 (/api/lease-generated-pdf, lines 809-817)
  requirements.txt + pyproject.toml       ← Step 4 (azure-storage-blob)
  .env.example                            ← Step 5
  docs\Deployment.md                      ← Step 6
```

Azure resources this cycle uses (already created, no action needed to provision them):
```
Storage account:  lucidpmdocs24899        (Lucido-Apps-RG, westus3, Standard_LRS, StorageV2)
Blob container:    lucidpm-documents       (private, no public access)
```
