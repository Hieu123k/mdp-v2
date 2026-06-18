# Prompt 31 — prod-safe Node-RED simulator image for the accounting report sample.
# Self-contained: bakes node-red-dashboard (the /ui nodes the flow uses) + the simulator flow, so a fresh
# volume is initialised with the flow and the demo objects self-seed on start. No secrets are baked in —
# the MDP base URL and the API-key VALUES are supplied at runtime via env (see .env.example).
FROM nodered/node-red:4.0.9

# /ui dashboard nodes used by the simulator flow (pinned to the version validated on mdp2).
RUN npm install --no-audit --no-fund --no-update-notifier node-red-dashboard@3.6.6

# Seed the flow + settings into the image's /data so a brand-new named volume picks them up on first run.
COPY --chown=node-red:node-red mdp_simulator_flow.json /data/flows.json
COPY --chown=node-red:node-red settings.js /data/settings.js
