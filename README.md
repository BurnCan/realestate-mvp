# Real Estate Deal Finder

- Ingests county parcel data
- Scores distressed properties
- API + React dashboard

## Run

Backend:
uvicorn app.api:app --reload

Frontend:
npm start

## Prototype scrapers

- `python scripts/divorce_scraper_prototype.py --search-url "https://<court-site>/search" --query "divorce" --out divorce_results.csv`
  - The prototype now iterates through **all available result pages** (via `Next` links or `?page=` fallback) instead of stopping after page 1.

