import logging

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.models.schemas import Job, ResumeDoc

logger = logging.getLogger(__name__)

# The core Helvetica font is Latin-1 only. LLM-edited resume text routinely
# contains these Unicode punctuation marks (em/en dashes, curly quotes,
# bullets, ellipses) which would otherwise crash PDF rendering.
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


def _safe(text: str) -> str:
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Anything else the core font still can't render is dropped rather than
    # crashing the whole run.
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _line(pdf: FPDF, text: str, height: float, indent: float = 0) -> None:
    # new_x must return to the left margin: multi_cell's default (RIGHT)
    # parks the cursor at the right edge, leaving zero width for the next
    # call.
    if indent:
        pdf.set_x(pdf.l_margin + indent)
    pdf.multi_cell(0, height, _safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def create_resume_pdf(resume: ResumeDoc, job: Job) -> bytes:
    """Render a ResumeDoc to an ATS-friendly, single-column PDF in memory.

    The layout is a fixed template over structured data, so every generated
    resume comes out consistently: the LLM can edit content but can never
    break the document's typography. Pure-Python (fpdf2), nothing persisted.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header: name + contact
    pdf.set_font("Helvetica", style="B", size=16)
    _line(pdf, resume.name, 8)
    if resume.contact:
        pdf.set_font("Helvetica", size=9)
        pdf.set_text_color(90, 90, 90)
        _line(pdf, resume.contact, 5)
        pdf.set_text_color(0, 0, 0)

    for section in resume.sections:
        pdf.ln(3)
        pdf.set_font("Helvetica", style="B", size=11.5)
        _line(pdf, section.title, 6)
        rule_y = pdf.get_y()
        pdf.line(pdf.l_margin, rule_y, pdf.w - pdf.r_margin, rule_y)
        pdf.ln(1.5)

        for entry in section.entries:
            if entry.heading and (entry.bullets or entry.dates):
                # A real role/project entry: bold heading, italic dates
                # right-aligned on the same row.
                pdf.set_font("Helvetica", style="B", size=10.5)
                if entry.dates:
                    dates_text = _safe(entry.dates)
                    pdf.set_font("Helvetica", style="I", size=9.5)
                    dates_width = pdf.get_string_width(dates_text) + 2
                    pdf.set_font("Helvetica", style="B", size=10.5)
                    pdf.cell(pdf.epw - dates_width, 5.5, _safe(entry.heading))
                    pdf.set_font("Helvetica", style="I", size=9.5)
                    pdf.cell(
                        dates_width, 5.5, dates_text,
                        align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                    )
                else:
                    _line(pdf, entry.heading, 5.5)
            elif entry.heading:
                # Bare text line (summary paragraph, skills list): body style.
                pdf.set_font("Helvetica", size=10.5)
                _line(pdf, entry.heading, 5.5)

            pdf.set_font("Helvetica", size=10.5)
            for bullet in entry.bullets:
                _line(pdf, f"- {bullet}", 5.5, indent=3)
            if entry.bullets:
                pdf.ln(1)

    logger.info(f"Rendered resume PDF for {job.company} — {job.title}")
    return bytes(pdf.output())
