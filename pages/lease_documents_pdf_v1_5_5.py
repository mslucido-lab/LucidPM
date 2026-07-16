"""
Lease template PDF utility functions.

Stores source PDFs and split sections on disk. SQL Server stores metadata only.

Patched 5/3/2026:
- v1.5.5: normalized soft-wrapped legal paragraphs for stronger justification and improved clause spacing fallback styles.
- v1.5.3: improved signature footer fallback style and table-based footer layout.

Patched 5/1/2026:
- v1.5.2: fixed style import path and softened conditional page breaks.
- v1.5.1: legal header formatting with softened anti-orphan rules so clauses keep flowing across pages.
- v1.5: smart legal formatting rules.
- v1.4: style-aware legal renderer with flowing pagination, clause headers, justified text, and per-page signature footer.
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
from reportlab.platypus import SimpleDocTemplate, Spacer, Preformatted, KeepTogether, Paragraph, CondPageBreak

DEFAULT_DOCUMENT_ROOT = r"C:\Dell Inspirion\TenantCRM\LeaseDocuments"

try:
    from LucidPM_Reflex.pages.lease_render_styles import (
        PAGE_SETUP,
        LEASE_STYLES,
        LEASE_MONOSPACE,
        SIGNATURE_FOOTER_TEXT,
    )
except Exception:
    PAGE_SETUP = {
        "pagesize": letter,
        "leftMargin": 54,
        "rightMargin": 54,
        "topMargin": 54,
        "bottomMargin": 72,
    }
    LEASE_MONOSPACE = ParagraphStyle(
        name="LeaseMonospace",
        fontName="Courier",
        fontSize=9,
        leading=12,
    )
    LEASE_STYLES = {
        "CLAUSE_BODY": ParagraphStyle("ClauseBody", fontName="Times-Roman", fontSize=10, leading=13, alignment=4, leftIndent=18, firstLineIndent=-18, spaceAfter=8),
        "ARTICLE_HEADER": ParagraphStyle("ArticleHeader", fontName="Times-Bold", fontSize=10, leading=12, keepWithNext=True, spaceBefore=6, spaceAfter=5),
        "DOC_TITLE": ParagraphStyle("DocTitle", fontName="Times-Bold", fontSize=12, leading=15, alignment=1),
        "JURISDICTION": ParagraphStyle("Jurisdiction", fontName="Times-Roman", fontSize=10, leading=12, alignment=2),
        "PARTY_NAME": ParagraphStyle("PartyName", fontName="Times-Bold", fontSize=11, leading=13),
        "PARTY_LABEL": ParagraphStyle("PartyLabel", fontName="Times-Italic", fontSize=9, leading=11),
        "WITNESSETH": ParagraphStyle("Witnesseth", fontName="Times-Bold", fontSize=10, leading=12, alignment=1),
        "INDENTED_BODY": ParagraphStyle("IndentedBody", fontName="Times-Roman", fontSize=10, leading=13, alignment=4, leftIndent=36, firstLineIndent=-18, spaceAfter=8),
        "PAYMENT_SCHEDULE": LEASE_MONOSPACE,
        "SIGNATURE_FOOTER": ParagraphStyle(
            "SignatureFooter",
            fontName="Times-Roman",
            fontSize=8,
            leading=9,
            alignment=1,
        ),
    }
    SIGNATURE_FOOTER_TEXT = "________              ________              ________<br/>Landlord                 Tenant                    Tenant"


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




def _normalize_legal_paragraph(text: str) -> str:
    """Remove PDF/Word soft wraps so ReportLab can fully justify paragraphs."""
    lines = [ln.strip() for ln in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    joined = " ".join(lines)
    return re.sub(r"\s+", " ", joined).strip()


def _xml(text: str, preserve_line_breaks: bool = False) -> str:
    """Escape text for ReportLab Paragraph. Legal body text is soft-wrap normalized by default."""
    if preserve_line_breaks:
        return escape(str(text or "")).replace("\n", "<br/>")
    return escape(_normalize_legal_paragraph(text))


def _is_doc_title(block: str) -> bool:
    text = str(block or "").strip()
    return bool(text) and len(text) <= 80 and text.upper() == text and any(word in text for word in ["LEASE", "AGREEMENT", "ADDENDUM", "EXHIBIT"])


def _is_jurisdiction(block: str) -> bool:
    lines = [ln.strip() for ln in str(block or "").split("\n") if ln.strip()]
    return len(lines) in (1, 2, 3) and any(ln.lower().startswith("state of") for ln in lines) and any(ln.lower().startswith("county of") for ln in lines)


def _is_party_label(block: str) -> bool:
    text = str(block or "").strip().lower()
    return text.startswith("(") and "hereinafter" in text


def _is_party_name(block: str) -> bool:
    text = str(block or "").strip()
    if not text or "\n" in text:
        return False
    lower = text.lower()
    return len(text) <= 100 and any(term in lower for term in ["llc", "inc", "l.l.c.", "capital partners", "properties"])


def _is_witnesseth(block: str) -> bool:
    return str(block or "").strip().upper().replace(".", "") == "WITNESSETH"


def _header_match(block: str):
    text = str(block or "").strip()
    return re.match(r"^((?:ARTICLE|Article|SECTION|Section)\s+[0-9A-Za-zIVXLCDM\.]+|[0-9]{1,3}[\.)]|[A-Z][\.)]|[a-z]\))\s*(.*)$", text)




def _is_signature_block(block: str) -> bool:
    text = str(block or "").strip().lower()
    return any(term in text for term in [
        "landlord", "tenant", "witness", "by:", "name:", "title:"
    ]) and ("____" in text or "signature" in text)


def _is_article_heading(block: str) -> bool:
    text = str(block or "").strip()
    return bool(re.match(r"^(ARTICLE|Article)\s+[A-Z0-9IVXLCDM]+", text))


def _is_numbered_clause(block: str) -> bool:
    text = str(block or "").strip()
    return bool(re.match(r"^[0-9]{1,3}(\.[0-9]+)*[\.)]?\s+", text))


def _is_lettered_clause(block: str) -> bool:
    text = str(block or "").strip()
    return bool(re.match(r"^[a-zA-Z][\.)]\s+", text))

def _is_payment_schedule(block: str) -> bool:
    text = str(block or "")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if len(lines) < 3:
        return False

    money_lines = sum(1 for ln in lines if "$" in ln)
    lettered_rows = sum(1 for ln in lines if re.search(r"(^|\s)[a-l]\)", ln, flags=re.IGNORECASE))
    dated_rows = sum(1 for ln in lines if re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b", ln, flags=re.IGNORECASE))

    # Only true schedules should use Courier. Single lines like "Rent Amount: $1,300.00" stay Times Roman.
    return money_lines >= 3 and (lettered_rows >= 2 or dated_rows >= 2)


def _paragraph_for_block(block: str):
    """Return one or more flowables for a plain-text lease block."""
    clean = str(block or "").strip()
    if not clean:
        return []

    if _is_doc_title(clean):
        return [Paragraph(_xml(clean), LEASE_STYLES["DOC_TITLE"])]
    if _is_jurisdiction(clean):
        return [Paragraph(_xml(clean, preserve_line_breaks=True), LEASE_STYLES["JURISDICTION"])]
    if _is_witnesseth(clean):
        return [Paragraph(_xml(clean), LEASE_STYLES["WITNESSETH"])]
    if _is_party_label(clean):
        return [Paragraph(_xml(clean), LEASE_STYLES["PARTY_LABEL"])]
    if _is_party_name(clean):
        return [Paragraph(_xml(clean), LEASE_STYLES["PARTY_NAME"])]
    if _is_payment_schedule(clean):
        return [KeepTogether([
            Preformatted(escape(clean), LEASE_STYLES["PAYMENT_SCHEDULE"], maxLineLength=95)
        ])]

    if _is_signature_block(clean):
        return [KeepTogether([
            Paragraph(_xml(clean, preserve_line_breaks=True), LEASE_STYLES["SIGNATURE_BLOCK"])
        ])]

    if _is_article_heading(clean):
        return [Paragraph(_xml(clean), LEASE_STYLES["ARTICLE_CENTERED"])]

    header = _header_match(clean)
    if header:
        marker = header.group(1).strip()
        rest = header.group(2).strip()
        if rest:
            return [Paragraph(_xml(f"{marker} {rest}"), LEASE_STYLES["ARTICLE_HEADER"])]
        return [Paragraph(_xml(marker), LEASE_STYLES["ARTICLE_HEADER"])]

    if re.match(r"^[a-z]\)\s+", clean) or re.match(r"^[ivxlcdm]+[\.)]\s+", clean, flags=re.IGNORECASE):
        return [Paragraph(_xml(clean), LEASE_STYLES["INDENTED_BODY"])]

    return [Paragraph(_xml(clean), LEASE_STYLES["CLAUSE_BODY"])]


def _split_blocks(text: str) -> list[str]:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return [""]
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
    return blocks or [text]


def _story_for_text_sections(section_texts: Sequence[str]) -> list:
    """Build styled ReportLab flowables for one or more token-resolved text sections."""
    story = []
    texts = [str(t or "").replace("\r\n", "\n").replace("\r", "\n").strip() for t in section_texts]
    texts = [t for t in texts if t]
    if not texts:
        texts = [""]

    for section_index, text in enumerate(texts):
        blocks = _split_blocks(text)
        first_real_block = True
        for block in blocks:
            flowables = _paragraph_for_block(block)
            if not flowables:
                continue

            story.append(CondPageBreak(int(0.75 * 72)))

            if first_real_block and len(flowables) == 1:
                story.append(KeepTogether(flowables))
                first_real_block = False
            else:
                story.extend(flowables)
                first_real_block = False
        if section_index < len(texts) - 1:
            # Paragraph styles already define clause spacing; avoid adding extra vertical gap between saved sections.
            story.append(Spacer(1, 0))

    return story


def _signature_footer(canvas, doc):
    """Draw the standard lease signature footer on every generated text page."""
    try:
        from reportlab.platypus import Table, TableStyle

        width, _ = doc.pagesize
        left_margin = PAGE_SETUP.get("leftMargin", 0.75 * 72)
        right_margin = PAGE_SETUP.get("rightMargin", 0.75 * 72)
        usable_width = width - left_margin - right_margin
        col_w = usable_width / 3

        footer_style = LEASE_STYLES.get(
            "SIGNATURE_FOOTER",
            ParagraphStyle("SigFtr", fontName="Times-Roman", fontSize=8, leading=9, alignment=1),
        )
        footer_font = getattr(footer_style, "fontName", "Times-Roman") or "Times-Roman"
        footer_size = getattr(footer_style, "fontSize", 8) or 8

        line_table = Table([["________", "________", "________"]], colWidths=[col_w, col_w, col_w])
        line_table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Times-Roman", 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))

        label_table = Table([["Landlord", "Tenant", "Tenant"]], colWidths=[col_w, col_w, col_w])
        label_table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), footer_font, footer_size),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))

        footer_y = 0.45 * 72
        _lw, label_h = label_table.wrap(usable_width, 20)
        label_table.drawOn(canvas, left_margin, footer_y)

        line_y = footer_y + label_h + 4
        line_table.wrap(usable_width, 20)
        line_table.drawOn(canvas, left_margin, line_y)
    except Exception:
        return

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
    doc.build(story, onFirstPage=_signature_footer, onLaterPages=_signature_footer)
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
