from serviceops.integrations.commerce.contracts import (
    READ_ONLY_CAPABILITIES,
    REQUIRED_READINESS_REQUIREMENTS,
    AdapterState,
    IntegrationStatus,
    OfficialAdapterReadinessEvidence,
    OfficialAdapterReadinessReport,
)


def evaluate_official_adapter_readiness(
    evidence: OfficialAdapterReadinessEvidence,
    *,
    runtime_status: IntegrationStatus,
) -> OfficialAdapterReadinessReport:
    """Evaluate evidence without making any platform request or changing runtime state."""
    if runtime_status.provider != evidence.provider:
        raise ValueError("Readiness evidence and runtime status must use the same provider")

    missing = [
        requirement.value
        for requirement in REQUIRED_READINESS_REQUIREMENTS
        if requirement not in evidence.completed
    ]
    missing.extend(
        f"capability:{capability.value}"
        for capability in sorted(
            READ_ONLY_CAPABILITIES - set(runtime_status.capabilities),
            key=lambda item: item.value,
        )
    )
    if runtime_status.state != AdapterState.READY:
        missing.append("runtime_adapter_ready")
    if not runtime_status.external_requests_enabled:
        missing.append("external_requests_enabled")

    capabilities = tuple(
        sorted(runtime_status.capabilities, key=lambda capability: capability.value)
    )
    if missing:
        return OfficialAdapterReadinessReport(
            provider=evidence.provider,
            state=AdapterState.NOT_CONFIGURED,
            capabilities=capabilities,
            external_requests_enabled=False,
            missing_requirements=tuple(missing),
            message="官方适配器准入条件未完成，保持 NOT_CONFIGURED 且不发起外部请求",
        )
    return OfficialAdapterReadinessReport(
        provider=evidence.provider,
        state=AdapterState.READY,
        capabilities=capabilities,
        external_requests_enabled=True,
        missing_requirements=(),
        message="官方适配器已满足只读沙箱准入条件",
    )
