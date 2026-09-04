from datetime import datetime


def to_date(v):
    if v is None:
        return None

    try:
        if isinstance(v, str):
            return v

        v = int(v)

        if v <= 0:
            return None

        if v > 10_000_000_000:
            v = v / 1000

        if v > 4102444800:
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
        "owners_hidename": a.get("OWNERS_HIDENAME"),
        "owners_name_1": a.get("OWNERS_NAME_1"),
        "owners_name_2": a.get("OWNERS_NAME_2"),
        "mail_address_1": a.get("MAIL_ADDRESS_1"),
        "mail_address_2": a.get("MAIL_ADDRESS_2"),
        "mail_address_3": a.get("MAIL_ADDRESS_3"),
        "land_value": a.get("LAND_ASSESSMENT"),
        "building_value": a.get("BUILDING_ASSESSMENT"),
        "sale_price": a.get("SALE_PRICE"),
        "sale_date": to_date(a.get("SALE_DATE")),
        "sale_type": a.get("SALE_TYPE"),
        "sale_validity_code": a.get("SALE_VALIDITY_CODE"),
        "sqft_living_area": a.get("SQFT_LIVING_AREA"),
        "bedrooms": a.get("NUMBER_OF_BEDROOMS"),
        "bathrooms": a.get("NUMBER_OF_BATHS"),
        "half_baths": a.get("NUMBER_HALF_BATHS"),
        "stories": a.get("NUMBER_OF_STORIES"),
        "year_built": a.get("RES_YEAR_BUILT") or a.get("YEAR_BUILT"),
        # Direct ArcGIS key mappings to ensure full key ingestion coverage.
        "objectid": a.get("OBJECTID"),
        "cama_id": a.get("CAMA_ID"),
        "map": a.get("MAP"),
        "block": a.get("BLOCK"),
        "lot": a.get("LOT"),
        "schdist": a.get("SCHDIST"),
        "flag": a.get("FLAG"),
        "gis_acreage": a.get("GIS_ACREAGE"),
        "asmt_acreage": a.get("ASMT_ACREAGE"),
        "deed": a.get("DEED"),
        "luc": a.get("LUC"),
        "total_value": a.get("TOTAL_VALUE"),
        "bldg_value": a.get("BLDG_VALUE"),
        "building_assessment": a.get("BUILDING_ASSESSMENT"),
        "land_assessment": a.get("LAND_ASSESSMENT"),
        "note_3_gis_code": a.get("NOTE_3_GIS_CODE"),
        "flag_1_319_515": a.get("FLAG_1_319_515"),
        "flag_2_lerta": a.get("FLAG_2_LERTA"),
        "flag_3_hmstd": a.get("FLAG_3_HMSTD"),
        "flag_4_fmstd": a.get("FLAG_4_FMSTD"),
        "flag_5_act_43": a.get("FLAG_5_ACT_43"),
        "flag_6_act_66": a.get("FLAG_6_ACT_66"),
        "flag_7_act_149": a.get("FLAG_7_ACT_149"),
        "flag_9_bill": a.get("FLAG_9_BILL"),
        "flag_10_koz": a.get("FLAG_10_KOZ"),
        "number_of_cards": a.get("NUMBER_OF_CARDS"),
        "number_of_stories": a.get("NUMBER_OF_STORIES"),
        "exterior": a.get("EXTERIOR"),
        "basement": a.get("BASEMENT"),
        "building_style": a.get("BUILDING_STYLE"),
        "number_of_bedrooms": a.get("NUMBER_OF_BEDROOMS"),
        "number_of_baths": a.get("NUMBER_OF_BATHS"),
        "number_half_baths": a.get("NUMBER_HALF_BATHS"),
        "total_rooms": a.get("TOTAL_ROOMS"),
        "swimming_pool": a.get("SWIMMING_POOL"),
        "comm_cards": a.get("COMM_CARDS"),
        "commercial_structure_type": a.get("COMMERCIAL_STRUCTURE_TYPE"),
        "improvement_name": a.get("IMPROVEMENT_NAME"),
        "com_year_built": a.get("COM_YEAR_BUILT"),
        "res_year_built": a.get("RES_YEAR_BUILT"),
        "notecd1": a.get("NOTECD1"),
        "shape_st_area": a.get("Shape.STArea()"),
        "shape_st_length": a.get("Shape.STLength()"),
    }
