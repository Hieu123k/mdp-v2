#!/usr/bin/env bash
# Idempotently create/refresh the least-privilege read-only Postgres role `grafana_ro` used by the
# Grafana datasource (SELECT-only on the MDP schemas — never the MDP app user). Run AFTER the stack
# is up and the backend has migrated (so the schemas exist).
#
#   set -a; . ops/.env; set +a          # export POSTGRES_* + GRAFANA_DB_PASSWORD
#   bash ops/init/grafana_ro.sh
#
# The password is read from the environment via psql `\getenv` (passed into the container with
# `docker exec -e`, so it never appears in any process argv). No secret is stored in this file.
set -euo pipefail
: "${GRAFANA_DB_PASSWORD:?GRAFANA_DB_PASSWORD must be exported (run: set -a; . ops/.env; set +a)}"
PG_CONTAINER="${PG_CONTAINER:-mdpv2-postgres-1}"
APP_USER="${POSTGRES_USER:-mdp_user}"
DB="${POSTGRES_DB:-mdp}"

docker exec -e GRAFANA_DB_PASSWORD -i "$PG_CONTAINER" \
  psql -v ON_ERROR_STOP=1 -U "$APP_USER" -d "$DB" <<'SQL'
\getenv ro_pw GRAFANA_DB_PASSWORD
-- Create the login role only if missing (idempotent), then (re)set its password every run.
SELECT 'CREATE ROLE grafana_ro LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro')\gexec
ALTER ROLE grafana_ro WITH LOGIN PASSWORD :'ro_pw';
GRANT CONNECT ON DATABASE mdp TO grafana_ro;
-- Grant SELECT on every MDP schema that exists, plus default privileges so future app-created
-- tables (e.g. new mdp_data.dm_* from Type A inbound, or Type B matviews in mdp_models) are
-- auto-readable. SELECT-only, no writes. (Re-run after the first matview is built so mdp_models exists.)
DO $$
DECLARE s text;
BEGIN
  FOREACH s IN ARRAY ARRAY['public', 'mdp_data', 'mdp_staging', 'mdp_models'] LOOP
    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = s) THEN
      EXECUTE format('GRANT USAGE ON SCHEMA %I TO grafana_ro', s);
      EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO grafana_ro', s);
      EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE mdp_user IN SCHEMA %I GRANT SELECT ON TABLES TO grafana_ro', s);
    END IF;
  END LOOP;
END $$;
SQL
echo "grafana_ro: read-only role + SELECT grants applied (idempotent)."
