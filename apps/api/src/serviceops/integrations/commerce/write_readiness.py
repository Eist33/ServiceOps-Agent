from dataclasses import dataclass
from enum import StrEnum

from serviceops.integrations.commerce.contracts import CommerceProvider


class ExternalWriteCapability(StrEnum):
    TICKET_WRITE = "TICKET_WRITE"
    WEBHOOK_RECEIVE = "WEBHOOK_RECEIVE"
    REFUND_SANDBOX = "REFUND_SANDBOX"


REQUIRED_EXTERNAL_WRITE_CAPABILITIES = frozenset(ExternalWriteCapability)


class ExternalWriteReadinessRequirement(StrEnum):
    READ_ONLY_ADAPTER_READY = "read_only_adapter_ready"
    SECRET_MANAGER_REFERENCE = "secret_manager_reference"
    TICKET_SANDBOX_AUTHORIZATION = "ticket_sandbox_authorization"
    TICKET_API_CONTRACT = "ticket_api_contract"
    TICKET_OUTBOX_DELIVERY = "ticket_outbox_delivery"
    TICKET_IDEMPOTENCY = "ticket_idempotency"
    TICKET_RECONCILIATION = "ticket_reconciliation"
    WEBHOOK_AUTHENTICATION = "webhook_authentication"
    WEBHOOK_REPLAY_PROTECTION = "webhook_replay_protection"
    REFUND_SANDBOX_AUTHORIZATION = "refund_sandbox_authorization"
    REFUND_CONFIRMATION = "refund_confirmation"
    REFUND_APPROVAL = "refund_approval"
    REFUND_AMOUNT_RECHECK = "refund_amount_recheck"
    REFUND_TIMEOUT_RECONCILIATION = "refund_timeout_reconciliation"
    PRIVACY_REVIEW = "privacy_review"
    MONITORING = "monitoring"
    ROLLBACK = "rollback"


REQUIRED_EXTERNAL_WRITE_READINESS_REQUIREMENTS = tuple(ExternalWriteReadinessRequirement)


class ExternalWriteReadinessState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_APPROVED = "NOT_APPROVED"
    READY_FOR_SANDBOX = "READY_FOR_SANDBOX"


@dataclass(frozen=True, slots=True)
class ExternalWriteReadinessEvidence:
    """Process evidence; it never contains credentials, payloads, or customer data."""

    provider: CommerceProvider
    completed: frozenset[ExternalWriteReadinessRequirement]
    approved_capabilities: frozenset[ExternalWriteCapability]


@dataclass(frozen=True, slots=True)
class ExternalWriteRuntimeStatus:
    """Adapter-owned configuration facts; no client or network behavior is exposed."""

    provider: CommerceProvider
    registered_capabilities: frozenset[ExternalWriteCapability]
    endpoint_configured: bool
    credential_reference_configured: bool
    external_requests_enabled: bool = False


@dataclass(frozen=True, slots=True)
class ExternalWriteReadinessReport:
    provider: CommerceProvider
    state: ExternalWriteReadinessState
    capabilities: tuple[ExternalWriteCapability, ...]
    external_requests_enabled: bool
    missing_configuration: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    missing_approvals: tuple[str, ...]
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider.value,
            "state": self.state.value,
            "capabilities": [capability.value for capability in self.capabilities],
            "external_requests_enabled": self.external_requests_enabled,
            "missing_configuration": list(self.missing_configuration),
            "missing_requirements": list(self.missing_requirements),
            "missing_approvals": list(self.missing_approvals),
            "message": self.message,
        }


def unconfigured_external_write_runtime_status(
    provider: CommerceProvider,
) -> ExternalWriteRuntimeStatus:
    return ExternalWriteRuntimeStatus(
        provider=provider,
        registered_capabilities=frozenset(),
        endpoint_configured=False,
        credential_reference_configured=False,
    )


def evaluate_external_write_readiness(
    evidence: ExternalWriteReadinessEvidence,
    *,
    runtime_status: ExternalWriteRuntimeStatus,
) -> ExternalWriteReadinessReport:
    """Evaluate stage 10 evidence without changing state or making an external request."""
    if runtime_status.provider != evidence.provider:
        raise ValueError("Write readiness evidence and runtime status must use the same provider")

    missing_configuration = [
        f"capability:{capability.value}"
        for capability in sorted(
            REQUIRED_EXTERNAL_WRITE_CAPABILITIES - set(runtime_status.registered_capabilities),
            key=lambda item: item.value,
        )
    ]
    if not runtime_status.endpoint_configured:
        missing_configuration.append("external_endpoint")
    if not runtime_status.credential_reference_configured:
        missing_configuration.append("credential_reference")
    if runtime_status.external_requests_enabled:
        missing_configuration.append("external_requests_must_remain_disabled")

    missing_requirements = [
        requirement.value
        for requirement in REQUIRED_EXTERNAL_WRITE_READINESS_REQUIREMENTS
        if requirement not in evidence.completed
    ]
    missing_approvals = [
        f"capability:{capability.value}"
        for capability in sorted(
            REQUIRED_EXTERNAL_WRITE_CAPABILITIES - set(evidence.approved_capabilities),
            key=lambda item: item.value,
        )
    ]
    capabilities = tuple(
        sorted(runtime_status.registered_capabilities, key=lambda capability: capability.value)
    )

    if missing_configuration:
        return ExternalWriteReadinessReport(
            provider=evidence.provider,
            state=ExternalWriteReadinessState.NOT_CONFIGURED,
            capabilities=capabilities,
            external_requests_enabled=False,
            missing_configuration=tuple(missing_configuration),
            missing_requirements=tuple(missing_requirements),
            missing_approvals=tuple(missing_approvals),
            message="阶段 10 外部写入尚未配置，保持 NOT_CONFIGURED 且不发起外部请求",
        )
    if missing_requirements or missing_approvals:
        return ExternalWriteReadinessReport(
            provider=evidence.provider,
            state=ExternalWriteReadinessState.NOT_APPROVED,
            capabilities=capabilities,
            external_requests_enabled=False,
            missing_configuration=(),
            missing_requirements=tuple(missing_requirements),
            missing_approvals=tuple(missing_approvals),
            message="阶段 10 外部写入尚未完成共同审批，保持 NOT_APPROVED 且不发起外部请求",
        )
    return ExternalWriteReadinessReport(
        provider=evidence.provider,
        state=ExternalWriteReadinessState.READY_FOR_SANDBOX,
        capabilities=capabilities,
        external_requests_enabled=False,
        missing_configuration=(),
        missing_requirements=(),
        missing_approvals=(),
        message="阶段 10 外部写入仅通过沙箱准入，当前仍不启用外部请求",
    )
