# Real Estate Deal Finder

- Ingests county parcel data
- Scores distressed properties
- API + React dashboard

## Startup procedure

### 1) Backend setup and start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api:app --reload
```

The backend listens on port `8000` by default. For internet access, use `http://64.121.154.166:8000`.

### 2) Frontend setup and start

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend starts at `http://127.0.0.1:5173` by default and proxies `/api` requests to `http://64.121.154.166:8000`.

If you need to change the API host later, set:

```bash
VITE_API_PROXY_TARGET=http://<new-ip-or-host>:8000 npm run dev
```

## Run

Backend:
`uvicorn app.api:app --reload`

Frontend:
`npm run dev` (from `frontend/`)

## Prototype scrapers

- `python scripts/divorce_scraper_prototype.py --search-url "https://<court-site>/search" --query "divorce" --out divorce_results.csv`
  - The prototype now iterates through **all available result pages** (via `Next` links or `?page=` fallback) instead of stopping after page 1.

## Data ingestion & scraper scripts

### `scripts/run_ingest.py`

- Run:

```bash
python scripts/run_ingest.py
```

- What it does:
  - Executes the main ingest pipeline (`app.ingest.run()`), which loads and processes source parcel/property data into the app database.
  - Use this when you want to refresh the core property dataset before using the API/dashboard.

### `scripts/pull_upcoming_sheriff_sales.py`

> Note: the filename in this repo is `pull_upcoming_sheriff_sales.py` (one `r` in `sheriff`).

- Run:

```bash
python scripts/pull_upcoming_sheriff_sales.py
```

- What it does:
  - Calls Northampton County Sheriff Sale endpoints to get the **next sale date** and all listings for that date.
  - Parses listing details (address, municipality, parcel, disposition, debt amount, attorney, case title, docket number).
  - Writes the results to a CSV in the repo root named like `sheriff_sale_YYYY-MM-DD.csv`.

## Northampton divorce scraper

### `scripts/northampton_divorce_scraper.py`

- Run:

```bash
python scripts/northampton_divorce_scraper.py
```

- What it does:
  - Uses Playwright to scrape Northampton divorce case-search results.
  - Upserts case rows into `divorce_cases` (`case_number`, participants, normalized participants, category, opened date, status).
  - Re-syncs divorce-related fields on `properties` after ingest (`recent_divorce`, `divorce_case_status`, `divorce_date_opened`) so `/deals` and `/search` use precomputed values.

## New API endpoint

- `GET /divorce-cases`
  - Returns paginated divorce case rows for the frontend dashboard.
