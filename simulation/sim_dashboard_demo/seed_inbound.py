#!/usr/bin/env python3
"""prompt 22 — seed the sim_customer (dim) + sim_invoice (fact) Type A models via MDP inbound.

Replicates the Node-RED simulator's Seq/List config deterministically:
  - sim_customer: customer_id = Seq 1..10 (distinct dim), region/segment = List (round-robin, decoupled).
  - sim_invoice : customer_id = List 1..10 (FK into dim), amount = float 50..5000, status = List, dates spread 90d.

Run INSIDE the mdpv2-backend container (reaches the API at reverse-proxy:8456); the inbound API key is
passed via env (NEVER committed):
    docker exec -e KEY="$INBOUND_KEY" -i mdpv2-backend-1 python - < seed_inbound.py
"""
import os, json, urllib.request, urllib.error, random, datetime

KEY = os.environ["KEY"]
BASE = os.environ.get("BASE", "http://reverse-proxy:8456/api")
N_INVOICES = int(os.environ.get("N_INVOICES", "240"))


def post(model, rec):
    req = urllib.request.Request(f"{BASE}/inbound/{model}", data=json.dumps(rec).encode(),
                                 method="POST", headers={"X-API-Key": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:300]


regions = ["North", "Central", "South"]
segments = ["SME", "Enterprise", "Retail"]
statuses = ["open", "paid", "cancelled"]
random.seed(22)  # reproducible distribution

ok_c, first_err = 0, None
for i in range(1, 11):  # dim: seed-once, 10 distinct ids
    rec = {"customer_id": str(i), "customer_name": f"CUST-{i}",
           "region": regions[(i - 1) % 3], "segment": segments[(2 * i) % 3],
           "created_date": (datetime.date.today() - datetime.timedelta(days=random.randint(0, 365))).isoformat()}
    s, b = post("sim_customer", rec)
    if s in (200, 201):
        ok_c += 1
    elif first_err is None:
        first_err = (i, s, b)
print("customers ok:", ok_c, "first_err:", first_err)

ok_i, first_err = 0, None
for n in range(1, N_INVOICES + 1):  # fact: stream
    cid = random.randint(1, 10)
    d = datetime.date.today() - datetime.timedelta(days=random.randint(0, 90))
    rec = {"invoice_no": f"INV-{n}", "customer_id": str(cid), "amount": round(random.uniform(50, 5000), 2),
           "status": random.choice(statuses), "issued_date": d.isoformat(),
           "issued_at": datetime.datetime.combine(d, datetime.time(random.randint(0, 23), random.randint(0, 59))).isoformat()}
    s, b = post("sim_invoice", rec)
    if s in (200, 201):
        ok_i += 1
    elif first_err is None:
        first_err = (n, s, b)
print("invoices ok:", ok_i, "first_err:", first_err)
