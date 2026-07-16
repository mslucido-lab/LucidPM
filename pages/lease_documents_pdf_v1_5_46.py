"""
Lease template PDF utility functions.

Stores source PDFs and split sections on disk. SQL Server stores metadata only.

Patched 5/4/2026:
- v1.5.46: centers grouped 3+ year payment schedules with a fixed-width direct table; no other rendering changes.
- v1.5.42: baseline from v1.5.26; preserves header behavior, safely splits body <br/> into paragraphs, and fixes grouped 3+ year payment schedules.
- v1.5.45: centers grouped 3+ year payment schedules and keeps only Special Conditions headers with first child.
- v1.5.26: normalizes soft line breaks inside inline markup and justifies lettered child clauses to the right margin.
- v1.5.24: strips inline ReportLab tags before lettered-child detection so <b>a.</b> still indents correctly.
- v1.5.23: indents lettered child clauses using INDENTED_BODY for Special Conditions and similar subsections.
- v1.5.22: logs signature footer rendering exceptions instead of silently swallowing them.
- v1.5.21: removes hanging indent from numbered clause header lines.
- v1.5.20: forces generated text PDFs to use 0.5 inch left/right margins to match the Word lease baseline.

Patched 5/3/2026:
- v1.5.19: keeps multi-line inline markup blocks intact so tags like <b> are not split across paragraphs.
- v1.5.18: safely splits ReportLab markup blocks so <para> blocks are not combined with other markup in one Paragraph.
- v1.5.17: allows trusted ReportLab HTML-style markup in rendered text blocks, including <para>, <b>, <i>, <u>, <font>, and <br/>.
- v1.5.16: centers payment schedule tables within the indented clause body instead of the full page frame.
- v1.5.15: renders payment schedules as four-column tables: label, payment text, label, payment text, with 10pt font.
- v1.5.14: fixes payment schedule parsing for two-year schedules whose right column starts at m) or later.
- v1.5.9: renders payment schedules as centered two-column Times-Roman tables with left-aligned columns.
- v1.5.8: changed payment schedule/token rendering from Courier to Times-Roman.
- v1.5.7: preserves hard line breaks inside payment clauses and centers payment schedule blocks.
- v1.5.6: normalized soft-wrapped legal paragraphs for stronger justification and improved clause spacing fallback styles.
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
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Spacer, Preformatted, KeepTogether, Paragraph, CondPageBreak, Table, TableStyle

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
        fontName="Times-Roman",
        fontSize=9,
        leading=12,
    )
    LEASE_STYLES = {
        "CLAUSE_BODY": ParagraphStyle("ClauseBody", fontName="Times-Roman", fontSize=10, leading=12, alignment=4, leftIndent=36, firstLineIndent=0, spaceBefore=0, spaceAfter=10),
        "ARTICLE_HEADER": ParagraphStyle("ArticleHeader", fontName="Times-Bold", fontSize=10, leading=12, alignment=4, leftIndent=36, firstLineIndent=0, keepWithNext=True, spaceBefore=6, spaceAfter=4),
        "DOC_TITLE": ParagraphStyle("DocTitle", fontName="Times-Bold", fontSize=12, leading=15, alignment=1),
        "JURISDICTION": ParagraphStyle("Jurisdiction", fontName="Times-Roman", fontSize=10, leading=12, alignment=2),
        "PARTY_NAME": ParagraphStyle("PartyName", fontName="Times-Bold", fontSize=11, leading=13),
        "PARTY_LABEL": ParagraphStyle("PartyLabel", fontName="Times-Italic", fontSize=9, leading=11),
        "WITNESSETH": ParagraphStyle("Witnesseth", fontName="Times-Bold", fontSize=10, leading=12, alignment=1),
        "INDENTED_BODY": ParagraphStyle("IndentedBody", fontName="Times-Roman", fontSize=10, leading=12, alignment=4, leftIndent=54, firstLineIndent=0, spaceAfter=10),
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


def _page_setup_with_word_margins() -> dict:
    """Return page setup with Word-baseline 0.5 inch left/right margins."""
    setup = dict(PAGE_SETUP)
    setup["leftMargin"] = 0.5 * inch
    setup["rightMargin"] = 0.5 * inch
    return setup


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


def _looks_like_reportlab_markup(text: str) -> bool:
    """True when trusted section content contains ReportLab-supported markup."""
    raw = str(text or "")
    allowed_markers = [
        "<para", "</para>",
        "<b>", "</b>",
        "<i>", "</i>",
        "<u>", "</u>",
        "<font", "</font>",
        "<br/>", "<br />",
        "<super>", "</super>",
        "<sub>", "</sub>",
    ]
    return any(marker.lower() in raw.lower() for marker in allowed_markers)


def _sanitize_reportlab_markup(text: str) -> str:
    """Preserve supported ReportLab tags while escaping unsafe stray angle brackets."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    # Collapse physical soft wraps only inside marked-up paragraphs. Authored
    # paragraph breaks are handled before this with <br/> splitting in body text.
    raw = re.sub(r"[ \t]*\n[ \t]*", " ", raw)
    allowed_tag_re = re.compile(
        r"</?(?:para|b|i|u|font|super|sub)\b[^>]*>|<br\s*/?>",
        flags=re.IGNORECASE,
    )
    out: list[str] = []
    pos = 0
    for match in allowed_tag_re.finditer(raw):
        if match.start() > pos:
            out.append(escape(raw[pos:match.start()]))
        out.append(match.group(0))
        pos = match.end()
    if pos < len(raw):
        out.append(escape(raw[pos:]))
    return "".join(out)


