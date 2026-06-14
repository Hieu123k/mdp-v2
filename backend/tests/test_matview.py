"""Prompt 14 - Type B Materialized View PoC.

The actual CREATE / REFRESH CONCURRENTLY / read of a Postgres materialized view is verified on mdp2
Postgres (M1-M9 acceptance). These tests cover what is deterministic on the SQLite test DB:
  * matview body SQL is generated from the validated Type B plan (reuses the read-through builder),
  * the per-model ``matview_enabled`` flag persists and survives a partial edit,
  * matview operations are Postgres-only (clear error on SQLite),
  * the refresh endpoint wiring (404 / not-enabled / postgres-required),
  * outbound in matview mode falls back to the live read-through on non-Postgres (never 500s).
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import matview_service
from app.services.data_model_service import get_data_model_by_name
from app.services.matview_service import MatviewError
from tests.test_outbound import ob


def _seed_join_tables(db: Session) -> None:
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS mv_event (event_id INTEGER PRIMARY KEY, machine_id INTEGER, "
            "status TEXT, event_ts TIMESTAMP, value REAL)"
        )
    )
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS mv_machine (machine_id INTEGER PRIMARY KEY, machine_name TEXT, site TEXT)"
        )
    )
    db.execute(text("DELETE FROM mv_event"))
    db.execute(text("DELETE FROM mv_machine"))
    db.execute(text("INSERT INTO mv_machine (machine_id, machine_name, site) VALUES (1,'M-1','HN'),(2,'M-2','HCM')"))
    db.execute(
        text(
            "INSERT INTO mv_event (event_id, machine_id, status, event_ts, value) VALUES "
            "(10,1,'ok','2026-06-01 00:00:00',1.5),(11,2,'err','2026-06-02 00:00:00',2.5)"
        )
    )
    db.commit()


def _va(name, col, table, *, schema="mdp_data", dtype="text", pk=False, fk=False):
    return {
        "name": name,
        "data_type": dtype,
        "source_schema": schema,
        "source_table": table,
        "source_column": col,
        "is_primary_key": pk,
        "is_foreign_key": fk,
    }


def _event_model_payload(name="poc_event_enriched", *, matview_enabled=False):
    attrs = [
        _va("event_id", "event_id", "mv_event", dtype="integer", pk=True),
        _va("machine_id", "machine_id", "mv_event", dtype="integer", fk=True),
        _va("status", "status", "mv_event"),
        _va("event_ts", "event_ts", "mv_event", dtype="datetime"),
        _va("value", "value", "mv_event", dtype="float"),
        _va("machine_name", "machine_name", "mv_machine"),
        _va("site", "site", "mv_machine"),
    ]
    joins = [
        {
            "type": "left",
            "left": {"table": "mv_event", "column": "machine_id"},
            "right": {"schema": "mdp_data", "table": "mv_machine", "column": "machine_id"},
        }
    ]
    payload = {
        "name": name,
        "display_name": name,
        "type": "B",
        "primary_key": "event_id",
        "attributes": attrs,
        "relationships": joins,
    }
    if matview_enabled:
        payload["matview_enabled"] = True
    return payload


def _create(client, auth_headers, payload):
    r = client.post("/data-models", headers=auth_headers, json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


def test_matview_default_off_and_metadata_null(client: TestClient, auth_headers, db_session: Session):
    _seed_join_tables(db_session)
    body = _create(client, auth_headers, _event_model_payload())
    assert body["matview_enabled"] is False
    assert body["matview_last_refresh_at"] is None
    assert body["matview_row_count"] is None
    assert body["matview_refresh_duration_sec"] is None


def test_matview_flag_persists_and_survives_partial_edit(client: TestClient, auth_headers, db_session: Session):
    _seed_join_tables(db_session)
    body = _create(client, auth_headers, _event_model_payload(matview_enabled=True))
    assert body["matview_enabled"] is True  # flag saved even though no matview is built on SQLite
    model_id = body["id"]
    # a partial edit that does NOT resend matview_enabled must preserve it (not silently turn it off)
    r = client.put(f"/data-models/{model_id}", headers=auth_headers, json={"display_name": "renamed"})
    assert r.status_code == 200, r.json()
    assert r.json()["matview_enabled"] is True
    assert r.json()["display_name"] == "renamed"


def test_build_matview_plan_generates_join_select(client: TestClient, auth_headers, db_session: Session):
    _seed_join_tables(db_session)
    _create(client, auth_headers, _event_model_payload())
    model = get_data_model_by_name(db_session, "poc_event_enriched")
    plan = matview_service.build_matview_plan(db_session, model)

    assert plan["pk_columns"] == ["event_id"]
    # secondary indexes target the time + foreign-key/numeric columns Grafana groups/filters by
    assert "event_ts" in plan["secondary_columns"]
    assert "machine_id" in plan["secondary_columns"]
    select_sql = plan["select_sql"]
    assert select_sql.startswith("SELECT ")
    assert 'AS "event_id"' in select_sql and 'AS "site"' in select_sql  # gathers cols from both tables
    assert "JOIN" in select_sql  # >=2 source tables joined


def test_enable_matview_requires_postgres(client: TestClient, auth_headers, db_session: Session):
    _seed_join_tables(db_session)
    _create(client, auth_headers, _event_model_payload(matview_enabled=True))
    model = get_data_model_by_name(db_session, "poc_event_enriched")
    with pytest.raises(MatviewError) as exc:
        matview_service.enable_matview(db_session, model)
    assert "PostgreSQL" in exc.value.message


def test_refresh_endpoint_404_not_enabled_and_postgres_required(client: TestClient, auth_headers, db_session: Session):
    # unknown model -> 404
    missing = client.post(f"/data-models/{uuid.uuid4()}/refresh", headers=auth_headers)
    assert missing.status_code == 404

    _seed_join_tables(db_session)
    body = _create(client, auth_headers, _event_model_payload())
    model_id = body["id"]

    # matview not enabled -> 400 with a clear message
    not_enabled = client.post(f"/data-models/{model_id}/refresh", headers=auth_headers)
    assert not_enabled.status_code == 400
    assert "Enable matview" in not_enabled.json()["detail"]

    # enable, then refresh on SQLite -> 400 (Postgres required), surfaced from MatviewError
    enabled = client.put(f"/data-models/{model_id}", headers=auth_headers, json={"matview_enabled": True})
    assert enabled.status_code == 200 and enabled.json()["matview_enabled"] is True
    pg_required = client.post(f"/data-models/{model_id}/refresh", headers=auth_headers)
    assert pg_required.status_code == 400
    assert "PostgreSQL" in pg_required.json()["detail"]


def test_outbound_matview_mode_falls_back_to_readthrough_on_sqlite(client: TestClient, auth_headers, db_session: Session):
    _seed_join_tables(db_session)
    _create(client, auth_headers, _event_model_payload(matview_enabled=True))
    # matview_enabled is True but we are on SQLite -> dispatch must fall back to the live read-through
    # JOIN (never try to read a non-existent matview). Result is identical to the read-through.
    response = client.get("/outbound/poc_event_enriched", headers=auth_headers)
    assert response.status_code == 200, response.json()
    data = ob(response)
    assert data["count"] == 2
    by = {row["event_id"]: row for row in data["data"]}
    assert by[10]["site"] == "HN" and by[10]["machine_name"] == "M-1"
    assert by[11]["status"] == "err"
