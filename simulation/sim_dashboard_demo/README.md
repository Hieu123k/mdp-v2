# Sim → Type A → MDP → Type B → Dashboard demo (prompt 22)

End-to-end demo on **DEV mdp2**: a Simulator-style feed of two Type A models (`sim_customer` dim +
`sim_invoice` fact) → MDP → a Type B join `sim_sales_360` → a **"Sales Statistics"** Grafana dashboard built
**two ways** to compare: **Path A** (Postgres `grafana_ro` reads the materialized view, server-side SQL
aggregate) and **Path B** (Infinity reads `GET /api/outbound/sim_sales_360`, read-through + client-side
aggregate). Both paths show the **same numbers**.

Design: [`../../design/sim_to_dashboard_pipeline.md`](../../design/sim_to_dashboard_pipeline.md).
**DEV-only, FE/back-end head 019 (no migration). API keys are runtime-only — never committed.**

## Files
- `seed_inbound.py` — POSTs 10 distinct customers + 240 invoices to `/api/inbound/{model}` (replicates the
  simulator's Seq/List config; key via env `KEY`).
- `gen_dashboard.py` — generates the 12-panel dashboard model and prints it (pipe to Grafana
  `POST /api/dashboards/db`).
- `sim_sales_stats.dashboard.json` — the rendered dashboard model (importable; references datasources
  `mdp_postgres` for Path A and `mdp_out_sim` for Path B).

## Rebuild (on mdp2; `BASE=http://localhost:8457/api`, admin JWT from the backend's security module)

1. **Type A models** (`POST $BASE/data-models`, JWT) — `sim_customer` [customer_id, customer_name, region,
   segment text; created_date date] and `sim_invoice` [invoice_no, customer_id, status text; amount float;
   issued_date date; issued_at datetime]. MDP casts → `mdp_data.dm_sim_*` with `amount double precision`,
   `issued_date date` (verified).
2. **Inbound key** (`POST $BASE/api-keys`, `allowed_directions:["inbound"]`, `allowed_models:["sim_customer",
   "sim_invoice"]`) → seed:
   `docker exec -e KEY="<inbound key>" -i mdpv2-backend-1 python - < seed_inbound.py`.
3. **Type B** `sim_sales_360` (`type:"B"`, `primary_key:"invoice_no"`): attributes carry
   `source_schema/source_table/source_column`; the join is a `relationships` entry
   `{"type":"left","left":{"table":"dm_sim_invoice","column":"customer_id"},"right":{"schema":"mdp_data",
   "table":"dm_sim_customer","column":"customer_id"}}`. (The right join key must be data-unique → the 10
   distinct customers satisfy the fan-out guard.) Create an **outbound** key for it.
4. **Matview**: `PUT $BASE/data-models/{id} {"matview_enabled":true}` then `POST .../{id}/refresh` →
   `mdp_models.sim_sales_360`. Grant the reader:
   `GRANT USAGE ON SCHEMA mdp_models TO grafana_ro; GRANT SELECT ON ALL TABLES IN SCHEMA mdp_models TO
   grafana_ro; ALTER DEFAULT PRIVILEGES FOR ROLE mdp_user IN SCHEMA mdp_models GRANT SELECT ON TABLES TO
   grafana_ro;`.
5. **Path B datasource** (Infinity): create `mdp_out_sim` with `allowedHosts:["http://reverse-proxy:8456"]`,
   `httpHeaderName1:"X-API-Key"`, `tlsSkipVerify:true`, and `httpHeaderValue1 = <outbound key>` (secure).
6. **Dashboard**: `docker exec -i mdpv2-backend-1 python - < gen_dashboard.py > dash.json` then
   `POST /api/dashboards/db` (`{dashboard:<model>, overwrite:true}`) — or import
   `sim_sales_stats.dashboard.json`.

## Notes / gotchas
- Inbound was driven by **direct POST** (what the simulator does under the hood) rather than hand-driving the
  Node-RED UI — deterministic and identical result; the Node-RED simulator stack is left untouched (coexist).
- On DEV mdp2 the outbound API is **HTTP** via `reverse-proxy:8456`; the self-signed-HTTPS + skip-TLS in the
  design is the prod pattern (skip-TLS is set on the datasource anyway).
- **Grafana + Postgres**: emit numeric panel values as `double precision` (`...::float8`), not `numeric` —
  and remember single-quoted SQL literals like `status='paid'` (a stripped quote turns `paid` into a column →
  empty panels).
