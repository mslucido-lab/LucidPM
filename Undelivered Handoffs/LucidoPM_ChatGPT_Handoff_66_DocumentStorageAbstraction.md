# LucidoPM — ChatGPT Handoff 66
*Storage abstraction for generated lease package PDFs: local filesystem today, Azure Blob as a second
implementation — proves the round-trip Cycle 4.2 needs*
*Prepared: 2026-09-11*
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
Called from `LucidPM/pages/lease_package_builder.py:1581` (`output_path = merge_pdf_files(...)`),
which then validates it (`os.path.isfile`, `page_count()` — the latter calls `PdfReader(path)`
again, `lease_documents_pdf.py:209-211`) and inserts `output_path` as `StoredFilePath` in
`LeaseGeneratedDocuments` (`lease_package_builder.py:1595-1600`).

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
        self._container.upload_blob(name=relative_key, data=data, overwrite=True)
        return relative_key

    def read(self, identifier: str) -> bytes:
        return self._container.download_blob(identifier).readall()

    def exists(self, identifier: str) -> bool:
        if not identifier:
            return False
        return self._container.get_blob_client(identifier).exists()


_STORAGE: DocumentStorage | None = None


def get_document_storage() -> DocumentStorage:
    """Lazy singleton, mirrors the module-level config pattern in state.py."""
    global _STORAGE
    if _STORAGE is not None:
        return _STORAGE

    backend = os.getenv("LUCIDPM_STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        from LucidPM.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT, generated_folder

        _STORAGE = LocalFilesystemStorage(generated_folder(DEFAULT_DOCUMENT_ROOT))
    elif backend == "azure_blob":
        conn_str = os.getenv("LUCIDPM_BLOB_CONNECTION_STRING", "")
        container = os.getenv("LUCIDPM_BLOB_CONTAINER", "lucidpm-documents")
        if not conn_str:
            raise RuntimeError(
                "LUCIDPM_STORAGE_BACKEND=azure_blob requires LUCIDPM_BLOB_CONNECTION_STRING."
            )
        _STORAGE = AzureBlobStorage(conn_str, container)
    else:
        raise RuntimeError(f"LUCIDPM_STORAGE_BACKEND={backend!r} is not valid — use 'local' or 'azure_blob'.")
    return _STORAGE
```

Follow the `state.py` fail-fast convention (H58/H60/H63 precedent): an invalid/incomplete config
raises immediately with a named error, never silently degrades. This one raises `RuntimeError` at
first use rather than `ConfigError` at import time — it's genuinely lazy (matches `get_fernet()`'s
laziness, H63) since most of the app never touches document storage at all.

### Step 2 — wire the write side: `lease_documents_pdf.py`, `merge_pdf_files()`

Current (lines 1173–1199, see Current State above) writes to a real local path and returns it.
Replace the body from the `writer = PdfWriter()` line down:

```python
def merge_pdf_files(section_paths: Iterable[str], output_name: str, storage_root: str | None = None) -> str:
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

    buffer = io.BytesIO()
    writer.write(buffer)
    data = buffer.getvalue()

    # Validate before persisting — matches the existing page_count() check the
    # caller used to do against the file on disk, just against the in-memory
    # bytes instead, so it works identically for either storage backend.
    if not data:
        raise RuntimeError("Merged PDF produced no bytes.")

    filename = safe_pdf_filename(output_name)
    from LucidPM.document_storage import get_document_storage
    storage = get_document_storage()
    # Uniqueness (the existing counter-suffix loop) still matters for local disk;
    # for blob it just becomes part of the key. Keep the same filename-collision
    # behavior either way by asking the backend, not by checking os.path here.
    target_key = f"Generated/{filename}"
    return storage.save(target_key, data)
```

Note: the local-disk collision-avoidance loop (`while os.path.exists(target): ...`) that used to live
here moves into `LocalFilesystemStorage.save()` **only if you want to preserve exact collision
behavior** — flag this as a decision point for whoever implements: either (a) port the counter loop
into `LocalFilesystemStorage.save()` so local-backend behavior is unchanged, or (b) accept that this
cycle changes local collision handling slightly (last-write-wins) since it's such an edge case. **(a)
is the byte-identical-default-path-safe choice — do that one.**

Add `import io` near the top of `lease_documents_pdf.py` if not already present.

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
    storage = get_document_storage()

    file_path = str(row.get("StoredFilePath") or "").strip()
    filename = str(row.get("GeneratedFileName") or os.path.basename(file_path) or "lease_package.pdf").strip()

    if not file_path or not storage.exists(file_path):
        msg = f"Generated PDF not found in storage: {file_path}"
        return Response(content=msg.encode("utf-8"), status_code=404)

    pdf_bytes = storage.read(file_path)
```
(`os.path.basename(file_path)` for the filename fallback still works fine on a blob key like
`"Generated/foo.pdf"` — no change needed there.)

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
- **The Azure Blob account key.** Use the connection string for this cycle's local testing only —
  flag in the handout below that Cycle 4.2 (once this runs inside the deployed container) should move
  to a scoped SAS token or managed identity rather than the full account key, same least-privilege
  progression the SQL user (`lucidadmin` → `lucidpm_app`) and GHCR tokens (write → read-only) already
  went through.

---

## Validation Checklist

- [ ] `LUCIDPM_STORAGE_BACKEND` unset (or `local`) — generate a lease package from a **text-only**
      template (avoids the unrelated stale-path issue), confirm it downloads correctly via
      `/api/lease-generated-pdf`, byte-identical to pre-change behavior. This is the regression check
      — the default path must not change.
- [ ] `LUCIDPM_STORAGE_BACKEND=azure_blob` + `LUCIDPM_BLOB_CONNECTION_STRING` pointed at the real
      `lucidpmdocs24899` account — generate the same package again.
      - [ ] Confirm the blob actually landed:
            `az storage blob list --account-name lucidpmdocs24899 --container-name lucidpm-documents --auth-mode login -o table`
      - [ ] Confirm `/api/lease-generated-pdf` retrieves and serves it correctly — byte-identical PDF
            to the local-backend run.
- [ ] Switching back to `local` afterward still works (no state leaked between backends via the
      lazy-singleton pattern — restart the process between backend switches, don't expect a live
      env-var change mid-run to take effect, same as every other env-driven config in this app).
- [ ] `get_document_storage()` fails fast with a clear error when `LUCIDPM_STORAGE_BACKEND=azure_blob`
      and `LUCIDPM_BLOB_CONNECTION_STRING` is missing — don't let it silently fall back to local.
- [ ] `import LucidPM.LucidPM` still exits 0 (the standard post-change import check this repo uses).

**Done when:** both backends work locally, proven with a real write + read against the actual Azure
Blob container. Cycle 4.2 (deploy the updated image, generate a PDF in the live Container App, scale
to zero and back, confirm it survived) is next — and is **Gate 4**, the actual POC-complete decision
point.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\document_storage.py          ← new, Step 1
  LucidPM\pages\lease_documents_pdf.py  ← Step 2 (merge_pdf_files, + `import io`)
  LucidPM\LucidPM.py                    ← Step 3 (/api/lease-generated-pdf, lines 809-817)
  requirements.txt + pyproject.toml     ← Step 4 (azure-storage-blob)
  .env.example                          ← Step 5
```

Azure resources this cycle uses (already created, no action needed to provision them):
```
Storage account:  lucidpmdocs24899        (Lucido-Apps-RG, westus3, Standard_LRS, StorageV2)
Blob container:    lucidpm-documents       (private, no public access)
```
