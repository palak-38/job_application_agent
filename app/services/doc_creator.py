import logging

from fpdf import FPDF

from app.models.schemas import Job

logger = logging.getLogger(__name__)


def create_resume_pdf(resume_text: str, job: Job) -> bytes:
    """Render resume_text to an ATS-friendly, single-column PDF in memory.

    Pure-Python (fpdf2), no LaTeX/system deps, nothing persisted to disk.
    """
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)

    for line in resume_text.splitlines() or [""]:
        pdf.multi_cell(0, 6, line)

    logger.info(f"Rendered resume PDF for {job.company} — {job.title}")
    return bytes(pdf.output())
