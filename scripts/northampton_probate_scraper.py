"""Scrape Northampton County estate filings and synchronize property matches.

The portal is intentionally driven through each public UI step.  When its labels
or table headings change, this script saves diagnostic HTML and fails instead of
guessing a replacement selector.
"""

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import (  # noqa: E402
    ensure_probate_schema,
    ensure_properties_schema,
    get_conn,
    sync_property_probate_fields,
)

URL = "https://wior.northamptoncounty.org/countyweb/loginDisplay.action?countyname=NorthamptonPA"
DEFAULT_DIAGNOSTICS = PROJECT_ROOT / "artifacts" / "northampton-probate"
DATE_FORMAT = "%m/%d/%Y"


class PortalStructureError(RuntimeError):
    """The live portal no longer matches the documented workflow."""


def one_calendar_year_before(value: date) -> date:
    """Return the same calendar date last year (Feb. 29 becomes Feb. 28)."""
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def parse_portal_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    match = re.search(r"\d{1,2}/\d{1,2}/\d{4}", value)
    if not match:
        raise PortalStructureError(f"Unrecognized portal date: {value!r}")
    return datetime.strptime(match.group(), DATE_FORMAT).date()


def normalize_estate_name(value: str) -> str:
    """Normalize a decedent name to the county assessor's owner-name shape."""
    value = re.sub(r"\b(estate of|decedent|deceased|dec'?d)\b", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _column_index(headers, aliases, field):
    normalized = [re.sub(r"\s+", " ", item.strip().lower()) for item in headers]
    for alias in aliases:
        if alias in normalized:
            return normalized.index(alias)
    raise PortalStructureError(
        f"Results table has no {field} column; observed headings: {headers!r}"
    )


def parse_result_rows(headers, rows, base_url):
    """Convert extracted table cells into database-ready records."""
    name_i = _column_index(headers, {"decedent", "decedent name", "estate", "estate name"}, "estate name")
    death_i = _column_index(headers, {"date of death", "death date", "dod"}, "death date")
    filing_i = _column_index(headers, {"filing date", "date filed", "filed"}, "filing date")
    id_aliases = {"estate number", "estate/file number", "file number", "case number", "docket number", "record id"}
    normalized_headers = [re.sub(r"\s+", " ", h.strip().lower()) for h in headers]
    id_i = next((normalized_headers.index(alias) for alias in id_aliases if alias in normalized_headers), None)

    records = []
    for row in rows:
        cells = row["cells"]
        if max(name_i, death_i, filing_i) >= len(cells):
            continue
        detail_href = row.get("detail_url")
        detail_url = urljoin(base_url, detail_href) if detail_href else None
        identifier = cells[id_i].strip() if id_i is not None and id_i < len(cells) else ""
        identifier = identifier or detail_url
        if not identifier:
            raise PortalStructureError("A result exposes neither a record number nor a detail URL")
        estate_name = cells[name_i].strip()
        filing_date = parse_portal_date(cells[filing_i])
        if not estate_name or filing_date is None:
            raise PortalStructureError(f"Result is missing estate name or filing date: {cells!r}")
        records.append(
            {
                "record_identifier": identifier,
                "estate_name": estate_name,
                "normalized_estate_name": normalize_estate_name(estate_name),
                "death_date": parse_portal_date(cells[death_i]),
                "filing_date": filing_date,
                "detail_url": detail_url,
            }
        )
    return records


def save_diagnostics(page, directory: Path, step: str):
    directory.mkdir(parents=True, exist_ok=True)
    safe_step = re.sub(r"[^a-z0-9_-]+", "-", step.lower())
    (directory / f"{safe_step}.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=directory / f"{safe_step}.png", full_page=True)


def require_visible(locator, description, timeout):
    try:
        locator.first.wait_for(state="visible", timeout=timeout)
        return locator.first
    except Exception as exc:
        raise PortalStructureError(f"Could not find {description}") from exc


def click_and_wait_for(page, control, destination, description, timeout):
    """Click a control, then explicitly wait for the expected next view."""
    require_visible(control, f"{description} control", timeout).click()
    require_visible(destination, f"view after {description}", timeout)


def fill_labeled_date(page, labels, value, timeout):
    for label in labels:
        locator = page.get_by_label(re.compile(rf"^{re.escape(label)}\s*\*?$", re.I))
        if locator.count():
            field = require_visible(locator, label, timeout)
            field.fill(value.strftime(DATE_FORMAT))
            field.press("Tab")
            return
    raise PortalStructureError(f"No date input labeled as one of {labels!r}")


def read_visible_table(page):
    table = require_visible(page.locator("table:has(thead):has(tbody)"), "results table", 30_000)
    headers = [text.strip() for text in table.locator("thead th").all_inner_texts()]
    rows = []
    for row in table.locator("tbody tr").all():
        cells = [text.strip() for text in row.locator("td").all_inner_texts()]
        link = row.locator("a[href]").first
        rows.append({"cells": cells, "detail_url": link.get_attribute("href") if link.count() else None})
    return headers, rows


def scrape(page, today: date, timeout: int, diagnostics: Path):
    print("[1/7] Opening initial login page")
    page.goto(URL, wait_until="domcontentloaded", timeout=timeout)
    guest = page.get_by_role("link", name=re.compile(r"^(login as )?guest", re.I)).or_(
        page.get_by_role("button", name=re.compile(r"^(login as )?guest", re.I))
    )
    terms = page.get_by_role("button", name=re.compile(r"^accept$", re.I)).or_(
        page.get_by_role("link", name=re.compile(r"^accept$", re.I))
    )
    print("[2/7] Choosing Login as Guest and waiting for terms")
    click_and_wait_for(page, guest, terms, "Guest Login -> terms page", timeout)

    public_records = page.get_by_text(re.compile(r"^search public records$", re.I), exact=True)
    print("[3/7] Accepting terms and waiting for public-records area")
    click_and_wait_for(page, terms, public_records, "Accept -> public records area", timeout)

    estate_choice = page.get_by_text(re.compile(r"^(estate|probate)( public records)?( search)?$", re.I), exact=True)
    date_field = page.get_by_label(re.compile(r"filing date (start|from)", re.I))
    print("[4/7] Opening Search Public Records")
    require_visible(public_records, "Search Public Records", timeout).click()
    try:
        date_field.first.wait_for(state="visible", timeout=5_000)
    except Exception:
        print("      Selecting the estate/probate search type")
        click_and_wait_for(page, estate_choice, date_field, "estate/probate search selection", timeout)

    print("[5/7] Configuring the blank-name, one-calendar-year search")
    start = one_calendar_year_before(today)
    fill_labeled_date(page, ("Filing Date Start", "Filing Date From", "From Filing Date"), start, timeout)
    fill_labeled_date(page, ("Filing Date End", "Filing Date To", "To Filing Date"), today, timeout)
    name = page.get_by_label(re.compile(r"^(decedent|estate )?name\s*\*?$", re.I))
    if name.count():
        name.first.fill("")
    search = page.get_by_role("button", name=re.compile(r"^search$", re.I)).or_(
        page.get_by_role("link", name=re.compile(r"^search$", re.I))
    )
    require_visible(search, "Search", timeout).click()
    require_visible(page.locator("table:has(thead):has(tbody)"), "loaded results", timeout)

    print("[6/7] Reading every results page")
    records, seen = [], set()
    while True:
        headers, raw_rows = read_visible_table(page)
        page_records = parse_result_rows(headers, raw_rows, page.url)
        signature = tuple(record["record_identifier"] for record in page_records)
        if signature in seen:
            raise PortalStructureError("Pagination repeated a previously read results page")
        seen.add(signature)
        records.extend(page_records)
        next_control = page.get_by_role("link", name=re.compile(r"^next", re.I)).or_(
            page.get_by_role("button", name=re.compile(r"^next", re.I))
        ).first
        if not next_control.count() or next_control.is_disabled() or next_control.get_attribute("aria-disabled") == "true":
            break
        next_control.click()
        page.wait_for_function(
            "previous => document.querySelector('table tbody')?.innerText !== previous",
            page.locator("table tbody").inner_text(),
            timeout=timeout,
        )
    print(f"      Collected {len(records)} records from {len(seen)} page(s)")
    return records


def upsert_estates(records):
    conn = get_conn()
    try:
        ensure_probate_schema(conn)
        ensure_properties_schema(conn)
        with conn.cursor() as cur:
            for record in records:
                cur.execute(
                    """
                    INSERT INTO probate_estates
                        (record_identifier, estate_name, normalized_estate_name,
                         death_date, filing_date, detail_url, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (record_identifier) DO UPDATE SET
                        estate_name = EXCLUDED.estate_name,
                        normalized_estate_name = EXCLUDED.normalized_estate_name,
                        death_date = EXCLUDED.death_date,
                        filing_date = EXCLUDED.filing_date,
                        detail_url = EXCLUDED.detail_url,
                        updated_at = NOW()
                    """,
                    tuple(record[key] for key in ("record_identifier", "estate_name", "normalized_estate_name", "death_date", "filing_date", "detail_url")),
                )
        conn.commit()
        print(f"Upserted {len(records)} probate estate(s)")

        # Deliberately separate from ingestion: matching can also be rerun alone.
        print("[7/7] Synchronizing probate matches onto properties")
        sync_property_probate_fields(conn)
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headed", action="store_true", help="show the browser for workflow debugging")
    parser.add_argument("--slow-mo", type=int, default=0, metavar="MS", help="delay browser actions (most useful with --headed)")
    parser.add_argument("--timeout", type=int, default=30_000, metavar="MS")
    parser.add_argument("--diagnostics", type=Path, default=DEFAULT_DIAGNOSTICS)
    parser.add_argument("--sync-only", action="store_true", help="skip Playwright and rerun property matching")
    args = parser.parse_args(argv)

    if args.sync_only:
        conn = get_conn()
        try:
            ensure_probate_schema(conn)
            ensure_properties_schema(conn)
            sync_property_probate_fields(conn)
        finally:
            conn.close()
        return

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed, slow_mo=args.slow_mo)
        page = browser.new_page()
        try:
            records = scrape(page, date.today(), args.timeout, args.diagnostics)
        except Exception:
            save_diagnostics(page, args.diagnostics, "workflow-failure")
            raise
        finally:
            browser.close()
    upsert_estates(records)


if __name__ == "__main__":
    main()
