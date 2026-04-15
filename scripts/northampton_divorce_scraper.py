import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import (
    ensure_divorce_schema,
    ensure_properties_schema,
    get_conn,
    sync_property_divorce_fields,
)

URL = "https://web.northamptoncounty.org/CountySuite.EServices/CaseSearch"


# -------------------------------------------------
# Enter date into Kendo date input correctly
# -------------------------------------------------
def enter_date(page, selector, date_value):
    formatted = date_value.strftime("%m/%d/%Y")
    field = page.locator(selector)
    field.wait_for()

    # Click to focus
    field.click()
    page.wait_for_timeout(200)

    # Clear existing value by selecting all and deleting
    field.press("Control+a")
    field.press("Backspace")
    page.wait_for_timeout(100)

    # Type the date character by character
    field.type(formatted, delay=50)  # small delay for Kendo
    page.wait_for_timeout(200)

    # Press Enter to commit
    field.press("Enter")
    page.wait_for_timeout(300)


# -------------------------------------------------
def read_results_page(page):
    header_cells = page.locator("table thead th")
    header_map = {}
    for i in range(header_cells.count()):
        label = header_cells.nth(i).inner_text().strip().lower()
        if label:
            header_map[label] = i

    case_number_idx = header_map.get("case number", 0)
    participants_idx = header_map.get("case participants", 1)
    category_idx = header_map.get("case category", 2)
    opened_idx = header_map.get("opened", 3)
    status_idx = header_map.get("status", 4)

    rows = page.locator("table tbody tr")
    row_count = rows.count()
    page_results = []

    for i in range(row_count):
        cells = rows.nth(i).locator("td")
        cell_count = cells.count()
        values = [cells.nth(j).inner_text().strip() for j in range(cell_count)]

        if len(values) <= max(
            case_number_idx, participants_idx, category_idx, opened_idx, status_idx
        ):
            fallback_values = [
                token.strip()
                for token in rows.nth(i).inner_text().split("\n")
                if token.strip()
            ]
            values = fallback_values

        if len(values) >= 5:
            page_results.append(
                {
                    "case_number": values[case_number_idx],
                    "case_participants": values[participants_idx],
                    "case_category": values[category_idx],
                    "date_opened": values[opened_idx],
                    "status": values[status_idx],
                }
            )

    return page_results


