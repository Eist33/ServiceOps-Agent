from serviceops.agent.model_pilot_readiness import (
    MINIMUM_REAL_MODEL_CASES,
    REQUIRED_MODEL_PILOT_CAPABILITIES,
    REQUIRED_MODEL_PILOT_READINESS_REQUIREMENTS,
    ModelPilotCapability,
    ModelPilotReadinessEvidence,
    ModelPilotReadinessRequirement,
    ModelPilotReadinessState,
    ModelPilotRuntimeStatus,
    ModelPilotScope,
    ModelPilotScopeBinding,
    evaluate_model_pilot_readiness,
    unconfigured_model_pilot_runtime_status,
)


def _scope(*bindings: ModelPilotScopeBinding) -> ModelPilotScope:
    return ModelPilotScope(
        scope_ref="pilot-scope-1",
        bindings=tuple(bindings),
        max_active_sessions=len(bindings),
    )


def _binding(
    *,
    role: str = "SUPPORT",
    tenant_ref: str = "tenant-1",
    connection_ref: str = "connection-1",
    account_ref: str = "account-1",
    session_ref: str = "session-1",
    tab_ref: str = "tab-1",
) -> ModelPilotScopeBinding:
    return ModelPilotScopeBinding(
        role=role,
        tenant_ref=tenant_ref,
        connection_ref=connection_ref,
        account_ref=account_ref,
        session_ref=session_ref,
        tab_ref=tab_ref,
    )


def _runtime(
    *,
    environment: str = "staging",
    model_requests_enabled: bool = False,
    pilot_traffic_enabled: bool = False,
    deterministic_fallback_enabled: bool = False,
    refund_execution_enabled: bool = False,
    pilot_scope: ModelPilotScope | None = None,
) -> ModelPilotRuntimeStatus:
    return ModelPilotRuntimeStatus(
        environment=environment,
        configured_capabilities=frozenset(REQUIRED_MODEL_PILOT_CAPABILITIES),
        server_side_key_reference_configured=True,
        budget_controls_configured=True,
        model_requests_enabled=model_requests_enabled,
        pilot_traffic_enabled=pilot_traffic_enabled,
        deterministic_fallback_enabled=deterministic_fallback_enabled,
        refund_execution_enabled=refund_execution_enabled,
        pilot_scope=pilot_scope if pilot_scope is not None else _scope(_binding()),
    )


def _evidence(
    *,
    completed: frozenset[ModelPilotReadinessRequirement] | None = None,
    approved_capabilities: frozenset[ModelPilotCapability] | None = None,
    real_model_case_count: int = MINIMUM_REAL_MODEL_CASES,
    safety_failure_count: int = 0,
    deterministic_fallback_count: int = 0,
) -> ModelPilotReadinessEvidence:
    return ModelPilotReadinessEvidence(
        completed=(
            completed
            if completed is not None
            else frozenset(REQUIRED_MODEL_PILOT_READINESS_REQUIREMENTS)
        ),
        approved_capabilities=(
            approved_capabilities
            if approved_capabilities is not None
            else frozenset(REQUIRED_MODEL_PILOT_CAPABILITIES)
        ),
        real_model_case_count=real_model_case_count,
        safety_failure_count=safety_failure_count,
        deterministic_fallback_count=deterministic_fallback_count,
    )


def test_default_model_pilot_runtime_is_not_configured() -> None:
    report = evaluate_model_pilot_readiness(
        ModelPilotReadinessEvidence(completed=frozenset(), approved_capabilities=frozenset()),
        runtime_status=unconfigured_model_pilot_runtime_status(),
    )

    assert report.state == ModelPilotReadinessState.NOT_CONFIGURED
    assert report.model_requests_enabled is False
    assert report.pilot_traffic_enabled is False
    assert report.refund_execution_enabled is False
    assert report.real_model_case_count == 0
    assert report.safety_failure_count == 0
    assert report.deterministic_fallback_count == 0
    assert report.missing_configuration == (
        "capability:BUDGET_CONTROLS",
        "capability:BUSINESS_SANDBOX",
        "capability:EVALUATION_CORPUS",
        "capability:HUMAN_ESCALATION",
        "capability:MODEL_PROVIDER",
        "capability:OBSERVABILITY_ROLLBACK",
        "capability:PILOT_SCOPE",
        "pilot_environment",
        "server_side_model_key_reference",
        "budget_controls",
        "deterministic_fallback_must_be_disabled",
        "pilot_scope_must_be_explicit",
    )
    assert report.missing_requirements == tuple(
        requirement.value for requirement in REQUIRED_MODEL_PILOT_READINESS_REQUIREMENTS
    )


