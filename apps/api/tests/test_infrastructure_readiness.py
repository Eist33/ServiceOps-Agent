from serviceops.production import (
    REQUIRED_INFRASTRUCTURE_CAPABILITIES,
    REQUIRED_INFRASTRUCTURE_READINESS_REQUIREMENTS,
    InfrastructureCapability,
    InfrastructureReadinessEvidence,
    InfrastructureReadinessRequirement,
    InfrastructureReadinessState,
    InfrastructureRuntimeStatus,
    evaluate_infrastructure_readiness,
    unconfigured_infrastructure_runtime_status,
)


def _configured_runtime(
    *,
    environment: str = "production",
    database_publicly_exposed: bool = False,
    external_resources_enabled: bool = False,
) -> InfrastructureRuntimeStatus:
    return InfrastructureRuntimeStatus(
        environment=environment,
        configured_capabilities=frozenset(REQUIRED_INFRASTRUCTURE_CAPABILITIES),
        database_publicly_exposed=database_publicly_exposed,
        external_resources_enabled=external_resources_enabled,
    )


def _complete_evidence(
    *,
    completed: frozenset[InfrastructureReadinessRequirement] | None = None,
    approved_capabilities: frozenset[InfrastructureCapability] | None = None,
) -> InfrastructureReadinessEvidence:
    return InfrastructureReadinessEvidence(
        completed=(
            completed
            if completed is not None
            else frozenset(REQUIRED_INFRASTRUCTURE_READINESS_REQUIREMENTS)
        ),
        approved_capabilities=(
            approved_capabilities
            if approved_capabilities is not None
            else frozenset(REQUIRED_INFRASTRUCTURE_CAPABILITIES)
        ),
    )


def test_default_infrastructure_runtime_is_not_configured() -> None:
    report = evaluate_infrastructure_readiness(
        InfrastructureReadinessEvidence(
            completed=frozenset(),
            approved_capabilities=frozenset(),
        ),
        runtime_status=unconfigured_infrastructure_runtime_status(),
    )

    assert report.state == InfrastructureReadinessState.NOT_CONFIGURED
    assert report.external_resources_enabled is False
    assert report.configured_capabilities == ()
    assert report.missing_configuration == (
        "capability:BACKUP_RECOVERY",
        "capability:EXTERNAL_ALERTING",
        "capability:HTTPS_DOMAIN_CORS",
        "capability:MANAGED_DATABASE",
        "capability:OBSERVABILITY",
        "capability:SECRET_MANAGER",
        "capability:SHARED_RUNTIME_STATE",
        "production_environment",
    )
    assert report.missing_requirements == tuple(
        requirement.value for requirement in REQUIRED_INFRASTRUCTURE_READINESS_REQUIREMENTS
    )
    assert report.missing_approvals == tuple(
        f"capability:{capability.value}"
        for capability in sorted(
            REQUIRED_INFRASTRUCTURE_CAPABILITIES,
            key=lambda item: item.value,
        )
    )


def test_technical_infrastructure_configuration_still_requires_approval() -> None:
    report = evaluate_infrastructure_readiness(
        InfrastructureReadinessEvidence(
            completed=frozenset(),
            approved_capabilities=frozenset(),
        ),
        runtime_status=_configured_runtime(),
    )

    assert report.state == InfrastructureReadinessState.NOT_APPROVED
    assert report.external_resources_enabled is False
    assert report.missing_configuration == ()
    assert report.missing_requirements == tuple(
        requirement.value for requirement in REQUIRED_INFRASTRUCTURE_READINESS_REQUIREMENTS
    )
    assert report.missing_approvals == (
        "capability:BACKUP_RECOVERY",
        "capability:EXTERNAL_ALERTING",
        "capability:HTTPS_DOMAIN_CORS",
        "capability:MANAGED_DATABASE",
        "capability:OBSERVABILITY",
        "capability:SECRET_MANAGER",
        "capability:SHARED_RUNTIME_STATE",
    )


