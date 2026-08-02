# BAMF Leben in Deutschland Dataset

[![Update dataset](https://github.com/YehorAltshuler/bamf-lid-dataset/actions/workflows/update-dataset.yml/badge.svg)](https://github.com/YehorAltshuler/bamf-lid-dataset/actions/workflows/update-dataset.yml)
[![Deploy GitHub Pages](https://github.com/YehorAltshuler/bamf-lid-dataset/actions/workflows/pages.yml/badge.svg)](https://github.com/YehorAltshuler/bamf-lid-dataset/actions/workflows/pages.yml)

A machine-readable, validated dataset for the German **Leben in Deutschland** question catalogue.

The project builds the dataset exclusively from two official BAMF sources:

- the official `Gesamtfragenkatalog` PDF for question text, answer choices and graphics;
- the BAMF Online-Testcenter for the correct answer and BAMF internal answer ID.

No OCR, AI-generated content or third-party answer keys are used.

## Published dataset

The current dataset is available through GitHub Pages:

| Resource | URL |
|---|---|
| Manifest | <https://yehoraltshuler.github.io/bamf-lid-dataset/manifest.json> |
| Questions | <https://yehoraltshuler.github.io/bamf-lid-dataset/questions.json> |
| Human-readable review | <https://yehoraltshuler.github.io/bamf-lid-dataset/review.html> |
| Images | `https://yehoraltshuler.github.io/bamf-lid-dataset/images/<filename>` |

The published dataset contains:

- **460 questions** in total;
- **300 general questions**;
- **160 state-specific questions** — 10 for each of the 16 federal states;
- stable IDs for every question;
- four answer choices and one validated solution per question;
- extracted graphics with dimensions, MIME type and SHA-256 hash.

## Quick start

### JavaScript

```js
const baseUrl =
  "https://yehoraltshuler.github.io/bamf-lid-dataset";

const manifest = await fetch(`${baseUrl}/manifest.json`)
  .then((response) => {
    if (!response.ok) {
      throw new Error(`Manifest request failed: ${response.status}`);
    }

    return response.json();
  });

const dataset = await fetch(
  `${baseUrl}/${manifest.questions.url}`,
).then((response) => {
  if (!response.ok) {
    throw new Error(`Dataset request failed: ${response.status}`);
  }

  return response.json();
});

console.log(dataset.questions.length); // 460
```

### Python

```python
import requests

base_url = (
    "https://yehoraltshuler.github.io/"
    "bamf-lid-dataset"
)

manifest = requests.get(
    f"{base_url}/manifest.json",
    timeout=30,
).json()

dataset = requests.get(
    f"{base_url}/{manifest['questions']['url']}",
    timeout=30,
).json()

print(len(dataset["questions"]))  # 460
```

## Dataset schema

Top-level structure of `questions.json`:

```json
{
  "schemaVersion": 1,
  "datasetVersion": "2026-08-02.123456",
  "generatedAt": "2026-08-02T12:34:56Z",
  "source": {
    "pdfUrl": "https://...",
    "pdfSha256": "...",
    "onlineTestcenterUrl": "https://..."
  },
  "questions": []
}
```

Question object:

```json
{
  "id": "general-001",
  "officialNumber": 1,
  "scope": "general",
  "stateCode": null,
  "question": "Question text",
  "answers": {
    "a": "First answer",
    "b": "Second answer",
    "c": "Third answer",
    "d": "Fourth answer"
  },
  "images": [],
  "sourcePage": 5,
  "solution": "b",
  "bamfInternalId": "12345"
}
```

Image reference:

```json
{
  "path": "images/general-021-1.png",
  "sha256": "...",
  "width": 640,
  "height": 360,
  "mimeType": "image/png"
}
```

Image URLs are relative to the published dataset root:

```text
https://yehoraltshuler.github.io/bamf-lid-dataset/
  + images/general-021-1.png
```

## Stable question IDs

General questions use the official catalogue number:

```text
general-001
general-002
...
general-300
```

State-specific questions use the two-letter state code and a local number:

```text
BW-01
BY-01
BE-01
...
TH-10
```

Supported state codes:

| Code | State |
|---|---|
| `BW` | Baden-Württemberg |
| `BY` | Bayern |
| `BE` | Berlin |
| `BB` | Brandenburg |
| `HB` | Bremen |
| `HH` | Hamburg |
| `HE` | Hessen |
| `MV` | Mecklenburg-Vorpommern |
| `NI` | Niedersachsen |
| `NW` | Nordrhein-Westfalen |
| `RP` | Rheinland-Pfalz |
| `SL` | Saarland |
| `SN` | Sachsen |
| `ST` | Sachsen-Anhalt |
| `SH` | Schleswig-Holstein |
| `TH` | Thüringen |

## Manifest

`manifest.json` is intended as the entry point for clients. It contains:

- schema and dataset versions;
- generation and last-check timestamps;
- the `questions.json` URL, SHA-256 and question count;
- the image base URL and image count;
- official source URLs and the source PDF hash.

A client can fetch the manifest first and download the full dataset only when its version or hash changes.

## Validation guarantees

Publication succeeds only when all required checks pass:

- exactly 460 unique questions;
- exactly 300 general questions;
- exactly 10 questions for each of 16 states;
- exactly four answer choices per question;
- one solution from `a`, `b`, `c` or `d`;
- a matching Online-Testcenter solution for every PDF question;
- every referenced image exists;
- every image hash and metadata entry is valid;
- no missing or unreferenced published image files.

An invalid build fails before deployment, so the previously published dataset remains available.

## Local development

### Requirements

- Python 3.11 or newer;
- Chromium installed through Playwright.

### Installation

```bash
git clone https://github.com/YehorAltshuler/bamf-lid-dataset.git
cd bamf-lid-dataset

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e ".[dev]"
playwright install chromium
```

### Run tests

```bash
pytest
```

### Build the complete dataset

```bash
bamf-lid all
```

Build stages can also be run separately:

```bash
bamf-lid download-pdf
bamf-lid parse-pdf
bamf-lid scrape-solutions
bamf-lid build
```

Generated files:

```text
data/published/
├── manifest.json
├── questions.json
├── review.html
└── images/
```

Open the review page on macOS:

```bash
open data/published/review.html
```

## Automatic updates

GitHub Actions rebuilds and validates the dataset weekly.

A successful update:

1. downloads the current official BAMF PDF;
2. parses questions, answers and graphics;
3. reads official solutions from the Online-Testcenter;
4. validates the complete dataset;
5. updates `lastCheckedAt`;
6. commits changed published files;
7. deploys `data/published` to GitHub Pages.

A failed update does not replace the currently published dataset. Scraper diagnostics are uploaded as a workflow artifact for investigation.

## Project structure

```text
.
├── .github/workflows/
│   ├── pages.yml
│   └── update-dataset.yml
├── data/
│   └── published/
├── src/bamf_lid/
├── tests/
├── pyproject.toml
└── README.md
```

## Disclaimer

This is an independent technical project and not an official BAMF publication.

The dataset is generated from official publicly accessible BAMF sources. Applications using it should retain source attribution, check the manifest for updates and review the applicable terms before redistributing source material.
