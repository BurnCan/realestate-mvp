import csv
import json
import logging
import re
import secrets
import unicodedata
from functools import lru_cache
from itertools import islice
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from psycopg2 import OperationalError

from .db import (
    ensure_campaign_schema,
    ensure_divorce_schema,
    ensure_properties_schema,
    get_conn,
)

app = FastAPI()
logger = logging.getLogger(__name__)


class CampaignCreateRequest(BaseModel):
    name: str
    target_url: str | None = None
    parcel_ids: list[str] | None = None
    muni: str | None = None
    munis: str | None = None
    min_year_built: int | None = None
    max_year_built: int | None = None
    distressed_only: bool = False
    bank_owned_only: bool = False
    sheriff_sale_only: bool = False
    owner_occupant_only: bool = False
    recent_divorce_only: bool = False
    ownership_change_date_only: bool = False
    search_query: str | None = None
    search_mode: str = "all"


class CampaignUpdateRequest(BaseModel):
    redirect_url: str | None = None


def _slugify_campaign_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.strip().lower()).strip("-")
    return slug or "campaign"


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_address(value: str | None) -> str:
    text = _normalize_text(value)
    # Keep only alphanumeric and spaces for more reliable matching across systems.
    return re.sub(r"[^a-z0-9 ]", "", text)


_ORDINAL_BASE_WORDS: dict[str, int] = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "thirtieth": 30,
    "fortieth": 40,
    "fiftieth": 50,
    "sixtieth": 60,
    "seventieth": 70,
    "eightieth": 80,
    "ninetieth": 90,
}
_ORDINAL_TENS: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_ORDINAL_UNITS: dict[str, int] = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
}
_ORDINAL_PHRASE_TO_NUMBER: list[tuple[str, int]] = sorted(
    [
        *[(word, number) for word, number in _ORDINAL_BASE_WORDS.items()],
        *[
            (f"{tens_word} {unit_word}", tens_value + unit_value)
            for tens_word, tens_value in _ORDINAL_TENS.items()
            for unit_word, unit_value in _ORDINAL_UNITS.items()
        ],
    ],
    key=lambda item: len(item[0]),
    reverse=True,
)


def _normalize_owner_occupant_address(value: str | None) -> str:
    text = _normalize_text(value)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", r"\1", text)
    for phrase, number in _ORDINAL_PHRASE_TO_NUMBER:
        text = re.sub(rf"\b{re.escape(phrase)}\b", str(number), text)
    return re.sub(r"\s+", " ", text).strip()


def _owner_occupant_address_match(address: str | None, mailing_address: str | None) -> bool:
    normalized_address = _normalize_owner_occupant_address(address)
    normalized_mailing = _normalize_owner_occupant_address(mailing_address)
    if not normalized_address or not normalized_mailing:
        return False
    return (
        normalized_mailing in normalized_address
        or normalized_address in normalized_mailing
    )


def _normalize_owner_occupant_sql(expression: str) -> str:
    normalized = f"LOWER(TRIM(COALESCE({expression}, '')))"
    normalized = f"REGEXP_REPLACE({normalized}, '[^a-z0-9 ]', ' ', 'g')"
    normalized = f"REGEXP_REPLACE({normalized}, '\\\\m([0-9]+)(st|nd|rd|th)\\\\M', '\\\\1', 'g')"
    for phrase, number in _ORDINAL_PHRASE_TO_NUMBER:
        normalized = f"REGEXP_REPLACE({normalized}, '\\\\m{phrase}\\\\M', '{number}', 'g')"
    normalized = f"REGEXP_REPLACE({normalized}, '\\\\s+', ' ', 'g')"
    return f"TRIM({normalized})"


def _normalize_owner_search_text(value: str | None) -> str:
    text = _normalize_text(value)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_owner_name_clause(query: str) -> tuple[str, list[str]]:
    normalized_query = _normalize_owner_search_text(query)
    name_tokens = [token for token in normalized_query.split(" ") if token]

    # If we only have one token, keep the default ILIKE behavior.
    if len(name_tokens) < 2:
        return "", []

    normalized_with_commas = _normalize_text(query)
    has_comma = "," in normalized_with_commas

    if has_comma:
        # Support "LAST, FIRST MIDDLE" formats by prioritizing last + first tokens.
        before_comma, _, after_comma = normalized_with_commas.partition(",")
        comma_last_name = _normalize_owner_search_text(before_comma).split(" ")
        comma_given_names = _normalize_owner_search_text(after_comma).split(" ")

        if comma_last_name and comma_given_names:
            last_name = comma_last_name[0]
            first_name = comma_given_names[0]
        else:
            first_name = name_tokens[0]
            last_name = name_tokens[-1]
    else:
        first_name = name_tokens[0]
        last_name = name_tokens[-1]
    owner_blob = """
        LOWER(
            REGEXP_REPLACE(
                CONCAT_WS(' ', owners_name_1, owners_name_2, owners_hidename),
                '[^a-z0-9]+',
                ' ',
                'g'
            )
        )
    """

    clause = f"""
            OR (
                {owner_blob} ~ %s
                AND {owner_blob} ~ %s
            )
    """
    # PostgreSQL word-boundary operators avoid partial token matches.
    return clause, [rf"\\m{first_name}\\M", rf"\\m{last_name}\\M"]


