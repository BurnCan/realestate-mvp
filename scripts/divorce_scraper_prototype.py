"""Prototype scraper for collecting divorce case search results across *all* pages.

This script intentionally focuses on pagination behavior so we don't stop at the
first page of results.

Usage example:
    python scripts/divorce_scraper_prototype.py \
        --search-url "https://example-court-site/search" \
        --query "divorce" \
        --out divorce_results.csv
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


@dataclass
class DivorceResult:
    case_number: str
    title: str
    filed_date: str
    status: str
    details_url: str


class DivorceScraper:
    """Fetches and parses paginated divorce search results."""

    def __init__(self, search_url: str, pause_seconds: float = 0.25) -> None:
        self.search_url = search_url
        self.pause_seconds = max(0.0, pause_seconds)
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_all_pages(self, query: str, max_pages: int = 500) -> list[DivorceResult]:
        """Return results from every page, not only page 1.

        Supports two common pagination patterns:
        1. `?page=<n>` style.
        2. `Next` link navigation in HTML.
        """
        page = 1
        next_url: str | None = None
        all_results: list[DivorceResult] = []
        seen_page_signatures: set[tuple[str, ...]] = set()

        while page <= max_pages:
            html = self._fetch_page(query=query, page=page, override_url=next_url)
            rows = list(self.parse_results(html))

            if not rows:
                print(f"No rows found on page {page}; stopping.")
                break

            signature = tuple(r.case_number for r in rows if r.case_number)
            if signature in seen_page_signatures:
                print(
                    f"Detected repeated page content at page {page}; stopping to avoid loop."
                )
                break
            seen_page_signatures.add(signature)

            all_results.extend(rows)
            print(f"Fetched page {page}: {len(rows)} rows (running total={len(all_results)}).")

            soup = BeautifulSoup(html, "html.parser")
            next_href = self._find_next_link(soup)
            if next_href:
                next_url = urljoin(self.search_url, next_href)
                page += 1
                time.sleep(self.pause_seconds)
                continue

            # Fallback for query-param pagination: try next numeric page only if this one had rows.
            next_url = None
            page += 1
            time.sleep(self.pause_seconds)

        return all_results

    def _fetch_page(self, query: str, page: int, override_url: str | None = None) -> str:
        if override_url:
            url = override_url
            params = None
        else:
            url = self.search_url
            params = {"q": query, "page": page}

        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _find_next_link(soup: BeautifulSoup) -> str | None:
        # Common cases: explicit rel=next, button text, or an element class hint.
        next_link = soup.select_one('a[rel="next"]')
        if next_link and next_link.get("href"):
            return next_link["href"]

        for selector in ["a.next", "a.pagination-next", "li.next a"]:
            candidate = soup.select_one(selector)
            if candidate and candidate.get("href"):
                return candidate["href"]

        for a_tag in soup.find_all("a"):
            label = " ".join(a_tag.get_text(strip=True).lower().split())
            if label in {"next", "next >", "›", "»"} and a_tag.get("href"):
                return a_tag["href"]

        return None

    @staticmethod
    def parse_results(html: str) -> Iterable[DivorceResult]:
        """Parse one page of results.

        NOTE: selectors below are intentionally generic for a prototype.
        Adjust class names/selectors if your target site uses different markup.
        """
        soup = BeautifulSoup(html, "html.parser")

        rows = soup.select("table tbody tr")
        if not rows:
            rows = soup.select(".search-results .result-row")

        for row in rows:
            # Table layout (most common)
            cells = row.find_all("td")
            if cells:
                detail_anchor = cells[0].find("a")
                details_url = detail_anchor["href"] if detail_anchor and detail_anchor.get("href") else ""
                yield DivorceResult(
                    case_number=cells[0].get_text(" ", strip=True) if len(cells) > 0 else "",
                    title=cells[1].get_text(" ", strip=True) if len(cells) > 1 else "",
                    filed_date=cells[2].get_text(" ", strip=True) if len(cells) > 2 else "",
                    status=cells[3].get_text(" ", strip=True) if len(cells) > 3 else "",
                    details_url=details_url,
                )
                continue

            # Div layout fallback
            yield DivorceResult(
                case_number=_safe_text(row.select_one(".case-number")),
                title=_safe_text(row.select_one(".case-title, .title")),
                filed_date=_safe_text(row.select_one(".filed-date, .date")),
                status=_safe_text(row.select_one(".status")),
                details_url=_safe_href(row.select_one("a")),
            )


def _safe_text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _safe_href(node) -> str:
    return node.get("href", "") if node else ""


def write_csv(results: list[DivorceResult], output_file: str) -> None:
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["case_number", "title", "filed_date", "status", "details_url"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(result.__dict__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prototype divorce-case results scraper")
    parser.add_argument("--search-url", required=True, help="Base search endpoint URL")
    parser.add_argument("--query", default="divorce", help="Search term")
    parser.add_argument("--out", default="divorce_results.csv", help="Output CSV file path")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Safety cap for pagination traversal",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.25,
        help="Delay between page requests",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scraper = DivorceScraper(args.search_url, pause_seconds=args.pause_seconds)
    results = scraper.fetch_all_pages(query=args.query, max_pages=args.max_pages)
    write_csv(results, args.out)
    print(f"Saved {len(results)} total results to {args.out}")


if __name__ == "__main__":
    main()
