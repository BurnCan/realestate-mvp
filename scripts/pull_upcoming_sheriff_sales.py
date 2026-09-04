import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime
import urllib3

# Disable SSL warnings (site uses self-signed / misconfigured certs)
urllib3.disable_warnings()

BASE = "https://web.northamptoncounty.org/SheriffSale/api"

HEADERS_JSON = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}

HEADERS_XML = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/xml",
}


# ------------------------------------------------
# Get next sheriff sale date
# ------------------------------------------------
def get_next_sale_date() -> str:
    print("Getting next sale date...")

    r = requests.get(
        f"{BASE}/Dates/GetNextSaleDate",
        headers=HEADERS_JSON,
        verify=False,
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()
    sale_date = datetime.fromisoformat(data["SaleDate"]).date().isoformat()

    print("Sale Date:", sale_date)
    return sale_date


# ------------------------------------------------
# Pull XML listings for a given date
# ------------------------------------------------
def get_listings_xml(sale_date: str) -> str:
    print(f"Downloading listings for {sale_date}...")

    r = requests.get(
        f"{BASE}/Listings/GetSelListing/{sale_date}",
        headers=HEADERS_XML,
        verify=False,
        timeout=60,
    )
    r.raise_for_status()

    return r.text


# ------------------------------------------------
# Parse XML listings
# ------------------------------------------------
def parse_listings(xml_text: str) -> list[dict]:
    soup = BeautifulSoup(xml_text, "xml")
    records = []

    for listing in soup.find_all("Listing"):
        # Combine ParcelMap + ParcelBlock + ParcelLot
        parcel = ""
        if listing.ParcelMap and listing.ParcelBlock and listing.ParcelLot:
            parcel = (
                f"{listing.ParcelMap.text} {listing.ParcelBlock.text} {listing.ParcelLot.text}"
            )

        # Clean DebtAmount to numeric
        debt: float | str = ""
        if listing.DebtAmount and listing.DebtAmount.text:
            try:
                debt = float(listing.DebtAmount.text)
            except ValueError:
                debt = listing.DebtAmount.text

        records.append(
            {
                "Address": listing.SaleAddress.text if listing.SaleAddress else "",
                "Municipality": listing.Town.text if listing.Town else "",
                "Parcel": parcel,
                "Disposition": listing.Disposition.text if listing.Disposition else "",
                "DebtAmount": debt,
                "Attorney": listing.AttorneyName.text if listing.AttorneyName else "",
                "CaseTitle": listing.CaseTitle.text if listing.CaseTitle else "",
                "DocketNumber": listing.DocketNumber.text if listing.DocketNumber else "",
            }
        )

    return records


# ------------------------------------------------
# Main
# ------------------------------------------------
def main() -> None:
    sale_date = get_next_sale_date()
    xml_text = get_listings_xml(sale_date)
    records = parse_listings(xml_text)

    df = pd.DataFrame(records)

    filename = f"sheriff_sale_{sale_date}.csv"
    df.to_csv(filename, index=False)

    print(f"\nSaved {len(records)} records → {filename}")


if __name__ == "__main__":
    main()
