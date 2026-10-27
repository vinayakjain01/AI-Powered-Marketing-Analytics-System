# Deploying to SAP BTP (Cloud Foundry)

> **Status:** these files are prepared but **not deployed or tested on BTP**. `manifest.yml`, `runtime.txt`,
> `.cfignore` and the `Dockerfile` were written from the Cloud Foundry docs; expect to adjust the Python
> version (`runtime.txt`) to one your region's buildpack offers (`cf buildpacks`).

BTP cannot reach the Postgres on your laptop, so the warehouse has to live somewhere public first.

## 1. Put the warehouse in a hosted Postgres (free tiers: Supabase or Neon)

1. Create a project and copy the connection string (Supabase: use the **Session pooler** string, which is IPv4
   and works from BTP; Neon: the standard string). It looks like `postgresql://user:pass@host:5432/dbname`.
2. Load it from this repo (cleans the CSVs, builds the star schema, prints row counts):

   ```bash
   python scripts/build_warehouse.py --database-url "postgresql://user:pass@host:5432/dbname"
   ```
   `postgres://` and `postgresql://` URLs are accepted. This **drops and rebuilds** the `campaign_data` tables
   in that database, so use a database dedicated to this project.

## 2. Build the frontend locally

The Python buildpack does not run Node, so ship the built files:

```bash
cd frontend && npm ci && npm run build && cd ..
```
`frontend/dist` is git-ignored but is uploaded by `cf push` (it is not in `.cfignore`).

## 3. Log in and push (you run these; they need your BTP trial account)

```bash
# Region API endpoint is shown in the BTP cockpit (Cloud Foundry environment -> API Endpoint)
cf login -a https://api.cf.<region>.hana.ondemand.com --sso
cf target -o <your-org> -s <your-space>

cf push --no-start                       # uploads code + frontend/dist using manifest.yml

# Secrets go in the environment, never in manifest.yml or git
cf set-env marketing-insights DATABASE_URL  "postgresql://user:pass@host:5432/dbname"
cf set-env marketing-insights GEMINI_API_KEY "<your NEW key>"
cf set-env marketing-insights ASK_RATE_LIMIT 20      # optional: questions per minute per IP

cf restage marketing-insights
cf app marketing-insights                # shows the route (URL)
cf logs marketing-insights --recent      # if it does not start
```
Open the route: the React app is served at `/`, the API at `/api/*`, health at `/api/health`.

## Things to know before sharing the URL

* **There is no login.** Anyone with the URL can see your dashboard data and spend your Gemini quota (the
  rate limiter slows abuse, it is not authentication). Add auth (e.g. BTP's app router/XSUAA) before using real data.
* If memory is tight at 512M (pandas + scikit-learn are installed), raise it in `manifest.yml`.
* Without `GEMINI_API_KEY` the dashboard and Data pages work and the Ask page shows "agent disabled".

## Docker alternative

```bash
docker build -t marketing-insights .
docker run -p 8000:8000 -e DATABASE_URL=... -e GEMINI_API_KEY=... marketing-insights
```
(Not built here: the Docker daemon was not running when this was written.)
