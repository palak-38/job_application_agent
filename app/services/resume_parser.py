"""Parse the plain-text Drive export of the resume into a ResumeDoc.

The Google Doc keeps light structure conventions (the same ones the old
text pipeline already used), which survive the text/plain export:
- first non-empty line: the candidate's name
- lines before the first section header: contact details
- ALL-CAPS short lines: section headers (EXPERIENCE, SKILLS, ...)
- lines starting with "- " or a bullet char: bullets of the entry above
- "Something | 2023 - 2024" entry lines: the trailing segment with a year
  becomes the entry's date range

Unrecognized lines never crash the parse — they become plain entries.
"""

import logging
import re

from app.models.schemas import ResumeDoc, ResumeEntry, ResumeSection

logger = logging.getLogger(__name__)

_MAX_HEADER_LENGTH = 40
_YEAR_RE = re.compile(r"(19|20)\d{2}|present", re.IGNORECASE)
_BULLET_PREFIXES = ("- ", "• ", "* ")


def _is_section_header(line: str) -> bool:
    return (
        0 < len(line) <= _MAX_HEADER_LENGTH
        and line == line.upper()
        and any(c.isalpha() for c in line)
        and not line.startswith(_BULLET_PREFIXES)
    )


def _split_dates(line: str) -> tuple[str, str | None]:
    """'Intern | Acme | Jun 2025 - Aug 2025' -> ('Intern | Acme', 'Jun 2025 - Aug 2025')"""
    if "|" not in line:
        return line, None
    head, _, tail = line.rpartition("|")
    tail = tail.strip()
    if _YEAR_RE.search(tail):
        return head.strip(), tail
    return line, None


def parse_resume(text: str) -> ResumeDoc:
    name: str | None = None
    contact_lines: list[str] = []
    sections: list[ResumeSection] = []
    current_section: ResumeSection | None = None
    current_entry: ResumeEntry | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if name is None:
            name = line
            continue

        if _is_section_header(line):
            current_section = ResumeSection(title=line)
            sections.append(current_section)
            current_entry = None
            continue

        if current_section is None:
            contact_lines.append(line)
            continue

        if line.startswith(_BULLET_PREFIXES):
            if current_entry is None:
                current_entry = ResumeEntry()
                current_section.entries.append(current_entry)
            current_entry.bullets.append(line[2:].strip())
            continue

        heading, dates = _split_dates(line)
        current_entry = ResumeEntry(heading=heading, dates=dates)
        current_section.entries.append(current_entry)

    doc = ResumeDoc(
        name=name or "",
        contact=" | ".join(contact_lines) or None,
        sections=sections,
    )
    logger.info(
        f"Parsed resume: {len(doc.sections)} section(s), "
        f"{sum(len(s.entries) for s in doc.sections)} entries"
    )
    return doc


def resume_to_text(doc: ResumeDoc) -> str:
    """Serialize back to the plain-text conventions (LLM context, digests,
    and the fallback path all use this)."""
    lines = [doc.name]
    if doc.contact:
        lines.append(doc.contact)
    for section in doc.sections:
        lines.append("")
        lines.append(section.title)
        for entry in section.entries:
            if entry.heading:
                lines.append(
                    f"{entry.heading} | {entry.dates}" if entry.dates else entry.heading
                )
            lines.extend(f"- {b}" for b in entry.bullets)
    return "\n".join(lines)
