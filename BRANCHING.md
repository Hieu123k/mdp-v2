# Branching & Release Model (TIPA V2.0)

Trunk-based model for the **TIPA V2.0** repository. V2.0 is a major line (FastAPI + Next.js +
PostgreSQL inherited from MDP V1.x, plus Grafana and Apache Flink added incrementally). It lives in
its **own git repo**, separate from the V1.x release remote `deploy` (`Hieu123k/mdp-deploy-v0.0`)
which keeps shipping to prod `.63` until V2.0 is ready to cut over.

> The release line is **`v2.x`**. No remote is configured yet — the repo is **local-only** until
> the admin provisions the new V2 remote (then `main`/`develop` are pushed there, never to `deploy`).

## Branches

| Branch | Purpose | Rules |
|--------|---------|-------|
| `main` | **Stable trunk** = the latest released V2 code. | Every release is tagged `v2.Y.Z`. Enter ONLY via a reviewed merge (or an admin-approved trunk reset). No direct commits, no force-push, tags are immutable. `main` == the current release tag, byte-identical. |
| `develop` | **Integration / development branch.** | Feature and epic branches branch off `develop` and merge back into `develop`. When a release is cut, `develop` is merged into `main` and tagged `v2.Y.Z`. |
| `feat/<area>-<desc>` | A scoped feature. | Off `develop`. Built + tested DEV-only on `mdp2`; a handoff report must PASS (full pytest 0-failed + `next build` + acceptance) before merge to `develop`. |
| `fix/<area>-<desc>` | A scoped bug fix. | Same flow as `feat/*`. |
| `epic/<name>` | A large, multi-step change. | Off `develop`; integrates incrementally behind a coexist flag where it changes a live path. Planned V2 epics: `epic/reporting-grafana` (Grafana dashboards-as-code, P1) and `epic/ingestion-flink` (Apache Flink CDC ingestion replacing ora2pg, P2+, shipped behind a coexist feature-flag so the old path keeps working). |

## Versioning & rollback

- **SemVer** `v2.Y.Z`. Each release pushes an annotated tag `v2.Y.Z` on the release commit and a
  rollback anchor `pre-v2.Y.Z` pointing at the previous trunk commit.
- Rollback = `git checkout pre-v2.Y.Z` (or reset trunk to it with admin approval).
- **Schema changes**: each schema change is exactly **one alembic migration**; the repo keeps a
  **single alembic head** at all times. The V2.0 scaffold inherits MDP V1.x at head **018**.

## Provenance

The V2.0 backend + frontend are copied byte-identical from the V1.x trunk **`v0.1.5` (`3b3a33f`)**
on the `deploy` remote (the clean release tree via `git archive`, no `.git`/secrets/build
artifacts). The first V2 work (Grafana, then Flink) is additive on top of that baseline.

## Coexistence

V2.0 runs as an **isolated** docker-compose stack (`name: mdpv2`, host port `8457`, volumes
`mdpv2_*`) so it never collides with the live V1 `mdp2`/`mdp` stacks or the shared VPS services
(OpenRemote, neuron, postgres_uns, umh-core, nodered:1880, the shared Grafana). New services added
in V2 must keep using a free port and a V2-scoped name.
