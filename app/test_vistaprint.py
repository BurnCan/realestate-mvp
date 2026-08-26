import csv
import io
import unittest

from app.vistaprint import (
    VISTAPRINT_HEADERS,
    build_vistaprint_rows,
    derive_mailing_address,
    extract_recipient,
    make_vistaprint_row,
    normalize_zip,
)


def snapshot(name="DOE JOHN Q", line1="123 MAIN ST", line2="BETHLEHEM PA 18018", line3=""):
    return {
        "owners_name_1": name,
        "mail_address_1": line1,
        "mail_address_2": line2,
        "mail_address_3": line3,
    }


class VistaPrintHelpersTest(unittest.TestCase):
    def test_official_header_names_and_order(self):
        self.assertEqual(
            VISTAPRINT_HEADERS,
            ("First Name", "Last Name", "Company", "Address 1", "Address 2", "City", "State", "Zip Code"),
        )

    def test_individual_middle_name_and_suffix(self):
        # Representative values use the uppercase LAST FIRST convention emitted
        # by the Northampton County assessor source.
        self.assertEqual(extract_recipient(snapshot()), {
            "First Name": "JOHN Q", "Last Name": "DOE", "Company": ""
        })
        self.assertEqual(extract_recipient(snapshot("DOE JOHN A JR"))["Last Name"], "DOE JR")

    def test_ambiguous_mixed_case_name_is_sent_to_review_not_reversed(self):
        row, reason = make_vistaprint_row(snapshot("John Smith"))
        self.assertIsNone(row)
        self.assertEqual(reason, "Ambiguous recipient name order")

    def test_explicit_comma_name_order_is_not_ambiguous(self):
        row, reason = make_vistaprint_row(snapshot("Smith, John Q"))
        self.assertFalse(reason)
        self.assertEqual(row["First Name"], "John Q")
        self.assertEqual(row["Last Name"], "Smith")

    def test_organization_two_owner_and_et_al(self):
        self.assertEqual(extract_recipient(snapshot("ACME, LLC"))["Company"], "ACME, LLC")
        self.assertEqual(extract_recipient(snapshot("DOE JOHN & DOE JANE"))["First Name"], "JOHN")
        self.assertEqual(extract_recipient(snapshot("DOE JOHN ET AL"))["First Name"], "JOHN")
        self.assertEqual(extract_recipient(snapshot("FIRST NATIONAL BANK"))["Company"], "FIRST NATIONAL BANK")
        self.assertEqual(extract_recipient(snapshot("DOE FAMILY TRUST"))["Company"], "DOE FAMILY TRUST")

    def test_address_patterns_and_zip_normalization(self):
        parsed = derive_mailing_address(snapshot())
        self.assertEqual((parsed.address_1, parsed.city, parsed.state, parsed.zip_code), ("123 MAIN ST", "BETHLEHEM", "PA", "18018"))
        unit = derive_mailing_address(snapshot(line2="APT 4B", line3="BETHLEHEM, PA 18018-1234"))
        self.assertEqual((unit.address_2, unit.zip_code), ("APT 4B", "18018"))
        po_box = derive_mailing_address(snapshot(line1="PO BOX 42", line2="EASTON PA 180429999"))
        self.assertEqual((po_box.address_1, po_box.zip_code), ("PO BOX 42", "18042"))
        self.assertEqual(normalize_zip("18018-1234"), "18018")
        self.assertEqual(normalize_zip("180181234"), "18018")

    def test_missing_and_malformed_are_review(self):
        self.assertFalse(derive_mailing_address(snapshot(line1="", line2="")).exportable)
        self.assertFalse(derive_mailing_address(snapshot(line2="NOT A LOCALITY")).exportable)

    def test_deduplication_is_stable_and_normalizes_case_punctuation_zip4(self):
        rows, review = build_vistaprint_rows([
            snapshot("DOE JOHN", "123 Main St.", "Bethlehem, PA 18018-1234"),
            snapshot("ROE JANE", "123 MAIN ST", "BETHLEHEM PA 18018"),
            snapshot("SMITH AMY", "PO BOX 2", "EASTON PA 18042"),
        ])
        self.assertEqual(len(rows), 2)
        self.assertFalse(review)
        self.assertEqual([row["Last Name"] for row in rows], ["DOE", "SMITH"])

    def test_csv_writer_escapes_commas_and_quotes(self):
        row, reason = make_vistaprint_row(snapshot('ACME "HOME", LLC'))
        self.assertFalse(reason)
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=VISTAPRINT_HEADERS)
        writer.writeheader()
        writer.writerow(row)
        parsed = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(parsed[0]["Company"], 'ACME "HOME", LLC')

    def test_all_rows_are_processed_beyond_frontend_page_size(self):
        snapshots = [snapshot(f"DOE PERSON{i}", f"{i} MAIN ST", "EASTON PA 18042") for i in range(300)]
        rows, review = build_vistaprint_rows(snapshots)
        self.assertEqual(len(rows), 300)
        self.assertFalse(review)


if __name__ == "__main__":
    unittest.main()
