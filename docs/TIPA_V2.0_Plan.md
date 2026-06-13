# TIPA V2.0 — Kế hoạch: tách source mới + ghép Apache Flink + Grafana

> Mục tiêu: dựng workspace/source mới **TIPA V2.0** kế thừa MDP V1.x (FastAPI + Next.js + PostgreSQL), **bổ sung Apache Flink** (xử lý luồng / ingestion realtime) và **Grafana** (báo cáo). Sản phẩm V2.0 = 1 stack `docker-compose`: MDP (BE+FE+Postgres) + Flink (jobmanager+taskmanager) + Grafana.
> **Trạng thái: BẢN NHÁP — chờ admin chốt 3 quyết định ở mục H trước khi thực thi.** Mọi build DEV-first trên `mdp2`, gated.

---

## A. Cấu trúc thư mục đề xuất `D:\Project\TIPA\TIPA_V2.0\`
```
TIPA_V2.0\
├─ backend/            ← copy từ mdp-deploy-v0.0/backend (FastAPI app, alembic, services, models)
├─ frontend/           ← copy (Next.js src)
├─ flink/              ← MỚI: jobs + Dockerfile + conf
│  ├─ jobs/            (Flink SQL hoặc PyFlink)
│  └─ conf/
├─ grafana/            ← MỚI: provisioning (datasource Postgres) + dashboards-as-code (*.json)
├─ ops/                ← MỚI: docker-compose.v2.yml + .env.example + scripts
├─ handoff/            ← copy protocol (prompts/reports đánh số mới cho V2) + ONBOARDING + BRANCHING
├─ docs/               ← ARCHITECTURE.md, README, CHANGELOG
└─ reference/          ← copy JDE tables / PK ref nếu cần
```

## B. Copy gì từ source cũ (V1.x → V2.0)
**GIỮ:** `backend/app` (toàn bộ MDP API/services/models/alembic 018), `frontend/src`, docker-compose nền, handoff protocol + `BRANCHING.md` + onboarding, reference data (JDE tables, PK ref).
**KHÔNG copy:** `.env` thật / secrets, `node_modules`, build artifacts, data volumes, file tạm. (Tạo `.env.example` mới.)

## C. Kiến trúc luồng dữ liệu V2.0 (phương án mặc định — phụ thuộc vai trò Flink, mục H1)
```
Nguồn: JDE/Oracle  ·  MQTT/UNS  ·  3rd-party HTTP
        │
        ▼
   ┌──────────┐   (ingestion + transform realtime — thay/bổ sung ora2pg)
   │  FLINK   │
   └──────────┘
        │
        ▼
   PostgreSQL  (mdp_staging / mdp_data)
        │
        ▼
   MDP API (FastAPI: Type A inbound · Type B outbound · models)
        │
        ▼
   Next.js UI
        │
        ▼
   GRAFANA  (dashboards đọc Postgres → báo cáo)
```
- **Flink CDC** đọc Oracle (LogMiner) / Postgres → sink Postgres ⇒ ứng viên **thay ora2pg** (CDC realtime thay batch). Hoặc Flink consume **MQTT/Kafka (UNS)** → xử lý → Postgres.
- **Grafana datasource** = PostgreSQL (`mdp_data`/`mdp_staging`) trực tiếp [hoặc qua MDP outbound API].

## D. Hạ tầng & compose (thêm mới — additive)
- **Flink:** `jobmanager` + `taskmanager` (+ thư mục checkpoint/savepoint). Job ưu tiên **Flink SQL** (dễ vận hành, ít code) — PyFlink/Java nếu cần logic phức tạp. Pin version image chính chủ (`apache/flink:<ver>`).
- **Grafana:** image `grafana/grafana:<ver>`, provisioning datasource + dashboards-as-code. (Riêng hay dùng chung → mục H2.)
- **Coexist:** chỉ THÊM service mới; tuyệt đối không đụng OpenRemote/neuron/postgres_uns/umh-core/nodered-1880/grafana-stack-chung trên VPS. Cổng mới phải tránh trùng.

## E. Lộ trình (DEV-first mdp2, mỗi bước 1 epic/feat + report gated)
| Bước | Nội dung | Kết quả |
|---|---|---|
| **P0** | Scaffold V2.0: tạo folder + copy source cũ + compose nền + handoff/docs; build chạy MDP V2.0 (chưa Flink/Grafana) trên mdp2 | MDP chạy y V1.x ở workspace mới |
| **P1** | **Grafana**: thêm container + datasource Postgres + 1–2 dashboard mẫu (dashboards-as-code) đọc dữ liệu MDP hiện có | Báo cáo chạy ngay, rủi ro thấp |
| **P2** | **Flink skeleton**: jobmanager/taskmanager + 1 job "hello" (đọc 1 bảng staging → ghi 1 bảng kết quả) | Chứng minh pipeline Flink |
| **P3** | **Flink ingestion thật**: 1 nguồn cụ thể (Oracle CDC **hoặc** MQTT) → Postgres, **coexist song song ora2pg** (feature-flag), đối chiếu kết quả | Pipeline thật, an toàn |
| **P4** | **Dashboards thật + cutover**: dashboard báo cáo theo yêu cầu; Flink ổn → giảm/bỏ ora2pg | V2.0 hoàn chỉnh |

