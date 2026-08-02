from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    Error as PlaywrightError,
    Page,
    async_playwright,
)

from .models import STATE_CODES, SolutionRecord, question_id
from .util import normalize_text, write_json


DEFAULT_START_URL = "https://oet.bamf.de/ords/oetut/f?p=534:1:0"

QUESTION_SELECT_SELECTOR = "select#P30_ROWNUM"
ANSWER_RADIOS_SELECTOR = 'input[name="f20"]'
ANSWER_CELLS_SELECTOR = 'td[headers="ANTWORT"]'

NAVIGATION_TIMEOUT_MS = 30_000
QUESTION_TIMEOUT_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.05


QUESTION_SNAPSHOT_SCRIPT = """
() => {
    const normalize = (value) =>
        String(value ?? "")
            .replace(/\\s+/g, " ")
            .trim();

    const questionSelect = document.querySelector(
        "select#P30_ROWNUM"
    );

    const selectedOption =
        questionSelect?.selectedOptions?.[0] ?? null;

    const selectedLabel = normalize(
        selectedOption?.textContent
    );

    const radios = Array.from(
        document.querySelectorAll(
            'input[name="f20"]'
        )
    );

    const answerCells = Array.from(
        document.querySelectorAll(
            'td[headers="ANTWORT"]'
        )
    );

    if (
        radios.length !== 4 ||
        answerCells.length !== 4
    ) {
        return null;
    }

    const correct =
        document.querySelector(
            'input[name="f20"]#FARBE'
        ) ??
        document.querySelector(
            'td[name="FARBE"] input[name="f20"]'
        );

    if (correct === null) {
        return null;
    }

    const radioValues = radios.map(
        (radio) => radio.getAttribute("value")
    );

    const correctValue = correct.getAttribute(
        "value"
    );

    if (
        correctValue === null ||
        radioValues.some(
            (value) => value === null
        ) ||
        !radioValues.includes(correctValue)
    ) {
        return null;
    }

    const answers = answerCells.map(
        (cell) => normalize(cell.innerText)
    );

    const questionImage = document.querySelector(
        "#P30_AUFGABENSTELLUNG_BILD img"
    );

    const questionSrc =
        questionImage?.getAttribute("src") ?? null;

    /*
     * The radio values are BAMF's internal IDs and change
     * between questions. They form a reliable DOM fingerprint.
     */
    const fingerprint = JSON.stringify({
        radioValues,
        correctValue,
        questionSrc,
    });

    return {
        selectedLabel,
        answers,
        radioValues,
        correctValue,
        questionSrc,
        fingerprint,
    };
}
"""


async def _get_question_snapshot(
    page: Page,
) -> dict[str, Any] | None:
    """
    Atomically read one internally consistent question state.

    If navigation is currently replacing the document, page.evaluate()
    can temporarily fail. That is treated as "not ready yet".
    """
    try:
        snapshot = await page.evaluate(
            QUESTION_SNAPSHOT_SCRIPT
        )
    except PlaywrightError:
        return None

    if not isinstance(snapshot, dict):
        return None

    return snapshot


async def _wait_for_question_snapshot(
    page: Page,
    qid: str,
    *,
    expected_number: int | None = None,
    previous_fingerprint: str | None = None,
) -> dict[str, Any]:
    """
    Poll until one complete and consistent question snapshot exists.

    For question changes, the snapshot must:
    - display the requested catalogue number;
    - have a different BAMF fingerprint from the previous question;
    - contain four radios, four answer cells and one valid marker.
    """
    loop = asyncio.get_running_loop()
    deadline = (
        loop.time() + QUESTION_TIMEOUT_SECONDS
    )

    last_snapshot: dict[str, Any] | None = None

    while loop.time() < deadline:
        snapshot = await _get_question_snapshot(
            page
        )

        if snapshot is not None:
            last_snapshot = snapshot

            selected_label = snapshot.get(
                "selectedLabel"
            )
            fingerprint = snapshot.get(
                "fingerprint"
            )

            number_matches = (
                expected_number is None
                or selected_label
                == str(expected_number)
            )

            fingerprint_changed = (
                previous_fingerprint is None
                or fingerprint
                != previous_fingerprint
            )

            if (
                number_matches
                and fingerprint_changed
            ):
                return snapshot

        await asyncio.sleep(
            POLL_INTERVAL_SECONDS
        )

    selected_label = (
        last_snapshot.get("selectedLabel")
        if last_snapshot
        else None
    )

    fingerprint = (
        last_snapshot.get("fingerprint")
        if last_snapshot
        else None
    )

    raise RuntimeError(
        f"{qid}: question did not become ready; "
        f"expected_number={expected_number!r}, "
        f"selected_label={selected_label!r}, "
        f"previous_fingerprint="
        f"{previous_fingerprint!r}, "
        f"current_fingerprint={fingerprint!r}"
    )


