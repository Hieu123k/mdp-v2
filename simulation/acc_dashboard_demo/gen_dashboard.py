import json
PG = {"type": "postgres", "uid": "mdp_postgres"}
panels = []
_id = [0]
def add(p): _id[0] += 1; p["id"] = _id[0]; panels.append(p)
def t(sql, fmt="table", ref="A"): return {"refId": ref, "datasource": PG, "format": fmt, "rawQuery": True, "rawSql": sql}
def join(byf): return {"id": "joinByField", "options": {"byField": byf, "mode": "outer"}}
def calc(left, op, right, alias): return {"id": "calculateField", "options": {"mode": "binary", "binary": {"left": left, "operator": op, "right": right}, "alias": alias, "replaceFields": False}}
def organize(hide): return {"id": "organize", "options": {"excludeByName": {h: True for h in hide}}}
AR, AP, RC, PM, GL = ("mdp_models.acc_ar_360", "mdp_models.acc_ap_360", "mdp_models.acc_receipts_enriched", "mdp_models.acc_payments_enriched", "mdp_models.acc_gl_report")

# 1. KPI: Revenue / Cost / Gross Profit (=Rev-Cost) / Margin  — cross-fact = 2 queries + subtract in panel
add({"type": "stat", "title": "KPI: Revenue / Cost / Gross Profit / Margin (Rev & Cost from 2 facts, subtracted in panel)",
     "datasource": PG, "gridPos": {"h": 4, "w": 24, "x": 0, "y": 0},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": "value", "graphMode": "none", "textMode": "value", "orientation": "horizontal"},
     "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "Margin"}, "properties": [{"id": "unit", "value": "percentunit"}]}]},
     "targets": [t("SELECT 1 AS k, round(sum(amount)::numeric,2)::float8 AS \"Revenue\" FROM " + AR, ref="A"),
                 t("SELECT 1 AS k, round(sum(amount)::numeric,2)::float8 AS \"Cost\" FROM " + AP, ref="B")],
     "transformations": [join("k"), calc("Revenue", "-", "Cost", "Gross Profit"), calc("Gross Profit", "/", "Revenue", "Margin"), organize(["k"])]})

# 2. Revenue vs Cost vs Profit by month (time series; profit = 2-query subtract)
add({"type": "timeseries", "title": "Revenue vs Cost vs Profit by month", "datasource": PG, "gridPos": {"h": 9, "w": 24, "x": 0, "y": 4},
     "fieldConfig": {"defaults": {"custom": {"drawStyle": "line", "fillOpacity": 10, "lineWidth": 2}}, "overrides": []},
     "options": {"legend": {"showLegend": True, "placement": "bottom"}, "tooltip": {"mode": "multi"}},
     "targets": [t("SELECT date_trunc('month',issue_date)::timestamp AS time, round(sum(amount)::numeric,2)::float8 AS \"Revenue\" FROM " + AR + " GROUP BY 1 ORDER BY 1", "table", "A"),
                 t("SELECT date_trunc('month',issue_date)::timestamp AS time, round(sum(amount)::numeric,2)::float8 AS \"Cost\" FROM " + AP + " GROUP BY 1 ORDER BY 1", "table", "B")],
     "transformations": [join("time"), calc("Revenue", "-", "Cost", "Profit")]})

# 3. Revenue by region (bar)
add({"type": "barchart", "title": "Revenue by Region (AR)", "datasource": PG, "gridPos": {"h": 8, "w": 8, "x": 0, "y": 13},
     "options": {"xField": "region", "orientation": "auto", "showValue": "auto", "legend": {"showLegend": False}},
     "targets": [t("SELECT region, round(sum(amount)::numeric,2)::float8 AS revenue FROM " + AR + " GROUP BY region ORDER BY revenue DESC")]})
# 4. Cost by category (bar)
add({"type": "barchart", "title": "Cost by Category (AP)", "datasource": PG, "gridPos": {"h": 8, "w": 8, "x": 8, "y": 13},
     "options": {"xField": "category", "orientation": "auto", "showValue": "auto", "legend": {"showLegend": False}},
     "targets": [t("SELECT category, round(sum(amount)::numeric,2)::float8 AS cost FROM " + AP + " GROUP BY category ORDER BY cost DESC")]})
# 5. AR invoice status (pie)
add({"type": "piechart", "title": "AR Invoice Status", "datasource": PG, "gridPos": {"h": 8, "w": 8, "x": 16, "y": 13},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}, "pieType": "donut", "legend": {"showLegend": True, "placement": "right", "values": ["value"]}},
     "targets": [t("SELECT status, count(*)::int AS invoices FROM " + AR + " GROUP BY status ORDER BY status")]})
