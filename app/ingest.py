import requests

from db import ensure_properties_schema, get_conn
from parser import parse

URL = "https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer/0/query"
LIMIT = 500


def fetch(offset):
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": LIMIT,
    }

    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("features", [])


def upsert(cur, p):
    cur.execute(
        """
        INSERT INTO properties (
            parcel_id, address,
            muni, neighborhood,
            assessed_value, total_assessed_value, owners_hidename, owners_name_1, owners_name_2, land_value, building_value,
            sale_price, sale_date, sale_type, sale_validity_code,
            sqft_living_area, bedrooms, bathrooms, half_baths, stories, year_built
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (parcel_id)
        DO UPDATE SET
            address = EXCLUDED.address,
            muni = EXCLUDED.muni,
            neighborhood = EXCLUDED.neighborhood,
            assessed_value = EXCLUDED.assessed_value,
            total_assessed_value = EXCLUDED.total_assessed_value,
            owners_hidename = EXCLUDED.owners_hidename,
            owners_name_1 = EXCLUDED.owners_name_1,
            owners_name_2 = EXCLUDED.owners_name_2,
            land_value = EXCLUDED.land_value,
            building_value = EXCLUDED.building_value,
            sale_price = EXCLUDED.sale_price,
            sale_date = EXCLUDED.sale_date,
            sqft_living_area = EXCLUDED.sqft_living_area,
            bedrooms = EXCLUDED.bedrooms,
            bathrooms = EXCLUDED.bathrooms,
            year_built = EXCLUDED.year_built,
            sale_type = EXCLUDED.sale_type,
            sale_validity_code = EXCLUDED.sale_validity_code,
            half_baths = EXCLUDED.half_baths,
            stories = EXCLUDED.stories,
            updated_at = NOW()
        """,
        (
            p["parcel_id"],
            p["address"],
            p["muni"],
            p["neighborhood"],
            p["assessed_value"],
            p["total_assessed_value"],
            p["owners_hidename"],
            p["owners_name_1"],
            p["owners_name_2"],
            p["land_value"],
            p["building_value"],
            p["sale_price"],
            p["sale_date"],
            p["sale_type"],
            p["sale_validity_code"],
            p["sqft"],
            p["bedrooms"],
            p["bathrooms"],
            p["half_baths"],
            p["stories"],
            p["year_built"],
        ),
    )


def run():
    conn = get_conn()
    ensure_properties_schema(conn)
    cur = conn.cursor()

    offset = 0
    total = 0

    while True:
        batch = fetch(offset)

        if not batch:
            break

        for f in batch:
            p = parse(f)

            if not p["parcel_id"]:
                continue

            upsert(cur, p)
            total += 1

        conn.commit()
        print(f"Processed: {total}")

        offset += LIMIT

    cur.close()
    conn.close()


if __name__ == "__main__":
    run()
