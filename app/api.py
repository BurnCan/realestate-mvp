import csv
import re
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import ensure_properties_schema, get_conn

app = FastAPI()


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_address(value: str | None) -> str:
    text = _normalize_text(value)
    # Keep only alphanumeric and spaces for more reliable matching across systems.
    return re.sub(r"[^a-z0-9 ]", "", text)


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
    min_score: float = 0,
    min_year_built: int | None = None,
    max_year_built: int | None = None,
    limit: int = 50,
    page: int = 1,
    distressed_only: bool = False,
    bank_owned_only: bool = False,
    sheriff_sale_only: bool = False,
):
    conn = get_conn()
    ensure_properties_schema(conn)
    cur = conn.cursor()

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
            deal_score,
            sale_type
        FROM properties
        WHERE deal_score IS NOT NULL
    """

    params = []

    muni_candidates = _muni_filter_candidates(muni)
    if muni_candidates:
        if len(muni_candidates) == 1:
            base_query += " AND TRIM(COALESCE(muni, '')) = %s"
            params.append(muni_candidates[0])
        else:
            base_query += " AND TRIM(COALESCE(muni, '')) = ANY(%s)"
            params.append(muni_candidates)

    if min_score is not None:
        base_query += " AND deal_score >= %s"
        params.append(min_score)

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

    if status_conditions:
        base_query += " AND (" + " OR ".join(status_conditions) + ")"
    elif sheriff_sale_only:
        # Sheriff sale filter selected but no sheriff addresses were found.
        base_query += " AND 1 = 0"
    page = max(page, 1)
    limit = max(limit, 1)
    offset = (page - 1) * limit

    count_query = f"SELECT COUNT(*) FROM ({base_query}) AS filtered_properties"
    cur.execute(count_query, params)
    total = cur.fetchone()[0]

    query = f"{base_query} ORDER BY deal_score DESC LIMIT %s OFFSET %s"
    query_params = params + [limit, offset]

    cur.execute(query, query_params)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    deals = [
        {
            "parcel_id": r[0],
            "address": r[1],
            "muni": r[2],
            "year_built": r[3],
            "assessed_value": r[4],
            "total_assessed_value": r[5],
            "owners_hidename": r[6],
            "owners_name_1": r[7],
            "owners_name_2": r[8],
            "ownership_change_date": r[9],
            "mail_address_1": r[10],
            "mail_address_2": r[11],
            "mail_address_3": r[12],
            "deal_score": r[13],
            "sale_type": r[14],
            "is_sheriff_sale": is_sheriff_sale_property(r[1], r[2]),
        }
        for r in rows
    ]

    return {
        "results": deals,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        },
    }


@app.get("/search")
def search_deals(q: str, limit: int = 50, mode: str = "all"):
    conn = get_conn()
    ensure_properties_schema(conn)
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
            deal_score,
            sale_type
        FROM properties
        WHERE deal_score IS NOT NULL
          AND {where_clause}
        ORDER BY deal_score DESC
        LIMIT %s
        """,
        [*params, limit],
    )
    rows = cur.fetchall()

    cur.close()
    conn.close()

    return {
        "results": [
            {
                "parcel_id": r[0],
                "address": r[1],
                "muni": r[2],
                "year_built": r[3],
                "assessed_value": r[4],
                "total_assessed_value": r[5],
                "owners_hidename": r[6],
                "owners_name_1": r[7],
                "owners_name_2": r[8],
                "ownership_change_date": r[9],
                "mail_address_1": r[10],
                "mail_address_2": r[11],
                "mail_address_3": r[12],
                "deal_score": r[13],
                "sale_type": r[14],
                "is_sheriff_sale": is_sheriff_sale_property(r[1], r[2]),
            }
            for r in rows
        ]
    }