def parse_date(date_str):
    match = re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", date_str or "")
    if match:
        date_str = match.group(0)

    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def normalize_participant_name(raw_name):
    if not raw_name:
        return ""

    normalized = re.sub(r"[^a-z0-9,\s]+", " ", raw_name.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return ""

    if "," in normalized:
        last, _, remainder = normalized.partition(",")
        first = remainder.strip().split(" ")[0] if remainder.strip() else ""
        return " ".join(part for part in [last.strip(), first.strip()] if part).strip()

    parts = normalized.split(" ")
    return " ".join(parts[:2]).strip()


def extract_normalized_participants(case_participants):
    normalized_names = []
    seen = set()
    pattern = re.compile(r"(?:Pla|Def):\s*([^:]+?)(?=\s*(?:Pla|Def):|$)", re.IGNORECASE)
    for match in pattern.finditer(case_participants or ""):
        normalized = normalize_participant_name(match.group(1))
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_names.append(normalized)
    return normalized_names


def save_cases_to_db(cases):
    if not cases:
        return 0

    print("Opening database connection...")
    conn = get_conn()
    ensure_divorce_schema(conn)
    ensure_properties_schema(conn)
    cur = conn.cursor()

    upsert_query = """
        INSERT INTO divorce_cases (
            case_number,
            case_participants,
            normalized_participants,
            case_category,
            date_opened,
            status,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (case_number)
        DO UPDATE SET
            case_participants = EXCLUDED.case_participants,
            normalized_participants = EXCLUDED.normalized_participants,
            case_category = EXCLUDED.case_category,
            date_opened = EXCLUDED.date_opened,
            status = EXCLUDED.status,
            updated_at = NOW()
    """

    inserted_count = 0
    normalized_names_to_check = []
    for case in cases:
        case_number = case.get("case_number", "").strip()
        if not case_number:
            continue

        normalized_participants = extract_normalized_participants(
            case.get("case_participants", "")
        )
        normalized_names_to_check.extend(normalized_participants)

        cur.execute(
            upsert_query,
            (
                case_number,
                case.get("case_participants"),
                normalized_participants,
                case.get("case_category"),
                parse_date(case.get("date_opened", "")),
                case.get("status"),
            ),
        )
        inserted_count += 1

    unique_normalized_names = []
    seen_normalized_names = set()
    for normalized_name in normalized_names_to_check:
        if normalized_name and normalized_name not in seen_normalized_names:
            seen_normalized_names.add(normalized_name)
            unique_normalized_names.append(normalized_name)

    owner_match_count_query = """
        SELECT COUNT(*)
        FROM properties p
        WHERE (
            TRIM(
                CONCAT_WS(
                    ' ',
                    SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_1, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 1),
                    SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_1, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 2)
                )
            ) = %s
        )
        OR (
            TRIM(
                CONCAT_WS(
                    ' ',
                    SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_2, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 1),
                    SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_2, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 2)
                )
            ) = %s
        )
    """

    print(f"Checking owner matches for {len(unique_normalized_names)} normalized name(s)...")
    for index, normalized_name in enumerate(unique_normalized_names, start=1):
        if index % 50 == 0:
            print(f"Owner match progress: {index}/{len(unique_normalized_names)}")
        cur.execute(owner_match_count_query, (normalized_name, normalized_name))
        owner_match_count = cur.fetchone()[0]
        if owner_match_count > 0:
            print(
                f"Found {owner_match_count} matching propert{'y' if owner_match_count == 1 else 'ies'} for '{normalized_name}'."
            )

    print("Committing divorce case upserts...")
    conn.commit()
    cur.close()

    # Materialize divorce fields directly onto properties so API reads avoid runtime joins.
    print("Syncing divorce fields onto properties (this may take a while)...")
    sync_started = perf_counter()
    sync_property_divorce_fields(conn)
    sync_elapsed = perf_counter() - sync_started
    print(f"Property divorce-field sync complete in {sync_elapsed:.1f}s.")
    conn.close()
    return inserted_count


# -------------------------------------------------
def parse_total_entries(page):
    paginator_current = page.locator("span.p-paginator-current").first
    if paginator_current.count() == 0:
        return None

    text = paginator_current.inner_text().strip()
    match = re.search(r"of\s+(\d+)\s+entries", text)
    if not match:
        return None

    return int(match.group(1))


# -------------------------------------------------
def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=250)
        page = browser.new_page()

        try:
            print("[1/8] Opening Northampton County case search page...")
            page.goto(URL)

            # -------------------------------------------------
            # ACCEPT DISCLAIMER
            # -------------------------------------------------
            print("[2/8] Checking for disclaimer dialog...")
            try:
                page.wait_for_selector("text=Accept", timeout=8000)
                print("Accepting disclaimer...")
                page.click("text=Accept")
                page.wait_for_load_state("networkidle")
            except Exception:
                print("Disclaimer accept prompt not shown; continuing.")

            # -------------------------------------------------
            # WAIT FOR SEARCH FORM
            # -------------------------------------------------
            print("[3/8] Waiting for search form...")
            page.wait_for_selector("text=Search Type")

            # -------------------------------------------------
            # INITIAL SEARCH STRING (required)
            # -------------------------------------------------
            print("[4/8] Populating search criteria...")
            search_input = page.get_by_label("Search String")  # Use visible label text
            search_input.click()
            search_input.fill("")  # clear anything
            search_input.type(" ")  # type a single space
            search_input.dispatch_event("input")
            search_input.dispatch_event("change")
            page.wait_for_timeout(500)  # give Kendo time to register

            # -------------------------------------------------
            # SEARCH TYPE
            # -------------------------------------------------
            page.locator("label:has-text('Search Type')").locator("..").click()
            page.locator("li:has-text('Case Number')").click()
            print("Search type set to 'Case Number'.")

            # -------------------------------------------------
            # DATE RANGE
            # -------------------------------------------------
            today = datetime.today()
            one_year_ago = today - timedelta(days=365)
            print(
                f"Date range set to {one_year_ago.strftime('%m/%d/%Y')} through {today.strftime('%m/%d/%Y')}."
            )

            enter_date(page, "input[placeholder='Start Date']", one_year_ago)
            enter_date(page, "input[placeholder='End Date']", today)

            # -------------------------------------------------
            # CASE CATEGORY
            # -------------------------------------------------
            page.locator("label:has-text('Case Categories')").locator("..").click()
            page.get_by_role("option", name="Divorce", exact=True).click()
            print("Case category set to 'Divorce'.")

            # -------------------------------------------------
            # SEARCH
            # -------------------------------------------------
            print("[5/8] Running search...")
            search_button = page.locator("button:has-text('Search')")

            # Wait for the loading overlay to appear and disappear
            try:
                loading = page.locator("div.k-loading-mask")
                loading.wait_for(state="visible", timeout=50000)
                loading.wait_for(state="hidden", timeout=60000)
                print("Loading overlay completed.")
            except Exception:
                print("No loading overlay detected before search; continuing.")

            print("Waiting for search response...")

            # Trigger search and wait for the POST request to complete
            with page.expect_response("**/CaseSearch/Search") as response_info:
                search_button.click()

            response = response_info.value
            if response.ok:
                print("Search request completed successfully.")

                # Switch paginator page size from 10 -> 100 before reading rows.
                try:
                    page_size_label = page.locator(
                        ".p-paginator .p-dropdown .p-dropdown-label"
                    ).first
                    page_size_label.wait_for(state="visible", timeout=10000)

                    current_page_size = page_size_label.inner_text().strip()
                    if current_page_size != "100":
                        page_size_label.click()
                        page.locator(
                            ".p-dropdown-panel .p-dropdown-items .p-dropdown-item:has-text('100')"
                        ).first.wait_for(state="visible", timeout=10000)
                        page.locator(
                            ".p-dropdown-panel .p-dropdown-items .p-dropdown-item:has-text('100')"
                        ).first.click()

                    # Wait for refreshed results after changing page size.
                    try:
                        loading = page.locator("div.k-loading-mask")
                        loading.wait_for(state="visible", timeout=5000)
                        loading.wait_for(state="hidden", timeout=30000)
                    except Exception:
                        pass

                    page.wait_for_timeout(1000)
                    print("Paginator page size changed to 100.")
                except Exception as exc:
                    print(f"Could not set paginator page size to 100: {exc}")
            else:
                print(f"Search request failed with status: {response.status}")

            page.wait_for_timeout(2000)  # short pause for DOM update

            # -------------------------------------------------
            # RESULTS (CACHE ALL PAGINATED ROWS)
            # -------------------------------------------------
            print("[6/8] Reading paginated results...")
            cached_results = []
            seen_rows = set()
            pages_processed = 0

            total_entries = parse_total_entries(page)
            if total_entries is None:
                print(
                    "Could not read total entries from paginator; defaulting to a single visible page."
                )
            else:
                print(f"Paginator reports {total_entries} total entries.")

            while True:
                pages_processed += 1
                page_rows = read_results_page(page)
                print(f"Processing page {pages_processed}: found {len(page_rows)} row(s).")
                added_this_page = 0
                for row_data in page_rows:
                    key = (
                        row_data["case_number"],
                        row_data["case_participants"],
                        row_data["date_opened"],
                        row_data["status"],
                    )
                    if key not in seen_rows:
                        seen_rows.add(key)
                        cached_results.append(row_data)
                        added_this_page += 1

                print(
                    f"Page {pages_processed}: added {added_this_page} new row(s), running total {len(cached_results)}."
                )

                if total_entries is not None and len(cached_results) >= total_entries:
                    print("Reached reported total entries; pagination complete.")
                    break

                next_button = page.locator(
                    "button.p-paginator-next.p-paginator-element.p-link"
                ).first
                if next_button.count() == 0 or next_button.is_disabled():
                    print("Next-page button not available; pagination complete.")
                    break

                previous_indicator = (
                    page.locator("span.p-paginator-current").first.inner_text()
                )
                next_button.click()
                print(f"Navigating to next page after: '{previous_indicator.strip()}'.")

                try:
                    page.wait_for_function(
                        """(prevText) => {
                            const el = document.querySelector('span.p-paginator-current');
                            return el && el.textContent && el.textContent.trim() !== prevText;
                        }""",
                        previous_indicator.strip(),
                        timeout=15000,
                    )
                    print("Next page loaded.")
                except Exception:
                    print("Paginator indicator did not update in time; waiting briefly.")
                    page.wait_for_timeout(1000)

            print("[7/8] Saving results...")
            if cached_results:
                print(f"\nFound {len(cached_results)} divorce case(s)\n")
                for row_data in cached_results:
                    print(row_data)
                    print("-" * 60)
                saved_count = save_cases_to_db(cached_results)
                print(f"Upserted {saved_count} case(s) into divorce_cases table.")
            else:
                no_cases = page.locator("text=No cases found")
                if no_cases.count() > 0:
                    print("No cases found. Please update your search and try again.")
                else:
                    print(
                        "No table rows found and 'No cases found' message not present — something went wrong."
                    )
        finally:
            print("[8/8] Closing browser...")
            browser.close()
            print("Script complete.")


if __name__ == "__main__":
    run()
