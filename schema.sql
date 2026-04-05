CREATE TABLE properties (
    id SERIAL PRIMARY KEY,
    parcel_id TEXT UNIQUE,
    address TEXT,
    assessed_value BIGINT,
    land_value BIGINT,
    building_value BIGINT,
    last_sale_price BIGINT,
    last_sale_date TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);
