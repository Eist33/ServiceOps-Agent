import asyncio
import json
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session, sessionmaker

from serviceops.database import SessionLocal
from serviceops.models import Operator
from serviceops.workbench.service import list_workbench_tickets


def _queue_revision(tickets: list[dict]) -> tuple[tuple[str, int], ...]:
    return tuple((ticket["id"], ticket["version"]) for ticket in tickets)


async def stream_workbench_tickets(
    operator_id: str,
    *,
    once: bool = False,
    poll_interval: float = 1.0,
    heartbeat_polls: int = 15,
    session_factory: sessionmaker[Session] = SessionLocal,
) -> AsyncIterator[str]:
    previous_revision: tuple[tuple[str, int], ...] | None = None
    unchanged_polls = 0

    while True:
        with session_factory() as db:
            operator = db.get(Operator, operator_id)
            if not operator or operator.role != "SUPPORT_AGENT":
                return
            tickets = [
                ticket.model_dump(mode="json")
                for ticket in list_workbench_tickets(db, operator)
            ]

        revision = _queue_revision(tickets)
        if revision != previous_revision:
            yield json.dumps(
                {"type": "ticket_queue_snapshot", "tickets": tickets},
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