## F. Version & nhánh
- V2.0 = **major** → dòng `v2.x`. Giữ V1.x (`main`/v0.1.5 đang chạy `.63`) ổn định cho tới khi V2.0 sẵn sàng cutover.
- Repo: tuỳ mục H3 — (a) repo git mới cho V2.0, hoặc (b) epic lớn `epic/v2-*` trên repo `deploy` hiện tại.

## G. An toàn
- DEV-first trên mdp2; KHÔNG đụng prod/stack chung; secrets ngoài git (.env.example); additive + non-regression; pin version image; tải image từ nguồn chính chủ.

## H. QUYẾT ĐỊNH (ĐÃ CHỐT)
1. **Flink = THAY ora2pg** → CDC Oracle/JDE → PostgreSQL (đồng bộ realtime thay batch).
2. **Grafana = RIÊNG cho MDP** (container + cổng riêng trong stack V2.0, KHÔNG đụng Grafana chung `.63`).
3. **Repo = GIT REPO MỚI** cho V2.0 (tách bạch V1.x đang chạy prod).

## I. Điều kiện tiên quyết Flink CDC trên Oracle (PHẢI biết trước — hay vướng)
> CDC Oracle qua Flink (connector `flink-sql-connector-oracle-cdc`, nền Debezium/LogMiner) đòi hỏi cấu hình **ở phía Oracle nguồn** — không phải chỉ ở MDP:
- 🔴 Oracle phải **ARCHIVELOG mode** + bật **supplemental logging** (DB-level / hoặc per-table). Đây là thay đổi trên Oracle nguồn → **cần quyền DBA**; trên prod JDE thật phải xin phép (rủi ro/độ trễ tổ chức).
- 🔴 Cần **user Oracle có quyền LogMiner** (SELECT trên redo/archived logs, EXECUTE_CATALOG_ROLE…). Không thể bịa — phải xác nhận với DBA.
- Mỗi bảng CDC cần **Primary Key** → tận dụng **JDE PK reference 40 bảng** đã có.
- **Version compatibility:** Flink ↔ Oracle-CDC connector phải khớp cặp (deploy chọn cặp tương thích, pin + ghi rõ; KHÔNG hardcode version đoán).
- Flink CDC = **snapshot ban đầu → stream redo** (incremental). Khác mô hình ora2pg batch + watermark hiện tại → V2.0 Flink có thể **thay luôn module "streaming"** của MDP.
- **DEV trước trên Oracle Free sandbox (mdp2):** bật archivelog + supplemental logging trên sandbox để spike/PoC; chỉ đụng Oracle prod khi PoC OK + admin/DBA duyệt.

## J. Lộ trình tinh chỉnh (theo quyết định đã chốt)
| Bước | Nội dung | Ghi chú |
|---|---|---|
| **P0** | Tạo **repo git mới** `TIPA_V2.0` + copy source MDP V1.x + compose nền; build MDP V2.0 chạy trên mdp2 | nền sạch |
| **P1** | **Grafana riêng** + datasource Postgres + 1–2 dashboard mẫu | giá trị ngay, rủi ro thấp |
| **P2** | **Flink skeleton** (jobmanager/taskmanager) + job "hello" Postgres→Postgres | chứng minh pipeline |
| **P2.5 (SPIKE)** | **PoC Flink Oracle-CDC** trên **Oracle Free sandbox mdp2**: bật archivelog/supplemental logging, CDC 1 bảng → Postgres | **gate quyết định** — xác minh CDC khả thi trước khi cam kết |
| **P3** | CDC thật 1 nguồn JDE → Postgres, **coexist song song ora2pg** (feature-flag), đối chiếu | an toàn, có đường lùi |
| **P4** | Dashboards báo cáo thật + cutover (giảm/bỏ ora2pg khi Flink ổn) | hoàn chỉnh V2.0 |

(+ Sau P0, chốt tiếp: cặp Flink/connector version, danh sách bảng JDE đưa vào CDC, ngôn ngữ job (ưu tiên **Flink SQL**), và yêu cầu dashboard Grafana cụ thể.)
