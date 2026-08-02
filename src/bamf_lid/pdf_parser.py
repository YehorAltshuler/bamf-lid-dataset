from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import fitz
from PIL import Image

from .models import ImageRef, PdfQuestion, Scope, STATE_CODES, STATE_HEADING_ALIASES, question_id
from .util import normalize_text, sha256_bytes, write_json

TASK_RE = re.compile(r"^(?:Aufgabe|Frage)\s*(\d{1,3})\s*$", re.IGNORECASE)
ANSWER_PREFIX_RE = re.compile(r"^[□☐\uf0a3■▪●○oO]?\s*([a-dA-D])[\).:]?\s+(.*)$", re.DOTALL)
CHECKBOX_GLYPHS = {"□", "☐", "\uf0a3"}
BOX_PREFIX_RE = re.compile(r"^[□☐\uf0a3]\s*(.*)$", re.DOTALL)

# The state sections in the official catalogue are emitted after the 300 general
# questions, in the same alphabetical order as STATE_CODES, ten questions each.
STATE_SECTION_CODES = tuple(STATE_CODES.values())


@dataclass(frozen=True)
class TextLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float


@dataclass(frozen=True)
class ImageBlock:
    bbox: fitz.Rect
    data: bytes
    extension: str
    width: int
    height: int


def _page_lines(page: fitz.Page) -> list[TextLine]:
    data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
    result: list[TextLine] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = normalize_text("".join(span.get("text", "") for span in spans))
            if not text:
                continue
            bbox = fitz.Rect(line["bbox"])
            size = max(float(span.get("size", 0)) for span in spans)
            result.append(TextLine(text, bbox.x0, bbox.y0, bbox.x1, bbox.y1, size))
    # Checkbox glyphs and their answer text are separate PDF text lines. Their
    # y coordinates differ by a small fraction of a point, so a strict y sort can
    # place the checkbox *after* its answer. Group nearby baselines into one row
    # and sort that row from left to right.
    result.sort(key=lambda line: (line.y0, line.x0))
    rows: list[list[TextLine]] = []
    for line in result:
        if not rows or abs(line.y0 - rows[-1][0].y0) > 2.5:
            rows.append([line])
        else:
            rows[-1].append(line)
    ordered: list[TextLine] = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda line: line.x0))
    return ordered


def _page_images(page: fitz.Page) -> list[ImageBlock]:
    data = page.get_text("dict")
    result: list[ImageBlock] = []
    for block in data.get("blocks", []):
        if block.get("type") != 1 or not block.get("image"):
            continue
        bbox = fitz.Rect(block["bbox"])
        raw = bytes(block["image"])
        extension = str(block.get("ext") or "png").lower()

        # PyMuPDF exposes a PDF image's soft mask separately in ``block["mask"]``.
        # Writing only ``block["image"]`` discards transparency: transparent pixels
        # then appear as solid black, and a black silhouette can turn into a fully
        # black rectangle. Recombine the base image and its mask before saving.
        mask_raw = block.get("mask")
        try:
            with Image.open(io.BytesIO(raw)) as base_image:
                if mask_raw:
                    with Image.open(io.BytesIO(bytes(mask_raw))) as mask_image:
                        rgba = base_image.convert("RGBA")
                        alpha = mask_image.convert("L")
                        if alpha.size != rgba.size:
                            alpha = alpha.resize(rgba.size, Image.Resampling.LANCZOS)
                        rgba.putalpha(alpha)
                        buffer = io.BytesIO()
                        rgba.save(buffer, format="PNG")
                        raw = buffer.getvalue()
                        extension = "png"
                        width, height = rgba.size
                else:
                    width, height = base_image.size
        except Exception:
            width = int(block.get("width") or 0)
            height = int(block.get("height") or 0)
        # Ignore tiny decorative assets.
        if bbox.width < 40 or bbox.height < 25 or width < 40 or height < 25:
            continue
        result.append(ImageBlock(bbox, raw, extension, width, height))
    return result


def _detect_state(lines: list[TextLine], current: str | None) -> str | None:
    for line in lines:
        lower = line.text.casefold().replace("–", "-")
        for heading, code in STATE_HEADING_ALIASES.items():
            if heading in lower and ("bundesland" in lower or "fragen" in lower or len(lower) < 45):
                return code
    return current