def _muni_filter_candidates(muni: str | None) -> list[str]:
    raw = (muni or "").strip()
    if not raw:
        return []
    if not raw.isdigit():
        return [raw]

    numeric = str(int(raw))
    padded = numeric.zfill(2)
    return sorted({raw, numeric, padded})


def _muni_filter_candidates_from_list(munis: str | None) -> list[str]:
    raw_values = [
        part.strip()
        for part in (munis or "").split(",")
        if part and part.strip()
    ]
    if not raw_values:
        return []

    normalized: set[str] = set()
    for raw in raw_values:
        normalized.update(_muni_filter_candidates(raw))
    return sorted(normalized)


def _row_to_deal(row: tuple) -> dict:
    return {
        "parcel_id": row[0],
        "address": row[1],
        "muni": row[2],
        "year_built": row[3],
        "assessed_value": row[4],
        "total_assessed_value": row[5],
        "owners_hidename": row[6],
        "owners_name_1": row[7],
        "owners_name_2": row[8],
        "ownership_change_date": row[9],
        "mail_address_1": row[10],
        "mail_address_2": row[11],
        "mail_address_3": row[12],
        "sale_type": row[13],
        "recent_divorce": row[14],
        "divorce_case_status": row[15],
        "divorce_date_opened": row[16],
        "is_sheriff_sale": is_sheriff_sale_property(row[1], row[2]),
    }


def _build_filtered_deals_query(
    *,
    muni: str | None = None,
    munis: str | None = None,
    min_year_built: int | None = None,
    max_year_built: int | None = None,
    distressed_only: bool = False,
    bank_owned_only: bool = False,
    sheriff_sale_only: bool = False,
    owner_occupant_only: bool = False,
    recent_divorce_only: bool = False,
    ownership_change_date_only: bool = False,
) -> tuple[str, list]:
    base_query = """
        SELECT
            parcel_id,
            address,
            muni,
            year_built,
            assessed_value,
            total_assessed_value,
            owners_hidename,
            owners_name_1,
            owners_name_2,
            ownership_change_date,
            mail_address_1,
            mail_address_2,
            mail_address_3,
            sale_type,
            recent_divorce,
            divorce_case_status,
            divorce_date_opened
        FROM properties
        WHERE TRUE
    """

    params: list = []
    muni_candidates = sorted({
        *_muni_filter_candidates(muni),
        *_muni_filter_candidates_from_list(munis),
    })
    if muni_candidates:
        if len(muni_candidates) == 1:
            base_query += " AND TRIM(COALESCE(muni, '')) = %s"
            params.append(muni_candidates[0])
        else:
            base_query += " AND TRIM(COALESCE(muni, '')) = ANY(%s)"
            params.append(muni_candidates)

    if min_year_built is not None:
        base_query += " AND year_built >= %s"
        params.append(min_year_built)
    if max_year_built is not None:
        base_query += " AND year_built <= %s"
        params.append(max_year_built)

    distressed_condition = """
        (
            LOWER(COALESCE(owners_name_1, '')) LIKE '%%secretary%%'
            OR LOWER(COALESCE(owners_name_2, '')) LIKE '%%secretary%%'
            OR LOWER(COALESCE(owners_name_1, '')) LIKE '%%housing%%'
            OR LOWER(COALESCE(owners_name_2, '')) LIKE '%%housing%%'
        )
        AND NOT (
            LOWER(COALESCE(owners_name_1, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
            OR LOWER(COALESCE(owners_name_2, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
        )
    """
    bank_owned_condition = """
        (
            LOWER(COALESCE(owners_name_1, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
            OR LOWER(COALESCE(owners_name_2, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
        )
    """

    status_conditions: list[str] = []
    if distressed_only:
        status_conditions.append(f"({distressed_condition})")
    if bank_owned_only:
        status_conditions.append(f"({bank_owned_condition})")
    if sheriff_sale_only:
        sheriff_matches = sorted(get_sheriff_sale_matches())
        if sheriff_matches:
            status_conditions.append(
                "REGEXP_REPLACE(LOWER(COALESCE(address, '')), '[^a-z0-9 ]', '', 'g') = ANY(%s)"
            )
            params.append(sheriff_matches)
    if recent_divorce_only:
        status_conditions.append("COALESCE(recent_divorce, FALSE) IS TRUE")
    if ownership_change_date_only:
        status_conditions.append("NULLIF(BTRIM(COALESCE(CAST(ownership_change_date AS TEXT), '')), '') IS NOT NULL")
    if owner_occupant_only:
        normalized_property_address = _normalize_owner_occupant_sql("address")
        normalized_mailing_address = _normalize_owner_occupant_sql(
            "CONCAT_WS(' ', mail_address_1, mail_address_2, mail_address_3)"
        )
        status_conditions.append(
            f"""
            (
                {normalized_property_address} <> ''
                AND {normalized_mailing_address} <> ''
                AND (
                    {normalized_mailing_address} LIKE CONCAT('%%', {normalized_property_address}, '%%')
                    OR {normalized_property_address} LIKE CONCAT('%%', {normalized_mailing_address}, '%%')
                )
            )
            """
        )

    if status_conditions:
        # Combine enabled status filters with AND so multi-filter requests return
        # only properties matching every selected filter. This keeps API behavior
        # aligned with frontend filtering semantics.
        base_query += " AND (" + " AND ".join(status_conditions) + ")"
    elif sheriff_sale_only:
        base_query += " AND 1 = 0"

    return base_query, params


