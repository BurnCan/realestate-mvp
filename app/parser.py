from datetime import datetime

def to_date(v):
    if v is None:
        return None

    try:
        # already string date
        if isinstance(v, str):
            return v

        # convert to int safely
        v = int(v)

        # ignore obviously bad values
        if v <= 0:
            return None

        # FIX: handle milliseconds vs seconds
        if v > 10_000_000_000:  # looks like milliseconds
            v = v / 1000

        # clamp insane values (ArcGIS corruption guard)
        if v > 4102444800:  # year 2100
            return None

        return datetime.utcfromtimestamp(v)

    except Exception:
        return None


def parse(feature):
    a = feature.get("attributes", {})

    return {
        "parcel_id": a.get("PARCEL_ID"),
        "address": (a.get("LOCATION") or "").strip(),

        "muni": a.get("MUNI"),
        "neighborhood": a.get("NBHD"),

        "assessed_value": a.get("TOTAL_ASSESSED_VALUE"),
        "land_value": a.get("LAND_ASSESSMENT"),
        "building_value": a.get("BUILDING_ASSESSMENT"),

        "sale_price": a.get("SALE_PRICE"),
        "sale_date": to_date(a.get("SALE_DATE")),  # ✅ FIX
        "sale_type": a.get("SALE_TYPE"),
        "sale_validity_code": a.get("SALE_VALIDITY_CODE"),

        "sqft": a.get("SQFT_LIVING_AREA"),
        "bedrooms": a.get("NUMBER_OF_BEDROOMS"),
        "bathrooms": a.get("NUMBER_OF_BATHS"),
        "half_baths": a.get("NUMBER_HALF_BATHS"),
        "stories": a.get("NUMBER_OF_STORIES"),
        "year_built": a.get("RES_YEAR_BUILT") or a.get("YEAR_BUILT"),
    }
