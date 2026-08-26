"""VistaPrint Postcard Mailing Services CSV construction.

The header spelling and order below mirror the ``Mailing List Template`` linked
from VistaPrint's official Postcard Mailing Services page (verified
2026-08-26):
https://www.vistaprint.com/marketing-materials/postcard-mailing-services

The vendor template itself is intentionally not stored here. VistaPrint
validates uploaded CSVs by these labels, so re-check the current official
template before changing either spelling or order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


VISTAPRINT_HEADERS = (
    "First Name",
    "Last Name",
    "Company",
    "Address 1",
    "Address 2",
    "City",
    "State",
    "Zip Code",
)

_ENTITY_WORDS = re.compile(
    r"\b(?:LLC|L\.?L\.?C\.?|INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LP|LLP|"
    r"BANK|CREDIT UNION|TRUST|TRUSTEE|ESTATE|ASSOCIATION|AUTHORITY|COUNTY|CITY|"
    r"BOROUGH|TOWNSHIP|COMMONWEALTH|DEPARTMENT|GOVERNMENT|CHURCH|FOUNDATION)\b",
    re.IGNORECASE,
)
_SUFFIXES = {"JR", "SR", "II", "III", "IV", "V"}
_LOCALITY = re.compile(
    r"^(?P<city>.+?)[,\s]+(?P<state>[A-Za-z]{2})\s+(?P<zip>\d{5}(?:-?\d{4})?)$"
)


@dataclass(frozen=True)
class ParsedAddress:
    address_1: str = ""
    address_2: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    review_reason: str = ""

    @property
    def exportable(self) -> bool:
        return not self.review_reason


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalize_zip(value: object) -> str:
    """Return a five-digit US ZIP, including from ZIP+4 and 9-digit forms."""
    text = clean_text(value)
    match = re.fullmatch(r"(\d{5})(?:-?\d{4})?", text)
    return match.group(1) if match else ""


def is_likely_organization(value: object) -> bool:
    name = clean_text(value)
    return bool(name and _ENTITY_WORDS.search(name))


def _ambiguous_recipient_reason(value: str) -> str:
    """Flag names for which the county field does not establish name order.

    ``OWNERS_NAME_1`` is copied verbatim from Northampton County's Land Records
    ArcGIS service (see ``app.ingest.URL``). The service exposes no data
    dictionary documenting a universal name order. In observed assessor-style
    records, individual names are normalized in uppercase as ``LAST FIRST
    [MIDDLE...]``; mixed-case text such as ``John Smith`` is therefore not
    silently treated as that source convention. A comma makes the order
    explicit regardless of case.
    """
    first_owner = re.split(r"\s*&\s*", value, maxsplit=1)[0]
    first_owner = re.sub(r"\s+ET\s+AL\.?\s*$", "", first_owner, flags=re.IGNORECASE)
    if "," in first_owner or first_owner == first_owner.upper():
        return ""
    return "Ambiguous recipient name order"


def extract_recipient(snapshot: dict | None) -> dict[str, str]:
    """Map normalized assessor-style ``LAST FIRST ...`` names.

    Entity names remain intact in Company. For joint owners and ET AL records,
    the explicitly named first owner is used as the recipient. This is narrowly
    a Northampton County source-data convention, not a generic person-name
    parser; callers must check ambiguous mixed-case names before exporting.
    """
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    raw = clean_text(
        snapshot.get("owners_name_1")
        or snapshot.get("owners_name_2")
        or snapshot.get("owners_hidename")
    )
    empty = {"First Name": "", "Last Name": "", "Company": ""}
    if not raw:
        return empty
    if is_likely_organization(raw):
        return {**empty, "Company": raw}

    first_owner = re.split(r"\s*&\s*", raw, maxsplit=1)[0]
    first_owner = re.sub(r"\s+ET\s+AL\.?\s*$", "", first_owner, flags=re.IGNORECASE)
    tokens = first_owner.replace(",", " ").split()
    if len(tokens) < 2:
        # A single or otherwise ambiguous token is safer as a recipient/company
        # label than a manufactured individual name.
        return {**empty, "Company": first_owner}

    last_name, given = tokens[0], tokens[1:]
    suffix = ""
    if given and given[-1].rstrip(".").upper() in _SUFFIXES:
        suffix = given.pop().rstrip(".").upper()
    if not given:
        return {**empty, "Company": first_owner}
    return {
        "First Name": " ".join(given),
        "Last Name": " ".join(filter(None, [last_name, suffix])),
        "Company": "",
    }


def derive_mailing_address(snapshot: dict | None) -> ParsedAddress:
    """Parse preserved snapshot lines, only when a US locality is recognizable."""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    parts = [
        clean_text(snapshot.get(key))
        for key in ("mail_address_1", "mail_address_2", "mail_address_3")
    ]
    parts = [part for part in parts if part]
    if not parts:
        return ParsedAddress(review_reason="Missing mailing address")

    locality_index = -1
    locality_match = None
    for index in range(len(parts) - 1, -1, -1):
        match = _LOCALITY.fullmatch(parts[index])
        if match:
            locality_index, locality_match = index, match
            break
    if locality_match is None or locality_index == 0:
        return ParsedAddress(review_reason="Could not safely parse city, state, and ZIP")

    street_lines = parts[:locality_index]
    if not street_lines or len(street_lines) > 2:
        return ParsedAddress(review_reason="Could not safely identify address lines")
    zip_code = normalize_zip(locality_match.group("zip"))
    if not zip_code:
        return ParsedAddress(review_reason="Invalid ZIP code")
    city = locality_match.group("city").strip(" ,")
    if not city:
        return ParsedAddress(review_reason="Missing city")
    return ParsedAddress(
        address_1=street_lines[0],
        address_2=street_lines[1] if len(street_lines) == 2 else "",
        city=city,
        state=locality_match.group("state").upper(),
        zip_code=zip_code,
    )


def normalize_mailing_destination(snapshot: dict | None) -> str:
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    text = " ".join(
        clean_text(snapshot.get(key)).lower()
        for key in ("mail_address_1", "mail_address_2", "mail_address_3")
        if clean_text(snapshot.get(key))
    )
    text = re.sub(r"\b(\d{5})(?:-?\d{4})\b", r"\1", text)
    return re.sub(r"[^a-z0-9]", "", text)


def make_vistaprint_row(snapshot: dict | None) -> tuple[dict[str, str] | None, str]:
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    address = derive_mailing_address(snapshot)
    if not address.exportable:
        return None, address.review_reason
    raw_name = clean_text(
        snapshot.get("owners_name_1")
        or snapshot.get("owners_name_2")
        or snapshot.get("owners_hidename")
    )
    if raw_name and not is_likely_organization(raw_name):
        recipient_reason = _ambiguous_recipient_reason(raw_name)
        if recipient_reason:
            return None, recipient_reason
    row = {
        **extract_recipient(snapshot),
        "Address 1": address.address_1,
        "Address 2": address.address_2,
        "City": address.city,
        "State": address.state,
        "Zip Code": address.zip_code,
    }
    return row, ""


def build_vistaprint_rows(
    snapshots: list[dict],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return exportable and review rows in stable snapshot order, deduplicated."""
    ready: list[dict[str, str]] = []
    review: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, snapshot in enumerate(snapshots):
        key = normalize_mailing_destination(snapshot)
        # Empty destinations are distinct source records; non-empty physical
        # destinations are emitted/reported once.
        dedupe_key = key or f"__missing_{index}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        row, reason = make_vistaprint_row(snapshot)
        if row is not None:
            ready.append(row)
        else:
            address_parts = [
                clean_text(snapshot.get(key))
                for key in ("mail_address_1", "mail_address_2", "mail_address_3")
            ]
            review.append(
                {
                    "reason": reason,
                    "mailing_address": ", ".join(filter(None, address_parts)),
                }
            )
    return ready, review
