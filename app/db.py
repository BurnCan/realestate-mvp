import os

import psycopg2

DB_CONFIG = {
    "dbname": "realestate",
    "user": "realuser",
    "password": "password",
    "host": "localhost",
    "port": 5432,
    # Keep startup responsive when Postgres is down or unreachable.
    "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "3")),
}

REQUIRED_PROPERTY_COLUMNS = {
    "parcel_id": "TEXT UNIQUE",
    "address": "TEXT",
    "muni": "TEXT",
    "neighborhood": "TEXT",
    "assessed_value": "BIGINT",
    "total_assessed_value": "BIGINT",
    "owners_hidename": "TEXT",
    "owners_name_1": "TEXT",
    "owners_name_2": "TEXT",
    "ownership_change_date": "DATE",
    "recent_divorce": "BOOLEAN DEFAULT FALSE",
    "divorce_case_status": "TEXT",
    "divorce_date_opened": "DATE",
    "mail_address_1": "TEXT",
    "mail_address_2": "TEXT",
    "mail_address_3": "TEXT",
    "land_value": "BIGINT",
    "building_value": "BIGINT",
    "sale_price": "BIGINT",
    "sale_date": "TIMESTAMP",
    "sale_type": "TEXT",
    "sale_validity_code": "TEXT",
    "sqft_living_area": "NUMERIC",
    "bedrooms": "NUMERIC",
    "bathrooms": "NUMERIC",
    "half_baths": "NUMERIC",
    "stories": "NUMERIC",
    "year_built": "INT",
    "deal_score": "NUMERIC",
    "updated_at": "TIMESTAMP DEFAULT NOW()",
    # Raw ArcGIS attribute coverage
    "objectid": "BIGINT",
    "cama_id": "TEXT",
    "map": "TEXT",
    "block": "TEXT",
    "lot": "TEXT",
    "schdist": "TEXT",
    "flag": "TEXT",
    "gis_acreage": "NUMERIC",
    "asmt_acreage": "NUMERIC",
    "deed": "TEXT",
    "luc": "TEXT",
    "total_value": "BIGINT",
    "bldg_value": "BIGINT",
    "building_assessment": "BIGINT",
    "land_assessment": "BIGINT",
    "note_3_gis_code": "TEXT",
    "flag_1_319_515": "TEXT",
    "flag_2_lerta": "TEXT",
    "flag_3_hmstd": "TEXT",
    "flag_4_fmstd": "TEXT",
    "flag_5_act_43": "TEXT",
    "flag_6_act_66": "TEXT",
    "flag_7_act_149": "TEXT",
    "flag_9_bill": "TEXT",
    "flag_10_koz": "TEXT",
    "number_of_cards": "NUMERIC",
    "number_of_stories": "NUMERIC",
    "exterior": "TEXT",
    "basement": "TEXT",
    "building_style": "TEXT",
    "number_of_bedrooms": "NUMERIC",
    "number_of_baths": "NUMERIC",
    "number_half_baths": "NUMERIC",
    "total_rooms": "NUMERIC",
    "swimming_pool": "TEXT",
    "comm_cards": "NUMERIC",
    "commercial_structure_type": "TEXT",
    "improvement_name": "TEXT",
    "com_year_built": "INT",
    "res_year_built": "INT",
    "notecd1": "TEXT",
    "shape_st_area": "NUMERIC",
    "shape_st_length": "NUMERIC",
}

REQUIRED_DIVORCE_COLUMNS = {
    "case_number": "TEXT UNIQUE",
    "case_participants": "TEXT",
    "case_category": "TEXT",
    "date_opened": "DATE",
    "status": "TEXT",
    "updated_at": "TIMESTAMP DEFAULT NOW()",
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def ensure_properties_schema(conn):
    """
    Keep older databases compatible with current ingest/API expectations.
    This avoids runtime 500s when new columns are introduced before a manual migration.
    """
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS properties (
            id SERIAL PRIMARY KEY,
            parcel_id TEXT UNIQUE,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    for column, column_type in REQUIRED_PROPERTY_COLUMNS.items():
        cur.execute(
            f"ALTER TABLE properties ADD COLUMN IF NOT EXISTS {column} {column_type}"
        )

    conn.commit()
    cur.close()


def ensure_divorce_schema(conn):
    """Create and backfill the divorce_cases table required by scraper and API."""
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS divorce_cases (
            id SERIAL PRIMARY KEY,
            case_number TEXT UNIQUE,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    for column, column_type in REQUIRED_DIVORCE_COLUMNS.items():
        cur.execute(
            f"ALTER TABLE divorce_cases ADD COLUMN IF NOT EXISTS {column} {column_type}"
        )

    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_divorce_cases_date_opened
            ON divorce_cases (date_opened DESC)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_divorce_cases_status
            ON divorce_cases (status)
        """
    )

    conn.commit()
    cur.close()
