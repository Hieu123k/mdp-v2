# THIẾT KẾ — Pipeline demo: Node-RED Simulator → Type A → MDP → Type B → Dashboard thống kê

> Tác giả: tipa-admin (thiết kế). Triển khai: tipa-deploy-v2. Môi trường: **DEV mdp2 (tipa-vm)** trước. Domain: **nghiệp vụ invoice** (dim `customer` + fact `invoice`). Dashboard dựng **2 datasource** (Postgres/matview + Infinity API) để so sánh.
> Ngày: 2026-06-16 · Bám flow `TIPA_V2.0/simulation/mdp_simulator_flow.json` (đã có sẵn: định nghĩa "đối tượng" = model + attributes Random/List/Seq → POST `/api/inbound/{model}` + GET `/api/outbound/{model}`, header `X-API-Key`, TLS self-signed verify=off).

---

## 0. Luồng tổng thể
```
Node-RED Simulator (UI /ui)                      MDP (mdp2 :8456)                         Grafana
  ┌─ object: sim_customer ─┐  POST /api/inbound/sim_customer   ┌─ Type A: sim_customer (dim) ─┐
  │  (dim, seed 1 lần)     ├─────────────────────────────────▶│  mdp_data.dm_sim_customer    │
  └─ object: sim_invoice ──┘  POST /api/inbound/sim_invoice    │  mdp_data.dm_sim_invoice     │
                                                               │                              │
                                       Type B (read-through):  │  sim_sales_360 = invoice ⋈   │
                                       join trên customer_id    │     customer (LEFT JOIN)     │
                                                               └──────────────┬───────────────┘
                                                   ┌───────── path A: matview mdp_models.sim_sales_360 ─→ grafana_ro (Postgres)
                                                   └───────── path B: GET /api/outbound/sim_sales_360 ──→ Infinity (API)
                                                                                          │
                                                                              Dashboard "Sales Statistics"
```

---

## 1. Type A models (tạo trong MDP trước — để lấy API key inbound)

### 1A. `sim_customer` — DIMENSION (seed 1 lần, ~10 dòng distinct)
| attribute | kiểu | vai trò |
|---|---|---|
| `customer_id` | text | **JOIN KEY** (distinct) |
| `customer_name` | text | nhãn |
| `region` | text | chiều thống kê (North/Central/South) |
| `segment` | text | chiều thống kê (SME/Enterprise/Retail) |
| `created_date` | date | |

### 1B. `sim_invoice` — FACT (stream nhiều dòng)
| attribute | kiểu | vai trò |
|---|---|---|
| `invoice_no` | text | mã (template INV-{seq}) |
| `customer_id` | text | **FK** → sim_customer.customer_id |
| `amount` | float | trị đo (random) |
| `status` | text | open/paid/cancelled |
| `issued_date` | date | trục thời gian |
| `issued_at` | datetime | |

> Cả 2 model tạo qua MDP (UI Object Manager / API), direction = **inbound**, mỗi model 1 API key inbound. Lưu ý MDP Type A là **append** — fact cứ POST thêm; dim chỉ seed 1 lần (xem §2).

---

## 2. Cấu hình Simulator (đảm bảo JOIN khớp)

**Vấn đề:** simulator sinh ngẫu nhiên độc lập → FK của invoice phải tồn tại trong dim, dim phải distinct (tránh fan-out join).

**Giải pháp join-key — dùng tập 10 id cố định:**

**Object `sim_customer`** (key = API key inbound của sim_customer):
- `customer_id`: gen=**Seq**, start=1, step=1 → sinh "1".."10" distinct.
- `customer_name`: gen=Random text, template `CUST-{seq}`.
- `region`: gen=**List** `North, Central, South`.
- `segment`: gen=**List** `SME, Enterprise, Retail`.
- `created_date`: gen=Random date, daysback=365.
- **Seed:** tick object → **POST 1 lần với "Số lần"=10, chu kỳ=0** → 10 dòng customer_id 1..10 distinct. (Lưu object reset Seq về start → POST đúng 1..10.)

**Object `sim_invoice`** (key = API key inbound của sim_invoice):
- `invoice_no`: gen=Random text, template `INV-{seq}`.
- `customer_id`: gen=**List** `1,2,3,4,5,6,7,8,9,10` ← **đúng tập id của dim** → mọi invoice match 1 customer.
- `amount`: gen=Random float, min=50, max=5000, step=0.01.
- `status`: gen=**List** `open, paid, cancelled`.
- `issued_date`: gen=Random date, daysback=90.
- `issued_at`: gen=Random datetime.
- **Chạy:** "POST liên tục", count vài trăm, chu kỳ 1–2s → đổ fact.

> (Tùy chọn nâng cấp simulator sau: thêm chế độ "dim seed 1 lần" vs "fact stream" để khỏi nhầm. MVP không cần sửa code — chỉ cấu hình như trên.)

---

## 3. Type B model — `sim_sales_360` (read-through join)
- **Base/parent:** `sim_invoice` (fact). **Linked/child:** `sim_customer` (dim).
- **Relationship:** `sim_invoice.customer_id = sim_customer.customer_id`, kiểu **LEFT JOIN** (giữ mọi invoice; customer thiếu → null).
- **Cột expose:** `invoice_no, customer_id, customer_name, region, segment, amount, status, issued_date`.
- Direction = **outbound**, 1 API key outbound.
- MDP compile thành SELECT lúc đọc (không phải view). Bật **`matview_enabled`** cho path A (materialize `mdp_models.sim_sales_360` + unique index trên `invoice_no`).

