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

        # handle milliseconds vs seconds
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

    total_assessed_value = a.get("TOTAL_ASSESSED_VALUE")

    return {
        "parcel_id": a.get("PARCEL_ID"),
        "address": (a.get("LOCATION") or "").strip(),
        "muni": a.get("MUNI"),
        "neighborhood": a.get("NBHD"),
        # keep assessed_value for backward compatibility with scoring logic
        "assessed_value": total_assessed_value,
        "total_assessed_value": total_assessed_value,
        "owners_name_1": a.get("OWNERS_NAME_1"),
        "owners_name_2": a.get("OWNERS_NAME_2"),
        "land_value": a.get("LAND_ASSESSMENT"),
        "building_value": a.get("BUILDING_ASSESSMENT"),
        "sale_price": a.get("SALE_PRICE"),
        "sale_date": to_date(a.get("SALE_DATE")),
        "sale_type": a.get("SALE_TYPE"),
        "sale_validity_code": a.get("SALE_VALIDITY_CODE"),
        "sqft": a.get("SQFT_LIVING_AREA"),
        "bedrooms": a.get("NUMBER_OF_BEDROOMS"),
        "bathrooms": a.get("NUMBER_OF_BATHS"),
        "half_baths": a.get("NUMBER_HALF_BATHS"),
        "stories": a.get("NUMBER_OF_STORIES"),
        "year_built": a.get("RES_YEAR_BUILT") or a.get("YEAR_BUILT"),
    }