def _strip_para_tags(markup: str) -> str:
    text = str(markup or "")
    text = re.sub(r"<para\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</para>", "", text, flags=re.IGNORECASE)
    return text.strip()


def _balance_inline_tags(markup: str) -> str:
    text = str(markup or "").strip()
    tag_re = re.compile(r"</?(b|i|u|font|super|sub)\b[^>]*>", flags=re.IGNORECASE)
    stack: list[str] = []
    for m in tag_re.finditer(text):
        tag_text = m.group(0)
        tag = m.group(1).lower()
        if tag_text.startswith("</"):
            if tag in stack:
                while stack and stack[-1] != tag:
                    stack.pop()
                if stack and stack[-1] == tag:
                    stack.pop()
        else:
            stack.append(tag)
    return text + "".join(f"</{tag}>" for tag in reversed(stack))


def _safe_paragraph(markup: str, style):
    """Create a Paragraph without letting malformed inline markup crash generation."""
    text = str(markup or "").strip()
    attempts = []
    if text:
        attempts.append(text)
        no_para = _strip_para_tags(text)
        if no_para and no_para != text:
            attempts.append(no_para)
        balanced = _balance_inline_tags(no_para or text)
        if balanced and balanced not in attempts:
            attempts.append(balanced)
    last_error = None
    for candidate in attempts:
        try:
            return Paragraph(candidate, style)
        except Exception as ex:
            last_error = ex
    plain = re.sub(r"<[^>]+>", "", text)
    try:
        return Paragraph(_xml(plain), style)
    except Exception:
        if last_error:
            raise last_error
        raise


def _outer_inline_tags(text: str) -> tuple[list[tuple[str, str, str]], str]:
    """Return outer tags wrapping the whole text, plus inner text."""
    body = str(text or "").strip()
    wrappers: list[tuple[str, str, str]] = []
    wrapper_re = re.compile(
        r"^\s*(?P<open><(?P<tag>para|b|i|u|font|super|sub)\b[^>]*>)\s*"
        r"(?P<body>.*)"
        r"\s*(?P<close></(?P=tag)>)\s*$",
        flags=re.IGNORECASE | re.DOTALL,
    )
    while True:
        match = wrapper_re.match(body)
        if not match:
            break
        wrappers.append((match.group("open"), match.group("tag").lower(), match.group("close")))
        body = match.group("body").strip()
    return wrappers, body


