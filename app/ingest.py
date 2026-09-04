import requests

from app.db import ensure_properties_schema, get_conn
from app.parser import parse

URL = "https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer/0/query"
LIMIT = 500

UPSERT_COLUMNS = [
    "parcel_id",
    "address",
    "muni",
    "neighborhood",
    "assessed_value",
    "total_assessed_value",
    "owners_hidename",
    "owners_name_1",
    "owners_name_2",
    "mail_address_1",
    "mail_address_2",
    "mail_address_3",
    "land_value",
    "building_value",
    "sale_price",
    "sale_date",
    "sale_type",
    "sale_validity_code",
    "sqft_living_area",
    "bedrooms",
    "bathrooms",
    "half_baths",
    "stories",
    "year_built",
    "objectid",
    "cama_id",
    "map",
    "block",
    "lot",
    "schdist",
    "flag",
    "gis_acreage",
    "asmt_acreage",
    "deed",
    "luc",
    "total_value",
    "bldg_value",
    "building_assessment",
    "land_assessment",
    "note_3_gis_code",
    "flag_1_319_515",
    "flag_2_lerta",
    "flag_3_hmstd",
    "flag_4_fmstd",
    "flag_5_act_43",
    "flag_6_act_66",
    "flag_7_act_149",
    "flag_9_bill",
    "flag_10_koz",
    "number_of_cards",
    "number_of_stories",
    "exterior",
    "basement",
    "building_style",
    "number_of_bedrooms",
    "number_of_baths",
    "number_half_baths",
    "total_rooms",
    "swimming_pool",
    "comm_cards",
    "commercial_structure_type",
    "improvement_name",
    "com_year_built",
    "res_year_built",
    "notecd1",
    "shape_st_area",
    "shape_st_length",
]

UPDATE_COLUMNS = [c for c in UPSERT_COLUMNS if c != "parcel_id"]

INSERT_SQL = f"""
    INSERT INTO properties ({', '.join(UPSERT_COLUMNS)})
    VALUES ({', '.join(['%s'] * len(UPSERT_COLUMNS))})
    ON CONFLICT (parcel_id)
    DO UPDATE SET
        {', '.join(f'{col} = EXCLUDED.{col}' for col in UPDATE_COLUMNS)},
        ownership_change_date = CASE
            WHEN
                COALESCE(properties.owners_name_1, '') IS DISTINCT FROM COALESCE(EXCLUDED.owners_name_1, '')
                OR COALESCE(properties.owners_name_2, '') IS DISTINCT FROM COALESCE(EXCLUDED.owners_name_2, '')
            THEN CURRENT_DATE
            ELSE properties.ownership_change_date
        END,
        updated_at = NOW()
"""


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
        SELECT owners_name_1, owners_name_2
        FROM properties
        WHERE parcel_id = %s
        """,
        (p["parcel_id"],),
    )
    existing_owner_row = cur.fetchone()

    ownership_changed = False
    if existing_owner_row:
        existing_owner_1, existing_owner_2 = existing_owner_row
        new_owner_1 = p.get("owners_name_1")
        new_owner_2 = p.get("owners_name_2")

        ownership_changed = (existing_owner_1 or "") != (new_owner_1 or "") or (
            existing_owner_2 or ""
        ) != (new_owner_2 or "")

    cur.execute(INSERT_SQL, tuple(p.get(col) for col in UPSERT_COLUMNS))
    return ownership_changed


def run():
    conn = get_conn()
    ensure_properties_schema(conn)
    cur = conn.cursor()

    offset = 0
    total = 0
    ownership_changes = 0

    while True:
        batch = fetch(offset)

        if not batch:
            break

        for f in batch:
            p = parse(f)

            if not p["parcel_id"]:
                continue

            if upsert(cur, p):
                ownership_changes += 1
            total += 1

        conn.commit()
        print(f"Processed: {total}")
        print(f"Ownership changes detected so far: {ownership_changes}")

        offset += LIMIT

    cur.close()
    conn.close()
    print(f"Ownership changes detected: {ownership_changes}")


if __name__ == "__main__":
    run()
