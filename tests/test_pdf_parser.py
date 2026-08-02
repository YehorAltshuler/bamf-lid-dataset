from pathlib import Path

import fitz

from bamf_lid.pdf_parser import TextLine, _parse_text, parse_pdf


def test_parses_accessible_question_pdf(tmp_path: Path):
    pdf_path = tmp_path / "fixture.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 70
    for number in (1, 2):
        page.insert_text((60, y), f"Aufgabe {number}", fontsize=12)
        page.insert_text((60, y + 25), f"Testfrage Nummer {number}?", fontsize=11)
        for index, text in enumerate(("Antwort eins", "Antwort zwei", "Antwort drei", "Antwort vier")):
            page.insert_text((75, y + 50 + index * 20), f"{chr(97 + index)}) {text}", fontsize=10)
        y += 170
    doc.save(pdf_path)
    doc.close()

    output = tmp_path / "out"
    questions = parse_pdf(pdf_path, output)
    assert len(questions) == 2
    assert questions[0].id == "general-001"
    assert questions[0].answers["d"] == "Antwort vier"


def test_private_use_checkbox_glyph_is_supported() -> None:
    lines = [
        TextLine("Eine Frage?", 50, 10, 200, 20, 10),
        TextLine("\uf0a3", 50, 30, 60, 40, 10),
        TextLine("Antwort A", 70, 30, 200, 40, 10),
        TextLine("\uf0a3", 50, 50, 60, 60, 10),
        TextLine("Antwort B", 70, 50, 200, 60, 10),
        TextLine("\uf0a3", 50, 70, 60, 80, 10),
        TextLine("Antwort C", 70, 70, 200, 80, 10),
        TextLine("\uf0a3", 50, 90, 60, 100, 10),
        TextLine("Antwort D", 70, 90, 200, 100, 10),
    ]
    question, answers = _parse_text(lines)
    assert question == "Eine Frage?"
    assert answers == {"a": "Antwort A", "b": "Antwort B", "c": "Antwort C", "d": "Antwort D"}


def test_interleaved_image_choice_labels_are_reconstructed() -> None:
    lines = [
        TextLine("Welches Wappen gehört zum Freistaat Bayern?", 50, 10, 300, 20, 10),
        TextLine("Bild 1", 60, 30, 100, 40, 10),
        TextLine("Bild 2", 160, 30, 200, 40, 10),
        TextLine("Bild 3", 260, 30, 300, 40, 10),
        TextLine("Bild 4", 360, 30, 400, 40, 10),
        TextLine("\uf0a3", 50, 60, 60, 70, 10),
        TextLine("Bild 1", 70, 60, 110, 70, 10),
        TextLine("\uf0a3", 50, 80, 60, 90, 10),
        TextLine("Bild 2", 70, 80, 110, 90, 10),
        TextLine("Bild 3", 70, 100, 110, 110, 10),
        TextLine("\uf0a3", 50, 100, 60, 110, 10),
        TextLine("\uf0a3", 50, 120, 60, 130, 10),
        TextLine("Bild 4", 70, 120, 110, 130, 10),
    ]
    question, answers = _parse_text(lines)
    assert question == "Welches Wappen gehört zum Freistaat Bayern?"
    assert answers == {"a": "Bild 1", "b": "Bild 2", "c": "Bild 3", "d": "Bild 4"}


def test_interleaved_numeric_map_choices_are_reconstructed() -> None:
    lines = [
        TextLine("Welches Bundesland ist Berlin?", 50, 10, 250, 20, 10),
        TextLine("\uf0a3", 50, 40, 60, 50, 10),
        TextLine("1", 70, 40, 75, 50, 10),
        TextLine("\uf0a3", 50, 60, 60, 70, 10),
        TextLine("2", 70, 60, 75, 70, 10),
        TextLine("3", 70, 80, 75, 90, 10),
        TextLine("\uf0a3", 50, 80, 60, 90, 10),
        TextLine("\uf0a3", 50, 100, 60, 110, 10),
        TextLine("4", 70, 100, 75, 110, 10),
    ]
    question, answers = _parse_text(lines)
    assert question == "Welches Bundesland ist Berlin?"
    assert answers == {"a": "1", "b": "2", "c": "3", "d": "4"}


def test_pdf_soft_mask_is_recombined_in_extracted_image(tmp_path: Path) -> None:
    """Transparent PDF images must not become black rectangles."""
    import io

    from PIL import Image, ImageDraw

    pdf_path = tmp_path / "transparent-image.pdf"
    source = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(source)
    draw.ellipse((15, 15, 105, 105), fill=(0, 0, 0, 255))
    image_bytes = io.BytesIO()
    source.save(image_bytes, format="PNG")

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 70), "Aufgabe 1", fontsize=12)
    page.insert_text((60, 95), "Welche Form ist abgebildet?", fontsize=11)
    page.insert_image(fitz.Rect(250, 90, 370, 210), stream=image_bytes.getvalue())
    for index, text in enumerate(("Antwort eins", "Antwort zwei", "Antwort drei", "Antwort vier")):
        page.insert_text((75, 240 + index * 20), f"{chr(97 + index)}) {text}", fontsize=10)
    doc.save(pdf_path)
    doc.close()

    output = tmp_path / "out"
    questions = parse_pdf(pdf_path, output)
    assert len(questions) == 1
    assert len(questions[0].images) == 1

    extracted_path = output / questions[0].images[0].path
    with Image.open(extracted_path) as extracted:
        assert extracted.mode == "RGBA"
        alpha = extracted.getchannel("A")
        assert alpha.getextrema() == (0, 255)
        # A corner is transparent, while the centre remains visible and black.
        assert extracted.getpixel((0, 0))[3] == 0
        assert extracted.getpixel((60, 60)) == (0, 0, 0, 255)
