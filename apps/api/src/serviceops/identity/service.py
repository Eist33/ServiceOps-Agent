from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.database import get_db
from serviceops.models import Customer
from serviceops.shared.errors import ForbiddenError

DEMO_SESSION_HEADER = "X-Demo-Session"


def resolve_customer(db: Session, session_token: str | None) -> Customer:
    if not session_token:
        raise ForbiddenError("缺少演示会话凭证")
    customer = db.scalar(select(Customer).where(Customer.session_token == session_token))
    if not customer:
        raise ForbiddenError("演示会话无效")
    return customer


def current_customer(
    x_demo_session: str | None = Header(default=None, alias=DEMO_SESSION_HEADER),
    db: Session = Depends(get_db),
) -> Customer:
    return resolve_customer(db, x_demo_session)
