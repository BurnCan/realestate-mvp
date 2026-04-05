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
def get_deals(muni: str | None = None, min_score: float = 0, limit: int = 50):
    conn = get_conn()
    ensure_properties_schema(conn)
    cur = conn.cursor()

    query = """
        SELECT
            parcel_id,
            address,
            muni,
            assessed_value,
            total_assessed_value,
            owners_name_1,
            owners_name_2,
            deal_score,
            sale_type
        FROM properties
        WHERE deal_score IS NOT NULL
    """

    params = []

    if muni:
        query += " AND muni = %s"
        params.append(muni)

    if min_score is not None:
        query += " AND deal_score >= %s"
        params.append(min_score)

    query += " ORDER BY deal_score DESC LIMIT %s"
    params.append(limit)

    cur.execute(query, params)
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
                "owners_name_1": r[5],
                "owners_name_2": r[6],
                "deal_score": r[7],
                "sale_type": r[8],
            }
            for r in rows
        ]
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
                "owners_name_1": r[5],
                "owners_name_2": r[6],
                "deal_score": r[7],
                "sale_type": r[8],
            }
            for r in rows
        ]
    }
