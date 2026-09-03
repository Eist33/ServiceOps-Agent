import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session, sessionmaker

from serviceops.database import SessionLocal
from serviceops.models import Operator
from serviceops.operations.service import operations_alerts


def _alert_revision(alerts: list[dict]) -> tuple[tuple[str, str, int, bool], ...]:
    return tuple(
        (
            alert["id"],
            alert["severity"],
            alert["sla_remaining_minutes"],
            alert["acknowledged"],
        )
        for alert in alerts
    )


async def stream_operations_alerts(
    operator_id: str,
    *,
    once: bool = False,
    poll_interval: float = 1.0,
    heartbeat_polls: int = 15,
    session_factory: sessionmaker[Session] = SessionLocal,
) -> AsyncIterator[str]:
    previous_revision: tuple[tuple[str, str, int, bool], ...] | None = None
    unchanged_polls = 0

    while True:
        with session_factory() as db:
            if not db.get(Operator, operator_id):
                return
            snapshot = operations_alerts(db)
            payload = snapshot.model_dump(mode="json")

        revision = _alert_revision(payload["items"])
        if revision != previous_revision:
            yield json.dumps(
                {"type": "operations_alert_snapshot", "snapshot": payload},
                ensure_ascii=False,
            ) + "\n"
            previous_revision = revision
            unchanged_polls = 0
            if once:
                return
        else:
            unchanged_polls += 1
            if unchanged_polls >= heartbeat_polls:
                yield json.dumps({"type": "heartbeat"}) + "\n"
                unchanged_polls = 0

        await asyncio.sleep(poll_interval)
