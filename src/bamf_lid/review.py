from __future__ import annotations

import html
from pathlib import Path

from .models import Dataset


def write_review_html(dataset: Dataset, output_path: Path) -> Path:
    parts = ["""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAMF Dataset Review</title><style>
body{max-width:960px;margin:40px auto;padding:0 20px;font-family:system-ui,sans-serif;line-height:1.45}
.question{border-bottom:1px solid #ccc;padding:24px 0}.meta{color:#666;font-size:.9rem}.correct{font-weight:700;background:#dff5df}
img{max-width:230px;max-height:190px;object-fit:contain;margin:8px;border:1px solid #ddd}li{margin:8px 0;padding:4px}
</style></head><body><h1>BAMF Dataset Review</h1>"""]
    for question in dataset.questions:
        parts.append('<section class="question">')
        parts.append(f'<h2>{html.escape(question.id)}</h2>')
        parts.append(f'<div class="meta">PDF page {question.source_page}</div>')
        parts.append(f'<p>{html.escape(question.question)}</p>')
        for image in question.images:
            parts.append(f'<img src="{html.escape(image.path)}" alt="{html.escape(question.id)}">')
        parts.append('<ol type="a">')
        for key in "abcd":
            css = "correct" if key == question.solution else ""
            parts.append(f'<li class="{css}">{html.escape(question.answers[key])}</li>')
        parts.append('</ol></section>')
    parts.append('</body></html>')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts), encoding="utf-8")
    return output_path
