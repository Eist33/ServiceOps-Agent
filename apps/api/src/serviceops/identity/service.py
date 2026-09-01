from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.database import get_db
from serviceops.models import Customer, Operator
from serviceops.shared.errors import ForbiddenError

DEMO_SESSION_HEADER = "X-Demo-Session"
OPS_SESSION_HEADER = "X-Ops-Session"
AGENT_SESSION_HEADER = "X-Agent-Session"


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


def resolve_operator(db: Session, session_token: str | None) -> Operator:
    if not session_token:
        raise ForbiddenError("缺少运营会话凭证")
    operator = db.scalar(select(Operator).where(Operator.session_token == session_token))
    if not operator:
        raise ForbiddenError("运营会话无效")
    return operator


def current_operator(
    x_ops_session: str | None = Header(default=None, alias=OPS_SESSION_HEADER),
    db: Session = Depends(get_db),
) -> Operator:
    return resolve_operator(db, x_ops_session)


def current_support_agent(
    x_agent_session: str | None = Header(default=None, alias=AGENT_SESSION_HEADER),
    db: Session = Depends(get_db),
) -> Operator:
    if not x_agent_session:
        raise ForbiddenError("缺少坐席会话凭证")
    operator = db.scalar(
        select(Operator).where(Operator.session_token == x_agent_session)
    )
    if not operator or operator.role != "SUPPORT_AGENT":
        raise ForbiddenError("坐席会话无效")
    return operator
