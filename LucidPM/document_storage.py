"""Storage for generated lease package PDFs.

Only generated packages use this abstraction. Source PDFs, uploads, and splits
remain on the local filesystem until the later full document migration.
"""

from __future__ import annotations

import datetime
import os
import uuid
from typing import Protocol


class DocumentStorage(Protocol):
    """Persistence for a generated lease package."""

    def save(self, lease_id: int, filename: str, data: bytes) -> str:
        """Save data and return the identifier stored in StoredFilePath."""

    def read(self, identifier: str) -> bytes:
        """Read a previously saved package."""

    def exists(self, identifier: str) -> bool:
        """Return whether identifier resolves to a package."""


class LocalFilesystemStorage:
    """The existing flat Generated-folder convention."""

    def __init__(self, root: str):
        self._root = root

    def save(self, lease_id: int, filename: str, data: bytes) -> str:
        del lease_id
        target = os.path.join(self._root, filename)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        stem, ext = os.path.splitext(target)
        counter = 2
        while os.path.exists(target):
            target = f"{stem}_{counter}{ext}"
            counter += 1
        with open(target, "wb") as file:
            file.write(data)
        return target

    def read(self, identifier: str) -> bytes:
        with open(identifier, "rb") as file:
            return file.read()

    def exists(self, identifier: str) -> bool:
        return bool(identifier) and os.path.isfile(identifier)


class AzureBlobStorage:
    """Private Azure Blob storage for generated lease packages."""

    def __init__(self, connection_string: str, container: str):
        from azure.storage.blob import BlobServiceClient

        self._container = BlobServiceClient.from_connection_string(
            connection_string
        ).get_container_client(container)

    def save(self, lease_id: int, filename: str, data: bytes) -> str:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        key = f"Generated/{lease_id}/{stamp}_{uuid.uuid4().hex}_{filename}"
        self._container.upload_blob(name=key, data=data, overwrite=False)
        return key

    def read(self, identifier: str) -> bytes:
        return self._container.download_blob(identifier).readall()

    def exists(self, identifier: str) -> bool:
        return bool(identifier) and self._container.get_blob_client(identifier).exists()


_BLOB_STORAGE: DocumentStorage | None = None


def get_document_storage(storage_root: str | None = None) -> DocumentStorage:
    """Return the selected generated-package storage backend.

    Local storage is built per call because its root is admin-configurable.
    The Blob client is safe to reuse and is created lazily only when selected.
    """
    backend = os.getenv("LUCIDPM_STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        from LucidPM.pages.lease_documents_pdf import (
            DEFAULT_DOCUMENT_ROOT,
            generated_folder,
        )

        return LocalFilesystemStorage(
            generated_folder(storage_root or DEFAULT_DOCUMENT_ROOT)
        )

    if backend == "azure_blob":
        global _BLOB_STORAGE
        if _BLOB_STORAGE is None:
            connection_string = os.getenv("LUCIDPM_BLOB_CONNECTION_STRING", "")
            container = os.getenv("LUCIDPM_BLOB_CONTAINER", "lucidpm-documents")
            if not connection_string:
                raise RuntimeError(
                    "LUCIDPM_STORAGE_BACKEND=azure_blob requires "
                    "LUCIDPM_BLOB_CONNECTION_STRING."
                )
            _BLOB_STORAGE = AzureBlobStorage(connection_string, container)
        return _BLOB_STORAGE

    raise RuntimeError(
        f"LUCIDPM_STORAGE_BACKEND={backend!r} is not valid; "
        "use 'local' or 'azure_blob'."
    )