@lru_cache(maxsize=1)
def get_sheriff_sale_matches() -> set[str]:
    csv_files = sorted(Path(".").glob("*.csv"), reverse=True)
    if not csv_files:
        return set()

    matches: set[str] = set()

    for csv_path in csv_files:
        with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames:
                continue

            address_field = next(
                (name for name in reader.fieldnames if _normalize_text(name) == "address"),
                None,
            )
            if not address_field:
                continue

            for row in reader:
                normalized_address = _normalize_address(row.get(address_field))
                if normalized_address:
                    matches.add(normalized_address)

    return matches


def is_sheriff_sale_property(address: str | None, muni: str | None) -> bool:
    matches = get_sheriff_sale_matches()
    if not matches:
        return False
    return _normalize_address(address) in matches


@app.on_event("startup")
def prime_database_schema() -> None:
    """Apply lightweight boot-time schema checks once instead of every request."""
    try:
        conn = get_conn()
    except OperationalError:
        logger.warning(
            "Skipping startup schema checks: unable to connect to Postgres."
        )
        return

    try:
        ensure_properties_schema(conn)
        ensure_divorce_schema(conn)
        ensure_campaign_schema(conn)
    except Exception:
        logger.exception("Startup schema checks failed.")
    finally:
        conn.close()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/deals")
def get_deals(
    muni: str | None = None,
    munis: str | None = None,
    min_year_built: int | None = None,
    max_year_built: int | None = None,
    limit: int = 50,
    page: int = 1,
    distressed_only: bool = False,
    bank_owned_only: bool = False,
    sheriff_sale_only: bool = False,
    owner_occupant_only: bool = False,
    recent_divorce_only: bool = False,
    ownership_change_date_only: bool = False,
):
    conn = get_conn()
    cur = conn.cursor()
    base_query, params = _build_filtered_deals_query(
        muni=muni,
        munis=munis,
        min_year_built=min_year_built,
        max_year_built=max_year_built,
        distressed_only=distressed_only,
        bank_owned_only=bank_owned_only,
        sheriff_sale_only=sheriff_sale_only,
        owner_occupant_only=owner_occupant_only,
        recent_divorce_only=recent_divorce_only,
        ownership_change_date_only=ownership_change_date_only,
    )
    page = max(page, 1)
    limit = max(limit, 1)
    offset = (page - 1) * limit

    count_query = f"SELECT COUNT(*) FROM ({base_query}) AS filtered_properties"
    cur.execute(count_query, params)
    total = cur.fetchone()[0]

    unique_count_query = (
        f"SELECT COUNT(DISTINCT parcel_id) FROM ({base_query}) AS filtered_properties"
    )
    cur.execute(unique_count_query, params)
    unique_total = cur.fetchone()[0]

    query = f"{base_query} ORDER BY parcel_id ASC LIMIT %s OFFSET %s"
    query_params = params + [limit, offset]

    cur.execute(query, query_params)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    deals = [_row_to_deal(r) for r in rows]

    return {
        "results": deals,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "unique_total": unique_total,
            "total_pages": (total + limit - 1) // limit,
        },
    }


