import json
from pathlib import Path

from bamf_lid.builder import build_dataset
from bamf_lid.models import PdfQuestion, Scope, SolutionRecord
from bamf_lid.util import write_json


def test_build_merges_solution_by_id_without_comparing_wording(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "images").mkdir()

    question = PdfQuestion(
        id="general-001",
        officialNumber=1,
        scope=Scope.GENERAL,
        stateCode=None,
        question="Eine Frage?",
        answers={
            "a": "Die Wählerin/der Wähler darf frei wählen.",
            "b": "Antwort B",
            "c": "Antwort C",
            "d": "Antwort D",
        },
        images=[],
        sourcePage=2,
    )
    solution = SolutionRecord(
        id="general-001",
        solution="a",
        bamfInternalId="123",
        question="official-image-token",
        answers={
            "a": "Der Wähler darf frei wählen.",
            "b": "Anderer Wortlaut B",
            "c": "Anderer Wortlaut C",
            "d": "Anderer Wortlaut D",
        },
    )

    write_json(staging / "pdf-questions.json", [question.model_dump(by_alias=True)])
    write_json(staging / "solutions.json", [solution.model_dump(by_alias=True)])
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"test-pdf")

    # The production validator expects the complete official dataset. For this
    # focused unit test, patch only that boundary and verify the merge itself.
    import bamf_lid.builder as builder
    original_validate = builder.validate_dataset
    builder.validate_dataset = lambda dataset, output: None
    try:
        dataset = build_dataset(
            staging / "pdf-questions.json",
            staging / "solutions.json",
            pdf,
            tmp_path / "published",
            "https://example.invalid/catalog.pdf",
            "https://example.invalid/testcenter",
        )
    finally:
        builder.validate_dataset = original_validate

    assert dataset.questions[0].solution == "a"
    assert dataset.questions[0].bamf_internal_id == "123"
    assert dataset.questions[0].answers["a"] == "Die Wählerin/der Wähler darf frei wählen."


def test_build_rejects_missing_solution_ids(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    question = PdfQuestion(
        id="general-001",
        officialNumber=1,
        scope=Scope.GENERAL,
        stateCode=None,
        question="Eine Frage?",
        answers={"a": "A", "b": "B", "c": "C", "d": "D"},
        images=[],
        sourcePage=2,
    )
    write_json(staging / "pdf-questions.json", [question.model_dump(by_alias=True)])
    write_json(staging / "solutions.json", [])
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"test-pdf")

    try:
        build_dataset(
            staging / "pdf-questions.json",
            staging / "solutions.json",
            pdf,
            tmp_path / "published",
            "https://example.invalid/catalog.pdf",
            "https://example.invalid/testcenter",
        )
    except RuntimeError as error:
        assert "Question/solution mismatch" in str(error)
    else:
        raise AssertionError("Expected missing solution IDs to fail")
