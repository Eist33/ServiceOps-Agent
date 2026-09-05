from dataclasses import dataclass
from enum import StrEnum


class InfrastructureCapability(StrEnum):
    MANAGED_DATABASE = "MANAGED_DATABASE"
    SECRET_MANAGER = "SECRET_MANAGER"
    HTTPS_DOMAIN_CORS = "HTTPS_DOMAIN_CORS"
    OBSERVABILITY = "OBSERVABILITY"
    EXTERNAL_ALERTING = "EXTERNAL_ALERTING"
    SHARED_RUNTIME_STATE = "SHARED_RUNTIME_STATE"
    BACKUP_RECOVERY = "BACKUP_RECOVERY"


REQUIRED_INFRASTRUCTURE_CAPABILITIES = frozenset(InfrastructureCapability)


class InfrastructureReadinessRequirement(StrEnum):
    PRODUCTION_SECURITY_CONFIGURATION = "production_security_configuration"
    MANAGED_DATABASE = "managed_database"
    DATABASE_NETWORK_ENCRYPTION = "database_network_encryption"
    SECRET_MANAGER = "secret_manager"
    HTTPS_DOMAIN_CORS = "https_domain_cors"
    METRICS = "metrics"
    EXTERNAL_ALERTING = "external_alerting"
    SHARED_RUNTIME_STATE = "shared_runtime_state"
    BACKUP_SCHEDULE = "backup_schedule"
    POINT_IN_TIME_RECOVERY = "point_in_time_recovery"
    RECOVERY_DRILL = "recovery_drill"
    RETENTION_DELETE_PROPAGATION = "retention_delete_propagation"
    FAILURE_RUNBOOKS = "failure_runbooks"
    ROLLBACK_DRILL = "rollback_drill"
    SLO_APPROVAL = "slo_approval"


REQUIRED_INFRASTRUCTURE_READINESS_REQUIREMENTS = tuple(InfrastructureReadinessRequirement)


class InfrastructureReadinessState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_APPROVED = "NOT_APPROVED"
    READY_FOR_PRODUCTION_REVIEW = "READY_FOR_PRODUCTION_REVIEW"


@dataclass(frozen=True, slots=True)
class InfrastructureReadinessEvidence:
    """Process evidence without credentials, telemetry payloads, or customer data."""

    completed: frozenset[InfrastructureReadinessRequirement]
    approved_capabilities: frozenset[InfrastructureCapability]


@dataclass(frozen=True, slots=True)
class InfrastructureRuntimeStatus:
    """Deployment-owned facts; no resource creation or external client is exposed."""

    environment: str
    configured_capabilities: frozenset[InfrastructureCapability]
    database_publicly_exposed: bool
    external_resources_enabled: bool = False


@dataclass(frozen=True, slots=True)
class InfrastructureReadinessReport:
    state: InfrastructureReadinessState
    configured_capabilities: tuple[InfrastructureCapability, ...]
    external_resources_enabled: bool
    missing_configuration: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    missing_approvals: tuple[str, ...]
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "configured_capabilities": [
                capability.value for capability in self.configured_capabilities
            ],
            "external_resources_enabled": self.external_resources_enabled,
            "missing_configuration": list(self.missing_configuration),
            "missing_requirements": list(self.missing_requirements),
            "missing_approvals": list(self.missing_approvals),
            "message": self.message,
        }


def unconfigured_infrastructure_runtime_status() -> InfrastructureRuntimeStatus:
    return InfrastructureRuntimeStatus(
        environment="development",
        configured_capabilities=frozenset(),
        database_publicly_exposed=False,
    )


def evaluate_infrastructure_readiness(
    evidence: InfrastructureReadinessEvidence,
    *,
    runtime_status: InfrastructureRuntimeStatus,
) -> InfrastructureReadinessReport:
    """Evaluate stage 11 evidence without creating resources or making a network call."""
    missing_configuration = [
        f"capability:{capability.value}"
        for capability in sorted(
            REQUIRED_INFRASTRUCTURE_CAPABILITIES - set(runtime_status.configured_capabilities),
            key=lambda item: item.value,
        )
    ]
    if runtime_status.environment.strip().lower() != "production":
        missing_configuration.append("production_environment")
    if runtime_status.database_publicly_exposed:
        missing_configuration.append("database_public_port_must_be_closed")
    if runtime_status.external_resources_enabled:
        missing_configuration.append("external_resources_must_remain_disabled")

    missing_requirements = [
        requirement.value
        for requirement in REQUIRED_INFRASTRUCTURE_READINESS_REQUIREMENTS
        if requirement not in evidence.completed
    ]
    missing_approvals = [
        f"capability:{capability.value}"
        for capability in sorted(
            REQUIRED_INFRASTRUCTURE_CAPABILITIES - set(evidence.approved_capabilities),
            key=lambda item: item.value,
        )
    ]
    configured_capabilities = tuple(
        sorted(
            runtime_status.configured_capabilities,
            key=lambda capability: capability.value,
        )
    )

    if missing_configuration:
        return InfrastructureReadinessReport(
            state=InfrastructureReadinessState.NOT_CONFIGURED,
            configured_capabilities=configured_capabilities,
            external_resources_enabled=False,
            missing_configuration=tuple(missing_configuration),
            missing_requirements=tuple(missing_requirements),
            missing_approvals=tuple(missing_approvals),
            message="阶段 11 生产基础设施尚未配置，保持 NOT_CONFIGURED 且不创建外部资源",
        )
    if missing_requirements or missing_approvals:
        return InfrastructureReadinessReport(
            state=InfrastructureReadinessState.NOT_APPROVED,
            configured_capabilities=configured_capabilities,
            external_resources_enabled=False,
            missing_configuration=(),
            missing_requirements=tuple(missing_requirements),
            missing_approvals=tuple(missing_approvals),
            message="阶段 11 生产基础设施尚未完成审批和演练，保持 NOT_APPROVED 且不创建外部资源",
        )
    return InfrastructureReadinessReport(
        state=InfrastructureReadinessState.READY_FOR_PRODUCTION_REVIEW,
        configured_capabilities=configured_capabilities,
        external_resources_enabled=False,
        missing_configuration=(),
        missing_requirements=(),
        missing_approvals=(),
        message="阶段 11 生产基础设施仅通过评审门禁，当前仍不创建外部资源",
    )
