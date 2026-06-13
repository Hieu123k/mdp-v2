# simulation/ — Node-RED ESB (mô phỏng nguồn dữ liệu cho MDP) — TIPA V2.0

> **Tách riêng, KHÔNG gộp vào source MDP.** Đây là 1 stack độc lập (container Node-RED riêng) để
> **mô phỏng nguồn/đẩy dữ liệu** vào MDP, phục vụ test & tạo dữ liệu cho báo cáo Grafana (outbound từ data model).
> Triển khai **DEV-only trên `tipa-vm`/mdp2**, coexist, KHÔNG push/prod.

## Nội dung
- `flows.json` — flow Node-RED ESB gốc (auth, JDE mappings, object-types, inbound `/api/object`, monitor,
  incremental schedules; 27 `http in`, 145 function, 62 postgresql, 3 `mqtt in`, dashboard `ui-*`, inject timer `repeat:30/60`).
- `flows_cred.json` — **credential mã hoá của Node-RED (SECRET)**. Đã **.gitignore** → chỉ tồn tại trên VM, **KHÔNG commit/push**.
- `.gitignore` — chặn `flows_cred.json`, `.node-red/`, `node_modules/`.

## Nguyên tắc triển khai (cho tipa deploy v2)
1. **Container riêng** `mdpv2-nodered` (image chính chủ `nodered/node-red:<pin>`), **cổng host riêng** (vd `1881` —
   kiểm trống; TUYỆT ĐỐI không trùng `1880` của project khác trên VPS), volume `mdpv2_nodered_data`.
   → Đặt trong **compose riêng** `simulation/docker-compose.sim.yml` (project `mdpv2-sim`), **KHÔNG nhét vào** `ops/docker-compose.v2.yml` của MDP.
2. **Coexist non-destructive:** không đụng `nodered:1880`/grafana-chung/OpenRemote/neuron/postgres_uns/umh-core của hệ khác.
3. **Secret trên VM:** đặt `credentialSecret` qua env Node-RED (`NODE_RED_CREDENTIAL_SECRET`, sinh trên VM, `.env` chmod600),
   nạp `flows.json` + `flows_cred.json` cục bộ; **không** đưa cred vào git.
4. **Kết nối:** Node-RED ↔ Postgres/MQTT trỏ tới endpoint nội bộ phù hợp trên mdp2; nếu mô phỏng đẩy Type A vào MDP
   thì gọi `POST /api/inbound/{model}` (kèm `X-API-Key`) của stack MDP V2 — verify dữ liệu chạy vào `mdp_data.dm_*`.
5. **Verify:** Node-RED healthy, mở được editor/dashboard ở cổng riêng; chứng minh 1 luồng mô phỏng chạy
   (inject/timer → ghi DB hoặc → MDP inbound) → để Grafana đọc outbound ra số liệu thật.