def _rewrap_inline_tags(block: str, wrappers: list[tuple[str, str, str]]) -> str:
    out = str(block or "").strip()
    opening = "".join(open_tag for open_tag, _tag_name, _close_tag in wrappers)
    closing = "".join(close_tag for _open_tag, _tag_name, close_tag in reversed(wrappers))
    return f"{opening}{out}{closing}"


def _split_body_br_blocks(text: str) -> list[str]:
    """Split authored <br/> body text into paragraph blocks with balanced wrappers."""
    raw = str(text or "").strip()
    wrappers, inner_text = _outer_inline_tags(raw)
    split_source = re.sub(r"<br\s*/?>", "\n\n", inner_text, flags=re.IGNORECASE)
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", split_source) if b.strip()]
    if wrappers:
        blocks = [_rewrap_inline_tags(b, wrappers) for b in blocks]
    return blocks or [raw]


def _markup_or_xml(text: str, preserve_line_breaks: bool = False) -> str:
    """Allow trusted ReportLab inline markup, otherwise escape normally."""
    raw = str(text or "")
    if _looks_like_reportlab_markup(raw):
        return _sanitize_reportlab_markup(raw)
    return _xml(raw, preserve_line_breaks=preserve_line_breaks)


def _markup_flowables(text: str, style) -> list:
    """Render trusted markup as one or more safe ReportLab Paragraph flowables.

    ReportLab can render a single <para>...</para> block, but it can fail when
    multiple <para> blocks or a <para> block plus sibling markup are passed into
    one Paragraph. Split <para> blocks cleanly, but keep non-para inline markup
    intact so tags like <b>...</b> are not split across line breaks.
    """
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []

    if not _looks_like_reportlab_markup(raw):
        return [_safe_paragraph(_xml(raw), style)]

    parts: list[str] = []
    pos = 0
    para_re = re.compile(r"<para\b[^>]*>.*?</para>", flags=re.IGNORECASE | re.DOTALL)

    for m in para_re.finditer(raw):
        before = raw[pos:m.start()].strip()
        if before:
            # Keep inline markup before a para block intact. Do not split by line.
            parts.append(before)
        parts.append(m.group(0).strip())
        pos = m.end()

    after = raw[pos:].strip()
    if after:
        # Keep inline markup after a para block intact. Do not split by line.
        parts.append(after)

    if not parts:
        parts = [raw]

    flowables = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        if "<para" in cleaned.lower():
            flowables.append(_safe_paragraph(_sanitize_reportlab_markup(cleaned), style))
        else:
            flowables.append(_safe_paragraph(_markup_or_xml(cleaned), style))
    return flowables


def _is_doc_title(block: str) -> bool:
    text = str(block or "").strip()
    return bool(text) and len(text) <= 80 and text.upper() == text and any(word in text for word in ["LEASE", "AGREEMENT", "ADDENDUM", "EXHIBIT"])


