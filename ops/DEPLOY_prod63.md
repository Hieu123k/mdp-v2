# Deploy TIPA V2 (`v2.0.1`) to PROD `.63` — notes for **tipa mdp**

> MDP V2 app **@ `:8456`** replacing v0.1.4, **reusing the existing prod Postgres (79 GB)** + the v0.1.4
> secrets + Oracle `.16`; a **dedicated Grafana @ `:3001`** coexisting (NOT the shared Grafana on `:3000`).
> This file is documentation only — **tipa deploy v2 does NOT run prod**; tipa mdp executes the cutover.

## 0) Pre-flight (do NOT skip)
- **Back up first:** `pg_dump` the prod DB (the 79 GB), and record the current image/tag (v0.1.4 =
  `7db36fe` on repo `mdp-deploy-v0.0`) + the running compose. Rollback depends on this.
- Confirm free host ports on `.63`: **`:8456`** (v0.1.4 will be replaced) and **`:3001`** (Grafana —
  the shared Grafana is on `:3000`, do NOT touch it). `ss -ltn | grep -E ':(8456|3001)'`.
- Reuse `JWT_SECRET_KEY` + `CONNECTION_SECRET_KEY` from v0.1.4 — changing them invalidates every existing
  API key and login session.

## 1) Get the code
```
git remote add mdp-v2 https://github.com/Hieu123k/mdp-v2.git   # if not present
git fetch mdp-v2 --tags
git checkout v2.0.1
```

## 2) Real env (on the VM, never in git)
```
cd ops
cp .env.prod63.example .env.prod63
# fill REAL values: DATABASE_URL (reuse prod PG), JWT/CONNECTION (reuse v0.1.4), ORACLE_* (.16),
# GRAFANA_* , MDP_NETWORK. Then:
chmod 600 .env.prod63
```
**DATABASE_URL reachability** — the backend container must reach the prod Postgres. Either:
- host-exposed: `...@host.docker.internal:5432/mdp` (the compose maps `host.docker.internal` to the host
  gateway), **or**
- a shared network: add the prod Postgres's network to the backend in a small override and use the
  service name (`...@postgres:5432/mdp`).

## 3) Migrate (keep data) + bring up MDP @ :8456
```
# alembic runs automatically on backend start (CMD: alembic upgrade head && uvicorn). Migrations are
# additive and end at head 018; on the existing DB they no-op what is already applied.
docker compose -f docker-compose.prod63.yml --env-file .env.prod63 -p mdp up -d --build
```
- Recommended `-p mdp` so the new stack cleanly takes over the v0.1.4 project. (Or pick a distinct
  `-p` name and stop v0.1.4 separately — decide per the prod layout; `up` removes services not in the
  new compose from the SAME project, so confirm the prod Postgres is NOT in project `mdp` before reusing
  that name, else use a distinct project + external DATABASE_URL.)
- **Smoke:** `GET https://10.116.204.63:8456/api/health` → 200; login; Type A inbound/outbound; Type B.
- **ora2pg scripts volume (required for probe / Verify / streaming):** the backend writes its generated
  perl scripts into `/opt/ora2pg` (the named volume `${ORA2PG_VOLUME:-mdp_ora2pg_config}`, mounted by this
  compose). The ora2pg container (provided separately, `ORA2PG_CONTAINER`) MUST mount the **same** volume
  at `/config`, e.g.:
  ```
  docker run -d --name ora2pg --network <mdp net> -v mdp_ora2pg_config:/config <ora2pg image>
  ```
  (When reusing v0.1.4's ora2pg, it already mounts `mdp_ora2pg_config:/config` — keep that name.) Streaming
  reads Oracle through this script path; the volume self-populates on a clean deploy.

## 4) Dedicated Grafana @ :3001 (coexist)
```
docker compose -f docker-compose.prod63-grafana.yml --env-file .env.prod63 up -d
# set MDP_NETWORK in .env.prod63 to the MDP stack's network (mdp_default when -p mdp, else mdp_prod63_default)
```
- Grafana up on `:3001`; the **Infinity → MDP Outbound** datasource is provisioned (create
  `GRAFANA_MDP_API_KEY` = an outbound-scoped MDP API key first). Real report dashboards are decided later.
- Do NOT touch the shared Grafana (`:3000`) / Tier0-Edge / OpenRemote / neuron / postgres_uns / umh-core
  / nodered:1880.

## 5) Rollback (prod) — independent of the V2 tags
```
git checkout 7db36fe        # repo mdp-deploy-v0.0 (v0.1.4)
# restore the pg_dump if the DB changed, then bring up the old v0.1.4 compose.
```

## Later
Re-seed PK → migrate small→large → enable streaming per-table by batch (the per-row On/Off switch).
`F00165` is migrate-once with streaming OFF. The Node-RED simulator can be added to `.63` later if needed.
