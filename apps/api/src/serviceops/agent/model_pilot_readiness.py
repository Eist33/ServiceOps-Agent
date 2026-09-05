from dataclasses import dataclass
from enum import StrEnum


class ModelPilotCapability(StrEnum):
    MODEL_PROVIDER = "MODEL_PROVIDER"
    EVALUATION_CORPUS = "EVALUATION_CORPUS"
    BUSINESS_SANDBOX = "BUSINESS_SANDBOX"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    BUDGET_CONTROLS = "BUDGET_CONTROLS"
    OBSERVABILITY_ROLLBACK = "OBSERVABILITY_ROLLBACK"
    PILOT_SCOPE = "PILOT_SCOPE"


REQUIRED_MODEL_PILOT_CAPABILITIES = frozenset(ModelPilotCapability)


class ModelPilotReadinessRequirement(StrEnum):
    SERVER_SIDE_KEY_REFERENCE = "server_side_key_reference"
    MODEL_VERSION_PINNED = "model_version_pinned"
    PROMPT_TOOL_SCHEMA_PINNED = "prompt_tool_schema_pinned"
    KNOWLEDGE_VERSION_PINNED = "knowledge_version_pinned"
    DETERMINISTIC_BASELINE_PASSED = "deterministic_baseline_passed"
    REAL_MODEL_70_CASE_EVALUATION = "real_model_70_case_evaluation"
    REDACTED_SAMPLE_REVIEW = "redacted_sample_review"
    PROMPT_INJECTION_EVALUATION = "prompt_injection_evaluation"
    LONG_CONVERSATION_EVALUATION = "long_conversation_evaluation"
    AMBIGUOUS_MULTI_INTENT_EVALUATION = "ambiguous_multi_intent_evaluation"
    TOOL_FAILURE_EVALUATION = "tool_failure_evaluation"
    BUSINESS_SANDBOX_ISOLATION = "business_sandbox_isolation"
    HUMAN_ESCALATION_DRILL = "human_escalation_drill"
    BUDGET_RATE_LIMIT = "budget_rate_limit"
    REFUND_HUMAN_APPROVAL = "refund_human_approval"
    OBSERVABILITY_ROLLBACK_DRILL = "observability_rollback_drill"
    PILOT_SCOPE_APPROVAL = "pilot_scope_approval"


REQUIRED_MODEL_PILOT_READINESS_REQUIREMENTS = tuple(ModelPilotReadinessRequirement)
ALLOWED_MODEL_PILOT_ROLES = frozenset({"CUSTOMER", "SUPPORT"})
MINIMUM_REAL_MODEL_CASES = 70


class ModelPilotReadinessState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_APPROVED = "NOT_APPROVED"
    READY_FOR_PILOT_REVIEW = "READY_FOR_PILOT_REVIEW"


@dataclass(frozen=True, slots=True)
class ModelPilotScopeBinding:
    """An opaque, server-owned identity binding; it contains no customer data."""

    role: str
    tenant_ref: str
    connection_ref: str
    account_ref: str
    session_ref: str
    tab_ref: str


@dataclass(frozen=True, slots=True)
class ModelPilotScope:
    """Explicit pilot identities; wildcard and ambiguous bindings are rejected."""

    scope_ref: str
    bindings: tuple[ModelPilotScopeBinding, ...]
    max_active_sessions: int


@dataclass(frozen=True, slots=True)
class ModelPilotReadinessEvidence:
    """Review evidence without prompts, outputs, credentials, or customer data."""

    completed: frozenset[ModelPilotReadinessRequirement]
    approved_capabilities: frozenset[ModelPilotCapability]
    real_model_case_count: int = 0
    safety_failure_count: int = 0
    deterministic_fallback_count: int = 0


@dataclass(frozen=True, slots=True)
class ModelPilotRuntimeStatus:
    """Deployment-owned facts; this object never calls a model or enables traffic."""

    environment: str
    configured_capabilities: frozenset[ModelPilotCapability]
    server_side_key_reference_configured: bool
    budget_controls_configured: bool
    model_requests_enabled: bool = False
    pilot_traffic_enabled: bool = False
    deterministic_fallback_enabled: bool = True
    refund_execution_enabled: bool = False
    pilot_scope: ModelPilotScope | None = None


