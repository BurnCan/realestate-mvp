import requests

url = "https://gis.northamptoncounty.org/arcgisweb/rest/services/Assessment_Services/Land_Records_LGM/MapServer/0/query"

params = {
    "where": "1=1",
    "outFields": "*",
    "f": "json",
    "resultRecordCount": 1
}

data = requests.get(url, params=params).json()

print(data["features"][0]["attributes"].keys())
