from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from .builder import build_dataset
from .downloader import DEFAULT_PDF_URL, download_pdf
from .models import PdfQuestion
from .online_testcenter import DEFAULT_START_URL, scrape_solutions
from .pdf_parser import parse_pdf
from .util import write_json

app = typer.Typer(no_args_is_help=True)



@app.command("download-pdf")
def download_pdf_command(
    url: str = typer.Option(DEFAULT_PDF_URL),
    output: Path = typer.Option(Path("data/source/bamf-catalog.pdf")),
) -> None:
    download_pdf(url, output)
    typer.echo(f"Downloaded {output}")


@app.command("parse-pdf")
def parse_pdf_command(
    pdf: Path = typer.Option(Path("data/source/bamf-catalog.pdf")),
    output_dir: Path = typer.Option(Path("data/staging")),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    questions = parse_pdf(pdf, output_dir, output_dir / "diagnostics")
    write_json(output_dir / "pdf-questions.json", [question.model_dump(by_alias=True) for question in questions])
    typer.echo(f"Parsed {len(questions)} questions")


@app.command("scrape-solutions")
def scrape_solutions_command(
    output: Path = typer.Option(Path("data/staging/solutions.json")),
    start_url: str = typer.Option(DEFAULT_START_URL),
    headed: bool = typer.Option(False, help="Show Chromium window"),
) -> None:
    asyncio.run(scrape_solutions(output, start_url=start_url, headless=not headed))


@app.command("build")
def build_command(
    pdf_questions: Path = typer.Option(Path("data/staging/pdf-questions.json")),
    solutions: Path = typer.Option(Path("data/staging/solutions.json")),
    pdf: Path = typer.Option(Path("data/source/bamf-catalog.pdf")),
    output_dir: Path = typer.Option(Path("data/published")),
    pdf_url: str = typer.Option(DEFAULT_PDF_URL),
    testcenter_url: str = typer.Option(DEFAULT_START_URL),
) -> None:
    dataset = build_dataset(pdf_questions, solutions, pdf, output_dir, pdf_url, testcenter_url)
    typer.echo(f"Published {len(dataset.questions)} questions to {output_dir}")


@app.command("all")
def all_command(
    pdf_url: str = typer.Option(DEFAULT_PDF_URL),
    testcenter_url: str = typer.Option(DEFAULT_START_URL),
    headed: bool = typer.Option(False),
) -> None:
    pdf = Path("data/source/bamf-catalog.pdf")
    staging = Path("data/staging")
    published = Path("data/published")
    download_pdf(pdf_url, pdf)
    staging.mkdir(parents=True, exist_ok=True)
    questions = parse_pdf(pdf, staging, staging / "diagnostics")
    write_json(staging / "pdf-questions.json", [question.model_dump(by_alias=True) for question in questions])
    asyncio.run(scrape_solutions(staging / "solutions.json", start_url=testcenter_url, headless=not headed))
    dataset = build_dataset(staging / "pdf-questions.json", staging / "solutions.json", pdf, published, pdf_url, testcenter_url)
    typer.echo(f"Published {len(dataset.questions)} questions to {published}")


if __name__ == "__main__":
    app()
