#!/usr/bin/env python3
"""Prompt 31 — idempotent bootstrap of the accounting report-sample models + inbound keys.

Reads ``accounting_models.json`` (8 Type A + 5 Type B; no secrets) and, against an MDP instance:
  * creates each model that does not already exist (skips existing — IDEMPOTENT). The 5 Type B get
    ``matview_enabled`` + ``matview_refresh_interval_sec=300`` so the v2.2.0 MatviewRefresher keeps Path A
    fresh on its own.
  * ensures one INBOUND key per Type A model (label ``acc_in_<model>``): reuses + reveals an existing key
    (v2.2.0 reveal feature, level-2 password) or creates a new one.
  * writes the ``{label: value}`` map to a GIT-IGNORED file (default ``sim/.acc_keys.json``) for the
    simulator's ``MDP_ACC_KEYS`` env, and prints only the LABELS + status to stdout — NEVER the key values.

Config via env/args ONLY (never committed):
  MDP_BASE_URL          MDP edge URL reachable from here. mdp2 host: http://localhost:8457 (default).
                        Inside the MDP network: http://reverse-proxy:8456. prod: its published edge URL.   [--base]
  MDP_ADMIN_TOKEN       admin JWT (required)                                                                [--token]
  APIKEY_VIEW_PASSWORD  level-2 reveal password (default 0000)                                              [--view-password]
  --models <path>       defaults to the sibling accounting_models.json
  --keys-out <path>     defaults to sim/.acc_keys.json (git-ignored)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API_PREFIX = "/api"  # the integration/admin routes sit behind /api on the MDP edge
DIM_MODELS = {"acc_customer", "acc_vendor", "acc_account"}


def req(base, path, token, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw.decode()[:200]
        return e.code, detail


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Idempotent accounting models + inbound keys bootstrap.")
    ap.add_argument("--base", default=os.environ.get("MDP_BASE_URL", "http://localhost:8457"))
    ap.add_argument("--token", default=os.environ.get("MDP_ADMIN_TOKEN", ""))
    ap.add_argument("--view-password", default=os.environ.get("APIKEY_VIEW_PASSWORD", "0000"))
    ap.add_argument("--models", default=os.path.join(here, "accounting_models.json"))
    ap.add_argument("--keys-out", default=os.path.join(here, "sim", ".acc_keys.json"))
    args = ap.parse_args()
    if not args.token:
        sys.exit("ERROR: set MDP_ADMIN_TOKEN (admin JWT) via env or --token")

    base = args.base.rstrip("/")
    defs = json.load(open(args.models, encoding="utf-8"))

    st, existing = req(base, f"{API_PREFIX}/data-models", args.token)
    if st != 200:
        sys.exit(f"ERROR: list models -> {st} {existing}")
    by_name = {m["name"]: m for m in existing}
    have = set(by_name)

    print(f"== Bootstrap accounting models @ {base} ==")
    created = skipped = failed = reconciled = 0
    for d in defs:
        if d["name"] in have:
            # Idempotent reconcile: ensure the 5 Type B carry matview_enabled + the 300s auto-refresh cadence
            # even when the model already exists (so MatviewRefresher keeps Path A fresh).
            if d["type"] == "B":
                cur = by_name[d["name"]]
                want = {"matview_enabled": True, "matview_refresh_interval_sec": 300}
                if (cur.get("matview_enabled") is not True
                        or cur.get("matview_refresh_interval_sec") != 300):
                    st, res = req(base, f"{API_PREFIX}/data-models/{cur['id']}", args.token, "PUT", want)
                    tag = "RECONCILED matview@300s" if st in (200, 201) else f"RECONCILE FAILED {st}"
                    print(f"  model {d['name']:24} type B  EXISTS ({tag})")
                    reconciled += 1
                    continue
            print(f"  model {d['name']:24} type {d['type']}  EXISTS (skip)")
            skipped += 1
            continue
        st, res = req(base, f"{API_PREFIX}/data-models", args.token, "POST", d)
        if st in (200, 201):
            extra = f"  matview@{d.get('matview_refresh_interval_sec')}s" if d["type"] == "B" else ""
            print(f"  model {d['name']:24} type {d['type']}  CREATED{extra}")
            created += 1
        else:
            print(f"  model {d['name']:24} type {d['type']}  CREATE FAILED -> {st} {res}")
            failed += 1
    print(f"  models: {created} created, {reconciled} reconciled, {skipped} existed, {failed} failed")

    # one inbound key per Type A model
    type_a = [d["name"] for d in defs if d["type"] == "A"]
    st, keys = req(base, f"{API_PREFIX}/api-keys", args.token)
    key_by_label = {k["name"]: k for k in (keys or [])}
    out = {}
    print("== inbound keys (one per Type A model) ==")
    for model in type_a:
        label = f"acc_in_{model}"
        if label in key_by_label:
            kid = key_by_label[label]["id"]
            st, rv = req(base, f"{API_PREFIX}/api-keys/{kid}/reveal", args.token, "POST",
                         {"password": args.view_password})
            if st == 200 and rv and rv.get("available") and rv.get("api_key"):
                out[label] = rv["api_key"]
                print(f"  key {label:26} EXISTS (revealed)")
            else:
                print(f"  key {label:26} EXISTS (value not available — reveal off / legacy key)")
        else:
            st, res = req(base, f"{API_PREFIX}/api-keys", args.token, "POST",
                          {"name": label, "description": "prompt31 accounting inbound (sim)",
                           "allowed_directions": ["inbound"], "allowed_models": [model]})
            if st in (200, 201) and res and res.get("api_key"):
                out[label] = res["api_key"]
                print(f"  key {label:26} CREATED")
            else:
                print(f"  key {label:26} CREATE FAILED -> {st} {res}")

    os.makedirs(os.path.dirname(os.path.abspath(args.keys_out)), exist_ok=True)
    with open(args.keys_out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    try:
        os.chmod(args.keys_out, 0o600)
    except Exception:
        pass
    print(f"== wrote {len(out)}/{len(type_a)} key VALUES to {args.keys_out} "
          f"(git-ignored; never printed). Load into the simulator as MDP_ACC_KEYS: ==")
    print(f"   export MDP_ACC_KEYS=$(cat {args.keys_out})")


if __name__ == "__main__":
    main()
