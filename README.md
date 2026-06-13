# TIPA V2.0 (workspace)

Source mới kế thừa MDP V1.x (FastAPI + Next.js + PostgreSQL) + Apache Flink (CDC Oracle→PG, thay ora2pg) + Grafana riêng (báo cáo).

- Kế hoạch tổng thể: `docs/TIPA_V2.0_Plan.md`
- Scaffold (P0) do **tipa deploy v2** thực hiện theo prompt 57 (copy source V1.x từ trunk v0.1.5 `3b3a33f` vào đây + dựng nền compose).
- Thư mục: `backend/ frontend/` (copy), `flink/ grafana/ ops/` (mới), `docs/`.
- DEV-first trên mdp2; secrets ngoài git (`.env.example`); coexist non-destructive trên VPS.

> Thư mục này CHƯA có source — sẽ được scaffold ở P0. Handoff (prompts/reports) vẫn ở `TIPA_UI_V1.0/handoff`.
