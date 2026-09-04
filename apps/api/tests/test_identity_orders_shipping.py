from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from serviceops.identity.service import resolve_customer
from serviceops.models import Order, ShippingEvent
from serviceops.orders.service import get_order
from serviceops.shared.errors import ForbiddenError, NotFoundError
from serviceops.shipping.service import get_shipping_status


def test_health_includes_trace_id(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Trace-ID"]


def test_me_requires_session(client):
    response = client.get("/api/me", headers={"X-Demo-Session": ""})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_me_returns_server_resolved_identity(client):
    response = client.get("/api/me")
    assert response.status_code == 200
    assert response.json()["name"] == "林沐"


def test_invalid_session_is_rejected(client):
    response = client.get("/api/me", headers={"X-Demo-Session": "forged"})
    assert response.status_code == 403


def test_customer_can_read_own_order(client):
    response = client.get("/api/orders/ORD-20260828-1042")
    assert response.status_code == 200
    assert response.json()["refundable_amount"] == "329.00"


def test_recent_orders_returns_latest_three_for_current_customer(client):
    response = client.get("/api/orders/recent")
    assert response.status_code == 200
    assert [item["order_number"] for item in response.json()] == [
        "ORD-20260902-3188",
        "ORD-20260831-2256",
        "ORD-20260828-1042",
    ]
    assert "ORD-20260827-9001" not in response.text


def test_recent_orders_are_scoped_to_other_customer(other_client):
    response = other_client.get("/api/orders/recent")
    assert response.status_code == 200
    assert [item["order_number"] for item in response.json()] == [
        "ORD-20260827-9001"
    ]


def test_recent_orders_never_returns_more_than_three(client, db):
    customer = resolve_customer(db, "demo-linmu-session")
    db.add(
        Order(
            order_number="ORD-20260903-7777",
            customer_id=customer.id,
            product_name="旅行颈枕",
            paid_amount=Decimal("89.00"),
            refundable_amount=Decimal("89.00"),
            status="PAID",
            ordered_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
        )
    )
    db.commit()

    response = client.get("/api/orders/recent")
    assert response.status_code == 200
    assert len(response.json()) == 3
    assert response.json()[0]["order_number"] == "ORD-20260903-7777"


def test_other_customer_cannot_read_order(client):
    response = client.get("/api/orders/ORD-20260827-9001")
    assert response.status_code == 403
    assert "product_name" not in response.text
    assert "119" not in response.text


def test_missing_order_has_stable_error(client):
    response = client.get("/api/orders/ORD-NOT-FOUND")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_shipping_abnormality_is_deterministic(client):
    response = client.get("/api/orders/ORD-20260828-1042/shipping")
    payload = response.json()
    assert payload["abnormal"] is True
    assert payload["abnormal_reason"] == "运输停滞"
    assert len(payload["nodes"]) == 3


def test_recent_shipping_event_is_not_abnormal(db):
    customer = resolve_customer(db, "demo-linmu-session")
    order = get_order(db, customer, "ORD-20260828-1042")
    now = datetime(2026, 8, 31, 12, tzinfo=UTC)
    db.add(
        ShippingEvent(
            order_id=order.id,
            location="上海派送站",
            description="正在派送",
            occurred_at=now - timedelta(hours=1),
        )
    )
    db.commit()
    result = get_shipping_status(db, customer, order.order_number, now=now)
    assert result.abnormal is False
    assert result.stale_hours == 1


def test_service_rejects_cross_customer_order(db):
    customer = resolve_customer(db, "demo-linmu-session")
    with pytest.raises(ForbiddenError):
        get_order(db, customer, "ORD-20260827-9001")


def test_service_rejects_missing_order(db):
    customer = resolve_customer(db, "demo-linmu-session")
    with pytest.raises(NotFoundError):
        get_order(db, customer, "ORD-000")
