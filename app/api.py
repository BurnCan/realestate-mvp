from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import ensure_properties_schema, get_conn

app = FastAPI()

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
                OR LOWER(COALESCE(owners_name_1, '')) LIKE '%%bank%%'
                OR LOWER(COALESCE(owners_name_2, '')) LIKE '%%secretary%%'
                OR LOWER(COALESCE(owners_name_2, '')) LIKE '%%bank%%'
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
                "deal_score": r[8],
                "sale_type": r[9],
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
                "deal_score": r[8],
                "sale_type": r[9],
            }
            for r in rows
        ]
    }
