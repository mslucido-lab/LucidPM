"""Storage backends for generated packages and source lease PDFs."""

from __future__ import annotations

import datetime
import os
import uuid
from typing import Literal, Protocol


SOURCE_BLOB_PREFIX = "azblob:"
SourceKind = Literal["template", "section"]
SourceCollision = Literal["unique_name", "retry_suffix"]


class DocumentStorage(Protocol):
    """Persistence for generated packages and source/section PDFs."""

    def save(self, lease_id: int, filename: str, data: bytes) -> str:
        """Save a generated package and return its stored identifier."""

    def save_source(
        self,
        property_name: str,
        document_category: str,
        filename: str,
        data: bytes,
        *,
        kind: SourceKind = "template",
        collision: SourceCollision = "unique_name",
    ) -> str:
        """Save a source/section PDF and return its stored identifier."""

    def read(self, identifier: str) -> bytes:
        """Read a generated package."""

    def exists(self, identifier: str) -> bool:
        """Return whether a generated-package identifier resolves."""


class LocalFilesystemStorage:
    """Filesystem storage rooted at either Generated or the document root."""

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

    def save_source(
        self,
        property_name: str,
        document_category: str,
        filename: str,
        data: bytes,
        *,
        kind: SourceKind = "template",
        collision: SourceCollision = "unique_name",
    ) -> str:
        from LucidPM.pages.lease_documents_pdf import sections_folder, template_folder

        folder = (
            template_folder(self._root, property_name, document_category)
            if kind == "template"
            else sections_folder(self._root, property_name, document_category)
        )
        target = os.path.join(folder, filename)
        if collision == "retry_suffix":
            stem, ext = os.path.splitext(target)
            counter = 2
            while os.path.exists(target):
                target = f"{stem}_{counter}{ext}"
                counter += 1
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as file:
            file.write(data)
        return target

    def read(self, identifier: str) -> bytes:
        with open(identifier, "rb") as file:
            return file.read()

    def exists(self, identifier: str) -> bool:
        return bool(identifier) and os.path.isfile(identifier)


class AzureBlobStorage:
    """Private Azure Blob storage for generated and source lease PDFs."""

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

    def source_identifier(
        self,
        property_name: str,
        document_category: str,
        filename: str,
        *,
        kind: SourceKind = "template",
    ) -> str:
        """Return a collision-safe, self-describing source-document identifier."""
        from LucidPM.pages.lease_documents_pdf import slugify

        property_key = slugify(property_name or "General")
        category_key = slugify(document_category or "Other")
        section_segment = "/Sections" if kind == "section" else ""
        key = (
            f"Sources/{property_key}/{category_key}{section_segment}/"
            f"{uuid.uuid4().hex}_{filename}"
        )
        return SOURCE_BLOB_PREFIX + key

    def save_source(
        self,
        property_name: str,
        document_category: str,
        filename: str,
        data: bytes,
        *,
        kind: SourceKind = "template",
        collision: SourceCollision = "unique_name",
        identifier: str | None = None,
    ) -> str:
        del collision
        identifier = identifier or self.source_identifier(
            property_name, document_category, filename, kind=kind
        )
        if not identifier.startswith(SOURCE_BLOB_PREFIX):
            raise ValueError("Azure source-document identifiers must start with 'azblob:'.")
        key = identifier.removeprefix(SOURCE_BLOB_PREFIX)
        if not key:
            raise ValueError("Azure source-document identifier is missing its Blob key.")
        self._container.upload_blob(name=key, data=data, overwrite=False)
        return identifier

    def read(self, identifier: str) -> bytes:
        return self._container.download_blob(identifier).readall()

    def exists(self, identifier: str) -> bool:
        return bool(identifier) and self._container.get_blob_client(identifier).exists()


_BLOB_STORAGE: AzureBlobStorage | None = None


def _blob_storage(
    missing_message: str = "LUCIDPM_STORAGE_BACKEND=azure_blob requires "
    "LUCIDPM_BLOB_CONNECTION_STRING.",
) -> AzureBlobStorage:
    global _BLOB_STORAGE
    if _BLOB_STORAGE is None:
        connection_string = os.getenv("LUCIDPM_BLOB_CONNECTION_STRING", "")
        container = os.getenv("LUCIDPM_BLOB_CONTAINER", "lucidpm-documents")
        if not connection_string:
            raise RuntimeError(missing_message)
        _BLOB_STORAGE = AzureBlobStorage(connection_string, container)
    return _BLOB_STORAGE


def get_document_storage(storage_root: str | None = None) -> DocumentStorage:
    """Return the selected generated-package storage backend."""
    backend = os.getenv("LUCIDPM_STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        from LucidPM.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT, generated_folder

        return LocalFilesystemStorage(generated_folder(storage_root or DEFAULT_DOCUMENT_ROOT))
    if backend == "azure_blob":
        return _blob_storage()
    raise RuntimeError(
        f"LUCIDPM_STORAGE_BACKEND={backend!r} is not valid; use 'local' or 'azure_blob'."
    )


def get_source_document_storage(storage_root: str | None = None) -> DocumentStorage:
    """Return source/section storage, rooted above ``Generated`` locally."""
    backend = os.getenv("LUCIDPM_STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        from LucidPM.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT, normalize_storage_root

        return LocalFilesystemStorage(normalize_storage_root(storage_root or DEFAULT_DOCUMENT_ROOT))
    if backend == "azure_blob":
        return _blob_storage(
            "Blob-backed source documents require LUCIDPM_BLOB_CONNECTION_STRING."
        )
    raise RuntimeError(
        f"LUCIDPM_STORAGE_BACKEND={backend!r} is not valid; use 'local' or 'azure_blob'."
    )


def _blob_key(identifier: str) -> str | None:
    if not identifier.startswith(SOURCE_BLOB_PREFIX):
        return None
    key = identifier.removeprefix(SOURCE_BLOB_PREFIX)
    return key or None


def read_source_document(identifier: str) -> bytes:
    """Read a source/section identifier, dispatching by its own storage scheme."""
    key = _blob_key(identifier)
    if key is not None:
        return _blob_storage(
            "Blob-backed source documents require LUCIDPM_BLOB_CONNECTION_STRING."
        ).read(key)
    with open(identifier, "rb") as file:
        return file.read()


def source_document_exists(identifier: str) -> bool:
    """Return whether a source/section identifier resolves."""
    if not identifier:
        return False
    key = _blob_key(identifier)
    if key is not None:
        return _blob_storage(
            "Blob-backed source documents require LUCIDPM_BLOB_CONNECTION_STRING."
        ).exists(key)
    return os.path.isfile(identifier)


def source_document_location(identifier: str, storage_root: str | None = None) -> tuple[str, str]:
    """Return the DB StorageRoot/RelativePath pair for a source identifier."""
    key = _blob_key(identifier)
    if key is not None:
        return os.getenv("LUCIDPM_BLOB_CONTAINER", "lucidpm-documents"), key
    from LucidPM.pages.lease_documents_pdf import DEFAULT_DOCUMENT_ROOT, relative_to_root

    root = str(storage_root or "").strip() or DEFAULT_DOCUMENT_ROOT
    return root, relative_to_root(identifier, root)
