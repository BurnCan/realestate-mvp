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
uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

The local API URL is `http://127.0.0.1:8000`. For example, the deals endpoint is
`http://127.0.0.1:8000/deals`. From another device, replace `127.0.0.1` with the
server's LAN IP, hostname, or properly configured public address. Opening port
`8000` directly shows API JSON, not the frontend.

### 2) Frontend setup and start

In a separate terminal:

```bash
cd frontend
npm install
VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev -- --host 0.0.0.0
```

The local dashboard URL is `http://127.0.0.1:5173`. From another device, open
`http://<server-ip>:5173`.

Vite receives requests such as `/api/deals`, strips the `/api` prefix, and proxies
them to `http://127.0.0.1:8000/deals`. `VITE_API_PROXY_TARGET` is the backend
origin only and must not include `/api`. Use a different target only when the
backend runs on another host, for example:

```bash
VITE_API_PROXY_TARGET=http://<different-backend-host>:8000 npm run dev -- --host 0.0.0.0
```

### 3) Verify the API and frontend proxy

With both services running, use:

```bash
curl -i http://127.0.0.1:8000/deals
curl -i http://127.0.0.1:5173/api/deals
```

Both commands should return `HTTP 200` when the services and proxy are working.

### External access

Binding the services to `0.0.0.0` makes them listen on the machine's network
interfaces, but does not by itself guarantee internet access. The machine firewall
and router/NAT may also need TCP ports `5173` and `8000` opened or forwarded.

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
