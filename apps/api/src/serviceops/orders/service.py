from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.models import Customer, Order
from serviceops.shared.errors import ForbiddenError, NotFoundError


def get_order(db: Session, customer: Customer, order_number: str) -> Order:
    order = db.scalar(select(Order).where(Order.order_number == order_number))
    if not order:
        raise NotFoundError("订单不存在")
    if order.customer_id != customer.id:
        # Deliberately indistinguishable from a missing order to avoid data disclosure.
        raise ForbiddenError("无法访问该订单")
    return order


def get_latest_order(db: Session, customer: Customer) -> Order:
    order = db.scalar(
        select(Order)
        .where(Order.customer_id == customer.id)
        .order_by(Order.ordered_at.desc())
        .limit(1)
    )
    if not order:
        raise NotFoundError("当前账号没有可用订单")
    return order
