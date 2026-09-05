import unittest
from datetime import date

from scripts.northampton_probate_scraper import (
    PortalStructureError,
    normalize_estate_name,
    one_calendar_year_before,
    parse_result_rows,
)


class ProbateScraperTest(unittest.TestCase):
    def test_calendar_year_handles_leap_day(self):
        self.assertEqual(one_calendar_year_before(date(2024, 2, 29)), date(2023, 2, 28))
        self.assertEqual(one_calendar_year_before(date(2026, 9, 5)), date(2025, 9, 5))

    def test_parse_rows_uses_identifier_and_dates(self):
        records = parse_result_rows(
            ["Estate Number", "Decedent Name", "Date of Death", "Filing Date"],
            [{"cells": ["12-345", "Estate of SMITH, JANE", "1/2/2026", "02/03/2026"], "detail_url": "/record/12-345"}],
            "https://county.example/search",
        )
        self.assertEqual(records[0]["record_identifier"], "12-345")
        self.assertEqual(records[0]["estate_name"], "Estate of SMITH, JANE")
        self.assertEqual(records[0]["normalized_estate_name"], "smith jane")
        self.assertEqual(records[0]["death_date"], date(2026, 1, 2))
        self.assertEqual(records[0]["filing_date"], date(2026, 2, 3))
        self.assertEqual(records[0]["detail_url"], "https://county.example/record/12-345")

    def test_detail_url_is_stable_identifier_fallback(self):
        records = parse_result_rows(
            ["Estate", "Death Date", "Date Filed"],
            [{"cells": ["Jones, Sam", "", "9/5/2026"], "detail_url": "detail?id=99"}],
            "https://county.example/search",
        )
        self.assertEqual(records[0]["record_identifier"], "https://county.example/detail?id=99")
        self.assertIsNone(records[0]["death_date"])

    def test_missing_required_heading_fails_instead_of_guessing(self):
        with self.assertRaisesRegex(PortalStructureError, "death date"):
            parse_result_rows(
                ["Estate Number", "Estate Name", "Filing Date"], [], "https://example.test"
            )

    def test_normalization_removes_only_estate_markers(self):
        self.assertEqual(normalize_estate_name("DOE, JOHN JR., Deceased"), "doe john jr")


if __name__ == "__main__":
    unittest.main()
