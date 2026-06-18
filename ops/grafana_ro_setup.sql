-- Prompt 31 — read-only Postgres role for the Grafana "Accounting (Sample)" datasource. Idempotent:
-- safe to run repeatedly. Run as a superuser against the MDP database, e.g.
--   docker exec -i <postgres> psql -U <admin> -d mdp < ops/grafana_ro_setup.sql
--
-- 🔴 The role's PASSWORD is set OUT OF BAND (never in git). After this script, set it once with the real
-- value (kept in the Grafana datasource config / host env, not committed):
--   ALTER ROLE grafana_ro PASSWORD '...';

-- 1) Create the login role if it does not already exist (no password here).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
    CREATE ROLE grafana_ro LOGIN;
  END IF;
END
$$;

-- 2) Read-only access to the mdp_models schema (where the accounting Path A matviews live).
GRANT USAGE ON SCHEMA mdp_models TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA mdp_models TO grafana_ro;

-- 3) Materialized views are NOT always covered by "ALL TABLES" — grant SELECT on each explicitly.
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN SELECT matviewname FROM pg_matviews WHERE schemaname = 'mdp_models'
  LOOP
    EXECUTE format('GRANT SELECT ON mdp_models.%I TO grafana_ro', r.matviewname);
  END LOOP;
END
$$;

-- 4) Future tables/views created in mdp_models are auto-granted SELECT (re-run this script after adding
--    new Type B *matviews*, which default privileges do not cover).
ALTER DEFAULT PRIVILEGES IN SCHEMA mdp_models GRANT SELECT ON TABLES TO grafana_ro;
