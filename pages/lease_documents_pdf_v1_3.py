"""
Lease template PDF utility functions.

Stores source PDFs and split sections on disk. SQL Server stores metadata only.

Patched 5/1/2026:
- v1.3: added render_text_sections_to_pdf() pagination engine for consecutive text-backed clauses.
- Keeps render_text_to_pdf() as a backward-compatible wrapper.

Patched 4/29/2026:
- PDF-1: merge_pdf_files() now fails on missing section files instead of silently dropping them.
- PDF-2: requires pypdf only. Removed PyPDF2 fallback.
- PDF-3: render_text_to_pdf() validates that ReportLab produced a non-empty PDF.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
from typing import Iterable, Sequence

from pypdf import PdfReader, PdfWriter

from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Spacer, Preformatted, KeepTogether

DEFAULT_DOCUMENT_ROOT = r"C:\Dell Inspirion\TenantCRM\LeaseDocuments"

try:
    from LucidPM_Reflex.pages.lease_render_styles import PAGE_SETUP, LEASE_MONOSPACE
except Exception:
    PAGE_SETUP = {
        "pagesize": letter,
        "leftMargin": 54,
        "rightMargin": 54,
        "topMargin": 54,
        "bottomMargin": 54,
    }
    LEASE_MONOSPACE = ParagraphStyle(
        name="LeaseMonospace",
        fontName="Courier",
        fontSize=9,
        leading=12,
    )


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


def sections_folder(root_path: str, property_name: str, document_category: str) -> str:
    return os.path.join(template_folder(root_path, property_name, document_category), "Sections")


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
    folder = sections_folder(storage_root, property_name, document_category)
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



def _story_for_text_sections(section_texts: Sequence[str]) -> list:
    """Build ReportLab flowables for one or more token-resolved text sections.

    Consecutive text-backed clauses are intentionally placed in one story so
    ReportLab can paginate them naturally instead of forcing one page per clause.
    """
    story = []
    texts = [str(t or "").replace("\r\n", "\n").replace("\r", "\n").strip() for t in section_texts]
    texts = [t for t in texts if t]
    if not texts:
        texts = [""]

    for section_index, text in enumerate(texts):
        blocks = text.split("\n\n") if text.strip() else [""]
        first_block = True
        for block in blocks:
            clean = block.rstrip()
            if clean:
                flowable = Preformatted(escape(clean), LEASE_MONOSPACE, maxLineLength=110)
                if first_block:
                    story.append(KeepTogether([flowable]))
                    first_block = False
                else:
                    story.append(flowable)
            story.append(Spacer(1, 8))
        if section_index < len(texts) - 1:
            story.append(Spacer(1, 10))

    return story


def _validate_pdf_output(output_path: str, function_name: str) -> str:
    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"{function_name} failed to produce output at {output_path}")
    try:
        if len(PdfReader(output_path).pages) <= 0:
            raise RuntimeError(f"{function_name} produced a PDF with no pages at {output_path}")
    except Exception as ex:
        raise RuntimeError(f"{function_name} produced an unreadable PDF at {output_path}: {ex}")
    return output_path


def render_text_to_pdf(section_text: str, output_path: str) -> str:
    """Render one token-resolved lease text section to a PDF file.

    Kept for backward compatibility. New package generation should prefer
    render_text_sections_to_pdf() for consecutive text clauses.
    """
    return render_text_sections_to_pdf([section_text], output_path)


def render_text_sections_to_pdf(section_texts: Sequence[str], output_path: str) -> str:
    """Render multiple token-resolved lease text sections into one flowing PDF.

    This is the pagination-engine entry point. It lets consecutive clauses share
    pages and flow across page boundaries instead of rendering each clause as its
    own single-section PDF.
    """
    doc = SimpleDocTemplate(output_path, **PAGE_SETUP)
    story = _story_for_text_sections(section_texts)
    doc.build(story)
    return _validate_pdf_output(output_path, "render_text_sections_to_pdf()")


def merge_pdf_files(section_paths: Iterable[str], output_name: str, storage_root: str | None = None) -> str:
    folder = generated_folder(storage_root or DEFAULT_DOCUMENT_ROOT)
    ensure_folder(folder)
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
