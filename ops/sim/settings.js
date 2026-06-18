// Prompt 31 — minimal Node-RED settings for the prod-safe accounting simulator.
// Defaults apply for anything omitted. Context is persisted on the local filesystem (matches the setup
// validated on mdp2); the demo objects self-seed on start regardless. credentialSecret comes from env
// (never committed) — with no flows_cred.json shipped, Node-RED creates a fresh one.
module.exports = {
    flowFile: "flows.json",
    flowFilePretty: true,
    credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET || false,
    contextStorage: { default: { module: "localfilesystem" } },
    uiPort: process.env.PORT || 1880,
    logging: { console: { level: "info", metrics: false, audit: false } },
    exportGlobalContextKeys: false,
    // Expose the runtime acc key map to the flow's "load acc keys" function via global context. settings.js
    // runs in Node with full process.env access, so this reliably surfaces MDP_ACC_KEYS (set at runtime,
    // never committed) as global.get("accKeys"). Empty when unset → no keys loaded, sim still starts.
    functionGlobalContext: { accKeys: process.env.MDP_ACC_KEYS || "" },
    // node-red-dashboard mounts the simulator UI at /ui
    ui: { path: "ui" },
};
