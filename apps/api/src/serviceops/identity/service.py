import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceops.config import Settings, get_settings
from serviceops.database import get_db
from serviceops.models import AuthSession, Customer, IdentityAccount, Operator
from serviceops.shared.errors import ForbiddenError, UnauthorizedError

DEMO_SESSION_HEADER = "X-Demo-Session"
OPS_SESSION_HEADER = "X-Ops-Session"
AGENT_SESSION_HEADER = "X-Agent-Session"
AUTHORIZATION_HEADER = "Authorization"


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    account_id: str
    provider: str
    principal_type: str
    principal_id: str
    display_name: str
    role: str


def _require_demo_identity(settings: Settings) -> None:
    if not settings.demo_mode_enabled:
        raise ForbiddenError("当前环境未启用开发身份认证")


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise UnauthorizedError("登录凭证格式无效")
    return token.strip()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _principal_from_account(
    db: Session, account: IdentityAccount
) -> AuthenticatedPrincipal:
    if account.principal_type == "CUSTOMER":
        customer = db.get(Customer, account.principal_id)
        if customer is None:
            raise UnauthorizedError("登录账号未绑定有效客户")
        return AuthenticatedPrincipal(
            account_id=account.id,
            provider=account.provider,
            principal_type="CUSTOMER",
            principal_id=customer.id,
            display_name=customer.name,
            role="CUSTOMER",
        )
    if account.principal_type == "OPERATOR":
        operator = db.get(Operator, account.principal_id)
        if operator is None:
            raise UnauthorizedError("登录账号未绑定有效员工")
        return AuthenticatedPrincipal(
            account_id=account.id,
            provider=account.provider,
            principal_type="OPERATOR",
            principal_id=operator.id,
            display_name=operator.name,
            role=operator.role,
        )
    raise UnauthorizedError("登录账号主体类型无效")


def resolve_bearer_principal(
    db: Session, authorization: str | None
) -> AuthenticatedPrincipal:
    token = _bearer_token(authorization)
    if token is None:
        raise UnauthorizedError("请先登录")
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == _token_hash(token))
    )
    if session is None or session.revoked_at is not None:
        raise UnauthorizedError("登录已失效，请重新登录")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise UnauthorizedError("登录已过期，请重新登录")
    account = db.get(IdentityAccount, session.identity_account_id)
    if account is None or not account.active:
        raise UnauthorizedError("登录账号已停用")
    return _principal_from_account(db, account)


def list_development_accounts(db: Session) -> list[IdentityAccount]:
    return list(
        db.scalars(
            select(IdentityAccount)
            .where(
                IdentityAccount.provider == "DEVELOPMENT",
                IdentityAccount.active.is_(True),
            )
            .order_by(IdentityAccount.principal_type, IdentityAccount.login_name)
        )
    )


def login_development_account(
    db: Session,
    login_name: str,
    password: str,
    settings: Settings,
) -> tuple[str, datetime, AuthenticatedPrincipal]:
    _require_demo_identity(settings)
    if not hmac.compare_digest(
        password.encode("utf-8"), settings.demo_login_password.encode("utf-8")
    ):
        raise UnauthorizedError("账号或密码错误")
    account = db.scalar(
        select(IdentityAccount).where(
            IdentityAccount.provider == "DEVELOPMENT",
            IdentityAccount.login_name == login_name.strip().lower(),
            IdentityAccount.active.is_(True),
        )
    )
    if account is None:
        raise UnauthorizedError("账号或密码错误")
    principal = _principal_from_account(db, account)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=settings.auth_session_hours)
    db.add(
        AuthSession(
            identity_account_id=account.id,
            token_hash=_token_hash(token),
            expires_at=expires_at,
        )
    )
    db.commit()
    return token, expires_at, principal


def revoke_auth_session(db: Session, authorization: str | None) -> None:
    token = _bearer_token(authorization)
    if token is None:
        raise UnauthorizedError("请先登录")
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == _token_hash(token))
    )
    if session is None or session.revoked_at is not None:
        raise UnauthorizedError("登录已失效，请重新登录")
    session.revoked_at = datetime.now(UTC)
    db.commit()


def current_authenticated_principal(
    authorization: str | None = Header(default=None, alias=AUTHORIZATION_HEADER),
    db: Session = Depends(get_db),
) -> AuthenticatedPrincipal:
    return resolve_bearer_principal(db, authorization)


def resolve_customer(db: Session, session_token: str | None) -> Customer:
    if not session_token:
        raise ForbiddenError("缺少演示会话凭证")
    customer = db.scalar(select(Customer).where(Customer.session_token == session_token))
    if not customer:
        raise ForbiddenError("演示会话无效")
    return customer


def current_customer(
    authorization: str | None = Header(default=None, alias=AUTHORIZATION_HEADER),
    x_demo_session: str | None = Header(default=None, alias=DEMO_SESSION_HEADER),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Customer:
    if authorization:
        principal = resolve_bearer_principal(db, authorization)
        if principal.principal_type != "CUSTOMER":
            raise ForbiddenError("当前账号不是客户账号")
        customer = db.get(Customer, principal.principal_id)
        if customer is None:
            raise UnauthorizedError("登录账号未绑定有效客户")
        return customer
    _require_demo_identity(settings)
    return resolve_customer(db, x_demo_session)


def resolve_operator(db: Session, session_token: str | None) -> Operator:
    if not session_token:
        raise ForbiddenError("缺少运营会话凭证")
    operator = db.scalar(select(Operator).where(Operator.session_token == session_token))
    if not operator:
        raise ForbiddenError("运营会话无效")
    return operator


def current_operator(
    authorization: str | None = Header(default=None, alias=AUTHORIZATION_HEADER),
    x_ops_session: str | None = Header(default=None, alias=OPS_SESSION_HEADER),
    x_agent_session: str | None = Header(default=None, alias=AGENT_SESSION_HEADER),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Operator:
    if authorization:
        principal = resolve_bearer_principal(db, authorization)
        if principal.principal_type != "OPERATOR":
            raise ForbiddenError("当前账号不是后台员工账号")
        operator = db.get(Operator, principal.principal_id)
        if operator is None:
            raise UnauthorizedError("登录账号未绑定有效员工")
        return operator
    _require_demo_identity(settings)
    return resolve_operator(db, x_ops_session or x_agent_session)


def current_support_agent(
    operator: Operator = Depends(current_operator),
) -> Operator:
    if operator.role != "SUPPORT_AGENT":
        raise ForbiddenError("当前账号没有客服工作台权限")
    return operator


def current_knowledge_manager(
    operator: Operator = Depends(current_operator),
) -> Operator:
    if operator.role != "KNOWLEDGE_MANAGER":
        raise ForbiddenError("当前账号没有知识运营权限")
    return operator


def current_operations_operator(
    operator: Operator = Depends(current_operator),
) -> Operator:
    if operator.role not in {"KNOWLEDGE_MANAGER", "OPERATIONS_MANAGER"}:
        raise ForbiddenError("当前账号没有运营看板权限")
    return operator
