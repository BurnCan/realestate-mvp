import requests

url = "https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer/0/query"

params = {
    "where": "1=1",
    "outFields": "PARCEL_ID,LOCATION,TOTAL_ASSESSED_VALUE",
    "f": "json",
    "resultRecordCount": 5
}

r = requests.get(url, params=params)
data = r.json()

for f in data.get("features", []):
    print(f["attributes"])