def test_configured_model_pilot_still_requires_evidence_and_approvals() -> None:
    report = evaluate_model_pilot_readiness(
        ModelPilotReadinessEvidence(completed=frozenset(), approved_capabilities=frozenset()),
        runtime_status=_runtime(),
    )

    assert report.state == ModelPilotReadinessState.NOT_APPROVED
    assert report.missing_configuration == ()
    assert report.missing_requirements == tuple(
        requirement.value for requirement in REQUIRED_MODEL_PILOT_READINESS_REQUIREMENTS
    )
    assert report.missing_approvals == tuple(
        f"capability:{capability.value}"
        for capability in sorted(REQUIRED_MODEL_PILOT_CAPABILITIES, key=lambda item: item.value)
    )


def test_real_model_case_count_has_a_hard_boundary() -> None:
    evidence = _evidence(real_model_case_count=MINIMUM_REAL_MODEL_CASES - 1)
    report = evaluate_model_pilot_readiness(evidence, runtime_status=_runtime())

    assert report.state == ModelPilotReadinessState.NOT_APPROVED
    assert report.missing_requirements == ("real_model_case_count_minimum_70",)

    complete_report = evaluate_model_pilot_readiness(
        _evidence(real_model_case_count=MINIMUM_REAL_MODEL_CASES),
        runtime_status=_runtime(),
    )
    assert complete_report.state == ModelPilotReadinessState.READY_FOR_PILOT_REVIEW


def test_safety_and_fallback_failures_never_pass_the_model_gate() -> None:
    report = evaluate_model_pilot_readiness(
        _evidence(safety_failure_count=1, deterministic_fallback_count=1),
        runtime_status=_runtime(),
    )

    assert report.state == ModelPilotReadinessState.NOT_APPROVED
    assert report.missing_requirements == (
        "safety_failure_count_must_be_zero",
        "deterministic_fallback_count_must_be_zero",
    )


def test_model_requests_pilot_traffic_and_refunds_fail_closed() -> None:
    report = evaluate_model_pilot_readiness(
        _evidence(),
        runtime_status=_runtime(
            model_requests_enabled=True,
            pilot_traffic_enabled=True,
            refund_execution_enabled=True,
        ),
    )

    assert report.state == ModelPilotReadinessState.NOT_CONFIGURED
    assert report.model_requests_enabled is False
    assert report.pilot_traffic_enabled is False
    assert report.refund_execution_enabled is False
    assert report.missing_configuration == (
        "model_requests_must_remain_disabled",
        "pilot_traffic_must_remain_disabled",
        "refund_execution_must_remain_disabled",
    )


def test_non_staging_environment_and_deterministic_fallback_are_not_accepted() -> None:
    report = evaluate_model_pilot_readiness(
        _evidence(),
        runtime_status=_runtime(
            environment="development",
            deterministic_fallback_enabled=True,
        ),
    )

    assert report.state == ModelPilotReadinessState.NOT_CONFIGURED
    assert report.missing_configuration == (
        "pilot_environment",
        "deterministic_fallback_must_be_disabled",
    )


def test_scope_rejects_unknown_roles_and_cross_account_session_or_tab_reuse() -> None:
    first = _binding()
    second = _binding(
        role="ADMIN",
        connection_ref="connection-2",
        account_ref="account-2",
        tab_ref="tab-2",
    )
    invalid_scope = _scope(
        first,
        ModelPilotScopeBinding(
            role=second.role,
            tenant_ref=second.tenant_ref,
            connection_ref=second.connection_ref,
            account_ref=second.account_ref,
            session_ref=first.session_ref,
            tab_ref=first.tab_ref,
        ),
    )

    report = evaluate_model_pilot_readiness(
        _evidence(),
        runtime_status=_runtime(pilot_scope=invalid_scope),
    )

    assert report.state == ModelPilotReadinessState.NOT_CONFIGURED
    assert report.missing_configuration == ("pilot_scope_must_be_explicit",)
    assert report.scope_violations == (
        "binding:1:role_not_allowed",
        "binding:1:session_binding_must_be_unique",
        "binding:1:tab_binding_must_be_unique",
    )


def test_complete_candidate_is_idempotent_and_only_ready_for_review() -> None:
    evidence = _evidence()
    runtime_status = _runtime()
    first = evaluate_model_pilot_readiness(evidence, runtime_status=runtime_status)
    second = evaluate_model_pilot_readiness(evidence, runtime_status=runtime_status)

    assert first == second
    assert first.state == ModelPilotReadinessState.READY_FOR_PILOT_REVIEW
    assert first.missing_configuration == ()
    assert first.missing_requirements == ()
    assert first.missing_approvals == ()
    assert first.scope_violations == ()
    assert first.model_requests_enabled is False
    assert first.pilot_traffic_enabled is False
    assert first.refund_execution_enabled is False
    assert first.as_dict()["state"] == "READY_FOR_PILOT_REVIEW"
    assert first.as_dict()["real_model_case_count"] == MINIMUM_REAL_MODEL_CASES