@dataclass(frozen=True, slots=True)
class ModelPilotReadinessReport:
    state: ModelPilotReadinessState
    configured_capabilities: tuple[ModelPilotCapability, ...]
    model_requests_enabled: bool
    pilot_traffic_enabled: bool
    refund_execution_enabled: bool
    real_model_case_count: int
    safety_failure_count: int
    deterministic_fallback_count: int
    missing_configuration: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    missing_approvals: tuple[str, ...]
    scope_violations: tuple[str, ...]
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "configured_capabilities": [
                capability.value for capability in self.configured_capabilities
            ],
            "model_requests_enabled": self.model_requests_enabled,
            "pilot_traffic_enabled": self.pilot_traffic_enabled,
            "refund_execution_enabled": self.refund_execution_enabled,
            "real_model_case_count": self.real_model_case_count,
            "safety_failure_count": self.safety_failure_count,
            "deterministic_fallback_count": self.deterministic_fallback_count,
            "missing_configuration": list(self.missing_configuration),
            "missing_requirements": list(self.missing_requirements),
            "missing_approvals": list(self.missing_approvals),
            "scope_violations": list(self.scope_violations),
            "message": self.message,
        }


def unconfigured_model_pilot_runtime_status() -> ModelPilotRuntimeStatus:
    return ModelPilotRuntimeStatus(
        environment="development",
        configured_capabilities=frozenset(),
        server_side_key_reference_configured=False,
        budget_controls_configured=False,
    )


def _scope_violations(scope: ModelPilotScope) -> tuple[str, ...]:
    violations: list[str] = []
    if not scope.scope_ref.strip() or scope.scope_ref.strip() in {"*", "all", "ALL"}:
        violations.append("scope_ref_must_be_explicit")
    if not scope.bindings:
        violations.append("pilot_scope_must_have_bindings")
    if scope.max_active_sessions < 1 or scope.max_active_sessions > len(scope.bindings):
        violations.append("max_active_sessions_must_match_scope")

    binding_keys: set[tuple[str, str, str, str, str]] = set()
    session_keys: set[tuple[str, str]] = set()
    tab_keys: set[tuple[str, str]] = set()
    for index, binding in enumerate(scope.bindings):
        if binding.role not in ALLOWED_MODEL_PILOT_ROLES:
            violations.append(f"binding:{index}:role_not_allowed")
        for label, value in (
            ("tenant", binding.tenant_ref),
            ("connection", binding.connection_ref),
            ("account", binding.account_ref),
            ("session", binding.session_ref),
            ("tab", binding.tab_ref),
        ):
            if not value.strip() or value.strip() in {"*", "all", "ALL"}:
                violations.append(f"binding:{index}:{label}_ref_must_be_explicit")

        binding_key = (
            binding.tenant_ref,
            binding.connection_ref,
            binding.account_ref,
            binding.session_ref,
            binding.tab_ref,
        )
        if binding_key in binding_keys:
            violations.append(f"binding:{index}:duplicate_binding")
        binding_keys.add(binding_key)

        session_key = (binding.tenant_ref, binding.session_ref)
        if session_key in session_keys:
            violations.append(f"binding:{index}:session_binding_must_be_unique")
        session_keys.add(session_key)

        tab_key = (binding.tenant_ref, binding.tab_ref)
        if tab_key in tab_keys:
            violations.append(f"binding:{index}:tab_binding_must_be_unique")
        tab_keys.add(tab_key)
    return tuple(violations)


