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


@lru_cache(maxsize=1)
def get_sheriff_sale_matches() -> set[tuple[str, str]]:
    sheriff_files = sorted(Path(".").glob("sheriff_sale_*.csv"), reverse=True)
    if not sheriff_files:
        return set()

    latest_file = sheriff_files[0]
    matches: set[tuple[str, str]] = set()

    with latest_file.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            normalized_address = _normalize_address(row.get("Address"))
            normalized_muni = _normalize_text(row.get("Municipality"))
            if not normalized_address or not normalized_muni:
                continue
            matches.add((normalized_address, normalized_muni))

    return matches


def is_sheriff_sale_property(address: str | None, muni: str | None) -> bool:
    matches = get_sheriff_sale_matches()
    if not matches:
        return False
    return (_normalize_address(address), _normalize_text(muni)) in matches

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
    limit: int = 50,
    page: int = 1,
    distressed_only: bool = False,
    bank_owned_only: bool = False,
):
    conn = get_conn()
    ensure_properties_schema(conn)
    cur = conn.cursor()

    base_query = """
        SELECT
            parcel_id,
            address,
            muni,
            assessed_value,
            total_assessed_value,
            owners_hidename,
            owners_name_1,
            owners_name_2,
            mail_address_1,
            mail_address_2,
            mail_address_3,
            deal_score,
            sale_type
        FROM properties
        WHERE deal_score IS NOT NULL
    """

    params = []

    if muni:
        base_query += " AND muni = %s"
        params.append(muni)

    if min_score is not None:
        base_query += " AND deal_score >= %s"
        params.append(min_score)

    if distressed_only:
        base_query += """
            AND (
                LOWER(COALESCE(owners_name_1, '')) LIKE '%%secretary%%'
                OR LOWER(COALESCE(owners_name_2, '')) LIKE '%%secretary%%'
            )
            AND NOT (
                LOWER(COALESCE(owners_name_1, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
                OR LOWER(COALESCE(owners_name_2, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
            )
        """

    if bank_owned_only:
        base_query += """
            AND (
                LOWER(COALESCE(owners_name_1, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
                OR LOWER(COALESCE(owners_name_2, '')) ~ '(^|[^a-z])bank([^a-z]|$)'
            )
        """

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
            "assessed_value": r[3],
            "total_assessed_value": r[4],
            "owners_hidename": r[5],
            "owners_name_1": r[6],
            "owners_name_2": r[7],
            "mail_address_1": r[8],
            "mail_address_2": r[9],
            "mail_address_3": r[10],
            "deal_score": r[11],
            "sale_type": r[12],
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
def search_deals(q: str, limit: int = 50):
    conn = get_conn()
    ensure_properties_schema(conn)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            parcel_id,
            address,
            muni,
            assessed_value,
            total_assessed_value,
            owners_hidename,
            owners_name_1,
            owners_name_2,
            mail_address_1,
            mail_address_2,
            mail_address_3,
            deal_score,
            sale_type
        FROM properties
        WHERE deal_score IS NOT NULL
          AND address ILIKE %s
        ORDER BY deal_score DESC
        LIMIT %s
        """,
        (f"%{q}%", limit),
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
                "assessed_value": r[3],
                "total_assessed_value": r[4],
                "owners_hidename": r[5],
                "owners_name_1": r[6],
                "owners_name_2": r[7],
                "mail_address_1": r[8],
                "mail_address_2": r[9],
                "mail_address_3": r[10],
                "deal_score": r[11],
                "sale_type": r[12],
                "is_sheriff_sale": is_sheriff_sale_property(r[1], r[2]),
            }
            for r in rows
        ]
    }
