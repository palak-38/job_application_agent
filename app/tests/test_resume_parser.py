from app.services.resume_parser import (
    _is_section_header,
    parse_resume,
    resume_to_text,
)

SAMPLE = """Palak Sood
palaksood4150@gmail.com | github.com/palak-38

SUMMARY
Backend engineer focused on Python APIs and applied LLM integration.

EXPERIENCE
Software Engineering Intern | Acme Corp | Jun 2025 - Aug 2025
- Built FastAPI services integrating Groq LLM inference
- Designed SQLite-backed idempotent job processing

TECHNICAL SKILLS
Python, FastAPI, SQLite, Docker, GitHub Actions

EDUCATION
B.Tech Computer Science | 2022 - 2026
"""


def test_parse_extracts_name_and_contact():
    doc = parse_resume(SAMPLE)
    assert doc.name == "Palak Sood"
    assert "palaksood4150@gmail.com" in doc.contact


def test_parse_builds_sections_and_entries():
    doc = parse_resume(SAMPLE)
    assert [s.title for s in doc.sections] == [
        "SUMMARY", "EXPERIENCE", "TECHNICAL SKILLS", "EDUCATION",
    ]

    experience = doc.sections[1].entries[0]
    assert experience.heading == "Software Engineering Intern | Acme Corp"
    assert experience.dates == "Jun 2025 - Aug 2025"
    assert len(experience.bullets) == 2
    assert experience.bullets[0].startswith("Built FastAPI")

    # Bare text lines (summary, skills) become heading-only entries.
    assert doc.sections[0].entries[0].heading.startswith("Backend engineer")
    assert doc.sections[0].entries[0].bullets == []


def test_parse_splits_dates_only_when_year_present():
    doc = parse_resume("Name\n\nEXPERIENCE\nEngineer | Acme | Platform Team\n- did x")
    entry = doc.sections[0].entries[0]
    assert entry.dates is None  # 'Platform Team' has no year -> not a date
    assert entry.heading == "Engineer | Acme | Platform Team"


def test_parse_never_crashes_on_loose_lines():
    doc = parse_resume("Name\nstray contact line\n\nWEIRD SECTION\njust some text")
    assert doc.name == "Name"
    assert doc.contact == "stray contact line"
    assert doc.sections[0].entries[0].heading == "just some text"


def test_roundtrip_preserves_content():
    doc = parse_resume(SAMPLE)
    text = resume_to_text(doc)
    for fragment in (
        "Palak Sood",
        "EXPERIENCE",
        "Software Engineering Intern | Acme Corp | Jun 2025 - Aug 2025",
        "- Built FastAPI services integrating Groq LLM inference",
        "Python, FastAPI, SQLite, Docker, GitHub Actions",
    ):
        assert fragment in text


def test_section_header_detection():
    assert _is_section_header("EXPERIENCE")
    assert _is_section_header("TECHNICAL SKILLS")
    assert not _is_section_header("Palak Sood")                 # mixed case
    assert not _is_section_header("- BUILT APIS")               # bullet
    assert not _is_section_header("2021 - 2023")                # no letters
    assert not _is_section_header("A" * 41)                     # too long
    assert not _is_section_header("")
