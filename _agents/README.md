# _agents — Bộ governance 4-agent TIPA/MDP

Mô hình 4 agent (từ 2026-06-16): **tipa-chat** (thảo luận) · **tipa-admin** (tạo file/prompt + audit) · **tipa-deploy** (code) · **tipa-mdp** (deploy prod).

## File trong thư mục này (publish lên GitHub `Hieu123k/mdp-v2` → `_agents/`)
- **`PROJECT_STATE.md`** — trạng thái dự án sống, dùng chung. Đọc đầu mỗi phiên. Chỉ tipa-admin sửa.
- **`TOPOLOGY.md`** — 4 vai, ranh giới, luồng relay, gates chung.
- **`tipa-chat.charter.md`** — file init cho space tipa-chat.
- **`tipa-admin.charter.md`** — file init cho space tipa-admin.
- 🔒 **`INFRA.local.md`** — IP/SID/port nội bộ. **KHÔNG publish** (thêm `_agents/INFRA.local.md` vào `.gitignore`). Chỉ local cho operators.

## Init agent mới
- **tipa-chat:** tạo space mới → dán tin nhắn init (đọc `_agents/` từ **GitHub `Hieu123k/mdp-v2`** qua web). KHÔNG cần cấp folder local.
- **tipa-admin:** tạo space mới → cấp quyền thư mục **`D:\Project\TIPA`** (cần ghi file) → dán `tipa-admin.charter.md` làm tin nhắn đầu.
- Muốn xuyên suốt nhiều phiên: dùng Claude Project, thả charter + `PROJECT_STATE.md` vào Project knowledge.

## Đồng bộ ngữ cảnh
Memory **không** chia sẻ giữa các space → `PROJECT_STATE.md` (trên GitHub) là cầu nối ngữ cảnh; **relay copy-paste của anh** là cầu nối hành động. Sau mỗi mốc, tipa-admin sửa `PROJECT_STATE.md` (local) → tipa-deploy push lên mdp-v2.
