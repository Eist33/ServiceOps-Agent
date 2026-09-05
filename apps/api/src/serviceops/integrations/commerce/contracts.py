from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

MAX_RECENT_ORDER_LIMIT = 3


class CommerceProvider(StrEnum):
    TAOBAO = "TAOBAO"
    XIAOHONGSHU = "XIAOHONGSHU"
    XIANYU = "XIANYU"


class IntegrationCapability(StrEnum):
    IDENTITY = "IDENTITY"
    ORDERS_READ = "ORDERS_READ"
    SHIPPING_READ = "SHIPPING_READ"


READ_ONLY_CAPABILITIES = frozenset(
    {
        IntegrationCapability.IDENTITY,
        IntegrationCapability.ORDERS_READ,
        IntegrationCapability.SHIPPING_READ,
    }
)


class AdapterState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    READY = "READY"
    DEGRADED = "DEGRADED"


class AdapterErrorCode(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    INVALID_CALLBACK = "INVALID_CALLBACK"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_FOUND = "NOT_FOUND"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    PROVIDER_ERROR = "PROVIDER_ERROR"


SAFE_ERROR_MESSAGES: dict[AdapterErrorCode, str] = {
    AdapterErrorCode.NOT_CONFIGURED: "平台尚未配置，当前请求未发送到外部系统",
    AdapterErrorCode.INVALID_CALLBACK: "平台授权回调无效",
    AdapterErrorCode.UNAUTHORIZED: "平台授权已失效",
    AdapterErrorCode.FORBIDDEN: "当前平台身份无权访问该资源",
    AdapterErrorCode.TIMEOUT: "平台请求超时，请稍后重试",
    AdapterErrorCode.RATE_LIMITED: "平台请求频率受限，请稍后重试",
    AdapterErrorCode.NOT_FOUND: "平台未返回对应数据",
    AdapterErrorCode.MALFORMED_RESPONSE: "平台返回的数据不完整",
    AdapterErrorCode.PROVIDER_ERROR: "平台服务暂时不可用",
}


class CommerceAdapterError(RuntimeError):
    """A sanitized platform error that never contains raw provider payloads."""

    def __init__(
        self,
        provider: CommerceProvider,
        code: AdapterErrorCode,
        *,
        retryable: bool,
    ) -> None:
        self.provider = provider
        self.code = code
        self.retryable = retryable
        super().__init__(SAFE_ERROR_MESSAGES[code])

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider.value,
            "code": self.code.value,
            "message": str(self),
            "retryable": self.retryable,
        }


@dataclass(frozen=True, slots=True)
class AuthorizationCallback:
    code: str
    state: str
    redirect_uri: str


@dataclass(frozen=True, slots=True)
class PlatformIdentity:
    provider: CommerceProvider
    subject: str
    tenant_ref: str


@dataclass(frozen=True, slots=True)
class VerifiedExternalIdentity:
    identity: PlatformIdentity
    granted_scopes: tuple[str, ...]
    credential_reference: str
    authorized_at: datetime


@dataclass(frozen=True, slots=True)
class ExternalOrderRef:
    provider: CommerceProvider
    tenant_ref: str
    external_order_id: str


@dataclass(frozen=True, slots=True)
class ExternalOrder:
    reference: ExternalOrderRef
    ordered_at: datetime
    status: str
    item_summary: str
    total_amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class ExternalShippingNode:
    occurred_at: datetime
    status: str
    location: str | None
    description: str


@dataclass(frozen=True, slots=True)
class ExternalShippingSnapshot:
    order: ExternalOrderRef
    status: str
    nodes: tuple[ExternalShippingNode, ...]
    fetched_at: datetime
    partial: bool = False


@dataclass(frozen=True, slots=True)
class IntegrationStatus:
    provider: CommerceProvider
    state: AdapterState
    capabilities: tuple[IntegrationCapability, ...]
    external_requests_enabled: bool
    message: str


class ReadinessRequirement(StrEnum):
    OFFICIAL_APPLICATION = "official_application"
    AUTHORIZATION_CONTRACT = "authorization_contract"
    API_DOCUMENTATION = "api_documentation"
    SANDBOX_ACCOUNT = "sandbox_account"
    FIELD_MAPPING = "field_mapping"
    SECRET_MANAGER_REFERENCE = "secret_manager_reference"
    RELIABILITY_CONTROLS = "reliability_controls"
    CONTRACT_TESTS = "contract_tests"
    SANDBOX_READ_TESTS = "sandbox_read_tests"
    PRIVACY_REVIEW = "privacy_review"
    MONITORING = "monitoring"
    ROLLBACK = "rollback"


REQUIRED_READINESS_REQUIREMENTS = tuple(ReadinessRequirement)


@dataclass(frozen=True, slots=True)
class OfficialAdapterReadinessEvidence:
    """Platform-neutral evidence required before enabling an official adapter."""

    provider: CommerceProvider
    completed: frozenset[ReadinessRequirement]


@dataclass(frozen=True, slots=True)
class OfficialAdapterReadinessReport:
    provider: CommerceProvider
    state: AdapterState
    capabilities: tuple[IntegrationCapability, ...]
    external_requests_enabled: bool
    missing_requirements: tuple[str, ...]
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider.value,
            "state": self.state.value,
            "capabilities": [capability.value for capability in self.capabilities],
            "external_requests_enabled": self.external_requests_enabled,
            "missing_requirements": list(self.missing_requirements),
            "message": self.message,
        }


@runtime_checkable
class IntegrationStatusReader(Protocol):
    provider: CommerceProvider

    def integration_status(self) -> IntegrationStatus: ...


@runtime_checkable
class IdentityProvider(Protocol):
    provider: CommerceProvider

    def exchange_authorization(
        self, callback: AuthorizationCallback
    ) -> VerifiedExternalIdentity: ...


@runtime_checkable
class OrderReader(Protocol):
    provider: CommerceProvider

    def list_recent_orders(
        self,
        identity: PlatformIdentity,
        *,
        limit: int = MAX_RECENT_ORDER_LIMIT,
    ) -> tuple[ExternalOrder, ...]: ...


@runtime_checkable
class ShippingReader(Protocol):
    provider: CommerceProvider

    def get_shipping(
        self,
        identity: PlatformIdentity,
        order: ExternalOrderRef,
    ) -> ExternalShippingSnapshot: ...