def test_missing_infrastructure_requirement_and_approval_are_reported_separately() -> None:
    missing_requirement = InfrastructureReadinessRequirement.RECOVERY_DRILL
    report = evaluate_infrastructure_readiness(
        _complete_evidence(
            completed=frozenset(
                requirement
                for requirement in REQUIRED_INFRASTRUCTURE_READINESS_REQUIREMENTS
                if requirement != missing_requirement
            ),
            approved_capabilities=frozenset({InfrastructureCapability.MANAGED_DATABASE}),
        ),
        runtime_status=_configured_runtime(),
    )

    assert report.state == InfrastructureReadinessState.NOT_APPROVED
    assert report.missing_configuration == ()
    assert report.missing_requirements == (missing_requirement.value,)
    assert report.missing_approvals == (
        "capability:BACKUP_RECOVERY",
        "capability:EXTERNAL_ALERTING",
        "capability:HTTPS_DOMAIN_CORS",
        "capability:OBSERVABILITY",
        "capability:SECRET_MANAGER",
        "capability:SHARED_RUNTIME_STATE",
    )


def test_non_production_environment_cannot_become_ready() -> None:
    report = evaluate_infrastructure_readiness(
        _complete_evidence(),
        runtime_status=_configured_runtime(environment="staging"),
    )

    assert report.state == InfrastructureReadinessState.NOT_CONFIGURED
    assert report.external_resources_enabled is False
    assert report.missing_configuration == ("production_environment",)


def test_public_database_port_is_a_fail_closed_configuration_error() -> None:
    report = evaluate_infrastructure_readiness(
        _complete_evidence(),
        runtime_status=_configured_runtime(database_publicly_exposed=True),
    )

    assert report.state == InfrastructureReadinessState.NOT_CONFIGURED
    assert report.external_resources_enabled is False
    assert report.missing_configuration == ("database_public_port_must_be_closed",)


def test_external_resource_switch_is_never_accepted_by_local_gate() -> None:
    report = evaluate_infrastructure_readiness(
        _complete_evidence(),
        runtime_status=_configured_runtime(external_resources_enabled=True),
    )

    assert report.state == InfrastructureReadinessState.NOT_CONFIGURED
    assert report.external_resources_enabled is False
    assert report.missing_configuration == ("external_resources_must_remain_disabled",)


def test_complete_infrastructure_evidence_is_only_a_production_review_candidate() -> None:
    evidence = _complete_evidence()
    runtime_status = _configured_runtime()

    first = evaluate_infrastructure_readiness(evidence, runtime_status=runtime_status)
    second = evaluate_infrastructure_readiness(evidence, runtime_status=runtime_status)

    assert first == second
    assert first.state == InfrastructureReadinessState.READY_FOR_PRODUCTION_REVIEW
    assert first.configured_capabilities == (
        InfrastructureCapability.BACKUP_RECOVERY,
        InfrastructureCapability.EXTERNAL_ALERTING,
        InfrastructureCapability.HTTPS_DOMAIN_CORS,
        InfrastructureCapability.MANAGED_DATABASE,
        InfrastructureCapability.OBSERVABILITY,
        InfrastructureCapability.SECRET_MANAGER,
        InfrastructureCapability.SHARED_RUNTIME_STATE,
    )
    assert first.external_resources_enabled is False
    assert first.missing_configuration == ()
    assert first.missing_requirements == ()
    assert first.missing_approvals == ()
    assert first.as_dict() == {
        "state": "READY_FOR_PRODUCTION_REVIEW",
        "configured_capabilities": [
            "BACKUP_RECOVERY",
            "EXTERNAL_ALERTING",
            "HTTPS_DOMAIN_CORS",
            "MANAGED_DATABASE",
            "OBSERVABILITY",
            "SECRET_MANAGER",
            "SHARED_RUNTIME_STATE",
        ],
        "external_resources_enabled": False,
        "missing_configuration": [],
        "missing_requirements": [],
        "missing_approvals": [],
        "message": "阶段 11 生产基础设施仅通过评审门禁，当前仍不创建外部资源",
    }
