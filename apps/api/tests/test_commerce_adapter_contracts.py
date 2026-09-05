import pytest

from serviceops.integrations.commerce import (
    AdapterErrorCode,
    AdapterState,
    AuthorizationCallback,
    CommerceAdapterError,
    CommerceProvider,
    ExternalOrderRef,
    IdentityProvider,
    IntegrationCapability,
    IntegrationStatusReader,
    OrderReader,
    PlatformIdentity,
    ShippingReader,
    build_default_commerce_registry,
)


def login(client, login_name: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"login_name": login_name, "password": "serviceops"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_default_registry_contains_only_fail_closed_official_platform_stubs() -> None:
    registry = build_default_commerce_registry()

    assert {status.provider for status in registry.statuses()} == set(CommerceProvider)
    for status in registry.statuses():
        assert status.state == AdapterState.NOT_CONFIGURED
        assert status.external_requests_enabled is False
        assert set(status.capabilities) == {
            IntegrationCapability.IDENTITY,
            IntegrationCapability.ORDERS_READ,
            IntegrationCapability.SHIPPING_READ,
        }


@pytest.mark.parametrize("provider", list(CommerceProvider))
def test_stub_satisfies_all_protocols_and_never_returns_business_data(
    provider: CommerceProvider,
) -> None:
    bundle = build_default_commerce_registry().get(provider)
    assert isinstance(bundle.identity_provider, IdentityProvider)
    assert isinstance(bundle.status_reader, IntegrationStatusReader)
    assert isinstance(bundle.order_reader, OrderReader)
    assert isinstance(bundle.shipping_reader, ShippingReader)

    identity = PlatformIdentity(provider=provider, subject="subject-1", tenant_ref="shop-1")
    order = ExternalOrderRef(
        provider=provider,
        tenant_ref="shop-1",
        external_order_id="external-order-1",
    )
    operations = (
        lambda: bundle.identity_provider.exchange_authorization(
            AuthorizationCallback(
                code="one-time-code",
                state="expected-state",
                redirect_uri="https://merchant.example/callback",
            )
        ),
        lambda: bundle.order_reader.list_recent_orders(identity),
        lambda: bundle.shipping_reader.get_shipping(identity, order),
    )

    for operation in operations:
        with pytest.raises(CommerceAdapterError) as caught:
            operation()
        assert caught.value.code == AdapterErrorCode.NOT_CONFIGURED
        assert caught.value.retryable is False
        assert caught.value.as_dict() == {
            "provider": provider.value,
            "code": "NOT_CONFIGURED",
            "message": "平台尚未配置，当前请求未发送到外部系统",
            "retryable": False,
        }


def test_stub_rejects_cross_provider_and_cross_tenant_access_before_lookup() -> None:
    taobao = build_default_commerce_registry().get(CommerceProvider.TAOBAO)
    taobao_identity = PlatformIdentity(
        provider=CommerceProvider.TAOBAO,
        subject="subject-1",
        tenant_ref="shop-1",
    )
    xiaohongshu_identity = PlatformIdentity(
        provider=CommerceProvider.XIAOHONGSHU,
        subject="subject-1",
        tenant_ref="shop-1",
    )

    with pytest.raises(CommerceAdapterError) as wrong_provider:
        taobao.order_reader.list_recent_orders(xiaohongshu_identity)
    assert wrong_provider.value.code == AdapterErrorCode.FORBIDDEN

    with pytest.raises(CommerceAdapterError) as wrong_tenant:
        taobao.shipping_reader.get_shipping(
            taobao_identity,
            ExternalOrderRef(
                provider=CommerceProvider.TAOBAO,
                tenant_ref="another-shop",
                external_order_id="external-order-1",
            ),
        )
    assert wrong_tenant.value.code == AdapterErrorCode.FORBIDDEN


def test_recent_order_contract_never_allows_more_than_three_orders() -> None:
    bundle = build_default_commerce_registry().get(CommerceProvider.XIANYU)
    identity = PlatformIdentity(
        provider=CommerceProvider.XIANYU,
        subject="subject-1",
        tenant_ref="shop-1",
    )

    for invalid_limit in (0, 4):
        with pytest.raises(ValueError, match="between 1 and 3"):
            bundle.order_reader.list_recent_orders(identity, limit=invalid_limit)


def test_operations_can_inspect_safe_platform_readiness_without_credentials(client) -> None:
    manager_token = login(client, "xuzhixia")
    response = client.get(
        "/api/ops/integrations/commerce",
        headers=bearer(manager_token),
    )

    assert response.status_code == 200
    assert {item["provider"] for item in response.json()} == {
        "TAOBAO",
        "XIAOHONGSHU",
        "XIANYU",
    }
    assert all(item["state"] == "NOT_CONFIGURED" for item in response.json())
    assert all(item["external_requests_enabled"] is False for item in response.json())
    assert "token" not in response.text.lower()
    assert "secret" not in response.text.lower()
    assert "http" not in response.text.lower()


def test_platform_readiness_endpoint_enforces_server_side_roles(client) -> None:
    customer_token = login(client, "linmu")
    support_token = login(client, "shenqinghe")

    assert (
        client.get(
            "/api/ops/integrations/commerce",
            headers=bearer(customer_token),
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/ops/integrations/commerce",
            headers=bearer(support_token),
        ).status_code
        == 403
    )


def test_contract_dtos_do_not_require_customer_pii_or_raw_credentials() -> None:
    callback = AuthorizationCallback(
        code="one-time-code",
        state="state-value",
        redirect_uri="https://merchant.example/callback",
    )
    identity = PlatformIdentity(
        provider=CommerceProvider.TAOBAO,
        subject="stable-subject",
        tenant_ref="shop-1",
    )

    assert callback.code == "one-time-code"
    assert identity.subject == "stable-subject"
    assert not hasattr(identity, "customer_name")
    assert not hasattr(identity, "phone")
    assert not hasattr(identity, "access_token")
