from datetime import UTC, datetime
from pathlib import Path

from bamf_lid.models import Dataset, DatasetSource, Question, Scope
from bamf_lid.review import write_review_html


def test_review_marks_correct_answer(tmp_path: Path) -> None:
    question = Question(
        id="general-001",
        officialNumber=1,
        scope=Scope.GENERAL,
        stateCode=None,
        question="Eine Frage?",
        answers={"a": "A", "b": "B", "c": "C", "d": "D"},
        images=[],
        sourcePage=2,
        solution="c",
        bamfInternalId="42",
    )
    dataset = Dataset(
        datasetVersion="test",
        generatedAt=datetime.now(UTC),
        source=DatasetSource(pdfUrl="https://example.test/a.pdf", pdfSha256="0" * 64, onlineTestcenterUrl="https://example.test"),
        questions=[question],
    )
    output = write_review_html(dataset, tmp_path / "review.html")
    text = output.read_text(encoding="utf-8")
    assert 'class="correct">C</li>' in text
    assert "general-001" in text
