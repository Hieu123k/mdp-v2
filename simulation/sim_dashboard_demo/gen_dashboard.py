import json
PG = {"type": "postgres", "uid": "mdp_postgres"}
INF = {"type": "yesoreyeram-infinity-datasource", "uid": "mdp_out_sim"}
IURL = "http://reverse-proxy:8456/api/outbound/sim_sales_360"
PAID = "status='paid'"  # single-quoted literal preserved (file piped via stdin, no shell mangling)
panels = []
_id = [0]


def add(p):
    _id[0] += 1
    p["id"] = _id[0]
    panels.append(p)


def row(t, y):
    add({"type": "row", "title": t, "collapsed": False, "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}})


def pgt(sql, fmt="table"):
    return [{"refId": "A", "datasource": PG, "format": fmt, "rawQuery": True, "rawSql": sql}]


def inf(url, cols):
    return [{"refId": "A", "datasource": INF, "type": "json", "source": "url", "format": "table",
             "parser": "backend", "url": url, "url_options": {"method": "GET"},
             "root_selector": "data.data", "columns": cols}]


def C(s, t="string"):
    return {"selector": s, "text": s, "type": t}


def gb(group, fld, agg="sum"):
    return [{"id": "groupBy", "options": {"fields": {
        group: {"operation": "groupby", "aggregations": []},
        fld: {"operation": "aggregate", "aggregations": [agg]}}}}]


# ============ PATH A : Postgres / matview (server-side SQL) ============
row("Path A - Postgres (grafana_ro) reads matview mdp_models.sim_sales_360 (server-side SQL aggregate)", 0)
add({"type": "stat", "title": "KPI: Paid Revenue / Invoices / Avg Amount / Customers (SQL)", "datasource": PG,
     "gridPos": {"h": 4, "w": 24, "x": 0, "y": 1},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                 "colorMode": "value", "graphMode": "none", "textMode": "value", "orientation": "horizontal"},
     "targets": pgt("SELECT (round((sum(amount) filter (where " + PAID + "))::numeric,2))::float8 AS \"Paid Revenue\", "
                    "count(*)::int AS \"Invoices\", (round(avg(amount)::numeric,2))::float8 AS \"Avg Amount\", "
                    "count(distinct customer_id)::int AS \"Customers\" FROM mdp_models.sim_sales_360;")})
add({"type": "barchart", "title": "Revenue by Region (paid)", "datasource": PG,
     "gridPos": {"h": 8, "w": 8, "x": 0, "y": 5}, "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}}, "overrides": []},
     "options": {"xField": "region", "orientation": "auto", "showValue": "auto", "legend": {"showLegend": False}},
     "targets": pgt("SELECT region, (round((sum(amount) filter (where " + PAID + "))::numeric,2))::float8 AS revenue "
                    "FROM mdp_models.sim_sales_360 GROUP BY region ORDER BY revenue DESC;")})
add({"type": "piechart", "title": "Revenue by Segment (paid)", "datasource": PG,
     "gridPos": {"h": 8, "w": 8, "x": 8, "y": 5},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}, "pieType": "pie",
                 "legend": {"showLegend": True, "placement": "right", "values": ["value"]}},
     "targets": pgt("SELECT segment, (round((sum(amount) filter (where " + PAID + "))::numeric,2))::float8 AS revenue "
                    "FROM mdp_models.sim_sales_360 GROUP BY segment ORDER BY revenue DESC;")})
add({"type": "piechart", "title": "Invoice Status Ratio", "datasource": PG,
     "gridPos": {"h": 8, "w": 8, "x": 16, "y": 5},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}, "pieType": "donut",
                 "legend": {"showLegend": True, "placement": "right", "values": ["value"]}},
     "targets": pgt("SELECT status, count(*)::int AS invoices FROM mdp_models.sim_sales_360 GROUP BY status ORDER BY status;")})
add({"type": "timeseries", "title": "Paid Revenue by Issued Date", "datasource": PG,
     "gridPos": {"h": 8, "w": 16, "x": 0, "y": 13},
     "fieldConfig": {"defaults": {"custom": {"drawStyle": "bars", "fillOpacity": 60, "lineWidth": 1}}, "overrides": []},
     "options": {"legend": {"showLegend": False}, "tooltip": {"mode": "single"}},
     "targets": pgt("SELECT issued_date::timestamp AS \"time\", (round((sum(amount) filter (where " + PAID + "))::numeric,2))::float8 AS revenue "
                    "FROM mdp_models.sim_sales_360 GROUP BY issued_date ORDER BY issued_date;", "time_series")})
