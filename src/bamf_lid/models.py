from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnswerKey = Literal["a", "b", "c", "d"]


class Scope(str, Enum):
    GENERAL = "general"
    STATE = "state"


class ImageRef(BaseModel):
    path: str
    sha256: str
    width: int
    height: int
    mime_type: str


class PdfQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    official_number: int = Field(alias="officialNumber")
    scope: Scope
    state_code: str | None = Field(default=None, alias="stateCode")
    question: str
    answers: dict[AnswerKey, str]
    images: list[ImageRef] = Field(default_factory=list)
    source_page: int = Field(alias="sourcePage")

    @field_validator("answers")
    @classmethod
    def four_answers(cls, value: dict[AnswerKey, str]) -> dict[AnswerKey, str]:
        if set(value) != {"a", "b", "c", "d"}:
            raise ValueError("answers must contain exactly a, b, c and d")
        if any(not text.strip() for text in value.values()):
            raise ValueError("answers must not be empty")
        return value


class SolutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    solution: AnswerKey
    bamf_internal_id: str | None = Field(default=None, alias="bamfInternalId")
    question: str
    answers: dict[AnswerKey, str]

    @field_validator("answers")
    @classmethod
    def four_answers(cls, value: dict[AnswerKey, str]) -> dict[AnswerKey, str]:
        if set(value) != {"a", "b", "c", "d"}:
            raise ValueError("answers must contain exactly a, b, c and d")
        if any(not text.strip() for text in value.values()):
            raise ValueError("answers must not be empty")
        return value


class Question(PdfQuestion):
    solution: AnswerKey
    bamf_internal_id: str | None = Field(default=None, alias="bamfInternalId")


class DatasetSource(BaseModel):
    pdf_url: str = Field(alias="pdfUrl")
    pdf_sha256: str = Field(alias="pdfSha256")
    online_testcenter_url: str = Field(alias="onlineTestcenterUrl")


class Dataset(BaseModel):
    schema_version: int = Field(default=1, alias="schemaVersion")
    dataset_version: str = Field(alias="datasetVersion")
    generated_at: datetime = Field(alias="generatedAt")
    source: DatasetSource
    questions: list[Question]


STATE_CODES: dict[str, str] = {
    "Baden-Württemberg": "BW",
    "Bayern": "BY",
    "Berlin": "BE",
    "Brandenburg": "BB",
    "Bremen": "HB",
    "Hamburg": "HH",
    "Hessen": "HE",
    "Mecklenburg-Vorpommern": "MV",
    "Niedersachsen": "NI",
    "Nordrhein-Westfalen": "NW",
    "Rheinland-Pfalz": "RP",
    "Saarland": "SL",
    "Sachsen": "SN",
    "Sachsen-Anhalt": "ST",
    "Schleswig-Holstein": "SH",
    "Thüringen": "TH",
}

STATE_HEADING_ALIASES: dict[str, str] = {
    "baden-württemberg": "BW", "baden württemberg": "BW",
    "bayern": "BY", "berlin": "BE", "brandenburg": "BB",
    "bremen": "HB", "hamburg": "HH", "hessen": "HE",
    "mecklenburg-vorpommern": "MV", "mecklenburg vorpommern": "MV",
    "niedersachsen": "NI", "nordrhein-westfalen": "NW",
    "nordrhein westfalen": "NW", "rheinland-pfalz": "RP",
    "rheinland pfalz": "RP", "saarland": "SL", "sachsen": "SN",
    "sachsen-anhalt": "ST", "sachsen anhalt": "ST",
    "schleswig-holstein": "SH", "schleswig holstein": "SH",
    "thüringen": "TH",
}


def question_id(number: int, state_code: str | None) -> str:
    if state_code is None:
        return f"general-{number:03d}"
    return f"{state_code}-{number:02d}"
