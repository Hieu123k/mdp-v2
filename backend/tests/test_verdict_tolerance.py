"""Prompt 15: Verify-verdict tolerance.

A streaming-enabled table lags Oracle by a few not-yet-pulled rows (live-lag) — that tiny diff must
read MATCH, not a red MISMATCH. A non-streaming (migrate-once) table must match exactly. The verdict is
always computed from EXACT counts (the grid feeds it the last Verify's exact target, never reltuples —
that Postgres-specific path is verified live on mdp2)."""
from app.core.config import settings
from app.core.ora2pg_catalog import MIGRATABLE_TABLES
from app.services import source_count_service as svc

V0 = MIGRATABLE_TABLES[0].table  # e.g. V2_PRO_F4101
T0 = MIGRATABLE_TABLES[0].target_table


def _exact(db, count):
    return svc.upsert_source_count(
        db, source_view=V0, target_table=T0, count=count, mode="exact", approximate=False, status="ok"
    )


def test_verdict_tolerance_non_streaming_is_exact():
    # migrate-once tables require an exact match — no tolerance, however large the table
    assert svc.verdict_tolerance(1_000_000, is_streaming=False) == 0
    assert svc.verdict_tolerance(None, is_streaming=False) == 0


def test_verdict_tolerance_streaming_max_of_rows_and_ratio(monkeypatch):
    monkeypatch.setattr(settings, "streaming_verdict_tolerance_rows", 50)
    monkeypatch.setattr(settings, "streaming_verdict_tolerance_ratio", 0.0001)  # 0.01%
    assert svc.verdict_tolerance(1000, is_streaming=True) == 50          # abs-rows floor wins
    assert svc.verdict_tolerance(1_000_000, is_streaming=True) == 100    # 0.01% ratio wins
    assert svc.verdict_tolerance(0, is_streaming=True) == 50
    assert svc.verdict_tolerance(None, is_streaming=True) == 50


def test_source_verdict_match_within_tolerance(db_session):
    ex = _exact(db_session, 100)
    assert svc.source_verdict(ex, 100) == "MATCH"               # exact, tolerance 0
    assert svc.source_verdict(ex, 97) == "MISMATCH"             # 3-row diff, no tolerance
    assert svc.source_verdict(ex, 97, tolerance=5) == "MATCH"   # live-lag within band
    assert svc.source_verdict(ex, 95, tolerance=5) == "MATCH"   # exactly at the band edge
    assert svc.source_verdict(ex, 50, tolerance=5) == "MISMATCH"  # large/fixed diff is still a real MISMATCH


def test_source_verdict_estimate_never_mismatch_even_with_tolerance(db_session):
    est = svc.upsert_source_count(
        db_session, source_view="V_E2", target_table="v_e2", count=100, mode="estimate",
        approximate=True, status="ok",
    )
    assert svc.source_verdict(est, 50, tolerance=5) == "ESTIMATE"
    assert svc.source_verdict(None, 100, tolerance=5) == "PENDING"
    assert svc.source_verdict(est, None, tolerance=5) == "ESTIMATE"


def test_grid_exact_source_without_verify_is_pending_not_mismatch(client, auth_headers, db_session):
    # An exact source count is cached but no Verify has run (no exact target) → the grid must show
    # PENDING, never a MISMATCH derived from a stale/estimated target (prompt 15 — reltuples is out).
    _exact(db_session, 777)
    body = client.get("/ora2pg/tables", headers=auth_headers).json()
    row = next(t for t in body["tables"] if t["table"] == V0)
    assert row["source_count"] == 777
    assert row["source_verdict"] == "PENDING"
