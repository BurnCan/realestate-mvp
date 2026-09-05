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
    "recent_probate": "BOOLEAN DEFAULT FALSE",
    "probate_filing_date": "DATE",
    "probate_decedent_name": "TEXT",
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
    "normalized_participants": "TEXT[]",
    "case_category": "TEXT",
    "date_opened": "DATE",
    "status": "TEXT",
    "updated_at": "TIMESTAMP DEFAULT NOW()",
}

REQUIRED_PROBATE_COLUMNS = {
    "record_identifier": "TEXT UNIQUE",
    "estate_name": "TEXT NOT NULL",
    "normalized_estate_name": "TEXT",
    "death_date": "DATE",
    "filing_date": "DATE NOT NULL",
    "detail_url": "TEXT",
    "updated_at": "TIMESTAMP DEFAULT NOW()",
}

REQUIRED_CAMPAIGN_COLUMNS = {
    "name": "TEXT",
    "slug": "TEXT UNIQUE",
    "tracker_slug": "TEXT UNIQUE",
    "redirect_url": "TEXT",
    "filters_snapshot": "JSONB NOT NULL DEFAULT '{}'::JSONB",
    "results_count": "INT NOT NULL DEFAULT 0",
    "created_at": "TIMESTAMP DEFAULT NOW()",
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


def ensure_probate_schema(conn):
    """Create the probate estate store used by the Recorder of Wills scraper."""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS probate_estates (
            id SERIAL PRIMARY KEY,
            record_identifier TEXT UNIQUE,
            estate_name TEXT NOT NULL,
            filing_date DATE NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    for column, column_type in REQUIRED_PROBATE_COLUMNS.items():
        cur.execute(
            f"ALTER TABLE probate_estates ADD COLUMN IF NOT EXISTS {column} {column_type}"
        )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_probate_estates_filing_date "
        "ON probate_estates (filing_date DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_probate_estates_normalized_name "
        "ON probate_estates (normalized_estate_name)"
    )
    conn.commit()
    cur.close()


def sync_property_probate_fields(conn):
    """Match estate names to owners and materialize the newest probate filing."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE properties
        SET recent_probate = FALSE,
            probate_filing_date = NULL,
            probate_decedent_name = NULL,
            updated_at = NOW()
        WHERE recent_probate IS TRUE
           OR probate_filing_date IS NOT NULL
           OR probate_decedent_name IS NOT NULL
        """
    )
    cur.execute(
        """
        WITH owner_names AS (
            SELECT p.id,
                   REGEXP_REPLACE(LOWER(COALESCE(owner_name, '')), '[^a-z0-9]+', ' ', 'g') AS owner_name
            FROM properties p
            CROSS JOIN LATERAL UNNEST(ARRAY[p.owners_name_1, p.owners_name_2]) owner_name
        ),
        matches AS (
            SELECT o.id, pe.estate_name, pe.filing_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY o.id
                       ORDER BY pe.filing_date DESC, pe.record_identifier DESC
                   ) AS rank
            FROM owner_names o
            JOIN probate_estates pe
              ON TRIM(o.owner_name) = pe.normalized_estate_name
            WHERE pe.normalized_estate_name <> ''
        )
        UPDATE properties p
        SET recent_probate = TRUE,
            probate_filing_date = m.filing_date,
            probate_decedent_name = m.estate_name,
            updated_at = NOW()
        FROM matches m
        WHERE p.id = m.id AND m.rank = 1
        """
    )
    conn.commit()
    cur.close()


def ensure_campaign_schema(conn):
    """Create campaign and visitor tracking tables."""
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'campaigns'
        """
    )
    campaign_columns = {row[0] for row in cur.fetchall()}

    for column, column_type in REQUIRED_CAMPAIGN_COLUMNS.items():
        if column in campaign_columns:
            continue
        cur.execute(
            f"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS {column} {column_type}"
        )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_properties (
            id SERIAL PRIMARY KEY,
            campaign_id INT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            parcel_id TEXT,
            snapshot_data JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_properties_campaign_id
            ON campaign_properties (campaign_id)
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_visits (
            id SERIAL PRIMARY KEY,
            campaign_id INT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            visited_at TIMESTAMP DEFAULT NOW(),
            ip_address TEXT,
            user_agent TEXT,
            referer TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_campaign_visits_campaign_id
            ON campaign_visits (campaign_id)
        """
    )

    conn.commit()
    cur.close()


def sync_property_divorce_fields(conn):
    """
    Materialize divorce metadata directly onto properties so API reads stay cheap.
    """
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TEMP TABLE temp_property_divorce_matches AS
        WITH normalized_participants AS (
            SELECT
                dc.case_number,
                dc.status,
                dc.date_opened,
                LOWER(TRIM(UNNEST(COALESCE(dc.normalized_participants, ARRAY[]::TEXT[])))) AS normalized_name
            FROM divorce_cases dc
        ),
        ranked_matches AS (
            SELECT
                p.id AS property_id,
                npt.status,
                npt.date_opened,
                ROW_NUMBER() OVER (
                    PARTITION BY p.id
                    ORDER BY
                        CASE WHEN LOWER(COALESCE(npt.status, '')) = 'open' THEN 0 ELSE 1 END,
                        npt.date_opened DESC NULLS LAST,
                        npt.case_number DESC
                ) AS rn
            FROM normalized_participants npt
            JOIN properties p
                ON (
                    TRIM(
                        CONCAT_WS(
                            ' ',
                            SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_1, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 1),
                            SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_1, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 2)
                        )
                    ) = npt.normalized_name
                )
                OR (
                    TRIM(
                        CONCAT_WS(
                            ' ',
                            SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_2, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 1),
                            SPLIT_PART(REGEXP_REPLACE(LOWER(COALESCE(p.owners_name_2, '')), '[^a-z0-9 ]+', ' ', 'g'), ' ', 2)
                        )
                    ) = npt.normalized_name
                )
            WHERE npt.normalized_name <> ''
        )
        SELECT property_id, status, date_opened
        FROM ranked_matches
        WHERE rn = 1
        """
    )
    cur.execute(
        """
        UPDATE properties
        SET
            recent_divorce = FALSE,
            divorce_case_status = NULL,
            divorce_date_opened = NULL,
            updated_at = NOW()
        WHERE recent_divorce IS TRUE
           OR divorce_case_status IS NOT NULL
           OR divorce_date_opened IS NOT NULL
        """
    )
    cur.execute(
        """
        UPDATE properties p
        SET
            recent_divorce = TRUE,
            divorce_case_status = t.status,
            divorce_date_opened = t.date_opened,
            updated_at = NOW()
        FROM temp_property_divorce_matches t
        WHERE p.id = t.property_id
        """
    )
    cur.execute("DROP TABLE IF EXISTS temp_property_divorce_matches")
    conn.commit()
    cur.close()
