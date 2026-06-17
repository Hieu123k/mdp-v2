# THIẾT KẾ — Demo kế toán đa bảng: Node-RED Simulator → Type A (8 bảng) → Type B (5 join) → Dashboard thống kê

> Tác giả: tipa-admin (thiết kế). Triển khai: tipa-deploy-v2. Môi trường: **DEV mdp2** trước. Nguồn bắn: **Node-RED Simulator** (`TIPA_V2.0/simulation/mdp_simulator_flow.json`, host mdp2 `reverse-proxy:8456` — KHÔNG prod).
> Phạm vi: **AR (phải thu) + AP (phải trả) + GL (sổ cái) + Cash (dòng tiền)**. KPI: Doanh thu/Chi phí/Lợi nhuận · Top đối tác · Dòng tiền · Aging công nợ.
> Ngày 2026-06-16. **Thay thế** demo invoice tối giản (prompt 22/23); có thể drop `sim_customer/sim_invoice` cũ.

---

## 0. Nguyên tắc join-key (tránh fan-out)
- **Dim** seed 1 lần, distinct, id bằng **Seq** (1..N).
- **Fact** tham chiếu FK bằng **List** đúng dải id của dim → mọi FK khớp, dim không trùng → join 1-nhiều sạch.

---

## 1. Type A — 8 bảng (mỗi bảng 1 model inbound + 1 API key)

### Dim (seed distinct 1 lần)
| Model | Attributes (kiểu · sinh) | Seed |
|---|---|---|
| **`acc_customer`** | `customer_id` int·Seq(1) · `customer_name` text·`CUST-{seq}` · `region` text·List `North,Central,South` · `segment` text·List `SME,Enterprise,Retail` | POST 1 lần ×10 |
| **`acc_vendor`** | `vendor_id` int·Seq(1) · `vendor_name` text·`VEND-{seq}` · `category` text·List `Material,Logistics,Service,Utility` | POST 1 lần ×8 |
| **`acc_account`** | `account_id` int·Seq(1) · `account_name` text·`ACC-{seq}` · `account_type` text·List `Asset,Liability,Equity,Revenue,Expense` | POST 1 lần ×8 |

### Fact (stream)
| Model | Attributes | FK |
|---|---|---|
| **`acc_invoice`** (AR) | `invoice_no` text·`INV-{seq}` · `customer_id` int·List `1..10` · `issue_date` date·daysback120 · `due_date` date·daysback90 · `amount` float·50..5000 · `tax_amount` float·0..500 · `status` text·List `open,paid,overdue,cancelled` | →customer |
| **`acc_receipt`** (AR cash-in) | `receipt_no` text·`RCP-{seq}` · `customer_id` int·List `1..10` · `receipt_date` date·daysback90 · `amount` float·50..5000 · `method` text·List `cash,bank,card` | →customer |
| **`acc_bill`** (AP) | `bill_no` text·`BILL-{seq}` · `vendor_id` int·List `1..8` · `issue_date` date·daysback120 · `due_date` date·daysback90 · `amount` float·30..4000 · `status` text·List `open,paid,overdue` | →vendor |
| **`acc_payment`** (AP cash-out) | `payment_no` text·`PAY-{seq}` · `vendor_id` int·List `1..8` · `payment_date` date·daysback90 · `amount` float·30..4000 · `method` text·List `cash,bank` | →vendor |
| **`acc_journal`** (GL) | `entry_id` text·`JE-{seq}` · `account_id` int·List `1..8` · `entry_date` date·daysback120 · `debit` float·0..3000 · `credit` float·0..3000 · `doc_ref` text·`DOC-{seq}` | →account |

> 🔴 Verify cast: amount/tax/debit/credit→**float**, *_date→**date**. (GL ở đây là dữ liệu giả độc lập, KHÔNG đối chiếu chặt với AR/AP — đủ cho demo thống kê; nếu cần double-entry cân đối là việc lớn hơn.)

---

