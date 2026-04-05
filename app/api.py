from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import get_conn

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
    muni: str = None,
    min_score: float = 0,
    limit: int = 50,
):
    conn = get_conn()
    cur = conn.cursor()

    query = """
        SELECT parcel_id, address, muni, assessed_value, deal_score, sale_type
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
                "deal_score": r[4],
                "sale_type": r[5],
            }
            for r in rows
        ]
    }
