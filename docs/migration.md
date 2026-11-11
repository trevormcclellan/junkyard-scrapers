# Combining the frontend and scrapers

The canonical frontend is `junkyard-scrapers/frontend/`. The separate frontend
checkout has not been deleted or had its history rewritten. Keep its current
production image/revision for rollback, then retire that repository after the
combined deployment is verified. Future parser changes belong only in
`junkyard/providers/`.

## Deployment inventory and configuration

The inspected repositories contain Dockerfiles, but **no Compose manifests or
production deployment workflow**. The previous worker image ran cron and the
previous frontend image ran Gunicorn on port 5000. The actual Compose service
names, image tags, networks, mounts and MongoDB server version must be checked in
the deployment repository before rollout. No Compose services, databases,
production secrets, or running containers were changed during this refactor.

The combined Dockerfile has two targets. For existing locally built services,
change only their build configuration in the real Compose manifest, retaining
existing service names, networks, runtime configuration and volumes:

```yaml
# Illustrative fragments; replace the path and use your existing service names.
services:
  existing-web-service:
    build:
      context: /path/to/junkyard-scrapers
      dockerfile: Dockerfile
      target: web
  existing-worker-service:
    build:
      context: /path/to/junkyard-scrapers
      dockerfile: Dockerfile
      target: worker
```

For services that consume prebuilt `image:` tags, build/tag both targets from the
same reviewed commit using the existing publishing process, then update those
image references. CI intentionally does not publish images. Keep both services
on the same revision so they cannot run different parsers.

Configuration remains compatible with the existing environment names:

- `MONGO_URI`, `MONGO_DB_NAME`: existing server and database.
- `MONGO_COLLECTION_NAME_<YARD>`: existing collections, shared by worker and web.
  Workers also support legacy `MONGO_COLLECTION_NAME` in per-yard configuration.
- `HOME_ASSISTANT_WEBHOOK_URL_<YARD>` or `HOME_ASSISTANT_WEBHOOK_URL`: worker only.
  Existing `HOME_ASSISTANT_WEBHOOK_ID` remains supported with the original host;
  `HOME_ASSISTANT_WEBHOOK_ID_<YARD>` can select a per-yard destination.
- Legacy per-yard `.env` files can be mounted read-only at `/app/<yard>/.env` in
  the worker image. Runtime environment values take precedence. They are no longer
  baked into images. Do not give webhook credentials to the web service.
- `LKQ_PROXY_URL` defaults to `http://cloudflare-bypass:8000`; retain connectivity
  to the existing proxy service for both images.
- `SCRAPER_YARDS` defaults to the same five main-region yards. Add Utah yards only
  where their collection and notification settings are configured.

No database migration is required. Stock-number types and existing per-yard
collections are retained. The new driver is PyMongo 4.19.0, which supports MongoDB
4.4 and newer; confirm the deployed server is compatible before rollout. The
stateful MongoDB service is not upgraded as part of this change.

## Review and rollout

1. Run CI on the combined repository. It installs the exact pins, runs offline
   regression tests, validates installed templates, builds both images and smoke
   tests Gunicorn. Local source tests alone do not verify the upgraded runtime.
2. With isolated database/webhook settings, manually exercise parser/database
   behavior and one live search for each deployed yard, including LKQ through the
   proxy. Fixtures are representative examples derived from the original parser
   contracts, not fresh captures of every live yard. Confirm make/model lists,
   photos, empty results and failures. External sites can still change.
3. Confirm current backups and retain the previous web and worker images. Stop
   the old worker when replacing it to avoid duplicate notifications.
4. After human approval, update the existing deployment. For locally built
   services, use `docker compose build --pull <web-service> <worker-service>` then
   `docker compose up -d --no-deps <web-service> <worker-service>`. For prebuilt
   services, pull the approved tags and recreate those services instead.
5. Inspect `docker compose ps`, logs, `/healthz`, a saved-inventory page and a live
   search. Wait for a full worker cycle and check all configured health statuses.
   Record the deployed commit and any yard-specific follow-up.

Rollback uses the retained prior image/revision and the existing configuration.
Do not remove database volumes or use `docker compose down` for routine rollout.
