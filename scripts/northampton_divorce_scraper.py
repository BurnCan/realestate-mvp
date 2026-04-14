import re
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

from app.db import ensure_divorce_schema, get_conn

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
    rows = page.locator("table tbody tr")
    row_count = rows.count()
    page_results = []

    for i in range(row_count):
        cells = rows.nth(i).locator("td")
        cell_count = cells.count()
        values = [cells.nth(j).inner_text().strip() for j in range(cell_count)]
        values = [value for value in values if value]

        if len(values) < 5:
            fallback_values = [
                token.strip()
                for token in rows.nth(i).inner_text().split("\n")
                if token.strip()
            ]
            values = fallback_values

        if len(values) >= 5:
            page_results.append(
                {
                    "case_number": values[0],
                    "case_participants": values[1],
                    "case_category": values[2],
                    "date_opened": values[3],
                    "status": values[4],
                }
            )

    return page_results


def parse_date(date_str):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def save_cases_to_db(cases):
    if not cases:
        return 0

    conn = get_conn()
    ensure_divorce_schema(conn)
    cur = conn.cursor()

    upsert_query = """
        INSERT INTO divorce_cases (
            case_number,
            case_participants,
            case_category,
            date_opened,
            status,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (case_number)
        DO UPDATE SET
            case_participants = EXCLUDED.case_participants,
            case_category = EXCLUDED.case_category,
            date_opened = EXCLUDED.date_opened,
            status = EXCLUDED.status,
            updated_at = NOW()
    """

    inserted_count = 0
    for case in cases:
        case_number = case.get("case_number", "").strip()
        if not case_number:
            continue

        cur.execute(
            upsert_query,
            (
                case_number,
                case.get("case_participants"),
                case.get("case_category"),
                parse_date(case.get("date_opened", "")),
                case.get("status"),
            ),
        )
        inserted_count += 1

    conn.commit()
    cur.close()
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

        page.goto(URL)

        # -------------------------------------------------
        # ACCEPT DISCLAIMER
        # -------------------------------------------------
        try:
            page.wait_for_selector("text=Accept", timeout=8000)
            print("Accepting disclaimer...")
            page.click("text=Accept")
            page.wait_for_load_state("networkidle")
        except Exception:
            pass

        # -------------------------------------------------
        # WAIT FOR SEARCH FORM
        # -------------------------------------------------
        page.wait_for_selector("text=Search Type")

        # -------------------------------------------------
        # INITIAL SEARCH STRING (required)
        # -------------------------------------------------
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

        # -------------------------------------------------
        # DATE RANGE
        # -------------------------------------------------
        today = datetime.today()
        one_year_ago = today - timedelta(days=365)

        enter_date(page, "input[placeholder='Start Date']", one_year_ago)
        enter_date(page, "input[placeholder='End Date']", today)

        # -------------------------------------------------
        # CASE CATEGORY
        # -------------------------------------------------
        page.locator("label:has-text('Case Categories')").locator("..").click()
        page.get_by_role("option", name="Divorce", exact=True).click()

        # -------------------------------------------------
        # SEARCH
        # -------------------------------------------------
        search_button = page.locator("button:has-text('Search')")

        # Wait for the loading overlay to appear and disappear
        try:
            loading = page.locator("div.k-loading-mask")
            loading.wait_for(state="visible", timeout=50000)
            loading.wait_for(state="hidden", timeout=60000)
            print("Loading overlay completed")
        except Exception:
            print("No loading overlay detected, continuing")

        print("Waiting for search results...")

        # Trigger search and wait for the POST request to complete
        with page.expect_response("**/CaseSearch/Search") as response_info:
            search_button.click()

        response = response_info.value
        if response.ok:
            print("Search request completed successfully")

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
                print("Paginator page size changed to 100")
            except Exception as exc:
                print(f"Could not set paginator page size to 100: {exc}")
        else:
            print(f"Search request failed with status: {response.status}")

        page.wait_for_timeout(2000)  # short pause for DOM update

        # -------------------------------------------------
        # RESULTS (CACHE ALL PAGINATED ROWS)
        # -------------------------------------------------
        cached_results = []
        seen_rows = set()

        total_entries = parse_total_entries(page)
        if total_entries is None:
            print(
                "Could not read total entries from paginator; defaulting to a single visible page."
            )

        while True:
            page_rows = read_results_page(page)
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

            if total_entries is not None and len(cached_results) >= total_entries:
                break

            next_button = page.locator(
                "button.p-paginator-next.p-paginator-element.p-link"
            ).first
            if next_button.count() == 0 or next_button.is_disabled():
                break

            previous_indicator = page.locator("span.p-paginator-current").first.inner_text()
            next_button.click()

            try:
                page.wait_for_function(
                    """(prevText) => {
                        const el = document.querySelector('span.p-paginator-current');
                        return el && el.textContent && el.textContent.trim() !== prevText;
                    }""",
                    previous_indicator.strip(),
                    timeout=15000,
                )
            except Exception:
                page.wait_for_timeout(1000)

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

        browser.close()


if __name__ == "__main__":
    run()
