from __future__ import annotations

import re
from pathlib import Path

from playwright.async_api import Browser, Page, async_playwright

from .models import STATE_CODES, SolutionRecord, question_id
from .util import normalize_text, write_json

DEFAULT_START_URL = "https://oet.bamf.de/ords/oetut/f?p=534:1:0"


async def _open_catalog(page: Page, start_url: str, state_name: str) -> None:
    await page.goto(start_url, wait_until="domcontentloaded")
    select = page.locator("select").filter(has=page.locator("option")).first
    await select.select_option(label=state_name)
    start = page.locator('input[type="submit"], button[type="submit"], input[type="button"]').filter(has_text=re.compile("start|weiter|fragen", re.I)).first
    if await start.count() == 0:
        start = page.locator('input[type="submit"], button[type="submit"]').first
    await start.click()
    await page.wait_for_selector('select#P30_ROWNUM, input[name="f20"]', timeout=30_000)


async def _select_question(page: Page, number: int) -> None:
    select = page.locator("select#P30_ROWNUM")
    if number == 1:
        return
    await select.select_option(label=str(number))
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_selector('input[name="f20"]', timeout=20_000)


async def _read_solution(page: Page, qid: str) -> SolutionRecord:
    radios = page.locator('input[name="f20"]')
    if await radios.count() != 4:
        raise RuntimeError(f"{qid}: expected 4 answer radios")

    correct = page.locator('input[name="f20"]#FARBE')
    if await correct.count() != 1:
        correct = page.locator('td[name="FARBE"] input[name="f20"]')
    if await correct.count() != 1:
        raise RuntimeError(f"{qid}: BAMF correct-answer marker #FARBE was not found")

    answer_cells = page.locator('td[headers="ANTWORT"]')
    if await answer_cells.count() != 4:
        raise RuntimeError(f"{qid}: expected 4 answer cells")
    answers = {
        key: normalize_text(await answer_cells.nth(index).inner_text())
        for index, key in enumerate("abcd")
    }

    question_image = page.locator("#P30_AUFGABENSTELLUNG_BILD img")
    question_src = await question_image.get_attribute("src") if await question_image.count() else None
    # The Online-Testcenter renders the question itself as an image. The source
    # URL is retained as a stable cross-check token; answer text is compared
    # directly against the PDF during build.
    question_token = normalize_text(question_src or qid)

    correct_value = await correct.get_attribute("value")
    values = [await radios.nth(i).get_attribute("value") for i in range(4)]
    index = values.index(correct_value)
    return SolutionRecord(
        id=qid,
        solution="abcd"[index],
        bamfInternalId=correct_value,
        question=question_token,
        answers=answers,
    )


async def scrape_solutions(output_path: Path, start_url: str = DEFAULT_START_URL, headless: bool = True) -> list[SolutionRecord]:
    records: list[SolutionRecord] = []
    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(headless=headless)
        try:
            for state_index, (state_name, state_code) in enumerate(STATE_CODES.items()):
                page = await browser.new_page()
                try:
                    print(f"Opening {state_name}...")
                    await _open_catalog(page, start_url, state_name)
                    start = 1 if state_index == 0 else 301
                    for catalog_number in range(start, 311):
                        await _select_question(page, catalog_number)
                        qid = question_id(catalog_number, None) if catalog_number <= 300 else question_id(catalog_number - 300, state_code)
                        records.append(await _read_solution(page, qid))
                        print(f"  {qid}")
                except Exception:
                    diagnostics = output_path.parent / "diagnostics" / state_code
                    diagnostics.mkdir(parents=True, exist_ok=True)
                    (diagnostics / "page.html").write_text(await page.content(), encoding="utf-8")
                    await page.screenshot(path=diagnostics / "page.png", full_page=True)
                    raise
                finally:
                    await page.close()
        finally:
            await browser.close()
    write_json(output_path, [record.model_dump(by_alias=True) for record in records])
    return records
