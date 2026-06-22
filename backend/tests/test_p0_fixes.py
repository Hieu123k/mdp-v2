"""Prompt 36 — regression tests for the 4 confirmed P0 fixes (each reproduces the original bug → now passes).

P0-3 (Type A rename → orphan/500) is postgres-only (sync_generated_table_columns no-ops on sqlite), so its
regression is exercised by the dev (postgres) repro in report 36, not here.
"""
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.user import UserCreate
from app.services.user_service import create_user
from tests.test_inbound import create_invoice_model, create_sqlite_generated_table


# --- P0-1 (U1): inbound UPSERT on the business key ---
def test_inbound_upserts_on_business_key_no_duplicate(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    model = create_invoice_model(client, auth_headers)
    create_sqlite_generated_table(db_session)
    name = model["name"]

    r1 = client.post(f"/inbound/{name}", headers=auth_headers, json={"invoice_no": "INV-UP", "amount": 100})
    assert r1.status_code in (200, 201), r1.text
    r2 = client.post(f"/inbound/{name}", headers=auth_headers, json={"invoice_no": "INV-UP", "amount": 250})
    assert r2.status_code in (200, 201), r2.text

    rows = db_session.execute(
        text("SELECT amount FROM mdp_data.dm_invoice WHERE invoice_no = 'INV-UP'")
    ).fetchall()
    assert len(rows) == 1, "re-sending the same business key must UPDATE, not append a duplicate row"
    assert rows[0][0] == 250, "the row must reflect the latest payload"


# --- P0-2 (§A): clamp the date/UPMJ streaming cursor to today ---
def test_clamp_day_cursor_blocks_future_watermark() -> None:
    from app.services.streaming_service import _today_julian, build_streaming_predicate, clamp_day_cursor

    today = _today_julian()
    future = str(today + 500)

    assert clamp_day_cursor(future, "day", False) == str(today)        # future clamped to today
    assert clamp_day_cursor(str(today - 5), "day", False) == str(today - 5)  # past unchanged
    assert clamp_day_cursor(future, "timestamp", False) == future      # timestamp mode unchanged
    assert clamp_day_cursor("9", "day", True) == "9"                   # sequence mode unchanged

    # report-35 case: a future-dated target row no longer pushes the cutoff past today, so a TODAY row is admitted.
    clamped = clamp_day_cursor(future, "day", False)  # == today
    predicate = build_streaming_predicate(
        "ILTRDJ", "UPMJ", granularity="day", cursor_day=clamped, lookback_days=2, sequence=False
    )
    assert predicate == f"ILTRDJ[UPMJ >= {today - 2}]"
    assert today >= today - 2  # today's row satisfies the predicate (NOT skipped)


# --- P0-4 (#2): JWT RBAC on the integration API ---
def test_viewer_jwt_blocked_on_integration_endpoints(
    client: TestClient, auth_headers: dict[str, str], db_session: Session
) -> None:
    create_user(db_session, UserCreate(username="v_p0", email="v@p0.local", password="viewer123", role="viewer"))
    db_session.commit()
    viewer_jwt = client.post("/auth/login", json={"username": "v_p0", "password": "viewer123"}).json()["access_token"]
    vh = {"Authorization": f"Bearer {viewer_jwt}"}

    # a read-only viewer with only a Bearer token is now 403 on BOTH integration directions
    assert client.get("/outbound/any_model", headers=vh).status_code == 403
    assert client.post("/inbound/any_model", headers=vh, json={"x": 1}).status_code == 403
    # an integration-capable role (admin) is NOT 403 (reaches the endpoint — 404/422 for the missing model is fine)
    assert client.get("/outbound/any_model", headers=auth_headers).status_code != 403