@app.get("/search")
def search_deals(q: str, limit: int = 50, mode: str = "all"):
    conn = get_conn()
    cur = conn.cursor()
    normalized_mode = (mode or "all").strip().lower()
    owner_name_clause, owner_name_params = _build_owner_name_clause(q)
    owner_query = _normalize_owner_search_text(q)
    where_clause = ""
    params: list[str | int] = []

    if normalized_mode == "address":
        where_clause = "address ILIKE %s"
        params = [f"%{q}%"]
    elif normalized_mode in {"owner", "owner_1", "owner_2"}:
        where_clause = """
            (
                owners_name_1 ILIKE %s
                OR owners_name_2 ILIKE %s
            )
        """
        params = [f"%{owner_query}%", f"%{owner_query}%"]
    else:
        where_clause = f"""
            (
                address ILIKE %s
                OR owners_name_1 ILIKE %s
                OR owners_name_2 ILIKE %s
                OR owners_hidename ILIKE %s
                {owner_name_clause}
            )
        """
        params = [f"%{q}%", f"%{owner_query}%", f"%{owner_query}%", f"%{owner_query}%", *owner_name_params]

    cur.execute(
        f"""
        SELECT
            parcel_id,
            address,
            muni,
            year_built,
            assessed_value,
            total_assessed_value,
            owners_hidename,
            owners_name_1,
            owners_name_2,
            ownership_change_date,
            mail_address_1,
            mail_address_2,
            mail_address_3,
            sale_type,
            recent_divorce,
            divorce_case_status,
            divorce_date_opened
        FROM properties
        WHERE TRUE
          AND {where_clause}
        ORDER BY parcel_id ASC
        LIMIT %s
        """,
        [*params, limit],
    )
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return {
        "results": [
            _row_to_deal(r)
            for r in rows
        ]
    }


def _search_rows(cur, q: str, mode: str, limit: int = 100000):
    normalized_mode = (mode or "all").strip().lower()
    owner_name_clause, owner_name_params = _build_owner_name_clause(q)
    owner_query = _normalize_owner_search_text(q)
    where_clause = ""
    params: list[str | int] = []

    if normalized_mode == "address":
        where_clause = "address ILIKE %s"
        params = [f"%{q}%"]
    elif normalized_mode in {"owner", "owner_1", "owner_2"}:
        where_clause = """
            (
                owners_name_1 ILIKE %s
                OR owners_name_2 ILIKE %s
            )
        """
        params = [f"%{owner_query}%", f"%{owner_query}%"]
    else:
        where_clause = f"""
            (
                address ILIKE %s
                OR owners_name_1 ILIKE %s
                OR owners_name_2 ILIKE %s
                OR owners_hidename ILIKE %s
                {owner_name_clause}
            )
        """
        params = [f"%{q}%", f"%{owner_query}%", f"%{owner_query}%", f"%{owner_query}%", *owner_name_params]

    cur.execute(
        f"""
        SELECT
            parcel_id,
            address,
            muni,
            year_built,
            assessed_value,
            total_assessed_value,
            owners_hidename,
            owners_name_1,
            owners_name_2,
            ownership_change_date,
            mail_address_1,
            mail_address_2,
            mail_address_3,
            sale_type,
            recent_divorce,
            divorce_case_status,
            divorce_date_opened
        FROM properties
        WHERE TRUE
          AND {where_clause}
        ORDER BY parcel_id ASC
        LIMIT %s
        """,
        [*params, limit],
    )
    return cur.fetchall()




def _row_matches_campaign_filters(row: tuple, payload: CampaignCreateRequest, selected_munis: set[str]) -> bool:
    deal = _row_to_deal(row)

    if selected_munis and str(deal.get("muni") or "").strip() not in selected_munis:
        return False

    year_built = deal.get("year_built")
    if payload.min_year_built is not None and (year_built is None or year_built < payload.min_year_built):
        return False
    if payload.max_year_built is not None and (year_built is None or year_built > payload.max_year_built):
        return False

    has_mail_match = _owner_occupant_address_match(
        deal.get("address"),
        " ".join(
            [
                str(part).strip()
                for part in [deal.get("mail_address_1"), deal.get("mail_address_2"), deal.get("mail_address_3")]
                if part and str(part).strip()
            ]
        ),
    )

    if payload.distressed_only and deal.get("sale_type") != "distressed":
        return False
    if payload.bank_owned_only and deal.get("sale_type") != "bank_owned":
        return False
    if payload.sheriff_sale_only and not bool(deal.get("is_sheriff_sale")):
        return False
    if payload.owner_occupant_only and not has_mail_match:
        return False
    if payload.recent_divorce_only and not bool(deal.get("recent_divorce")):
        return False
    if payload.ownership_change_date_only and not str(deal.get("ownership_change_date") or "").strip():
        return False

    return True


