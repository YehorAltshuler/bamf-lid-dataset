from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .models import Dataset, DatasetSource, PdfQuestion, Question, SolutionRecord
from .review import write_review_html
from .util import sha256_file, write_json
from .validator import validate_dataset


def load_pdf_questions(path: Path) -> list[PdfQuestion]:
    return [PdfQuestion.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def load_solutions(path: Path) -> list[SolutionRecord]:
    return [SolutionRecord.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def _publish_atomically(staged_output: Path, output_dir: Path) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    backup = output_dir.with_name(f"{output_dir.name}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    if output_dir.exists():
        output_dir.rename(backup)
    try:
        staged_output.rename(output_dir)
    except Exception:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        if backup.exists():
            backup.rename(output_dir)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def build_dataset(pdf_questions_path: Path, solutions_path: Path, pdf_path: Path, output_dir: Path, pdf_url: str, testcenter_url: str) -> Dataset:
    questions = load_pdf_questions(pdf_questions_path)
    solution_records = load_solutions(solutions_path)
    solutions = {record.id: record for record in solution_records}
    if len(solutions) != len(solution_records):
        raise RuntimeError("Duplicate solution IDs")

    question_ids = {question.id for question in questions}
    missing = sorted(question_ids - solutions.keys())
    extra = sorted(solutions.keys() - question_ids)
    if missing or extra:
        raise RuntimeError(f"Question/solution mismatch. Missing={missing[:10]}, extra={extra[:10]}")

    merged: list[Question] = []
    for question in questions:
        solution = solutions[question.id]
        merged.append(Question(
            **question.model_dump(by_alias=True),
            solution=solution.solution,
            bamfInternalId=solution.bamf_internal_id,
        ))

    now = datetime.now(UTC)
    dataset = Dataset(
        datasetVersion=now.strftime("%Y-%m-%d.%H%M%S"),
        generatedAt=now,
        source=DatasetSource(pdfUrl=pdf_url, pdfSha256=sha256_file(pdf_path), onlineTestcenterUrl=testcenter_url),
        questions=merged,
    )

    with tempfile.TemporaryDirectory(prefix="bamf-publish-", dir=output_dir.parent) as temp:
        staged_output = Path(temp) / output_dir.name
        staged_output.mkdir(parents=True)
        source_images = pdf_questions_path.parent / "images"
        if source_images.exists():
            shutil.copytree(source_images, staged_output / "images")

        validate_dataset(dataset, staged_output)
        write_json(staged_output / "questions.json", dataset)
        write_review_html(dataset, staged_output / "review.html")
        questions_hash = sha256_file(staged_output / "questions.json")
        image_count = sum(len(question.images) for question in dataset.questions)
        manifest = {
            "schemaVersion": 1,
            "datasetVersion": dataset.dataset_version,
            "generatedAt": dataset.generated_at.isoformat(),
            "questions": {
                "url": "questions.json",
                "sha256": questions_hash,
                "count": len(dataset.questions),
                "generalCount": sum(q.scope.value == "general" for q in dataset.questions),
                "stateCount": sum(q.scope.value == "state" for q in dataset.questions),
            },
            "imagesBaseUrl": "images/",
            "imageCount": image_count,
            "questionsWithImages": sum(bool(q.images) for q in dataset.questions),
            "source": dataset.source.model_dump(by_alias=True, mode="json"),
        }
        write_json(staged_output / "manifest.json", manifest)
        _publish_atomically(staged_output, output_dir)
    return dataset
