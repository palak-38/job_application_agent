import logging

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.models.schemas import Job

logger = logging.getLogger(__name__)

# The core Helvetica font is Latin-1 only. LLM-rewritten resume text
# routinely contains these Unicode punctuation marks (em/en dashes, curly
# quotes, bullets, ellipses) which would otherwise crash PDF rendering.
_UNICODE_REPLACEMENTS = {
    "—": "-",   # em dash
    "–": "-",   # en dash
    "‘": "'",   # left single quote
    "’": "'",   # right single quote
    "“": '"',   # left double quote
    "”": '"',   # right double quote
    "•": "-",   # bullet
    "…": "...", # ellipsis
    " ": " ",   # non-breaking space
}

_MAX_HEADER_LENGTH = 40


def _to_latin1_safe(text: str) -> str:
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Anything else the core font still can't render is dropped rather than
    # crashing the whole run.
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _is_section_header(line: str) -> bool:
    """Section headers are short ALL-CAPS lines (the rewriter's output
    format), e.g. 'EXPERIENCE' or 'TECHNICAL SKILLS'."""
    return (
        0 < len(line) <= _MAX_HEADER_LENGTH
        and line == line.upper()
        and any(c.isalpha() for c in line)
        and not line.startswith("-")
    )


def _write_line(pdf: FPDF, text: str, height: float) -> None:
    # new_x must return to the left margin: multi_cell's default (RIGHT)
    # parks the cursor at the right edge, leaving zero width for the next
    # call.
    pdf.multi_cell(0, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def create_resume_pdf(resume_text: str, job: Job) -> bytes:
    """Render resume_text to an ATS-friendly, single-column PDF in memory.

    Styles the rewriter's plain-text structure: first line = name (large,
    bold), ALL-CAPS lines = section headers (bold, extra spacing), the rest
    = body text. Pure-Python (fpdf2), nothing persisted to disk.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    name_rendered = False
    for line in _to_latin1_safe(resume_text).splitlines():
        stripped = line.strip()
        if not stripped:
            pdf.ln(2)
        elif not name_rendered:
            pdf.set_font("Helvetica", style="B", size=16)
            _write_line(pdf, stripped, 8)
            name_rendered = True
        elif _is_section_header(stripped):
            pdf.ln(2)
            pdf.set_font("Helvetica", style="B", size=12)
            _write_line(pdf, stripped, 7)
        else:
            pdf.set_font("Helvetica", size=10.5)
            _write_line(pdf, stripped, 5.5)

    logger.info(f"Rendered resume PDF for {job.company} — {job.title}")
    return bytes(pdf.output())