def _resolve_campaign_property_rows(cur, payload: CampaignCreateRequest) -> list[tuple]:
    selected_munis = set(_muni_filter_candidates_from_list(payload.munis or payload.muni))

    if (payload.search_query or "").strip():
        candidate_rows = _search_rows(
            cur,
            payload.search_query.strip(),
            payload.search_mode or "all",
        )
        return [
            row for row in candidate_rows
            if _row_matches_campaign_filters(row, payload, selected_munis)
        ]

    query, params = _build_filtered_deals_query(
        muni=payload.muni,
        munis=payload.munis,
        min_year_built=payload.min_year_built,
        max_year_built=payload.max_year_built,
        distressed_only=payload.distressed_only,
        bank_owned_only=payload.bank_owned_only,
        sheriff_sale_only=payload.sheriff_sale_only,
        owner_occupant_only=payload.owner_occupant_only,
        recent_divorce_only=payload.recent_divorce_only,
        ownership_change_date_only=payload.ownership_change_date_only,
    )
    cur.execute(f"{query} ORDER BY parcel_id ASC")
    return cur.fetchall()


def _normalize_campaign_parcel_ids(parcel_ids: list[str] | None) -> list[str]:
    if parcel_ids is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_parcel_id in parcel_ids:
        parcel_id = str(raw_parcel_id or "").strip()
        if not parcel_id or parcel_id in seen:
            continue
        seen.add(parcel_id)
        normalized.append(parcel_id)
    return normalized


def _chunked(values: list, chunk_size: int):
    iterator = iter(values)
    while chunk := list(islice(iterator, chunk_size)):
        yield chunk