## 2. Type B — 5 model join (outbound, bật matview)
| Type B | Join | Cột expose | Phục vụ |
|---|---|---|---|
| **`acc_ar_360`** | invoice ⋈ customer (customer_id, LEFT) | invoice_no, customer_id, customer_name, region, segment, amount, tax_amount, status, issue_date, due_date | Doanh thu, AR aging, top customer |
| **`acc_ap_360`** | bill ⋈ vendor (vendor_id, LEFT) | bill_no, vendor_id, vendor_name, category, amount, status, issue_date, due_date | Chi phí, AP aging, top vendor |
| **`acc_receipts_enriched`** | receipt ⋈ customer | receipt_no, customer_id, customer_name, region, receipt_date, amount, method | Dòng tiền vào |
| **`acc_payments_enriched`** | payment ⋈ vendor | payment_no, vendor_id, vendor_name, payment_date, amount, method | Dòng tiền ra |
| **`acc_gl_report`** | journal ⋈ account (account_id, LEFT) | entry_id, account_id, account_name, account_type, debit, credit, entry_date | Trial balance / P&L theo loại TK |

Mỗi Type B: bật `matview_enabled` → `mdp_models.<model>` + refresh.

---

## 3. Dashboard "Accounting Statistics" (Path A — Postgres `grafana_ro` đọc matview; aggregate SQL)

**Nhóm 1 — Doanh thu / Chi phí / Lợi nhuận**
1. KPI row: Tổng doanh thu (Σ `acc_ar_360.amount`) · Tổng chi phí (Σ `acc_ap_360.amount`) · **Lợi nhuận gộp** (DT−CP) · Biên LN %.
2. Doanh thu vs Chi phí theo tháng (time-series kép) + đường Lợi nhuận.
3. Doanh thu theo region/segment (bar, ar_360) · Chi phí theo category (bar, ap_360).

**Nhóm 2 — Top đối tác**
4. Top 10 customer theo doanh thu (table, ar_360).
5. Top 10 vendor theo chi (table, ap_360).
6. Tỷ lệ trạng thái hóa đơn AR (pie: open/paid/overdue/cancelled).

**Nhóm 3 — Dòng tiền**
7. Tiền vào (receipts) vs tiền ra (payments) theo tháng + **net cash flow** (bar).
8. Cơ cấu theo phương thức (pie: cash/bank/card).

**Nhóm 4 — Aging công nợ**
9. **AR aging** buckets 0-30 / 31-60 / 61-90 / 90+ ngày — từ `acc_ar_360` where status≠paid, bucket theo `current_date − due_date`.
10. **AP aging** buckets — từ `acc_ap_360` where status≠paid.

**Nhóm 5 — Sổ cái (GL)**
11. Trial balance / P&L theo `account_type` — Σ(debit−credit) group by account_type (bar, gl_report).

> Ví dụ SQL aging:
> ```sql
> SELECT CASE WHEN current_date-due_date<=30 THEN '0-30'
>             WHEN current_date-due_date<=60 THEN '31-60'
>             WHEN current_date-due_date<=90 THEN '61-90' ELSE '90+' END AS bucket,
>        SUM(amount) AS outstanding
> FROM mdp_models.acc_ar_360 WHERE status<>'paid' AND current_date>=due_date
> GROUP BY 1 ORDER BY 1;
> ```
> Kỷ luật: aggregate ở SQL + `$__timeFilter(issue_date/receipt_date)` + cap LIMIT ≤1000 cho bảng chi tiết.

**Path B (Infinity → /api/outbound)**: tùy chọn, dựng cho **1–2 panel** (vd KPI/top) để minh hoạ real-time read-through; còn lại dùng Path A (aggregate nặng). (Đã so sánh ở prompt 22 — không cần dual-build toàn bộ.)

---

## 4. Cấu hình Simulator (8 đối tượng)
- Nạp **8 API key inbound** + định nghĩa **8 đối tượng** theo §1 (host mdp2 `reverse-proxy:8456`).
- **Seed dim** (tick từng dim, POST 1 lần): customer ×10, vendor ×8, account ×8 (Seq → distinct).
- **Stream fact** (tick từng/đồng thời các fact, POST liên tục): invoice ~300, receipt ~200, bill ~250, payment ~180, journal ~400. Chu kỳ 1–2s.
- 🔴 TRUNCATE các `dm_acc_*` trước khi seed lại (tránh fan-out dim trùng).

---

## 5. Phân công triển khai (tipa-deploy-v2, mdp2)
1. Tạo **8 Type A** (inbound) → 8 key; verify cast.
2. Tạo **5 Type B** (join §2) → outbound key + bật matview + refresh.
3. Cấu hình Node-RED sim (8 đối tượng, host mdp2) → seed dim + stream fact (§4).
4. PG role `grafana_ro` (SELECT `mdp_models`) + datasource; dựng dashboard "Accounting Statistics" 11 panel (Path A) + 1–2 panel Path B.
5. COEXIST; teardown giữ data cho admin xem.

