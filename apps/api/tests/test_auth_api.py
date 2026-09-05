import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from serviceops.models import AuthSession, SecurityAuditEvent


def login(client, login_name: str, password: str = "serviceops") -> dict:
    response = client.post(
        "/api/auth/login",
        json={"login_name": login_name, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_development_accounts_are_listed_without_credentials(client) -> None:
    response = client.get("/api/auth/development-accounts")

    assert response.status_code == 200
    accounts = response.json()
    assert {account["login_name"] for account in accounts} == {
        "linmu",
        "zhouyuan",
        "shenqinghe",
        "luchuan",
        "xuzhixia",
    }
    assert {account["principal_type"] for account in accounts} == {
        "CUSTOMER",
        "OPERATOR",
    }
    assert "token" not in response.text.lower()
    assert "password" not in response.text.lower()


def test_customer_login_issues_hashed_revocable_session(client, db) -> None:
    payload = login(client, "linmu")
    token = payload["access_token"]

    assert payload["token_type"] == "bearer"
    assert payload["principal"]["display_name"] == "林沐"
    assert payload["principal"]["role"] == "CUSTOMER"
    stored = db.scalar(select(AuthSession))
    assert stored is not None
    assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token != stored.token_hash
    login_audit = db.scalar(
        select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "AUTH_LOGIN",
            SecurityAuditEvent.outcome == "SUCCEEDED",
        )
    )
    assert login_audit is not None
    assert login_audit.account_id == stored.identity_account_id
    assert login_audit.principal_type == "CUSTOMER"
    assert login_audit.principal_id == payload["principal"]["principal_id"]
    assert login_audit.trace_id is None

    auth_me = client.get("/api/auth/me", headers=bearer(token))
    customer_me = client.get("/api/me", headers=bearer(token))
    assert auth_me.status_code == 200
    assert auth_me.json()["provider"] == "DEVELOPMENT"
    assert customer_me.status_code == 200
    assert customer_me.json()["name"] == "林沐"

    logout = client.post("/api/auth/logout", headers=bearer(token))
    assert logout.status_code == 200
    assert client.get("/api/me", headers=bearer(token)).status_code == 401
    assert db.scalar(select(func.count(AuthSession.id))) == 0
    logout_audit = db.scalar(
        select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "AUTH_LOGOUT")
    )
    assert logout_audit is not None
    assert logout_audit.outcome == "SUCCEEDED"
    assert token not in str(logout_audit)


def test_wrong_password_returns_generic_authentication_error(client, db) -> None:
    response = client.post(
        "/api/auth/login",
        json={"login_name": "linmu", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "账号或密码错误"
    audit = db.scalar(
        select(SecurityAuditEvent).where(SecurityAuditEvent.event_type == "AUTH_LOGIN")
    )
    assert audit is not None
    assert audit.outcome == "REJECTED"
    assert "wrong-password" not in str(audit)


def test_expired_session_is_rejected(client, db) -> None:
    token = login(client, "linmu")["access_token"]
    session = db.scalar(select(AuthSession))
    assert session is not None
    session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    response = client.get("/api/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "登录已过期，请重新登录"
    assert db.scalar(select(func.count(AuthSession.id))) == 0
    audit = db.scalar(
        select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "AUTH_SESSION_REJECTED"
        )
    )
    assert audit is not None
    assert audit.outcome == "EXPIRED"


def test_revoked_session_is_deleted_and_audited(client, db) -> None:
    token = login(client, "linmu")["access_token"]
    session = db.scalar(select(AuthSession))
    assert session is not None
    session.revoked_at = datetime.now(UTC)
    db.commit()

    response = client.get("/api/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "登录已失效，请重新登录"
    assert db.scalar(select(func.count(AuthSession.id))) == 0
    audit = db.scalar(
        select(SecurityAuditEvent).where(
            SecurityAuditEvent.event_type == "AUTH_SESSION_REJECTED"
        )
    )
    assert audit is not None
    assert audit.outcome == "REVOKED"


def test_customer_and_staff_roles_are_enforced_server_side(client) -> None:
    customer_token = login(client, "linmu")["access_token"]
    support_token = login(client, "shenqinghe")["access_token"]
    manager_token = login(client, "xuzhixia")["access_token"]

    assert (
        client.get("/api/agent/me", headers=bearer(customer_token)).status_code == 403
    )
    assert (
        client.get("/api/ops/dashboard", headers=bearer(support_token)).status_code
        == 403
    )
    assert (
        client.get("/api/ops/knowledge", headers=bearer(support_token)).status_code
        == 403
    )
    assert (
        client.get("/api/agent/me", headers=bearer(manager_token)).status_code == 403
    )
    assert client.get("/api/agent/me", headers=bearer(support_token)).status_code == 200
    assert (
        client.get("/api/ops/dashboard", headers=bearer(manager_token)).status_code
        == 200
    )
    assert (
        client.get("/api/ops/knowledge", headers=bearer(manager_token)).status_code
        == 200
    )