def evaluate_model_pilot_readiness(
    evidence: ModelPilotReadinessEvidence,
    *,
    runtime_status: ModelPilotRuntimeStatus,
) -> ModelPilotReadinessReport:
    """Evaluate stage 12 evidence without calling a model or changing traffic."""
    missing_configuration = [
        f"capability:{capability.value}"
        for capability in sorted(
            REQUIRED_MODEL_PILOT_CAPABILITIES - set(runtime_status.configured_capabilities),
            key=lambda item: item.value,
        )
    ]
    if runtime_status.environment.strip().lower() not in {"staging", "production"}:
        missing_configuration.append("pilot_environment")
    if not runtime_status.server_side_key_reference_configured:
        missing_configuration.append("server_side_model_key_reference")
    if not runtime_status.budget_controls_configured:
        missing_configuration.append("budget_controls")
    if runtime_status.model_requests_enabled:
        missing_configuration.append("model_requests_must_remain_disabled")
    if runtime_status.pilot_traffic_enabled:
        missing_configuration.append("pilot_traffic_must_remain_disabled")
    if runtime_status.deterministic_fallback_enabled:
        missing_configuration.append("deterministic_fallback_must_be_disabled")
    if runtime_status.refund_execution_enabled:
        missing_configuration.append("refund_execution_must_remain_disabled")

    scope_violations = (
        ("pilot_scope_must_be_configured",)
        if runtime_status.pilot_scope is None
        else _scope_violations(runtime_status.pilot_scope)
    )
    if scope_violations:
        missing_configuration.append("pilot_scope_must_be_explicit")

    missing_requirements = [
        requirement.value
        for requirement in REQUIRED_MODEL_PILOT_READINESS_REQUIREMENTS
        if requirement not in evidence.completed
    ]
    if (
        ModelPilotReadinessRequirement.REAL_MODEL_70_CASE_EVALUATION in evidence.completed
        and evidence.real_model_case_count < MINIMUM_REAL_MODEL_CASES
    ):
        missing_requirements.append("real_model_case_count_minimum_70")
    if (
        ModelPilotReadinessRequirement.REAL_MODEL_70_CASE_EVALUATION in evidence.completed
        and evidence.safety_failure_count != 0
    ):
        missing_requirements.append("safety_failure_count_must_be_zero")
    if (
        ModelPilotReadinessRequirement.REAL_MODEL_70_CASE_EVALUATION in evidence.completed
        and evidence.deterministic_fallback_count != 0
    ):
        missing_requirements.append("deterministic_fallback_count_must_be_zero")

    missing_approvals = [
        f"capability:{capability.value}"
        for capability in sorted(
            REQUIRED_MODEL_PILOT_CAPABILITIES - set(evidence.approved_capabilities),
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
        return ModelPilotReadinessReport(
            state=ModelPilotReadinessState.NOT_CONFIGURED,
            configured_capabilities=configured_capabilities,
            model_requests_enabled=False,
            pilot_traffic_enabled=False,
            refund_execution_enabled=False,
            real_model_case_count=evidence.real_model_case_count,
            safety_failure_count=evidence.safety_failure_count,
            deterministic_fallback_count=evidence.deterministic_fallback_count,
            missing_configuration=tuple(missing_configuration),
            missing_requirements=tuple(missing_requirements),
            missing_approvals=tuple(missing_approvals),
            scope_violations=scope_violations,
            message="阶段 12 真实模型试点尚未配置，保持 NOT_CONFIGURED 且不发起模型请求",
        )
    if missing_requirements or missing_approvals:
        return ModelPilotReadinessReport(
            state=ModelPilotReadinessState.NOT_APPROVED,
            configured_capabilities=configured_capabilities,
            model_requests_enabled=False,
            pilot_traffic_enabled=False,
            refund_execution_enabled=False,
            real_model_case_count=evidence.real_model_case_count,
            safety_failure_count=evidence.safety_failure_count,
            deterministic_fallback_count=evidence.deterministic_fallback_count,
            missing_configuration=(),
            missing_requirements=tuple(missing_requirements),
            missing_approvals=tuple(missing_approvals),
            scope_violations=(),
            message="阶段 12 真实模型试点尚未完成评测和共同审批，保持 NOT_APPROVED 且不发起模型请求",
        )
    return ModelPilotReadinessReport(
        state=ModelPilotReadinessState.READY_FOR_PILOT_REVIEW,
        configured_capabilities=configured_capabilities,
        model_requests_enabled=False,
        pilot_traffic_enabled=False,
        refund_execution_enabled=False,
        real_model_case_count=evidence.real_model_case_count,
        safety_failure_count=evidence.safety_failure_count,
        deterministic_fallback_count=evidence.deterministic_fallback_count,
        missing_configuration=(),
        missing_requirements=(),
        missing_approvals=(),
        scope_violations=(),
        message="阶段 12 真实模型试点仅通过评审门禁，当前仍不发起模型请求或扩大流量",
    )