# 6. Top 10 customers (table)
add({"type": "table", "title": "Top 10 Customers by Revenue", "datasource": PG, "gridPos": {"h": 9, "w": 12, "x": 0, "y": 21}, "options": {"showHeader": True},
     "targets": [t("SELECT customer_name, round(sum(amount)::numeric,2)::float8 AS revenue, count(*)::int AS invoices FROM " + AR + " GROUP BY customer_name ORDER BY revenue DESC LIMIT 10")]})
# 7. Top 10 vendors (table)
add({"type": "table", "title": "Top 10 Vendors by Cost", "datasource": PG, "gridPos": {"h": 9, "w": 12, "x": 12, "y": 21}, "options": {"showHeader": True},
     "targets": [t("SELECT vendor_name, round(sum(amount)::numeric,2)::float8 AS cost, count(*)::int AS bills FROM " + AP + " GROUP BY vendor_name ORDER BY cost DESC LIMIT 10")]})
# 8. Cash in vs out vs net by month (cross-fact 2-query subtract)
add({"type": "timeseries", "title": "Cash In vs Out vs Net by month (Receipts - Payments, subtracted in panel)", "datasource": PG, "gridPos": {"h": 9, "w": 24, "x": 0, "y": 30},
     "fieldConfig": {"defaults": {"custom": {"drawStyle": "bars", "fillOpacity": 60, "lineWidth": 1}}, "overrides": []},
     "options": {"legend": {"showLegend": True, "placement": "bottom"}, "tooltip": {"mode": "multi"}},
     "targets": [t("SELECT date_trunc('month',receipt_date)::timestamp AS time, round(sum(amount)::numeric,2)::float8 AS \"Cash In\" FROM " + RC + " GROUP BY 1 ORDER BY 1", "table", "A"),
                 t("SELECT date_trunc('month',payment_date)::timestamp AS time, round(sum(amount)::numeric,2)::float8 AS \"Cash Out\" FROM " + PM + " GROUP BY 1 ORDER BY 1", "table", "B")],
     "transformations": [join("time"), calc("Cash In", "-", "Cash Out", "Net Cash")]})
# 9. AR aging (bar)
add({"type": "barchart", "title": "AR Aging (outstanding, status<>paid)", "datasource": PG, "gridPos": {"h": 8, "w": 12, "x": 0, "y": 39},
     "options": {"xField": "bucket", "orientation": "auto", "showValue": "auto", "legend": {"showLegend": False}},
     "targets": [t("SELECT CASE WHEN current_date-due_date<=30 THEN '0-30' WHEN current_date-due_date<=60 THEN '31-60' WHEN current_date-due_date<=90 THEN '61-90' ELSE '90+' END AS bucket, round(sum(amount)::numeric,2)::float8 AS outstanding FROM " + AR + " WHERE status<>'paid' AND current_date>=due_date GROUP BY 1 ORDER BY 1")]})
# 10. AP aging (bar)
add({"type": "barchart", "title": "AP Aging (outstanding, status<>paid)", "datasource": PG, "gridPos": {"h": 8, "w": 12, "x": 12, "y": 39},
     "options": {"xField": "bucket", "orientation": "auto", "showValue": "auto", "legend": {"showLegend": False}},
     "targets": [t("SELECT CASE WHEN current_date-due_date<=30 THEN '0-30' WHEN current_date-due_date<=60 THEN '31-60' WHEN current_date-due_date<=90 THEN '61-90' ELSE '90+' END AS bucket, round(sum(amount)::numeric,2)::float8 AS outstanding FROM " + AP + " WHERE status<>'paid' AND current_date>=due_date GROUP BY 1 ORDER BY 1")]})
# 11. Trial balance by account_type (bar, GL)
add({"type": "barchart", "title": "Trial Balance / P&L by account_type (sum debit-credit)", "datasource": PG, "gridPos": {"h": 8, "w": 24, "x": 0, "y": 47},
     "options": {"xField": "account_type", "orientation": "auto", "showValue": "auto", "legend": {"showLegend": False}},
     "targets": [t("SELECT account_type, round(sum(debit-credit)::numeric,2)::float8 AS net FROM " + GL + " GROUP BY account_type ORDER BY account_type")]})

dash = {"dashboard": {"title": "Accounting Statistics", "uid": "acc_stats", "tags": ["mdp", "v2", "accounting", "demo"],
                      "schemaVersion": 39, "timezone": "browser", "time": {"from": "now-120d", "to": "now"}, "editable": True,
                      "annotations": {"list": []}, "panels": panels, "version": 0},
        "overwrite": True, "folderId": 0, "message": "prompt25 accounting dashboard (Path A)"}
print(json.dumps(dash))
