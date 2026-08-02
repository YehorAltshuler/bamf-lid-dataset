from html.parser import HTMLParser
from pathlib import Path


class RadioParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.radios = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name") == "f20":
            self.radios.append(attrs)


def test_official_html_marks_correct_answer():
    parser = RadioParser()
    parser.feed(Path("tests/fixtures/bamf_question_page.html").read_text(encoding="utf-8"))
    assert len(parser.radios) == 4
    assert [radio.get("id") for radio in parser.radios].index("FARBE") == 3
