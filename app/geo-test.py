import requests
import json

url = "https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer/0/query"

params = {
    "where": "1=1",
    "outFields": "*",
    "f": "json",
    "resultRecordCount": 1,
    "returnGeometry": "true"   # <-- critical
}

data = requests.get(url, params=params, timeout=30).json()

feature = data["features"][0]

print("\n=== ATTRIBUTES KEYS ===")
print(feature["attributes"].keys())

print("\n=== HAS GEOMETRY? ===")
print("geometry" in feature)

print("\n=== GEOMETRY RAW ===")
print(json.dumps(feature.get("geometry"), indent=2))
