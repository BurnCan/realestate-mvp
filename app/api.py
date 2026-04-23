import csv
import logging
import re
import secrets
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
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
    muni: str | None = None
    munis: str | None = None
    min_score: float = 0
    min_year_built: int | None = None
    max_year_built: int | None = None
    distressed_only: bool = False
    bank_owned_only: bool = False
    sheriff_sale_only: bool = False
    owner_occupant_only: bool = False
    recent_divorce_only: bool = False
    search_query: str | None = None
    search_mode: str = "all"


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
        "deal_score": row[13],
        "sale_type": row[14],
        "recent_divorce": row[15],
        "divorce_case_status": row[16],
        "divorce_date_opened": row[17],
        "is_sheriff_sale": is_sheriff_sale_property(row[1], row[2]),
    }


def _build_filtered_deals_query(
    *,
    muni: str | None = None,
    munis: str | None = None,
    min_score: float = 0,
    min_year_built: int | None = None,
    max_year_built: int | None = None,
    distressed_only: bool = False,
    bank_owned_only: bool = False,
    sheriff_sale_only: bool = False,
    owner_occupant_only: bool = False,
    recent_divorce_only: bool = False,
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
            deal_score,
            sale_type,
            recent_divorce,
            divorce_case_status,
            divorce_date_opened
        FROM properties
        WHERE deal_score IS NOT NULL
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
    if recent_divorce_only:
        status_conditions.append("COALESCE(recent_divorce, FALSE) IS TRUE")
    if owner_occupant_only:
        status_conditions.append(
            """
            (
                LOWER(TRIM(COALESCE(address, ''))) <> ''
                AND LOWER(TRIM(CONCAT_WS(' ', mail_address_1, mail_address_2, mail_address_3))) <> ''
                AND (
                    LOWER(TRIM(CONCAT_WS(' ', mail_address_1, mail_address_2, mail_address_3)))
                        LIKE CONCAT('%%', LOWER(TRIM(COALESCE(address, ''))), '%%')
                    OR LOWER(TRIM(COALESCE(address, '')))
                        LIKE CONCAT('%%', LOWER(TRIM(CONCAT_WS(' ', mail_address_1, mail_address_2, mail_address_3))), '%%')
                )
            )
            """
        )

    if status_conditions:
        base_query += " AND (" + " OR ".join(status_conditions) + ")"
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
    min_score: float = 0,
    min_year_built: int | None = None,
    max_year_built: int | None = None,
    limit: int = 50,
    page: int = 1,
    distressed_only: bool = False,
    bank_owned_only: bool = False,
    sheriff_sale_only: bool = False,
    owner_occupant_only: bool = False,
    recent_divorce_only: bool = False,
):
    conn = get_conn()
    cur = conn.cursor()
    base_query, params = _build_filtered_deals_query(
        muni=muni,
        munis=munis,
        min_score=min_score,
        min_year_built=min_year_built,
        max_year_built=max_year_built,
        distressed_only=distressed_only,
        bank_owned_only=bank_owned_only,
        sheriff_sale_only=sheriff_sale_only,
        owner_occupant_only=owner_occupant_only,
        recent_divorce_only=recent_divorce_only,
    )
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

    deals = [_row_to_deal(r) for r in rows]

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
            sale_type,
            recent_divorce,
            divorce_case_status,
            divorce_date_opened
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
            deal_score,
            sale_type,
            recent_divorce,
            divorce_case_status,
            divorce_date_opened
        FROM properties
        WHERE deal_score IS NOT NULL
          AND {where_clause}
        ORDER BY deal_score DESC
        LIMIT %s
        """,
        [*params, limit],
    )
    return cur.fetchall()


@app.post("/campaigns")
def create_campaign(payload: CampaignCreateRequest):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Campaign name is required.")

    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)

    if payload.search_query and payload.search_query.strip():
        rows = _search_rows(cur, payload.search_query.strip(), payload.search_mode, limit=100000)
        results = [_row_to_deal(r) for r in rows]
        filtered = []
        muni_candidates = sorted({
            *_muni_filter_candidates(payload.muni),
            *_muni_filter_candidates_from_list(payload.munis),
        })
        for deal in results:
            if muni_candidates and str((deal.get("muni") or "")).strip() not in muni_candidates:
                continue
            score = deal.get("deal_score")
            if score is None or score < payload.min_score:
                continue
            year_built = deal.get("year_built")
            if payload.min_year_built is not None and (year_built is None or year_built < payload.min_year_built):
                continue
            if payload.max_year_built is not None and (year_built is None or year_built > payload.max_year_built):
                continue
            filtered.append(deal)
        deals = filtered
    else:
        query, params = _build_filtered_deals_query(
            muni=payload.muni,
            munis=payload.munis,
            min_score=payload.min_score,
            min_year_built=payload.min_year_built,
            max_year_built=payload.max_year_built,
            distressed_only=payload.distressed_only,
            bank_owned_only=payload.bank_owned_only,
            sheriff_sale_only=payload.sheriff_sale_only,
            owner_occupant_only=payload.owner_occupant_only,
            recent_divorce_only=payload.recent_divorce_only,
        )
        cur.execute(f"{query} ORDER BY deal_score DESC")
        deals = [_row_to_deal(r) for r in cur.fetchall()]

    tracker_slug = secrets.token_urlsafe(6)
    cur.execute(
        """
        INSERT INTO campaigns (name, tracker_slug, filters_snapshot, results_count)
        VALUES (%s, %s, %s::jsonb, %s)
        RETURNING id, created_at
        """,
        [
            name,
            tracker_slug,
            payload.model_dump_json(),
            len(deals),
        ],
    )
    campaign_id, created_at = cur.fetchone()

    for deal in deals:
        cur.execute(
            """
            INSERT INTO campaign_properties (campaign_id, parcel_id)
            VALUES (%s, %s)
            """,
            [campaign_id, deal.get("parcel_id")],
        )

    conn.commit()
    cur.close()
    conn.close()

    return {
        "id": campaign_id,
        "name": name,
        "created_at": created_at,
        "results_count": len(deals),
        "tracker_path": f"/t/{tracker_slug}",
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
            c.created_at,
            c.results_count,
            c.tracker_slug,
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
                "created_at": r[2],
                "results_count": r[3],
                "tracker_path": f"/t/{r[4]}",
                "visitors": r[5],
            }
            for r in rows
        ]
    }


@app.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int):
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    cur.execute(
        """
        SELECT c.id, c.name, c.created_at, c.results_count, c.tracker_slug, COUNT(cv.id) AS visitors
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
        """
        SELECT
            p.parcel_id,
            p.address,
            p.muni,
            p.year_built,
            p.assessed_value,
            p.total_assessed_value,
            p.owners_hidename,
            p.owners_name_1,
            p.owners_name_2,
            p.ownership_change_date,
            p.mail_address_1,
            p.mail_address_2,
            p.mail_address_3,
            p.deal_score,
            p.sale_type,
            p.recent_divorce,
            p.divorce_case_status,
            p.divorce_date_opened
        FROM campaign_properties cp
        JOIN properties p ON p.parcel_id = cp.parcel_id
        WHERE cp.campaign_id = %s
        ORDER BY cp.id ASC
        """,
        [campaign_id],
    )
    deals = [_row_to_deal(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return {
        "id": campaign[0],
        "name": campaign[1],
        "created_at": campaign[2],
        "results_count": campaign[3],
        "tracker_path": f"/t/{campaign[4]}",
        "visitors": campaign[5],
        "results": deals,
    }


@app.get("/t/{tracker_slug}", response_class=HTMLResponse)
def tracker_redirect(tracker_slug: str, request: Request):
    conn = get_conn()
    cur = conn.cursor()
    ensure_campaign_schema(conn)
    cur.execute(
        "SELECT id FROM campaigns WHERE tracker_slug = %s",
        [tracker_slug],
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Tracker not found.")
    campaign_id = row[0]

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
    destination = f"/campaigns/{campaign_id}"
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
            <p>Redirecting to campaign page…</p>
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