def _group_question_segments(doc: fitz.Document) -> list[tuple[int, int, str | None, list[TextLine], list[ImageBlock]]]:
    segments: list[tuple[int, int, str | None, list[TextLine], list[ImageBlock]]] = []
    state_code: str | None = None
    for page_index in range(doc.page_count):
        page = doc[page_index]
        lines = _page_lines(page)
        state_code = _detect_state(lines, state_code)
        markers = [(i, int(match.group(1))) for i, line in enumerate(lines) if (match := TASK_RE.match(line.text))]
        if not markers:
            continue
        images = _page_images(page)
        for marker_index, (line_index, number) in enumerate(markers):
            y_start = lines[line_index].y0
            next_line_index = markers[marker_index + 1][0] if marker_index + 1 < len(markers) else len(lines)
            y_end = lines[next_line_index].y0 if next_line_index < len(lines) else page.rect.height
            segment_lines = [line for line in lines[line_index + 1:next_line_index] if line.y0 < y_end]
            segment_images = [image for image in images if image.bbox.y0 >= y_start - 2 and image.bbox.y1 <= y_end + 2]
            effective_state = state_code if state_code is not None else None
            segments.append((page_index + 1, number, effective_state, segment_lines, segment_images))
    return segments


def _is_noise_line(text: str) -> bool:
    return bool(
        re.search(r"Gesamtfragenkatalog|Stand:|Seite\s+\d+", text, re.I)
        or re.fullmatch(r"\d{1,3}\.", text)
    )


def _parse_text(lines: list[TextLine]) -> tuple[str, dict[str, str]]:
    usable = [line for line in lines if not _is_noise_line(line.text)]
    boxes = sorted(
        (line for line in usable if line.text.strip() in CHECKBOX_GLYPHS),
        key=lambda line: (line.y0, line.x0),
    )

    # The accessible BAMF PDF stores each checkbox and answer as separate text
    # objects. Parse them geometrically instead of trusting extraction order.
    if len(boxes) >= 4:
        boxes = boxes[:4]
        answers: dict[str, str] = {}
        claimed_ids: set[int] = {id(box) for box in boxes}

        for index, box in enumerate(boxes):
            next_y = boxes[index + 1].y0 if index + 1 < 4 else float("inf")
            parts: list[TextLine] = []
            for line in usable:
                if id(line) in claimed_ids:
                    continue
                # Include text on the checkbox baseline even when the PDF gives
                # the answer a slightly smaller y coordinate. Continuation lines
                # belong to this answer until the next checkbox row.
                if line.y0 < box.y0 - 3.0 or line.y0 >= next_y - 3.0:
                    continue
                if abs(line.y0 - box.y0) <= 3.0 and line.x1 <= box.x0:
                    continue
                parts.append(line)

            parts.sort(key=lambda line: (line.y0, line.x0))
            answer = normalize_text(" ".join(line.text for line in parts))
            if answer:
                answers["abcd"[index]] = answer
                claimed_ids.update(id(line) for line in parts)

        first_box = boxes[0]
        question_lines = [
            line
            for line in usable
            if id(line) not in claimed_ids
            and line.y0 < first_box.y0 - 3.0
            and not re.fullmatch(r"Bild\s*[1-4]", line.text, re.I)
        ]
        question_lines.sort(key=lambda line: (line.y0, line.x0))
        question = normalize_text(" ".join(line.text for line in question_lines))

        if question and len(answers) == 4 and all(answers.values()):
            return question, answers

    # Some image-choice questions in the BAMF PDF have the four option labels
    # positioned so close together that PDF text extraction interleaves labels
    # and checkbox glyphs. In those cases the labels themselves are still
    # unambiguous (Bild 1..4 or 1..4), so reconstruct the choices from that
    # repeated canonical set instead of relying on line order.
    texts = [line.text for line in usable]
    box_count = sum(text.strip() in CHECKBOX_GLYPHS for text in texts)
    normalized_tokens = [normalize_text(text) for text in texts]

    def canonical_choice_fallback(labels: list[str]) -> tuple[str, dict[str, str]] | None:
        if box_count != 4:
            return None
        positions: list[int] = []
        for label in labels:
            try:
                positions.append(normalized_tokens.index(label))
            except ValueError:
                return None
        first_label = min(positions)
        question_parts = [
            text
            for text in normalized_tokens[:first_label]
            if text not in CHECKBOX_GLYPHS and not _is_noise_line(text)
        ]
        question = normalize_text(" ".join(question_parts))
        if not question:
            return None
        return question, {key: value for key, value in zip("abcd", labels, strict=True)}

    image_choice = canonical_choice_fallback(["Bild 1", "Bild 2", "Bild 3", "Bild 4"])
    if image_choice is not None:
        return image_choice

    numeric_choice = canonical_choice_fallback(["1", "2", "3", "4"])
    if numeric_choice is not None:
        return numeric_choice

    # Fallback for synthetic fixtures and any future PDF variant that combines
    # the checkbox with its answer in one text object.
    cleaned = [line.text for line in usable]
    answers: dict[str, str] = {}
    question_parts: list[str] = []
    current_key: str | None = None

    for text in cleaned:
        match = ANSWER_PREFIX_RE.match(text)
        if match:
            key = match.group(1).lower()
            current_key = key
            answers[key] = normalize_text(match.group(2))
            continue
        box_match = BOX_PREFIX_RE.match(text)
        if box_match and len(answers) < 4:
            key = "abcd"[len(answers)]
            current_key = key
            answers[key] = normalize_text(box_match.group(1))
            continue
        if current_key is not None:
            answers[current_key] = normalize_text(f"{answers[current_key]} {text}")
        elif not re.fullmatch(r"Bild\s*[1-4]", text, re.I):
            question_parts.append(text)

    question = normalize_text(" ".join(question_parts))
    if not question or len(answers) != 4 or any(not value for value in answers.values()):
        preview = " | ".join(line.text for line in lines[:20])
        raise ValueError(f"Could not parse question/answers. Segment: {preview}")
    return question, answers