## 6. Acceptance (mdp2, ảnh)
- [ ] 8 `dm_acc_*` có data; dim distinct (customer10/vendor8/account8), fact ≥ ngưỡng §4, 0 orphan FK.
- [ ] 5 Type B GET outbound join đúng (region/category/account_type theo dim).
- [ ] 5 matview `mdp_models.acc_*` có data; grafana_ro SELECT được.
- [ ] Dashboard 11 panel hiển thị hợp lý: DT/CP/LN, top, cash flow, aging, GL.
- [ ] Nguồn bắn = **Node-RED /ui** (ảnh POST), host = mdp2 (không prod).
- [ ] Coexist nguyên.

## 7. Rủi ro / chốt
- Fan-out → seed dim distinct + truncate trước.
- GL không cân đối với AR/AP (dữ liệu giả độc lập) — chấp nhận cho demo.
- Aging cần due_date quá khứ → date gen daysback đủ lớn (đã set 90–120).
- 8 model + 5 Type B + 8 key: nhiều thao tác → deploy tự động hoá (script tạo model qua API nếu được).
- Matview refresh thủ công (demo) → production-hoá scheduler là backlog.

---

## 8. ADDENDUM — Quyết định đã chốt (2026-06-16)

**Function Service `?function=` (DUYỆT) — mở rộng endpoint outbound sẵn có, KHÔNG thêm model/route mới:**
`GET /api/outbound/{model}?function={fn}&<params>` (header X-API-Key). Không có `function` → raw rows như cũ (backward-compatible). Có `function` → chạy tổng hợp server-side trên dữ liệu của `{model}`, trả envelope.

| function | params | ví dụ |
|---|---|---|
| `aggregate` | `agg`(sum/avg/count)·`measure`·`group_by`·`from/to`·`date_col` | `?function=aggregate&agg=sum&measure=amount&group_by=region` |
| `timeseries` | `agg`·`measure`·`date_col`·`bucket`(day/month) | `?function=timeseries&agg=sum&measure=amount&date_col=issue_date&bucket=month` |
| `top` | `measure`·`group_by`·`limit` | `?function=top&measure=amount&group_by=customer_name&limit=10` |
| `aging` | `date_col`·`measure`·`buckets`·`where` | `?function=aging&date_col=due_date&measure=amount&where=status!=paid` |
| `breakdown` | `group_by` | `?function=breakdown&group_by=status` |

Code: mở rộng handler outbound; dispatcher `app/services/functions/` (registry name→handler, thêm trong source). 🔴 whitelist function+agg; validate `group_by/measure/date_col` ∈ cột model expose; bound from/to/limit; chỉ SELECT; parameterized (chống injection).

**Cross-fact (profit, net cash) — cách demo (DUYỆT):** KHÔNG dùng Type B link-hết (fan-out, sai nghiệp vụ) và KHÔNG làm ledger-union (để sau). Grafana gọi **2 URL** (sum `acc_ar_360` + sum `acc_ap_360`) rồi **trừ ở panel** (transformation/expression). Net cash = receipts − payments tương tự.

**Datasource — LÀM CẢ 2 PHASE (DUYỆT):** dashboard "Accounting Statistics" dựng **Path A** (grafana_ro→matview, aggregate SQL) **VÀ Path B** (Infinity gọi `?function=` → nhận data đã tổng hợp). Path B giờ mạnh vì Function service aggregate server-side.

**Cleanup (DUYỆT):** sau khi accounting demo chạy → **dọn bỏ** demo cũ `sim_customer`/`sim_invoice` + Type B `sim_sales_360` + dashboard `sim_sales_stats` (prompt 22/23).

**Thứ tự prompt (DUYỆT) — sau khi report 23 về:**
1. Accounting demo: 8 Type A + 5 Type B + simulator (Node-RED, host mdp2) + matview + dashboard **Path A**.
2. Đổi cơ chế xem API key: "1 lần" → **pass cấp 2** (default `0000`, hardcode source; repo public ⇒ chỉ rào ma sát).
3. **Function service `?function=`** + bổ sung **Path B** vào dashboard + dọn demo cũ.

---
*Bước sau: CHỜ report 23 → soạn prompt theo thứ tự trên.*
