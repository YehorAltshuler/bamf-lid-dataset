import pytest
from pydantic import ValidationError

from bamf_lid.models import SolutionRecord


def test_solution_record_requires_online_answer_texts() -> None:
    with pytest.raises(ValidationError):
        SolutionRecord(id="general-001", solution="a", bamfInternalId="1")


def test_solution_record_requires_four_answers() -> None:
    with pytest.raises(ValidationError):
        SolutionRecord(
            id="general-001",
            solution="a",
            bamfInternalId="1",
            question="token",
            answers={"a": "A"},
        )
