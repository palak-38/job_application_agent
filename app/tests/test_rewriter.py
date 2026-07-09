import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import (
    BulletEdit,
    Job,
    ResumeDoc,
    ResumeEdits,
    ResumeEntry,
    ResumeSection,
)
from app.services.rewriter import apply_edits, tailor_resume


def make_test_job() -> Job:
    return Job(
        title="Software Engineer",
        company="Acme Corp",
        location="Remote",
        description="We need a Python developer with FastAPI experience.",
        url="https://example.com/job/1",
    )


def make_doc() -> ResumeDoc:
    return ResumeDoc(
        name="Palak Sood",
        contact="mail@example.com",
        sections=[
            ResumeSection(
                title="EXPERIENCE",
                entries=[
                    ResumeEntry(
                        heading="Intern | Acme",
                        dates="2025",
                        bullets=["Built APIs", "Wrote tests"],
                    )
                ],
            )
        ],
    )


def make_model_mock(*responses: str):
    client = MagicMock()
    side_effects = []
    for text in responses:
        response = MagicMock()
        response.choices[0].message.content = text
        side_effects.append(response)
    client.chat.completions.create = AsyncMock(side_effect=side_effects)
    return client


def test_apply_edits_rewrites_targeted_bullet_only():
    doc = make_doc()
    edits = ResumeEdits(
        bullet_edits=[
            BulletEdit(section=0, entry=0, bullet=0, new_text="Built FastAPI services")
        ]
    )

    result = apply_edits(doc, edits)

    assert result.sections[0].entries[0].bullets == [
        "Built FastAPI services", "Wrote tests",
    ]
    # The original doc is untouched (deep copy).
    assert doc.sections[0].entries[0].bullets[0] == "Built APIs"


def test_apply_edits_skips_out_of_range_indices():
    doc = make_doc()
    edits = ResumeEdits(
        bullet_edits=[
            BulletEdit(section=5, entry=0, bullet=0, new_text="nope"),
            BulletEdit(section=0, entry=0, bullet=99, new_text="nope"),
        ]
    )

    result = apply_edits(doc, edits)

    assert result == doc  # nothing changed, nothing crashed


def test_apply_edits_inserts_summary_section_when_missing():
    result = apply_edits(make_doc(), ResumeEdits(summary="Fresher backend engineer."))

    assert result.sections[0].title == "SUMMARY"
    assert result.sections[0].entries[0].heading == "Fresher backend engineer."


def test_apply_edits_replaces_existing_summary_section():
    doc = make_doc()
    doc.sections.insert(
        0,
        ResumeSection(title="SUMMARY", entries=[ResumeEntry(heading="Old summary")]),
    )

    result = apply_edits(doc, ResumeEdits(summary="New tailored summary"))

    assert result.sections[0].entries[0].heading == "New tailored summary"
    assert len(result.sections) == len(doc.sections)


@pytest.mark.asyncio
async def test_tailor_applies_valid_model_edits():
    edits_json = json.dumps(
        {
            "summary": "Backend-focused fresher.",
            "bullet_edits": [
                {"section": 0, "entry": 0, "bullet": 0,
                 "new_text": "Built FastAPI services in Python"}
            ],
        }
    )
    # Model output wrapped in markdown fences must still parse.
    client = make_model_mock(f"```json\n{edits_json}\n```")

    with patch("app.services.rewriter.get_groq_client", return_value=client):
        result, ok = await tailor_resume(make_doc(), make_test_job())

    assert ok is True
    assert result.sections[0].title == "SUMMARY"
    assert (
        result.sections[1].entries[0].bullets[0]
        == "Built FastAPI services in Python"
    )


@pytest.mark.asyncio
async def test_tailor_fails_open_to_original_after_two_bad_outputs():
    client = make_model_mock("not json at all", "still { not json")

    with patch("app.services.rewriter.get_groq_client", return_value=client):
        doc = make_doc()
        result, ok = await tailor_resume(doc, make_test_job())

    assert ok is False
    assert result == doc  # original, untouched
    assert client.chat.completions.create.await_count == 2