async def _open_catalog(
    page: Page,
    start_url: str,
    state_name: str,
) -> dict[str, Any]:
    await page.goto(
        start_url,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    state_select = (
        page.locator("select")
        .filter(
            has=page.locator("option")
        )
        .first
    )

    await state_select.wait_for(
        state="visible",
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    await state_select.select_option(
        label=state_name,
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    start_button = page.locator(
        'input[type="submit"], '
        'button[type="submit"], '
        'input[type="button"]'
    ).filter(
        has_text=re.compile(
            r"start|weiter|fragen",
            re.IGNORECASE,
        )
    ).first

    if await start_button.count() == 0:
        start_button = page.locator(
            'input[type="submit"], '
            'button[type="submit"]'
        ).first

    await start_button.wait_for(
        state="visible",
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    await start_button.click(
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    # The first question does not always have option "1"
    # selected in the catalogue dropdown, so no label check.
    return await _wait_for_question_snapshot(
        page,
        "catalog-start",
    )


async def _select_question(
    page: Page,
    number: int,
    qid: str,
    current_snapshot: dict[str, Any],
) -> dict[str, Any]:
    if number == 1:
        return current_snapshot

    previous_fingerprint = (
        current_snapshot.get("fingerprint")
    )

    if not isinstance(
        previous_fingerprint,
        str,
    ):
        raise RuntimeError(
            f"{qid}: previous question has "
            f"no valid fingerprint"
        )

    question_select = page.locator(
        QUESTION_SELECT_SELECTOR
    )

    await question_select.wait_for(
        state="visible",
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    await question_select.select_option(
        label=str(number),
        timeout=NAVIGATION_TIMEOUT_MS,
    )

    return await _wait_for_question_snapshot(
        page,
        qid,
        expected_number=number,
        previous_fingerprint=(
            previous_fingerprint
        ),
    )


def _build_solution_record(
    snapshot: dict[str, Any],
    qid: str,
) -> SolutionRecord:
    raw_answers = snapshot.get("answers")
    radio_values = snapshot.get(
        "radioValues"
    )
    correct_value = snapshot.get(
        "correctValue"
    )
    question_src = snapshot.get(
        "questionSrc"
    )

    if (
        not isinstance(raw_answers, list)
        or len(raw_answers) != 4
    ):
        raise RuntimeError(
            f"{qid}: invalid answer cells: "
            f"{raw_answers!r}"
        )

    if (
        not isinstance(radio_values, list)
        or len(radio_values) != 4
        or not all(
            isinstance(value, str)
            for value in radio_values
        )
    ):
        raise RuntimeError(
            f"{qid}: invalid radio values: "
            f"{radio_values!r}"
        )

    if not isinstance(correct_value, str):
        raise RuntimeError(
            f"{qid}: invalid correct value: "
            f"{correct_value!r}"
        )

    try:
        correct_index = radio_values.index(
            correct_value
        )
    except ValueError as error:
        raise RuntimeError(
            f"{qid}: correct value "
            f"{correct_value!r} is not present "
            f"among {radio_values!r}"
        ) from error

    answers = {
        key: normalize_text(
            str(raw_answers[index])
        )
        for index, key in enumerate("abcd")
    }

    question_token = normalize_text(
        question_src
        if isinstance(question_src, str)
        else qid
    )

    return SolutionRecord(
        id=qid,
        solution="abcd"[correct_index],
        bamfInternalId=correct_value,
        question=question_token,
        answers=answers,
    )


async def _save_diagnostics(
    page: Page,
    output_path: Path,
    state_code: str,
    qid: str,
) -> None:
    safe_qid = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        qid,
    )

    diagnostics = (
        output_path.parent
        / "diagnostics"
        / state_code
        / safe_qid
    )

    diagnostics.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        html = await page.content()

        (
            diagnostics / "page.html"
        ).write_text(
            html,
            encoding="utf-8",
        )
    except Exception:
        pass

    try:
        await page.screenshot(
            path=diagnostics / "page.png",
            full_page=True,
        )
    except Exception:
        pass


async def scrape_solutions(
    output_path: Path,
    start_url: str = DEFAULT_START_URL,
    headless: bool = True,
) -> list[SolutionRecord]:
    records: list[SolutionRecord] = []

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    async with async_playwright() as playwright:
        browser: Browser = (
            await playwright.chromium.launch(
                headless=headless,
            )
        )

        try:
            for state_index, (
                state_name,
                state_code,
            ) in enumerate(
                STATE_CODES.items()
            ):
                page = await browser.new_page()

                page.set_default_timeout(
                    NAVIGATION_TIMEOUT_MS
                )
                page.set_default_navigation_timeout(
                    NAVIGATION_TIMEOUT_MS
                )

                current_qid = (
                    f"catalog-{state_code}"
                )

                try:
                    print(
                        f"Opening {state_name}...",
                        flush=True,
                    )

                    current_snapshot = (
                        await _open_catalog(
                            page,
                            start_url,
                            state_name,
                        )
                    )

                    start_number = (
                        1
                        if state_index == 0
                        else 301
                    )

                    for catalog_number in range(
                        start_number,
                        311,
                    ):
                        if catalog_number <= 300:
                            current_qid = question_id(
                                catalog_number,
                                None,
                            )
                        else:
                            current_qid = question_id(
                                catalog_number - 300,
                                state_code,
                            )

                        current_snapshot = (
                            await _select_question(
                                page,
                                catalog_number,
                                current_qid,
                                current_snapshot,
                            )
                        )

                        record = (
                            _build_solution_record(
                                current_snapshot,
                                current_qid,
                            )
                        )

                        records.append(record)

                        print(
                            f"  {current_qid}",
                            flush=True,
                        )

                except Exception:
                    await _save_diagnostics(
                        page,
                        output_path,
                        state_code,
                        current_qid,
                    )
                    raise

                finally:
                    await page.close()

        finally:
            await browser.close()

    write_json(
        output_path,
        [
            record.model_dump(
                by_alias=True
            )
            for record in records
        ],
    )

    return records