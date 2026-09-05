from serviceops.integrations.commerce.contracts import (
    MAX_RECENT_ORDER_LIMIT,
    AdapterErrorCode,
    AdapterState,
    AuthorizationCallback,
    CommerceAdapterError,
    CommerceProvider,
    ExternalOrder,
    ExternalOrderRef,
    ExternalShippingSnapshot,
    IntegrationCapability,
    IntegrationStatus,
    PlatformIdentity,
    VerifiedExternalIdentity,
)


class UnconfiguredCommercePlatform:
    """Fail-closed placeholder used until an official platform adapter is approved."""

    def __init__(self, provider: CommerceProvider) -> None:
        self.provider = provider

    def integration_status(self) -> IntegrationStatus:
        return IntegrationStatus(
            provider=self.provider,
            state=AdapterState.NOT_CONFIGURED,
            capabilities=(
                IntegrationCapability.IDENTITY,
                IntegrationCapability.ORDERS_READ,
                IntegrationCapability.SHIPPING_READ,
            ),
            external_requests_enabled=False,
            message="尚未配置官方平台资质和沙箱凭证",
        )

    def exchange_authorization(self, callback: AuthorizationCallback) -> VerifiedExternalIdentity:
        del callback
        self._raise_not_configured()

    def list_recent_orders(
        self,
        identity: PlatformIdentity,
        *,
        limit: int = MAX_RECENT_ORDER_LIMIT,
    ) -> tuple[ExternalOrder, ...]:
        self._require_identity(identity)
        if not 1 <= limit <= MAX_RECENT_ORDER_LIMIT:
            raise ValueError(f"Recent order limit must be between 1 and {MAX_RECENT_ORDER_LIMIT}")
        self._raise_not_configured()

    def get_shipping(
        self,
        identity: PlatformIdentity,
        order: ExternalOrderRef,
    ) -> ExternalShippingSnapshot:
        self._require_identity(identity)
        if order.provider != self.provider or order.tenant_ref != identity.tenant_ref:
            raise CommerceAdapterError(
                self.provider,
                AdapterErrorCode.FORBIDDEN,
                retryable=False,
            )
        self._raise_not_configured()

    def _require_identity(self, identity: PlatformIdentity) -> None:
        if identity.provider != self.provider:
            raise CommerceAdapterError(
                self.provider,
                AdapterErrorCode.FORBIDDEN,
                retryable=False,
            )

    def _raise_not_configured(self) -> None:
        raise CommerceAdapterError(
            self.provider,
            AdapterErrorCode.NOT_CONFIGURED,
            retryable=False,
        )
