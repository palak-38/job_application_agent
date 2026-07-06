import logging

from fpdf import FPDF

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
    " ": " ",   # non-breaking space
}


def _to_latin1_safe(text: str) -> str:
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Anything else the core font still can't render is dropped rather than
    # crashing the whole run.
    return text.encode("latin-1", errors="replace").decode("latin-1")


def create_resume_pdf(resume_text: str, job: Job) -> bytes:
    """Render resume_text to an ATS-friendly, single-column PDF in memory.

    Pure-Python (fpdf2), no LaTeX/system deps, nothing persisted to disk.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    # One multi_cell call for the whole text: it handles embedded newlines
    # itself. Calling it per line is a trap — its default new_x=RIGHT parks
    # the cursor at the right margin, so a second call has zero width left.
    safe_text = _to_latin1_safe(resume_text)
    pdf.multi_cell(0, 6, safe_text)

    logger.info(f"Rendered resume PDF for {job.company} — {job.title}")
    return bytes(pdf.output())
