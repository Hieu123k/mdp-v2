# Accounting report-sample artifacts (prod-safe)

Portable artifacts to stand up the **Accounting (Sample)** report with data fired from a **Node-RED
simulator** — validated on mdp2, intended for tipa-mdp to deploy on prod `.63` (prompt 32).

🔴 **COEXIST:** the simulator is fully namespaced (`mdpv2-sim-nodered`, host port **1881**, own image +
volume `mdpv2_sim_data`). It never touches the unrelated `nodered:1880` already on `.63`.

## Pieces
| artifact | path | purpose |
|---|---|---|
| A — simulator | `ops/sim/` (this dir) | prod-safe Node-RED that POSTs demo `acc_*` data via `/ui` |
| B — bootstrap | `ops/bootstrap_accounting_models.py` | idempotently create 8 Type A + 5 Type B accounting models + outbound dashboard key; prints the inbound key labels/values to load into the sim |
| C — grafana_ro | `ops/grafana_ro_setup.sql` | read-only Postgres role for the Grafana datasource |
| D — dashboard | `ops/dashboards/accounting_sample.json` | 5-panel "Accounting (Sample)" dashboard (`${DS_POSTGRES}`) |

## Deploy order
1. **Bootstrap the models** (creates models + matview auto-refresh @300s; skips anything that already exists):
   ```bash
   MDP_BASE_URL=http://reverse-proxy:8456 MDP_ADMIN_TOKEN=<admin-jwt> \
     python3 ops/bootstrap_accounting_models.py
   ```
   It prints, per inbound model, the key **label** and **value** — collect these into the `MDP_ACC_KEYS`
   JSON for the sim (the value is shown once; it is never committed).
2. **Stand up the simulator** (builds the image — bakes the dashboard nodes + the flow):
   ```bash
   cd ops/sim && cp .env.example .env
   #   prod : MDP_NETWORK=mdp_default     SIM_PORT=1881
   #   mdp2 : MDP_NETWORK=mdpv2_default   SIM_PORT=1882   (1881 = existing DEV sim)
   #   set MDP_ACC_KEYS={"acc_in_acc_customer":"mdp_live_...", ...} from step 1
   docker compose -f docker-compose.sim.prod63.yml up -d --build
   ```
   Open `http://<host>:<SIM_PORT>/ui`. The 8 acc objects self-seed on start; click **load acc keys** to
   pull the key values from `MDP_ACC_KEYS`.
3. **Fire from `/ui`**: seed the 3 dimensions first (acc_customer ×10, acc_vendor ×8, acc_account ×8 — so
   facts reference existing FK ids → **0 orphan**), then stream the 5 facts.
4. **Grafana**: apply `ops/grafana_ro_setup.sql` (as a superuser), add a Postgres datasource using the
   `grafana_ro` role, import `ops/dashboards/accounting_sample.json` and repoint its `${DS_POSTGRES}`
   variable to that datasource. The 5 panels read `mdp_models.acc_*` (Path A matviews, auto-refreshed).

## Secrets
Nothing here contains a real key/secret. The MDP base URL, the credential secret and the API-key **values**
are all runtime env (`ops/sim/.env`, git-ignored). The flow's `load acc keys` reads them from `MDP_ACC_KEYS`.