def _save_images(images: Iterable[ImageBlock], output_dir: Path, qid: str) -> list[ImageRef]:
    result: list[ImageRef] = []
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for index, image in enumerate(images, start=1):
        ext = image.extension if image.extension in {"png", "jpg", "jpeg", "webp"} else "png"
        suffix = "" if index == 1 else f"-{index}"
        filename = f"{qid}{suffix}.{ext}"
        path = image_dir / filename
        path.write_bytes(image.data)
        mime = "image/jpeg" if ext in {"jpg", "jpeg"} else f"image/{ext}"
        result.append(ImageRef(path=f"images/{filename}", sha256=sha256_bytes(image.data), width=image.width, height=image.height, mime_type=mime))
    return result


def parse_pdf(pdf_path: Path, output_dir: Path, diagnostics_dir: Path | None = None) -> list[PdfQuestion]:
    doc = fitz.open(pdf_path)
    segments = _group_question_segments(doc)
    questions: list[PdfQuestion] = []
    errors: list[dict[str, Any]] = []
    for segment_index, (page, raw_number, _detected_state, lines, images) in enumerate(segments):
        # Do not infer a state from arbitrary question text. General questions
        # mention state names (for example Nordrhein-Westfalen), which previously
        # switched the parser into state mode on question 23. The official PDF has
        # a stable structure: 300 general questions followed by 16 blocks of ten
        # state questions in alphabetical order.
        if segment_index < 300:
            expected_number = segment_index + 1
            number = raw_number
            state_code = None
            scope = Scope.GENERAL
            if raw_number != expected_number:
                errors.append({
                    "page": page,
                    "number": raw_number,
                    "error": f"Expected general question {expected_number}, found {raw_number}",
                })
                continue
        else:
            state_offset = segment_index - 300
            state_index, question_offset = divmod(state_offset, 10)
            if state_index >= len(STATE_SECTION_CODES):
                errors.append({"page": page, "number": raw_number, "error": "Unexpected extra state question"})
                continue
            expected_number = question_offset + 1
            if raw_number != expected_number:
                errors.append({
                    "page": page,
                    "number": raw_number,
                    "error": f"Expected state question {expected_number}, found {raw_number}",
                })
                continue
            number = raw_number
            state_code = STATE_SECTION_CODES[state_index]
            scope = Scope.STATE
        qid = question_id(number, state_code)
        try:
            question_text, answers = _parse_text(lines)
            refs = _save_images(images, output_dir, qid)
            questions.append(PdfQuestion(
                id=qid,
                officialNumber=number,
                scope=scope,
                stateCode=state_code,
                question=question_text,
                answers=answers,
                images=refs,
                sourcePage=page,
            ))
        except Exception as exc:
            errors.append({"page": page, "id": qid, "number": raw_number, "error": str(exc), "lines": [line.text for line in lines]})

    if diagnostics_dir is not None:
        write_json(diagnostics_dir / "pdf-parse-errors.json", errors)
        write_json(diagnostics_dir / "pdf-segments.json", [{"page": p, "number": n, "state": s, "lines": [line.text for line in ls], "images": len(img)} for p, n, s, ls, img in segments])
    if errors:
        raise RuntimeError(f"PDF parsing failed for {len(errors)} question segments. See diagnostics/pdf-parse-errors.json")
    return questions
