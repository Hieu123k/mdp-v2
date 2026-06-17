"""Background matview auto-refresh loop (prompt 25): every cycle, ``REFRESH MATERIALIZED VIEW
CONCURRENTLY`` each Type B model that has ``matview_enabled`` + ``matview_refresh_interval_sec > 0``
and is due (``now - matview_last_refresh_at >= interval``).

Mirrors ``streaming_refresher`` exactly (FastAPI lifespan task + a postgres advisory lock so only ONE
loop runs across uvicorn workers). The master kill-switch ``MATVIEW_REFRESH_ENABLED`` (default ON) is
re-checked each tick. A failing model (e.g. a duplicated dim key → fan-out → unique-index violation) is
caught PER MODEL: its status is recorded ``error`` (surfaced in the UI) and the loop moves on to the next
model — one bad matview never stops the others, and a cycle exception never kills the task. ``stop()``
cancels cleanly and releases the lock. Refresh runs in-process (no JWT) via ``matview_service``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.db.session import SessionLocal, engine

logger = logging.getLogger("mdp.matview")

# Distinct lock key from the streaming (0x53545257) + source-count refreshers so the singletons never
# collide. 0x4D565752 = "MVWR" (MatView Watermark Refresher).
_SINGLETON_LOCK_KEY = 0x4D565752

_status: dict[str, Any] = {"enabled": False, "running": False, "last_result": None}


def get_status() -> dict[str, Any]:
    return dict(_status)


def _acquire_singleton() -> Any | None:
    """Hold a postgres advisory lock so only one process auto-refreshes. Returns the held raw
    connection (keep open), ``"taken"`` if another holds it, or None (non-postgres / error → proceed)."""
    try:
        if engine.dialect.name != "postgresql":
            return None
        conn = engine.raw_connection()
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (_SINGLETON_LOCK_KEY,))
        got = cur.fetchone()[0]
        cur.close()
        if got:
            return conn
        conn.close()
        return "taken"
    except Exception:
        return None


def _refresh_due(db) -> dict[str, Any]:
    """Refresh every due matview-enabled Type B model. PER-MODEL error isolation: a failing refresh is
    recorded (status='error' via matview_service) and skipped — never aborts the cycle. Returns a summary
    plus ``next_interval`` = the smallest configured interval (the loop's sleep cadence)."""
    from app.models.data_model import DataModel
    from app.services import matview_service

    now = datetime.now(timezone.utc)
    models = (
        db.query(DataModel)
        .filter(DataModel.matview_enabled.is_(True), DataModel.type == "B")
        .all()
    )
    intervals: list[int] = []
    due: list[DataModel] = []
    for m in models:
        interval = int(m.matview_refresh_interval_sec or 0)
        if interval <= 0:
            continue  # manual-only model
        intervals.append(interval)
        last = m.matview_last_refresh_at
        if last is None or (now - last).total_seconds() >= interval:
            due.append(m)

    refreshed = 0
    errors = 0
    for m in due:
        try:
            matview_service.refresh_matview(db, m)  # records ok status + last_refresh_at
            refreshed += 1
        except Exception as exc:  # matview_service already recorded status='error'; isolate + continue
            errors += 1
            db.rollback()
            logger.warning("matview auto-refresh failed for %s: %s", m.name, exc)
    return {
        "ran": bool(due),
        "due": len(due),
        "refreshed": refreshed,
        "errors": errors,
        "next_interval": min(intervals) if intervals else None,
    }


def _run_cycle_blocking() -> dict[str, Any]:
    """Synchronous cycle (opens its own session). Run via run_in_executor so a long REFRESH never blocks
    the asyncio event loop — /health and every request stay responsive."""
    with SessionLocal() as db:
        return _refresh_due(db)


async def _loop(stop_event: asyncio.Event) -> None:
    _status.update(running=True)
    idle_interval = max(5, int(settings.matview_refresh_interval or 30))
    while not stop_event.is_set():
        interval = idle_interval
        try:
            # Master kill-switch (default ON), re-checked each tick so ops can globally pause/resume
            # without a restart.
            _status.update(enabled=bool(settings.matview_refresh_enabled))
            if settings.matview_refresh_enabled:
                result = await asyncio.get_running_loop().run_in_executor(None, _run_cycle_blocking)
                _status.update(last_result=result)
                if result.get("ran"):
                    logger.info("matview refresh cycle: %s", result)
                # Sleep the smallest configured interval so the per-model cadence is the real one.
                nxt = result.get("next_interval")
                if nxt:
                    interval = max(5, int(nxt))
        except Exception as exc:  # pragma: no cover - the cycle must never kill the task
            _status.update(last_result={"error": str(exc)})
            logger.warning("matview refresh cycle failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    _status.update(running=False)


class MatviewRefresher:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._lock_conn: Any | None = None

    def start(self) -> bool:
        # The loop ALWAYS starts (singleton via advisory lock); the per-model
        # `matview_refresh_interval_sec` is the control — setting it on the Data Model UI is enough to
        # start auto-refresh, no env flip / restart needed. `MATVIEW_REFRESH_ENABLED` is only a master
        # kill-switch (default ON). An idle loop (no auto matview) is near-free.
        lock = _acquire_singleton()
        if lock == "taken":
            logger.info("matview refresher not started (singleton lock held elsewhere)")
            return False
        self._lock_conn = lock if lock not in (None, "taken") else None
        self._task = asyncio.create_task(_loop(self._stop))
        return True

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self._lock_conn is not None:
            try:
                self._lock_conn.close()
            except Exception:
                pass
        _status.update(enabled=False, running=False)
