import math
from db import get_conn


def compute_score(p):

    def f(x):
        return float(x) if x is not None else 0.0

    assessed = f(p["assessed_value"])
    sale_price = f(p["sale_price"])
    year_built = p["year_built"] or 2000
    sqft = f(p["sqft"])

    sale_type = (p["sale_type"] or "").lower()
    validity = (p["sale_validity_code"] or "").lower()

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
    sale_type = str(p["sale_type"] or "").strip()

    distress_score = 0.0

    # -------------------------
    # PRIMARY SIGNAL (strong)
    # -------------------------
    if sale_type == "3":
        distress_score += 2.0

    # -------------------------
    # SECONDARY SIGNAL (weak)
    # -------------------------
    elif sale_type == "1":
        distress_score += 0.5

    # -------------------------
    # UNKNOWN DATA (neutral, but slightly penalize confidence)
    # -------------------------
    elif sale_type == "":
        distress_score += 0.2

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
            "year_built": r[5],
            "sqft": r[6],
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
