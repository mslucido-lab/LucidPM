"""
Lease template PDF utility functions.

Stores source PDFs and split pieces on disk. SQL Server stores metadata only.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
from typing import Iterable

try:
    from pypdf import PdfReader, PdfWriter
except Exception:  # pragma: no cover
    from PyPDF2 import PdfReader, PdfWriter

DEFAULT_DOCUMENT_ROOT = r"C:\Dell Inspirion\TenantCRM\LeaseDocuments"


def slugify(value: str, fallback: str = "document") -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value or fallback


def safe_pdf_filename(name: str, fallback: str = "lease.pdf") -> str:
    base = os.path.basename(str(name or fallback))
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    base = re.sub(r"[^A-Za-z0-9_. -]+", "_", base).strip()
    return base or fallback


def normalize_storage_root(root_path: str | None = None) -> str:
    root = str(root_path or "").strip() or DEFAULT_DOCUMENT_ROOT
    return os.path.abspath(root)


def template_folder(root_path: str, property_name: str, document_category: str) -> str:
    root = normalize_storage_root(root_path)
    prop = slugify(property_name or "General")
    category = slugify(document_category or "Other")
    return os.path.join(root, "Admin", prop, category)


def pieces_folder(root_path: str, property_name: str, document_category: str) -> str:
    return os.path.join(template_folder(root_path, property_name, document_category), "Pieces")


def generated_folder(root_path: str) -> str:
    return os.path.join(normalize_storage_root(root_path), "Generated")


def ensure_folder(folder: str) -> None:
    os.makedirs(folder, exist_ok=True)


def relative_to_root(path: str, root_path: str) -> str:
    try:
        return os.path.relpath(os.path.abspath(path), normalize_storage_root(root_path))
    except Exception:
        return os.path.basename(path)


def save_uploaded_pdf(
    file_bytes: bytes,
    original_filename: str,
    storage_root: str,
    property_name: str,
    document_category: str,
    template_name: str = "",
) -> str:
    folder = template_folder(storage_root, property_name, document_category)
    ensure_folder(folder)
    filename = safe_pdf_filename(original_filename)
    stem, ext = os.path.splitext(filename)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = slugify(template_name, "template")
    target = os.path.join(folder, f"{prefix}_{slugify(stem)}_{stamp}{ext}")
    with open(target, "wb") as f:
        f.write(file_bytes)
    return target


def copy_existing_pdf(
    source_path: str,
    original_filename: str,
    storage_root: str,
    property_name: str,
    document_category: str,
    template_name: str = "",
) -> str:
    folder = template_folder(storage_root, property_name, document_category)
    ensure_folder(folder)
    filename = safe_pdf_filename(original_filename or os.path.basename(source_path))
    stem, ext = os.path.splitext(filename)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = slugify(template_name, "template")
    target = os.path.join(folder, f"{prefix}_{slugify(stem)}_{stamp}{ext}")
    shutil.copyfile(source_path, target)
    return target


def page_count(path: str) -> int:
    reader = PdfReader(path)
    return len(reader.pages)


def split_pdf_pages(
    source_path: str,
    start_page: int,
    end_page: int,
    output_name: str,
    storage_root: str,
    property_name: str,
    document_category: str,
) -> str:
    folder = pieces_folder(storage_root, property_name, document_category)
    ensure_folder(folder)
    start = int(start_page)
    end = int(end_page)
    if start < 1 or end < 1 or end < start:
        raise ValueError("Invalid page range.")

    reader = PdfReader(source_path)
    total = len(reader.pages)
    if start > total or end > total:
        raise ValueError(f"Page range must be between 1 and {total}.")

    writer = PdfWriter()
    for page_index in range(start - 1, end):
        writer.add_page(reader.pages[page_index])

    filename = safe_pdf_filename(output_name)
    target = os.path.join(folder, filename)
    counter = 2
    stem, ext = os.path.splitext(target)
    while os.path.exists(target):
        target = f"{stem}_{counter}{ext}"
        counter += 1

    with open(target, "wb") as f:
        writer.write(f)
    return target


def merge_pdf_files(piece_paths: Iterable[str], output_name: str, storage_root: str | None = None) -> str:
    folder = generated_folder(storage_root or DEFAULT_DOCUMENT_ROOT)
    ensure_folder(folder)
    paths = [p for p in piece_paths if p and os.path.isfile(p)]
    if not paths:
        raise ValueError("Select at least one PDF piece.")

    writer = PdfWriter()
    for path in paths:
        reader = PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)

    filename = safe_pdf_filename(output_name)
    target = os.path.join(folder, filename)
    counter = 2
    stem, ext = os.path.splitext(target)
    while os.path.exists(target):
        target = f"{stem}_{counter}{ext}"
        counter += 1

    with open(target, "wb") as f:
        writer.write(f)
    return target


def is_safe_document_path(path: str, storage_root: str | None = None) -> bool:
    if not path:
        return False
    root = normalize_storage_root(storage_root)
    abs_path = os.path.abspath(path)
    return abs_path.startswith(root + os.sep) or abs_path == root
