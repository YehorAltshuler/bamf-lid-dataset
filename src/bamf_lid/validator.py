from __future__ import annotations

from collections import Counter
from pathlib import Path

from .models import Dataset, Scope, STATE_CODES
from .util import sha256_file


def validate_dataset(dataset: Dataset, output_dir: Path | None = None) -> None:
    if len(dataset.questions) != 460:
        raise ValueError(f"Expected 460 questions, got {len(dataset.questions)}")
    ids = [question.id for question in dataset.questions]
    duplicates = [qid for qid, count in Counter(ids).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate question IDs: {duplicates}")

    general = [question for question in dataset.questions if question.scope == Scope.GENERAL]
    if len(general) != 300:
        raise ValueError(f"Expected 300 general questions, got {len(general)}")
    for number, question in enumerate(general, start=1):
        if question.id != f"general-{number:03d}" or question.official_number != number:
            raise ValueError(f"General question order mismatch at {number}: {question.id}")

    for code in STATE_CODES.values():
        state = [question for question in dataset.questions if question.state_code == code]
        if len(state) != 10:
            raise ValueError(f"Expected 10 questions for {code}, got {len(state)}")
        expected_ids = [f"{code}-{number:02d}" for number in range(1, 11)]
        if [question.id for question in state] != expected_ids:
            raise ValueError(f"Invalid order/IDs for {code}")

    image_paths: list[str] = []
    for question in dataset.questions:
        if set(question.answers) != {"a", "b", "c", "d"}:
            raise ValueError(f"{question.id}: invalid answer keys")
        if question.solution not in question.answers:
            raise ValueError(f"{question.id}: invalid solution")
        if not question.question.strip():
            raise ValueError(f"{question.id}: empty question")
        for image in question.images:
            image_paths.append(image.path)
            if output_dir is not None:
                path = output_dir / image.path
                if not path.exists():
                    raise ValueError(f"{question.id}: missing image {image.path}")
                if sha256_file(path) != image.sha256:
                    raise ValueError(f"{question.id}: image hash mismatch {image.path}")
    duplicate_images = [path for path, count in Counter(image_paths).items() if count > 1]
    if duplicate_images:
        raise ValueError(f"Duplicate image references: {duplicate_images[:10]}")

    if output_dir is not None:
        image_dir = output_dir / "images"
        existing = {
            str(path.relative_to(output_dir))
            for path in image_dir.iterdir()
            if path.is_file()
        } if image_dir.exists() else set()
        referenced = set(image_paths)
        missing = sorted(referenced - existing)
        extra = sorted(existing - referenced)
        if missing or extra:
            raise ValueError(f"Image set mismatch. Missing={missing[:10]}, extra={extra[:10]}")
