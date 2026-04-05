import math
import re
from db import get_conn


def compute_score(p):

    def f(x):
        return float(x) if x is not None else 0.0

    assessed = f(p["assessed_value"])
    sale_price = f(p["sale_price"])
    year_built = p["year_built"] or 2000
    sqft = f(p["sqft"])

    # -------------------------
    # 1. VALUE DISCOUNT
    # -------------------------
    if assessed > 0 and sale_price > 0:
        discount = (assessed - sale_price) / assessed
    else:
        discount = 0.0

    value_score = max(0.0, min(discount * 3, 2.5))

    # -------------------------
    # 2. DISTRESS BONUS
    # -------------------------
    owner_1 = (p["owners_name_1"] or "").lower()
    owner_2 = (p["owners_name_2"] or "").lower()
    distress_score = 0.0

    # owner-name distress heuristic (sale type no longer used)
    has_secretary = "secretary" in owner_1 or "secretary" in owner_2
    has_bank_word = bool(re.search(r"\bbank\b", owner_1)) or bool(re.search(r"\bbank\b", owner_2))

    if has_secretary or has_bank_word:
        distress_score += 2.0

    # -------------------------
    # 3. QUALITY SCORE
    # -------------------------
    age = 2026 - year_built
    age_penalty = min(age / 100, 1.0)

    size_factor = min(sqft / 3000, 1.0)

    quality_score = size_factor - age_penalty
    quality_score = max(-1.0, min(quality_score, 1.0))

    # -------------------------
    # FINAL SCORE
    # -------------------------
    score = float(value_score + distress_score + quality_score)

    return round(max(score, 0.0), 3)


def run():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            parcel_id,
            assessed_value,
            sale_price,
            sale_type,
            sale_validity_code,
            owners_name_1,
            owners_name_2,
            year_built,
            sqft_living_area
        FROM properties
    """)

    rows = cur.fetchall()

    for r in rows:
        parcel_id = r[0]

        p = {
            "assessed_value": r[1],
            "sale_price": r[2],
            "sale_type": r[3],
            "sale_validity_code": r[4],
            "owners_name_1": r[5],
            "owners_name_2": r[6],
            "year_built": r[7],
            "sqft": r[8],
        }

        score = compute_score(p)

        cur.execute("""
            UPDATE properties
            SET deal_score = %s
            WHERE parcel_id = %s
        """, (score, parcel_id))

    conn.commit()
    cur.close()
    conn.close()

    print(f"Scored {len(rows)} properties")


if __name__ == "__main__":
    run()