def _is_jurisdiction(block: str) -> bool:
    text = re.sub(r"<br\s*/?>", "\n", str(block or ""), flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
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
    lettered_rows = sum(1 for ln in lines if re.search(r"(^|\s)[a-z]{1,2}\)", ln, flags=re.IGNORECASE))
    dated_rows = sum(1 for ln in lines if re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b", ln, flags=re.IGNORECASE))

    # Payment schedules now use Times-Roman for visual consistency with the lease body.
    return money_lines >= 3 and (lettered_rows >= 2 or dated_rows >= 2)


def _is_payment_schedule_line(line: str) -> bool:
    """True for an individual payment schedule row, not intro money lines."""
    text = str(line or "").strip()
    if not text or "$" not in text:
        return False
    month = r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
    return bool(re.search(month, text, flags=re.IGNORECASE)) and bool(
        re.search(r"(^|\s)[a-z]{1,2}\)", text, flags=re.IGNORECASE) or re.search(r"\d{1,2},\s*\d{4}", text)
    )


def _split_payment_schedule_item(item: str) -> tuple[str, str]:
    """Split a schedule item into its label and payment text.

    Example:
      "a) January 11, 2026: $750" -> ("a)", "January 11, 2026: $750")
    """
    text = str(item or "").strip()
    m = re.match(r"^([a-z]{1,2}\))\s*(.*)$", text, flags=re.IGNORECASE)
    if not m:
        return "", text
    return m.group(1).strip(), m.group(2).strip()


def _split_payment_schedule_row(line: str) -> list[tuple[str, str]]:
    """Split one schedule line into one or two label/text schedule items.

    Times-Roman is proportional, so spaces cannot be used for alignment.
    This parser turns lines like:
      a) September 1, 2025: $1,300.00   m) March 1, 2026: $1,300.00
    into:
      [("a)", "September 1, 2025: $1,300.00"), ("m)", "March 1, 2026: $1,300.00")]
    """
    text = str(line or "").strip()
    if not text:
        return []

    parts = re.findall(
        r"[a-z]{1,2}\)\s+.*?(?=\s+[a-z]{1,2}\)\s+|$)",
        text,
        flags=re.IGNORECASE,
    )
    parts = [p.strip() for p in parts if p and p.strip()]
    if parts:
        return [_split_payment_schedule_item(p) for p in parts[:2]]
    return [("", text)]


def _schedule_table_flowable(lines: list[str]):
    """Render schedule rows as a centered four-column block within the clause body.

    Columns are:
      left label, left payment text, right label, right payment text
    This matches the Word table structure and gives a stable tab-stop look.
    """
    schedule_style = ParagraphStyle(
        "PaymentScheduleTable10",
        parent=LEASE_STYLES["PAYMENT_SCHEDULE"],
        fontName="Times-Roman",
        fontSize=10,
        leading=12,
        alignment=0,  # TA_LEFT
    )

    parsed_rows = []
    has_two_column_rows = False
    for ln in lines or []:
        parts = _split_payment_schedule_row(ln)
        if not parts:
            continue
        if len(parts) >= 2 and any(str(x or "").strip() for x in parts[1]):
            has_two_column_rows = True
        parsed_rows.append(parts)

    if not parsed_rows:
        return []

    # Center the schedule inside the clause body, not the full page frame.
    # The clause body uses a left indent, so wrap the schedule in an invisible
    # outer table with matching left inset and center the inner table there.
    effective_setup = _page_setup_with_word_margins()
    frame_width = letter[0] - effective_setup.get("leftMargin", 36) - effective_setup.get("rightMargin", 36)
    clause_left_indent = getattr(LEASE_STYLES["CLAUSE_BODY"], "leftIndent", 0) or 0
    clause_body_width = frame_width - clause_left_indent

    label_w = 22

    if has_two_column_rows:
        # Monthly schedules use two side-by-side payment columns.
        table_width = min(4.95 * 72, clause_body_width)
        text_w = (table_width / 2) - label_w
        rows = []
        for parts in parsed_rows:
            if len(parts) == 1:
                parts.append(("", ""))
            left_label, left_text = parts[0]
            right_label, right_text = parts[1]
            rows.append([
                Paragraph(_xml(left_label), schedule_style),
                Paragraph(_xml(left_text), schedule_style),
                Paragraph(_xml(right_label), schedule_style),
                Paragraph(_xml(right_text), schedule_style),
            ])
        tbl = Table(
            rows,
            colWidths=[label_w, text_w, label_w, text_w],
            hAlign="CENTER",
        )
        tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Times-Roman", 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 4),
            ("RIGHTPADDING", (2, 0), (2, -1), 4),
            ("RIGHTPADDING", (1, 0), (1, -1), 10),
            ("RIGHTPADDING", (3, 0), (3, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
    else:
        # Grouped 3+ year schedules are one payment period per row. Keep this
        # branch fully separate from the monthly 4-column layout. Use a fixed
        # content-width table and center it directly in the document frame.
        # Do not use the indented outer wrapper here.
        table_width = min(4.75 * 72, clause_body_width)
        text_w = table_width - label_w
        rows = []
        for parts in parsed_rows:
            label, text = parts[0]
            rows.append([
                Paragraph(_xml(label), schedule_style),
                Paragraph(_xml(text), schedule_style),
            ])
        tbl = Table(
            rows,
            colWidths=[label_w, text_w],
            hAlign="CENTER",
        )
        tbl.hAlign = "CENTER"
        tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), "Times-Roman", 10),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 4),
            ("RIGHTPADDING", (1, 0), (1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return [KeepTogether([tbl])]

    outer = Table(
        [[tbl]],
        colWidths=[clause_body_width],
        hAlign="LEFT",
    )
    outer.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), clause_left_indent),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return [KeepTogether([outer])]


def _payment_clause_flowables(block: str):
    """Preserve hard line breaks around rent/payment instructions and center the schedule rows."""
    lines = [ln.strip() for ln in str(block or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    flowables = []
    schedule_lines: list[str] = []

    def flush_schedule():
        nonlocal schedule_lines
        if schedule_lines:
            flowables.extend(_schedule_table_flowable(schedule_lines))
            schedule_lines = []

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_schedule()
            # Keep a small visual paragraph break inside payment clauses.
            if flowables:
                flowables.append(Spacer(1, 3))
            continue

        if _is_payment_schedule_line(line):
            schedule_lines.append(line)
            continue

        flush_schedule()
        flowables.extend(_markup_flowables(line, LEASE_STYLES["CLAUSE_BODY"]))

    flush_schedule()
    return flowables


def _contains_payment_clause_layout(block: str) -> bool:
    text = str(block or "")
    if "\n" not in text:
        return False
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    schedule_rows = sum(1 for ln in lines if _is_payment_schedule_line(ln))
    return schedule_rows >= 2 or ("payment schedule" in text.lower() and "$" in text)


def _paragraph_for_block(block: str):
    """Return one or more flowables for a plain-text lease block."""
    clean = str(block or "").strip()
    if not clean:
        return []

    if _is_doc_title(clean):
        return _markup_flowables(clean, LEASE_STYLES["DOC_TITLE"])
    if _is_jurisdiction(clean):
        return _markup_flowables(clean, LEASE_STYLES["JURISDICTION"])
    if _is_witnesseth(clean):
        return _markup_flowables(clean, LEASE_STYLES["WITNESSETH"])
    if _is_party_label(clean):
        return _markup_flowables(clean, LEASE_STYLES["PARTY_LABEL"])
    if _is_party_name(clean):
        return _markup_flowables(clean, LEASE_STYLES["PARTY_NAME"])
    if _contains_payment_clause_layout(clean):
        return _payment_clause_flowables(clean)
    if _is_payment_schedule(clean):
        return _schedule_table_flowable(clean.split("\n"))

    if _is_signature_block(clean):
        return [KeepTogether([
            _safe_paragraph(_xml(clean, preserve_line_breaks=True), LEASE_STYLES["SIGNATURE_BLOCK"])
        ])]

    if _is_article_heading(clean):
        return _markup_flowables(clean, LEASE_STYLES["ARTICLE_CENTERED"])

    header = _header_match(clean)
    if header:
        marker = header.group(1).strip()
        rest = header.group(2).strip()
        if rest:
            return _markup_flowables(f"{marker} {rest}", LEASE_STYLES["ARTICLE_HEADER"])
        return _markup_flowables(marker, LEASE_STYLES["ARTICLE_HEADER"])

    # Treat authored <br/> tags as body paragraph breaks only after header
    # detection. This preserves the lease header/jurisdiction behavior from
    # v1.5.26 while fixing body clauses that use <br/> for paragraph breaks.
    if "<br" in clean.lower():
        flowables = []
        for body_block in _split_body_br_blocks(clean):
            flowables.extend(_paragraph_for_block(body_block))
        return flowables

    # Detect lettered / roman child clauses against plain text so inline
    # markup like <b>a.</b> does not bypass indentation. Keep the original
    # marked-up text for rendering.
    plain_for_detection = re.sub(r"<[^>]+>", "", clean).lstrip()
    if re.match(r"^[a-z][\.)]\s+", plain_for_detection) or re.match(r"^[ivxlcdm]+[\.)]\s+", plain_for_detection, flags=re.IGNORECASE):
        base_style = LEASE_STYLES["INDENTED_BODY"]
        child_style = ParagraphStyle(
            "IndentedChildBody",
            parent=base_style,
            alignment=4,  # TA_JUSTIFY
            rightIndent=0,
        )
        return _markup_flowables(clean, child_style)

    return _markup_flowables(clean, LEASE_STYLES["CLAUSE_BODY"])


def _split_blocks(text: str) -> list[str]:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return [""]
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
    return blocks or [text]



def _flowable_plain_text(flowable) -> str:
    """Return plain text for Paragraph or simple KeepTogether flowables."""
    try:
        if hasattr(flowable, "getPlainText"):
            return str(flowable.getPlainText() or "")
        content = getattr(flowable, "_content", None)
        if content:
            return " ".join(_flowable_plain_text(item) for item in content).strip()
    except Exception:
        return ""
    return ""


def _is_special_conditions_header_flowable(flowable) -> bool:
    """Detect only the Special Conditions parent header, not every article header."""
    text = re.sub(r"\s+", " ", _flowable_plain_text(flowable)).strip()
    return bool(re.match(r"^22\.?\s+SPECIAL CONDITIONS\b", text, flags=re.IGNORECASE))


def _is_zero_spacer(flowable) -> bool:
    try:
        return flowable.__class__.__name__ == "Spacer" and float(getattr(flowable, "height", 0) or 0) == 0
    except Exception:
        return False


def _is_cond_page_break(flowable) -> bool:
    return flowable.__class__.__name__ == "CondPageBreak"


def _keep_special_conditions_with_next(story: list) -> list:
    """Keep only 22. SPECIAL CONDITIONS with the first following flowable.

    Do not apply this to all ARTICLE_HEADER paragraphs. Doing so can make normal
    clauses too large to split and forces each clause onto a separate page.
    """
    out = []
    i = 0
    while i < len(story):
        current = story[i]
        if _is_special_conditions_header_flowable(current):
            j = i + 1
            skipped = []
            while j < len(story) and (_is_zero_spacer(story[j]) or _is_cond_page_break(story[j])):
                skipped.append(story[j])
                j += 1
            if j < len(story):
                # Drop internal CondPageBreak/zero spacer between the header and child.
                # KeepTogether will move the pair if they do not fit at page bottom.
                out.append(KeepTogether([current, story[j]]))
                i = j + 1
                continue
        out.append(current)
        i += 1
    return out


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

    return _keep_special_conditions_with_next(story)


def _signature_footer(canvas, doc):
    """Draw the standard lease signature footer on every generated text page."""
    try:
        from reportlab.platypus import Table, TableStyle

        width, _ = doc.pagesize
        effective_setup = _page_setup_with_word_margins()
        left_margin = effective_setup.get("leftMargin", 0.5 * 72)
        right_margin = effective_setup.get("rightMargin", 0.5 * 72)
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
    except Exception as ex:
        import traceback
        print(f"[lease_documents_pdf] _signature_footer failed: {ex}")
        traceback.print_exc()
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
    doc = SimpleDocTemplate(output_path, **_page_setup_with_word_margins())
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
