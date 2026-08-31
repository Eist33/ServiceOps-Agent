from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import Customer, ShippingEvent
from serviceops.orders.service import get_order
from serviceops.shared.schemas import ShippingResponse

SHIPPING_STALE_THRESHOLD_HOURS = 36


def get_shipping_status(
    db: Session,
    customer: Customer,
    order_number: str,
    *,
    now: datetime | None = None,
) -> ShippingResponse:
    order = get_order(db, customer, order_number)
    nodes = list(
        db.scalars(
            select(ShippingEvent)
            .where(ShippingEvent.order_id == order.id)
            .order_by(ShippingEvent.occurred_at.desc())
        )
    )
    current_time = now or datetime.now(UTC)
    latest = nodes[0].occurred_at if nodes else order.ordered_at
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    stale_hours = max(0, int((current_time - latest).total_seconds() // 3600))
    abnormal = stale_hours >= SHIPPING_STALE_THRESHOLD_HOURS
    return ShippingResponse(
        order_id=order.id,
        order_number=order.order_number,
        abnormal=abnormal,
        abnormal_reason="运输停滞" if abnormal else None,
        stale_hours=stale_hours,
        nodes=[
            {
                "location": node.location,
                "description": node.description,
                "occurred_at": node.occurred_at.isoformat(),
            }
            for node in nodes
        ],
    )