---

## 4. Dashboard "Sales Statistics" — dựng 2 bản để so sánh

### Panel (giống nhau cả 2 path)
1. **KPI hàng**: Tổng doanh thu (Σ amount where status='paid') · Số invoice · Invoice trung bình · Số customer distinct.
2. **Doanh thu theo region** (bar) — group by region.
3. **Doanh thu theo segment** (pie/bar).
4. **Tỷ lệ status** (pie: open/paid/cancelled).
5. **Doanh thu theo thời gian** (time-series theo issued_date).
6. **Top 10 customer theo doanh thu** (table).

### Path A — Postgres `grafana_ro` đọc matview (aggregate ở SQL, nhanh)
- Datasource: PostgreSQL, user **`grafana_ro`** (SELECT trên schema `mdp_models`), DB MDP.
- Ví dụ query:
  ```sql
  -- Doanh thu theo region (paid)
  SELECT region, SUM(amount) AS revenue
  FROM mdp_models.sim_sales_360
  WHERE status='paid' AND issued_date BETWEEN $__timeFrom()::date AND $__timeTo()::date
  GROUP BY region ORDER BY revenue DESC;

  -- Time-series
  SELECT issued_date AS time, SUM(amount) AS revenue
  FROM mdp_models.sim_sales_360 WHERE status='paid'
  GROUP BY issued_date ORDER BY issued_date;
  ```
- **Kỷ luật query:** aggregate ở SQL + time filter + cap (LIMIT ~500–1000 cho bảng chi tiết).

### Path B — Infinity gọi `/api/outbound/sim_sales_360` (read-through, aggregate ở Grafana)
- Datasource Infinity. **Cấu hình bắt buộc (đã gặp lỗi):**
  - **Security → Allowed hosts**: thêm `https://<mdp2-host>:8456`.
  - **TLS → Skip TLS Verify = ON** (cert self-signed) — hoặc add CA + gọi bằng hostname.
- Query: Type JSON · Parser JSONata · Source URL · `GET {host}/api/outbound/sim_sales_360` · header `X-API-Key: <outbound key>`.
- Aggregate bằng **Grafana Transformations** (Group by → sum) vì Infinity không group server-side → **kéo capped rows** (≤500–1000) rồi transform. Phù hợp demo nhỏ; lưu ý đây là điểm yếu so với Path A.

### So sánh (mục tiêu của việc dựng 2 bản)
| Tiêu chí | Path A (Postgres/matview) | Path B (Infinity/API) |
|---|---|---|
| Aggregate | SQL server-side (nhanh, đúng) | Grafana transform (client, giới hạn) |
| Hạ tầng | cần grafana_ro + matview refresh | chỉ cần API key + allowed-host/TLS |
| Tươi dữ liệu | theo cadence refresh matview | real-time read-through |
| Khuyến nghị | thống kê/đồ thị nặng | xem nhanh, bảng nhỏ |

---

## 5. Phân công triển khai (tipa-deploy-v2, trên mdp2)
1. **Tạo 2 Type A model** `sim_customer`, `sim_invoice` (inbound) → lấy 2 API key inbound.
2. **Tạo Type B** `sim_sales_360` (relationship invoice⋈customer trên customer_id, LEFT JOIN, cột §3) → API key outbound; **bật matview** + refresh lần đầu.
3. **Dựng Node-RED sim** (stack riêng `docker-compose.sim.yml`, network thấy `reverse-proxy:8456`); nạp 2 object + 2 key theo §2 (hoặc pre-seed flow context). Seed dim 10 dòng → stream fact vài trăm dòng.
4. **Grafana:** tạo datasource `grafana_ro` (Postgres) + Infinity (allowed-host + skip TLS); import/dựng dashboard "Sales Statistics" **2 bản** (§4).
5. **Coexist:** chỉ đụng stack mdp2/sim; không chạm dịch vụ khác.

## 6. Acceptance (mdp2, có ảnh)
- [ ] POST sim_customer (10) + sim_invoice (≥200) → MDP 2xx; `dm_sim_*` có dòng.
- [ ] GET `/api/outbound/sim_sales_360` trả join đúng (invoice kèm region/segment).
- [ ] Matview `mdp_models.sim_sales_360` có dữ liệu; grafana_ro SELECT được.
- [ ] Dashboard Path A: 6 panel hiển thị thống kê đúng (revenue theo region/segment/time/top).
- [ ] Dashboard Path B: cùng số liệu (qua Infinity), allowed-host/TLS OK.
- [ ] Coexist nguyên; teardown demo data nếu cần.

## 7. Rủi ro / điểm cần chốt
- **Fan-out join** nếu dim customer_id trùng → seed dim đúng 10 distinct (Seq, POST 10).
- **Matview refresh cadence** (path A) hiện thủ công → demo refresh tay; production-hoá scheduler là việc riêng (backlog).
- **Kiểu dữ liệu** amount/issued_date khi qua Type A inbound: xác nhận MDP cast đúng float/date để SQL aggregate/time-filter chạy.
- Infinity self-signed: nếu không skip-TLS sẽ lỗi PKIX như iHUB/Grafana đã gặp.

---
*Bước sau: admin chuyển bản thiết kế này thành prompt cho tipa-deploy-v2 (file `handoff/prompts/NN_*.md`) khi anh ra lệnh.*
