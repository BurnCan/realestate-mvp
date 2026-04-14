import re
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

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
    return [rows.nth(i).inner_text() for i in range(row_count)]


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
            for row_text in page_rows:
                if row_text not in seen_rows:
                    seen_rows.add(row_text)
                    cached_results.append(row_text)

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
            for row_text in cached_results:
                print(row_text)
                print("-" * 60)
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