add({"type": "table", "title": "Top 10 Customers by Paid Revenue", "datasource": PG,
     "gridPos": {"h": 8, "w": 8, "x": 16, "y": 13}, "options": {"showHeader": True},
     "targets": pgt("SELECT customer_name, (round((sum(amount) filter (where " + PAID + "))::numeric,2))::float8 AS paid_revenue, "
                    "count(*)::int AS invoices FROM mdp_models.sim_sales_360 GROUP BY customer_name ORDER BY paid_revenue DESC LIMIT 10;")})

# ============ PATH B : Infinity / outbound API (client-side aggregate) ============
row("Path B - Infinity reads GET /api/outbound/sim_sales_360 (read-through; client-side aggregate)", 21)
add({"type": "stat", "title": "KPI: Paid Revenue (sum) via outbound API", "datasource": INF,
     "gridPos": {"h": 4, "w": 24, "x": 0, "y": 22},
     "options": {"reduceOptions": {"calcs": ["sum"], "fields": "", "values": False},
                 "colorMode": "value", "graphMode": "none", "textMode": "value", "orientation": "horizontal"},
     "targets": inf(IURL + "?status=paid&limit=500", [C("amount", "number")])})
add({"type": "barchart", "title": "Revenue by Region (paid)", "datasource": INF,
     "gridPos": {"h": 8, "w": 8, "x": 0, "y": 26}, "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}}, "overrides": []},
     "options": {"xField": "region", "orientation": "auto", "showValue": "auto", "legend": {"showLegend": False}},
     "targets": inf(IURL + "?status=paid&limit=500", [C("region"), C("amount", "number")]), "transformations": gb("region", "amount")})
add({"type": "piechart", "title": "Revenue by Segment (paid)", "datasource": INF,
     "gridPos": {"h": 8, "w": 8, "x": 8, "y": 26},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}, "pieType": "pie",
                 "legend": {"showLegend": True, "placement": "right", "values": ["value"]}},
     "targets": inf(IURL + "?status=paid&limit=500", [C("segment"), C("amount", "number")]), "transformations": gb("segment", "amount")})
add({"type": "piechart", "title": "Invoice Status Ratio", "datasource": INF,
     "gridPos": {"h": 8, "w": 8, "x": 16, "y": 26},
     "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True}, "pieType": "donut",
                 "legend": {"showLegend": True, "placement": "right", "values": ["value"]}},
     "targets": inf(IURL + "?limit=500", [C("status"), C("invoice_no")]), "transformations": gb("status", "invoice_no", "count")})
add({"type": "timeseries", "title": "Paid Revenue by Issued Date", "datasource": INF,
     "gridPos": {"h": 8, "w": 16, "x": 0, "y": 34},
     "fieldConfig": {"defaults": {"custom": {"drawStyle": "bars", "fillOpacity": 60, "lineWidth": 1}}, "overrides": []},
     "options": {"legend": {"showLegend": False}, "tooltip": {"mode": "single"}},
     "targets": inf(IURL + "?status=paid&limit=500", [C("issued_date", "timestamp"), C("amount", "number")]), "transformations": gb("issued_date", "amount")})
add({"type": "table", "title": "Top 10 Customers by Paid Revenue", "datasource": INF,
     "gridPos": {"h": 8, "w": 8, "x": 16, "y": 34}, "options": {"showHeader": True},
     "targets": inf(IURL + "?status=paid&limit=500", [C("customer_name"), C("amount", "number")]),
     "transformations": gb("customer_name", "amount") + [{"id": "sortBy", "options": {"sort": [{"field": "amount (sum)", "desc": True}]}}]})

dash = {"dashboard": {"title": "Sales Statistics (sim demo)", "uid": "sim_sales_stats",
                      "tags": ["mdp", "v2", "sim", "demo"], "schemaVersion": 39, "timezone": "browser",
                      "time": {"from": "now-90d", "to": "now"}, "editable": True, "annotations": {"list": []},
                      "panels": panels, "version": 0},
        "overwrite": True, "folderId": 0, "message": "prompt22 sim sales dashboard (fixed quotes)"}
print(json.dumps(dash))
