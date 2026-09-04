from fastapi import FastAPI
import requests
import json

app = FastAPI()

URL = "https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer/0/query"


def fetch(n=1):
    params = {
        "where": "1=1",
        "outFields": "*",
        "f": "json",
        "resultRecordCount": n,
        "returnGeometry": "true"
    }

    r = requests.get(URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["features"]


@app.get("/inspect/full")
def inspect_full():
    features = fetch(3)  # grab multiple to see variability

    first = features[0]

    attributes = first.get("attributes", {})
    geometry = first.get("geometry", {})

    return {
        # 🔥 raw sample
        "sample_feature": first,

        # 🔥 schema discovery
        "attribute_fields": list(attributes.keys()),
        "geometry_fields": list(geometry.keys()) if geometry else None,

        # 🔥 data profiling (very important)
        "sample_values": {
            "PARCEL_ID": attributes.get("PARCEL_ID"),
            "LOCATION": attributes.get("LOCATION"),
            "MUNI": attributes.get("MUNI"),
            "TOTAL_ASSESSED_VALUE": attributes.get("TOTAL_ASSESSED_VALUE"),
            "SALE_PRICE": attributes.get("SALE_PRICE"),
            "YEAR_BUILT": attributes.get("YEAR_BUILT"),
            "OWNERS_HIDENAME": attributes.get("OWNERS_HIDENAME"),
        },

        # 🔥 geometry classification
        "geometry_type": (
            "polygon" if geometry.get("rings") else
            "point" if geometry.get("x") else
            "unknown"
        ),

        # 🔥 dataset insights
        "has_assessment_data": "TOTAL_ASSESSED_VALUE" in attributes,
        "has_sale_data": "SALE_PRICE" in attributes,
        "has_owner_data": (
            "OWNERS_NAME_1" in attributes or "OWNERS_HIDENAME" in attributes
        ),
        "has_address_data": "LOCATION" in attributes,

        # 🔥 raw multi-sample (important for schema variance)
        "multi_sample_parcel_ids": [
            f["attributes"].get("PARCEL_ID") for f in features
        ]
    }
