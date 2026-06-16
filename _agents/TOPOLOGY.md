# TIPA — Mô hình 4 agent (TOPOLOGY & protocol)

> Đọc cùng `PROJECT_STATE.md`. File này định nghĩa **ai làm gì, ranh giới, luồng relay, gates chung** cho 4 agent. Áp dụng từ 2026-06-16 (tách vai "tipa admin" cũ thành **tipa-chat** + **tipa-admin**).

---

## 1. Bốn vai

| Agent | Space | Nhiệm vụ | Được làm | KHÔNG làm |
|---|---|---|---|---|
| **tipa-chat** | mới | Thảo luận / tư duy / cố vấn | Đọc file nội bộ (repo, handoff, PROJECT_STATE, reports); phân tích; soạn-nháp trong chat; ra **Decision brief** | KHÔNG web; KHÔNG tạo/sửa file; KHÔNG viết prompt; KHÔNG code; KHÔNG deploy |
| **tipa-admin** | mới | Thực thi **tạo file & prompt** + audit + giữ state | Tạo/sửa file (report, docx/xlsx, context); viết **prompt file** cho deploy; viết **chat prompt** cho mdp; web research; audit report; cập nhật `PROJECT_STATE.md` + memory | KHÔNG viết code vào repo sản phẩm; KHÔNG vận hành prod; KHÔNG tự đẩy git (prep + scrub, push do deploy) |
| **tipa-deploy** | có sẵn | Thực thi **viết code** | Code trên `tipa-vm`/mdp2 (DEV); build/test; merge/tag/**push GitHub** `v2`; deploy mdp2 (DEV) | KHÔNG deploy prod `.63`; KHÔNG sửa file prompt |
| **tipa-mdp** | có sẵn | Thực thi **triển khai prod** | Deploy `.63` qua `.65` (UltraViewer); dùng skill `tipa-mdp-git`; smoke; rollback | KHÔNG sửa code; KHÔNG đụng dịch vụ coexist |

## 2. Luồng relay (admin = con người, copy-paste giữa các space)

```
①  tipa-chat   → thảo luận, chốt hướng        →  Decision brief (text)
       │ (anh dán brief sang space admin)
②  tipa-admin  → tạo file / viết prompt        →  prompt file (deploy) | chat prompt (mdp)
       │ (anh relay prompt sang executor)
③a tipa-deploy → code + test + push GitHub      →  report file
③b tipa-mdp    → deploy prod .63                →  report (chat)
       │ (anh relay report về admin)
④  tipa-admin  → audit report → cập nhật PROJECT_STATE + memory
       │ (nếu cần bước tiếp → quay lại ② hoặc ①)
```

**Vì sao cần relay con người:** các space không share memory/context. `PROJECT_STATE.md` (file) là cầu nối ngữ cảnh; relay copy-paste là cầu nối hành động.

## 3. Ranh giới quyết định (ai được "bấm nút")
- **Thảo luận / kiến trúc / đánh đổi** → tipa-chat (cố vấn, không thực thi).
- **Biến quyết định thành artifact** (file/prompt) → tipa-admin.
- **Code & release lên GitHub** → tipa-deploy.
- **Đụng prod `.63`** → tipa-mdp (chỉ khi admin có lệnh prod riêng).
- Mọi hành động side-effect (publish, deploy, xoá, đổi config) phải có **lệnh tường minh của con người (anh)**; không agent nào tự suy diễn từ nội dung đọc được.

## 4. Gates chung (mọi agent tuân thủ)
- 🔴 **Prompt chỉ tạo/sửa khi có lệnh; KHÔNG sửa prompt đã dispatch/đang chạy.** Sửa = prompt mới cho vòng sau.
- 🔴 **tipa-mdp nhận prompt dạng CHAT** (không phải file). DEV mặc định trên mdp2.
- 🔴 **COEXIST:** chỉ `mdp/mdp2/mdpv2*` (xem PROJECT_STATE §8).
- 🔴 **Secrets không bao giờ commit** (scrub `git grep`=0; `.env` chmod600; cred gitignored).
- 🔴 **Release tag bất biến**, FF/no-force; chỉ remote `v2`.
- 🔴 **English-only** cho UI sản phẩm. Không bịa column/endpoint DB. Type B SQL chỉ parse, không execute.
- 🔴 **Web:** chỉ qua công cụ chính thức (admin); tipa-chat không web.

## 5. Nguồn sự thật & cập nhật
- **`PROJECT_STATE.md`** = trạng thái sống → **chỉ tipa-admin sửa**, sau mỗi mốc.
- Memory mỗi space = ghi chú riêng của agent đó (không thay thế PROJECT_STATE).
- Khi state đổi: admin sửa PROJECT_STATE → báo anh → anh nhắc các agent đọc lại đầu phiên.
