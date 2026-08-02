from __future__ import annotations

from pathlib import Path

import httpx

DEFAULT_PDF_URL = (
    "https://www.bamf.de/SharedDocs/Anlagen/DE/Integration/Einbuergerung/"
    "gesamtfragenkatalog-lebenindeutschland.pdf?__blob=publicationFile"
)


def download_pdf(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 bamf-lid-dataset/0.1"}
    with httpx.Client(follow_redirects=True, timeout=120, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not response.content.startswith(b"%PDF"):
            raise RuntimeError(f"BAMF response is not a PDF: {content_type}")
        destination.write_bytes(response.content)
    return destination
