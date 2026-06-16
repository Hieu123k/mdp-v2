# TIPA / MDP — PROJECT_STATE (nguồn sự thật dùng chung)

> **Vai trò của file này:** trạng thái dự án mới nhất, dùng chung cho **cả 4 agent** (tipa-chat, tipa-admin, tipa-deploy, tipa-mdp). Vì memory trong Cowork **không chia sẻ giữa các space**, đây là "single source of truth" dạng file. **Đọc file này ở đầu mỗi phiên.**
> **Ai cập nhật:** chỉ **tipa-admin** (sau mỗi mốc: release, deploy prod, quyết định kiến trúc). Các agent khác chỉ đọc.
> **Cảnh báo:** đây là snapshot point-in-time — luôn verify lại với repo/hệ thống thật trước khi khẳng định.

**Cập nhật lần cuối:** 2026-06-16 · by tipa-admin

---

## 1. Sản phẩm & repo
- **MDP (Manufacturing Data Platform)** — nền tảng dữ liệu cho thiết bị/CN: ingest (Type A) + expose (Type B) + đồng bộ JDE→Postgres (streaming watermark) + reporting (Grafana).
- **Repo app đang chạy:** GitHub `Hieu123k/mdp-v2` (git remote alias **`v2`**). Thư mục làm việc V2: `D:\Project\TIPA\TIPA_V2.0\`.
- **Branch model:** trunk-based. `main` = `develop` = tag mới nhất; mỗi release có tag rollback `pre-vX.Y.Z`. FF, **no-force**, tag cũ bất biến.
- **Phiên bản hiện tại:**
  - Published mới nhất: **`v2.1.2`** (`cbe50e0`) — main/develop = đây.
  - **Prod `.63` đang chạy: `v2.1.1`** → **chờ deploy `v2.1.2`** (FE-only, không migration; rollback `pre-v2.1.2`).
  - DEV (tipa-vm / mdp2): `:8457`.

## 2. Stack kỹ thuật
- Backend: **FastAPI + SQLAlchemy + Alembic** (single head **019** = `202605300019`).
- DB: **PostgreSQL 16**. Frontend: **Next.js (App Router)**. Reverse-proxy: **Caddy**.
- Prod URL: **HTTPS `:8456`** (Caddy self-signed, CN=`mdp-63`).
- Envelope API: `{code, message, data}` (numeric code; 0=OK, 2003=INTERNAL_ERROR).

## 3. Data model
- **Type A (inbound):** `POST /api/inbound/{model}` → `mdp_data.dm_*`.
- **Type B (outbound, linked):** read-through — kế hoạch join lưu JSONB trong `data_model.attributes`/`relationships`, **compile thành SELECT lúc đọc** (`build_type_b_from_clause`). **KHÔNG phải view DB.** Type B SQL **chỉ parse AST, không bao giờ execute** tuỳ tiện.
- **Matview (tuỳ chọn cho Type B):** `mdp_models.<model>` + unique PK index (REFRESH CONCURRENTLY); cờ `matview_enabled` per-model; PoC merged `v2.1.0`, hiện **refresh thủ công**. Perf ~80× so read-through.
- API key scoped theo direction + model (1 key có thể `["inbound","outbound"]`).

## 4. Streaming (JDE → Postgres)
- **Watermark-incremental, 38/40 bảng đang bật.**
- **Case A (incremental):** watermark = cột sequence (vd `ILUKID`) **hoặc** ngày (`UPMJ`) + PK upsert.
- **Case B (full-reload):** copy lại + atomic swap, floor 12h.
- Bảng `streaming_config` (enabled, ts_col, kind, poll_interval_sec, last_run_at, last_watermark, last_status). Master gate **`STREAMING_ENABLED`**. Loop `run_all_due` (due-based, worker thread). `POST /api/streaming/run-once/{table}`.
- Verdict grid: tolerance streaming-aware = **max(50 rows, 0.01%)**; auto-ANALYZE sau reload (sửa false-MISMATCH do reltuples).
- **F4111 (Item Ledger ~59M):** Case A, ts_col=`ILUKID` (sequence), 15m, **MATCH** (verified 2026-06-15). ILUKID NOT NULL/min=1/unique/monotonic + append-only → strict `>` đủ.

## 5. CDC / DBA (đã chốt — quan trọng)
- **Log-based CDC (LogMiner/Debezium/Flink-CDC) = ĐÃ LOẠI** (quyết định 2026-06-13). Lý do: JDE Oracle `.16` (19c SE2 non-CDB) **ARCHIVELOG OFF + supplemental logging OFF**; bật cần **restart prod** → admin **không** làm.
- Bằng chứng vận hành (2026-06-16): redo switch **~36s/lần** (~480 GB/ngày), single-member → mine redo online chỉ thấy **<2 phút** lịch sử → CDC online bất khả khi thiếu archivelog.
- **Giữ ora2pg + query-based watermark** (đang chạy ổn). Deletes (nếu cần) qua reconciliation diff.
- 🔴 **Watermark hazard:** `ILTRDJ` có dòng **future-dated** (vd 2026-06-18) → **không dùng date watermark khi có sequence**. **TODO:** audit các bảng dùng date/UPMJ watermark (nhóm PO/SO `F4301/F4311/F43121/F4211` fallback UPMJ vì UKID=0) xem có future-date → mất dòng thầm.
- Tài liệu: `Report/logminer_f4111.sql`, Decision pack CDC/DBA (`Report/Checklist_DBA_Oracle_CDC.docx` + `Checklist_ArchiveLog_DBA.xlsx`).

## 6. Grafana reporting (đang chuẩn bị)
- Container Grafana **riêng** trong compose `mdpv2` (Grafana sẵn trên `.63` thuộc project khác — KHÔNG dùng).
- Datasource: `grafana_ro` (Postgres, đọc matview `mdp_models.*`); Infinity → `/api/outbound`.
- **Query discipline:** aggregate ở SQL + time filter + cap **~500–1000 dòng**.

## 7. Hạ tầng & prod (chi tiết IP/SID/port: `INFRA.local.md` — không publish)
- Prod host **`.63`** (Ubuntu/Docker) = target prod MDP, HTTPS :8456 · ESB host **`.64`** (WSO2) · Windows jump-box **`.65`** (reach qua UltraViewer) · JDE Oracle source **`.16`** (19c SE2). DEV = `tipa-vm` (mdp2).
- JDE table thật ở DB remote qua DB-link; MDP thấy qua view passthrough (vd `V2_PRO_F4111`).
- **Source transfer = git:** local → GitHub (scrubbed) → `.65` clone → `.63`. `tipa-mdp` dùng skill **`tipa-mdp-git`** (truyền ref, không gõ git thô).

## 8. COEXIST — tuyệt đối không đụng (host dùng chung)
Chỉ **`mdp` / `mdp2` / `mdpv2*`** là của mình. KHÔNG stop/restart/remove/sửa các dịch vụ co-tenant khác trên host dùng chung (danh sách chi tiết: `INFRA.local.md`). Khi deploy/retire chỉ chạm stack của mình.

## 9. Việc đang mở (backlog)
- [ ] Deploy `v2.1.2` lên prod `.63` (tipa-mdp; FE-only).
- [ ] Audit date/UPMJ-watermark tables cho future-date hazard (§5).
- [ ] Matview production-hoá: scheduler refresh + cadence per-model (hiện manual).
- [ ] Grafana reporting container: build + deploy mdp2 → prod.
- [ ] (User-side) iHUB Java client import MDP cert vào JDK cacerts.

---
*Khi thay đổi: tipa-admin sửa file này + ghi ngày + báo các agent đọc lại.*
