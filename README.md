# Junkyard inventory

One repository now contains the yard integrations, scheduled watches, and Flask
search frontend. Fix upstream URLs, request formats and parsing **once**, in
`junkyard/providers/`. Both Docker targets install the same package and dependency
lock from the same checkout.

```text
junkyard/providers/     eight integrations; HTTP, pagination, parsing, enrichment
junkyard/worker.py      personal watch rules, MongoDB sync, Home Assistant notifications
frontend/              Flask routes, templates, static files; imports the integrations
tests/fixtures/        representative HTML/JSON regression examples
requirements.txt       fully pinned runtime dependency lock for both images
requirements-build.txt pinned packaging tools
Dockerfile             web and worker targets (worker is the default)
```

The original `junkyard-frontend` checkout is retained for comparison and rollback.
The maintained frontend is now `frontend/` in this repository. See
[the migration guide](docs/migration.md) before changing the deployment.

## Development

Use Python 3.14 (the Docker and CI runtime is pinned to 3.14.10).

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-build.txt -r requirements.txt
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
python -m unittest discover -s tests -v
flask --app frontend.app:create_app run --port 5001
```

Copy `.env.example` to `.env` and fill in your existing configuration for local
Flask use. Flask's CLI loads `.env` through python-dotenv. Docker uses runtime
environment variables / Compose `env_file`; `.env` files are excluded from images.
The tests mock HTTP, MongoDB, and notification boundaries and need no secrets.

The scheduled worker has real database and webhook side effects. After configuring
an isolated test database and notification destination, a single check can be run
with `python -m junkyard.worker lkq`. The old `python lkq/main.py` entry points
remain available **after installing the package**. Imports never start a scrape.

## Integration contract

Each integration accepts search criteria and returns a complete list or raises
`InventoryError`. It must not turn network failures, missing tables, malformed
rows, or incomplete pagination into an empty result. A verified empty response
returns `[]`. Request parameters are encoded by Requests and every request has
connect/read timeouts.

Vehicle dictionaries share `year` (integer), `make` and `model` (uppercase),
`stock_num` (original source type to preserve MongoDB identities), `location`,
`image` and `image_urls` (including the primary image). Source-specific details
such as VIN, row, section, engine, reference and notes remain available. Missing
optional enrichment does not invalidate a successfully parsed inventory.
Dropdown response shapes remain compatible with the existing yard templates.

Personal interests are in `watch_results` / `interested`, outside the integrations.
Main-region workers retain all matching Mercedes vehicles and assign an interest
level. Utah workers retain only the existing year/model matches. Search requests
use the user's filters and are not restricted by those watch rules.

A worker validates a complete search before changing its database scope. A failed
location does not erase saved vehicles or prevent another location from running.
New arrivals are notified before insertion; an unsuccessful notification prevents
stale-record deletion. Existing records are refreshed without repeating arrival
notifications. Notification delivery is not transactional with MongoDB: a process
failure after a successful webhook and before insertion can still cause a retry.
Avoid running two worker instances for the same yard.

## Images and scheduling

```sh
docker build --target web -t junkyard-web:review .
docker build --target worker -t junkyard-worker:review .
```

The worker runs the existing five main-region yards on startup and then on an
hourly cadence. `SCRAPER_YARDS` can include any of the eight integrations;
`SCRAPER_INTERVAL_SECONDS` defaults to 3600 and `SCRAPER_TIMEOUT_SECONDS` caps each
individual job at 1800 seconds. A Python scheduler replaces cron so each job
inherits runtime container environment variables. Failures do not short-circuit
later jobs. Health checks inspect both status and freshness. Web `/healthz` is a
process health check; it does not probe external yards or MongoDB.

## Dependency maintenance

[Dependency policy](docs/dependency-update-policy.md) and
[repository-specific maintenance notes](docs/maintenance.md) describe the quarterly
schedule, continuous security response, verification and deployment procedure.
CI builds and tests pull requests; it never publishes, merges or deploys them.