def _dedupe_deals_by_parcel_id(deals: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for deal in deals:
        parcel_id = str(deal.get("parcel_id") or "").strip()
        if not parcel_id or parcel_id in seen:
            continue
        seen.add(parcel_id)
        deduped.append(deal)
    return deduped


def _fetch_campaign_deals(cur, campaign_id: int, *, limit: int, offset: int) -> list[dict]:
    cur.execute(
        """
        SELECT cp.parcel_id, cp.snapshot_data
        FROM campaign_properties cp
        WHERE cp.campaign_id = %s
        ORDER BY cp.id ASC
        LIMIT %s
        OFFSET %s
        """,
        [campaign_id, limit, offset],
    )
    rows = cur.fetchall()
    if not rows:
        return []

    deals: list[dict] = []
    for parcel_id, snapshot_data in rows:
        if isinstance(snapshot_data, dict):
            deals.append(snapshot_data)
            continue
        deals.append({"parcel_id": parcel_id})
    return deals


def _count_unique_campaign_mailing_addresses(cur, campaign_id: int) -> int:
    return len(_dedupe_campaign_mailing_rows(cur, campaign_id))


def _sanitize_owner_name_for_export(owner_name: str | None) -> str:
    value = str(owner_name or "").strip()
    if not value:
        return ""

    amp_index = value.find("&")
    first_owner_only = value if amp_index < 0 else value[:amp_index].rstrip()
    without_suffixes = " ".join(
        token
        for token in first_owner_only.split()
        if not re.fullmatch(r"(et|al|jr|sr|iii|iv)\.?", token, flags=re.IGNORECASE)
    ).strip()
    if not without_suffixes:
        return ""

    name_parts = without_suffixes.split()
    if len(name_parts) < 2:
        return without_suffixes

    last_name, *given_names = name_parts
    return f"{' '.join(given_names)} {last_name}".strip()


def _combine_mailing_address_parts(snapshot_data: dict | None) -> str:
    if not isinstance(snapshot_data, dict):
        return ""
    parts = [
        str(snapshot_data.get("mail_address_1") or "").strip(),
        str(snapshot_data.get("mail_address_2") or "").strip(),
        str(snapshot_data.get("mail_address_3") or "").strip(),
    ]
    return ", ".join(part for part in parts if part)


def _normalize_mailing_address_for_dedupe(mailing_address: str | None) -> str:
    text = _normalize_text(mailing_address)
    if not text:
        return ""

    # Normalize ZIP+4 (or 9-digit ZIP) to 5 digits so equivalent addresses dedupe.
    text = re.sub(r"\b(\d{5})\s*-\s*\d{4}\b", r"\1", text)
    text = re.sub(r"\b(\d{5})\d{4}\b", r"\1", text)

    # Keep only alphanumeric and spaces for stable matching.
    return re.sub(r"[^a-z0-9 ]", "", text)


def _fetch_campaign_rows_for_mailing_dedupe(cur, campaign_id: int) -> list[tuple[int, str, str]]:
    cur.execute(
        """
        SELECT cp.id, cp.snapshot_data->>'owners_name_1', cp.snapshot_data
        FROM campaign_properties cp
        WHERE cp.campaign_id = %s
        ORDER BY cp.id ASC
        """,
        [campaign_id],
    )
    rows = cur.fetchall() or []

    resolved_rows: list[tuple[int, str, str]] = []
    for row_id, owner_name_1, snapshot_data in rows:
        mailing_address = _combine_mailing_address_parts(snapshot_data)
        resolved_rows.append((row_id, owner_name_1 or "", mailing_address))
    return resolved_rows


def _dedupe_campaign_mailing_rows(cur, campaign_id: int) -> list[dict]:
    deduped: list[dict] = []
    seen_normalized_addresses: set[str] = set()

    for row_id, owner_name_1, mailing_address in _fetch_campaign_rows_for_mailing_dedupe(cur, campaign_id):
        normalized_address = _normalize_mailing_address_for_dedupe(mailing_address)
        if not normalized_address or normalized_address in seen_normalized_addresses:
            continue

        seen_normalized_addresses.add(normalized_address)
        deduped.append(
            {
                "id": row_id,
                "owner_name_1": _sanitize_owner_name_for_export(owner_name_1),
                "mailing_address": mailing_address,
            }
        )

    return deduped


def _fetch_campaign_unique_mailing_rows(cur, campaign_id: int) -> list[dict]:
    rows = _dedupe_campaign_mailing_rows(cur, campaign_id)
    return [
        {
            "owner_name_1": row["owner_name_1"],
            "mailing_address": row["mailing_address"],
        }
        for row in rows
    ]


def _fetch_property_deals_by_parcel_ids(cur, parcel_ids: list[str]) -> list[dict]:
    if not parcel_ids:
        return []

    rows: list[tuple] = []
    for chunk in _chunked(parcel_ids, 1000):
        cur.execute(
            """
            SELECT
                parcel_id,
                address,
                muni,
                year_built,
                assessed_value,
                total_assessed_value,
                owners_hidename,
                owners_name_1,
                owners_name_2,
                ownership_change_date,
                mail_address_1,
                mail_address_2,
                mail_address_3,
                sale_type,
                recent_divorce,
                divorce_case_status,
                divorce_date_opened
            FROM properties
            WHERE parcel_id = ANY(%s)
            """,
            [chunk],
        )
        rows.extend(cur.fetchall())

    rows_by_parcel_id = {row[0]: row for row in rows}
    return [
        _row_to_deal(rows_by_parcel_id[parcel_id])
        for parcel_id in parcel_ids
        if parcel_id in rows_by_parcel_id
    ]

def _resolve_campaign_identifier(cur, identifier: str) -> int | None:
    normalized = (identifier or "").strip()
    if not normalized:
        return None

    if normalized.isdigit():
        cur.execute("SELECT id FROM campaigns WHERE id = %s", [int(normalized)])
        row = cur.fetchone()
        if row:
            return row[0]

    cur.execute("SELECT id FROM campaigns WHERE slug = %s", [normalized.lower()])
    row = cur.fetchone()
    return row[0] if row else None


def _normalize_redirect_url(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme or normalized.startswith("/"):
        return normalized

    if normalized.startswith("//"):
        return f"https:{normalized}"

    return f"https://{normalized}"


@app.post("/campaigns")
def create_campaign(payload: CampaignCreateRequest):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Campaign name is required.")

    conn = get_conn()
    cur = conn.cursor()
    ensure_properties_schema(conn)
    ensure_campaign_schema(conn)

    cur.execute(
        "SELECT 1 FROM campaigns WHERE LOWER(name) = LOWER(%s) LIMIT 1",
        [name],
    )
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Campaign name already exists please choose a different name.",
        )

    base_slug = _slugify_campaign_name(name)
    slug = base_slug
    suffix = 2
    while True:
        cur.execute("SELECT 1 FROM campaigns WHERE slug = %s", [slug])
        if not cur.fetchone():
            break
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    provided_parcel_ids = _normalize_campaign_parcel_ids(payload.parcel_ids)
    if payload.parcel_ids is not None:
        snapshot_deals = _fetch_property_deals_by_parcel_ids(cur, provided_parcel_ids)
    else:
        snapshot_rows = _resolve_campaign_property_rows(cur, payload)
        snapshot_deals = [_row_to_deal(row) for row in snapshot_rows]
    snapshot_deals = _dedupe_deals_by_parcel_id(snapshot_deals)
    snapshot_parcel_ids = [deal["parcel_id"] for deal in snapshot_deals]

    tracker_slug = secrets.token_urlsafe(6)
    redirect_url = _normalize_redirect_url(payload.target_url)
    cur.execute(
        """
        INSERT INTO campaigns (name, slug, tracker_slug, redirect_url, filters_snapshot, results_count)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        RETURNING id, created_at
        """,
        [
            name,
            slug,
            tracker_slug,
            redirect_url,
            payload.model_dump_json(),
            len(snapshot_parcel_ids),
        ],
    )
    campaign_id, created_at = cur.fetchone()

    if snapshot_parcel_ids:
        cur.executemany(
            """
            INSERT INTO campaign_properties (campaign_id, parcel_id, snapshot_data)
            VALUES (%s, %s, %s::jsonb)
            """,
            [
                [
                    campaign_id,
                    deal["parcel_id"],
                    json.dumps(jsonable_encoder(deal)),
                ]
                for deal in snapshot_deals
                if deal.get("parcel_id")
            ],
        )

    conn.commit()
    cur.close()
    conn.close()

    return {
        "id": campaign_id,
        "slug": slug,
        "name": name,
        "created_at": created_at,
        "results_count": len(snapshot_parcel_ids),
        "redirect_url": redirect_url,
        "tracker_path": f"/campaigns/{slug}/tracker",
    }


@app.get("/campaigns")
def list_campaigns():
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    cur.execute(
        """
        SELECT
            c.id,
            c.name,
            c.slug,
            c.created_at,
            c.results_count,
            c.tracker_slug,
            c.redirect_url,
            COUNT(cv.id) AS visitors
        FROM campaigns c
        LEFT JOIN campaign_visits cv ON cv.campaign_id = c.id
        GROUP BY c.id
        ORDER BY c.created_at DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {
        "results": [
            {
                "id": r[0],
                "name": r[1],
                "slug": r[2],
                "created_at": r[3],
                "results_count": r[4],
                "tracker_path": f"/campaigns/{r[2] or r[0]}/tracker",
                "redirect_url": r[6],
                "visitors": r[7],
            }
            for r in rows
        ]
    }


@app.get("/campaigns/{campaign_identifier}")
def get_campaign(campaign_identifier: str, page: int = 1, limit: int = 250):
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    page = max(page, 1)
    limit = max(1, min(limit, 250))
    offset = (page - 1) * limit
    campaign_id = _resolve_campaign_identifier(cur, campaign_identifier)
    if campaign_id is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Campaign not found.")

    cur.execute(
        """
        SELECT
            c.id,
            c.name,
            c.slug,
            c.created_at,
            c.results_count,
            c.tracker_slug,
            c.redirect_url,
            c.filters_snapshot,
            COUNT(cv.id) AS visitors
        FROM campaigns c
        LEFT JOIN campaign_visits cv ON cv.campaign_id = c.id
        WHERE c.id = %s
        GROUP BY c.id
        """,
        [campaign_id],
    )
    campaign = cur.fetchone()
    if not campaign:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Campaign not found.")

    cur.execute(
        "SELECT COUNT(*) FROM campaign_properties WHERE campaign_id = %s",
        [campaign_id],
    )
    total = cur.fetchone()[0]
    unique_mailing_addresses_count = _count_unique_campaign_mailing_addresses(cur, campaign_id)
    deals = _fetch_campaign_deals(cur, campaign_id, limit=limit, offset=offset)

    cur.close()
    conn.close()
    return {
        "id": campaign[0],
        "name": campaign[1],
        "slug": campaign[2],
        "created_at": campaign[3],
        "results_count": campaign[4],
        "tracker_path": f"/campaigns/{campaign[2] or campaign[0]}/tracker",
        "redirect_url": campaign[6],
        "filters_snapshot": campaign[7] or {},
        "visitors": campaign[8],
        "unique_mailing_addresses_count": unique_mailing_addresses_count,
        "deals": deals,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": max((total + limit - 1) // limit, 1),
        },
    }


@app.get("/campaigns/{campaign_identifier}/mailing-addresses")
def get_campaign_mailing_addresses(campaign_identifier: str):
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    campaign_id = _resolve_campaign_identifier(cur, campaign_identifier)
    if campaign_id is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Campaign not found.")

    mailing_rows = _fetch_campaign_unique_mailing_rows(cur, campaign_id)
    cur.close()
    conn.close()
    return {
        "count": len(mailing_rows),
        "rows": mailing_rows,
    }


@app.delete("/campaigns/{campaign_identifier}")
def delete_campaign(campaign_identifier: str):
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    campaign_id = _resolve_campaign_identifier(cur, campaign_identifier)
    if campaign_id is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Campaign not found.")

    cur.execute("DELETE FROM campaign_properties WHERE campaign_id = %s", [campaign_id])
    deleted_snapshot_rows = cur.rowcount
    cur.execute("DELETE FROM campaign_visits WHERE campaign_id = %s", [campaign_id])
    cur.execute("DELETE FROM campaigns WHERE id = %s", [campaign_id])
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True, "deleted_snapshots": deleted_snapshot_rows}


@app.patch("/campaigns/{campaign_identifier}")
def update_campaign(campaign_identifier: str, payload: CampaignUpdateRequest):
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    campaign_id = _resolve_campaign_identifier(cur, campaign_identifier)
    if campaign_id is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Campaign not found.")

    redirect_url = _normalize_redirect_url(payload.redirect_url)
    cur.execute(
        """
        UPDATE campaigns
        SET redirect_url = %s
        WHERE id = %s
        """,
        [redirect_url, campaign_id],
    )
    conn.commit()
    cur.close()
    conn.close()
    return {
        "ok": True,
        "id": campaign_id,
        "redirect_url": redirect_url,
    }


def _track_campaign_visit_and_resolve_destination(campaign_identifier: str, request: Request) -> str:
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    campaign_id = _resolve_campaign_identifier(cur, campaign_identifier)
    if campaign_id is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Tracker not found.")
    cur.execute(
        "SELECT id, slug, redirect_url FROM campaigns WHERE id = %s",
        [campaign_id],
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Tracker not found.")
    campaign_id, campaign_slug, redirect_url = row

    forwarded = request.headers.get("x-forwarded-for", "")
    ip_address = (forwarded.split(",")[0].strip() if forwarded else "") or (
        request.client.host if request.client else ""
    )
    cur.execute(
        """
        INSERT INTO campaign_visits (campaign_id, ip_address, user_agent, referer)
        VALUES (%s, %s, %s, %s)
        """,
        [
            campaign_id,
            ip_address,
            request.headers.get("user-agent"),
            request.headers.get("referer"),
        ],
    )
    conn.commit()
    cur.close()
    conn.close()
    destination = redirect_url or f"/campaigns/{campaign_slug or campaign_id}"
    return destination


@app.get("/campaigns/{campaign_identifier}/tracker", response_class=HTMLResponse)
def tracker_redirect(campaign_identifier: str, request: Request):
    destination = _track_campaign_visit_and_resolve_destination(campaign_identifier, request)
    return HTMLResponse(
        content=f"""
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8" />
            <meta http-equiv="refresh" content="0; url={destination}" />
            <title>Redirecting…</title>
          </head>
          <body>
            <p>Redirecting…</p>
            <p><a href="{destination}">Continue</a></p>
            <script>window.location.replace("{destination}");</script>
          </body>
        </html>
        """
    )


@app.get("/t/{tracker_slug}", response_class=HTMLResponse)
def tracker_redirect_by_slug(tracker_slug: str, request: Request):
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    cur.execute(
        "SELECT slug, id FROM campaigns WHERE tracker_slug = %s",
        [tracker_slug],
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Tracker not found.")
    destination = _track_campaign_visit_and_resolve_destination(row[0] or str(row[1]), request)
    return HTMLResponse(
        content=f"""
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8" />
            <meta http-equiv="refresh" content="0; url={destination}" />
            <title>Redirecting…</title>
          </head>
          <body>
            <p>Redirecting…</p>
            <p><a href="{destination}">Continue</a></p>
            <script>window.location.replace("{destination}");</script>
          </body>
        </html>
        """
    )


@app.get("/divorce-cases")
def get_divorce_cases(
    status: str | None = None,
    limit: int = 100,
    page: int = 1,
):
    conn = get_conn()
    ensure_divorce_schema(conn)
    cur = conn.cursor()

    base_query = """
        SELECT
            case_number,
            case_participants,
            case_category,
            date_opened,
            status
        FROM divorce_cases
        WHERE 1 = 1
    """
    params: list[str] = []

    if status:
        base_query += " AND LOWER(COALESCE(status, '')) = LOWER(%s)"
        params.append(status)

    page = max(page, 1)
    limit = max(limit, 1)
    offset = (page - 1) * limit

    count_query = f"SELECT COUNT(*) FROM ({base_query}) AS filtered_cases"
    cur.execute(count_query, params)
    total = cur.fetchone()[0]

    query = f"{base_query} ORDER BY date_opened DESC NULLS LAST, case_number ASC LIMIT %s OFFSET %s"
    cur.execute(query, [*params, limit, offset])
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return {
        "results": [
            {
                "case_number": r[0],
                "case_participants": r[1],
                "case_category": r[2],
                "date_opened": r[3],
                "status": r[4],
            }
            for r in rows
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        },
    }
