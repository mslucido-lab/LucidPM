"""
Lease document PDF utility functions.
MVP scope:
  - store PDFs on disk
  - count pages
  - split one source PDF into page-range pieces
  - merge selected pieces into one final lease PDF
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
from typing import Iterable

try:
    from pypdf import PdfReader, PdfWriter
except Exception:  # pragma: no cover - local fallback
    from PyPDF2 import PdfReader, PdfWriter

BASE_DOCUMENT_DIR = r"C:\Dell Inspirion\TenantCRM\LeaseDocuments"
SOURCE_DIR = os.path.join(BASE_DOCUMENT_DIR, "Uploaded")
PIECE_DIR = os.path.join(BASE_DOCUMENT_DIR, "ParsedPieces")
GENERATED_DIR = os.path.join(BASE_DOCUMENT_DIR, "Generated")

ALLOWED_ROOTS = [
    os.path.abspath(SOURCE_DIR),
    os.path.abspath(PIECE_DIR),
    os.path.abspath(GENERATED_DIR),
]


def ensure_document_dirs() -> None:
    for folder in [SOURCE_DIR, PIECE_DIR, GENERATED_DIR]:
        os.makedirs(folder, exist_ok=True)


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


def save_uploaded_pdf(file_bytes: bytes, original_filename: str, lease_id: int) -> str:
    ensure_document_dirs()
    filename = safe_pdf_filename(original_filename)
    stem, ext = os.path.splitext(filename)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(SOURCE_DIR, f"lease_{int(lease_id)}_{slugify(stem)}_{stamp}{ext}")
    with open(target, "wb") as f:
        f.write(file_bytes)
    return target


def copy_existing_pdf(source_path: str, original_filename: str, lease_id: int) -> str:
    ensure_document_dirs()
    filename = safe_pdf_filename(original_filename or os.path.basename(source_path))
    stem, ext = os.path.splitext(filename)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(SOURCE_DIR, f"lease_{int(lease_id)}_{slugify(stem)}_{stamp}{ext}")
    shutil.copyfile(source_path, target)
    return target


def page_count(path: str) -> int:
    reader = PdfReader(path)
    return len(reader.pages)


def split_pdf_pages(source_path: str, start_page: int, end_page: int, output_name: str) -> str:
    ensure_document_dirs()
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
    target = os.path.join(PIECE_DIR, filename)
    counter = 2
    stem, ext = os.path.splitext(target)
    while os.path.exists(target):
        target = f"{stem}_{counter}{ext}"
        counter += 1

    with open(target, "wb") as f:
        writer.write(f)
    return target


def merge_pdf_files(piece_paths: Iterable[str], output_name: str) -> str:
    ensure_document_dirs()
    paths = [p for p in piece_paths if p and os.path.isfile(p)]
    if not paths:
        raise ValueError("Select at least one PDF piece.")

    writer = PdfWriter()
    for path in paths:
        reader = PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)

    filename = safe_pdf_filename(output_name)
    target = os.path.join(GENERATED_DIR, filename)
    counter = 2
    stem, ext = os.path.splitext(target)
    while os.path.exists(target):
        target = f"{stem}_{counter}{ext}"
        counter += 1

    with open(target, "wb") as f:
        writer.write(f)
    return target


def is_safe_document_path(path: str) -> bool:
    if not path:
        return False
    abs_path = os.path.abspath(path)
    return any(abs_path.startswith(root + os.sep) or abs_path == root for root in ALLOWED_ROOTS)
