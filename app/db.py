import psycopg2

DB_CONFIG = {
    "dbname": "realestate",
    "user": "realuser",
    "password": "password",
    "host": "localhost",
    "port": 5432,
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
