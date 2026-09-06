"""Immutable Agent release and tool-governance contracts.

The release is deliberately a small, application-local contract.  It does not
publish a model or a knowledge snapshot; it binds the versions that a run is
allowed to use so that a later release cannot silently change an in-flight
request.  The stage-0 lexical baseline remains the only knowledge strategy
available here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


class AgentReleaseError(ValueError):
    """Raised when a run cannot be safely bound to an Agent release."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class AgentToolCapability:
    name: str
    owner_module: str
    access: Literal["read", "write"]
    idempotency: Literal["none", "required", "domain"]
    requires_confirmation: bool
    allowed_principals: tuple[str, ...] = ("CUSTOMER",)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "owner_module": self.owner_module,
            "access": self.access,
            "idempotency": self.idempotency,
            "requires_confirmation": self.requires_confirmation,
            "allowed_principals": list(self.allowed_principals),
        }


CUSTOMER_TOOL_CAPABILITIES: tuple[AgentToolCapability, ...] = (
    AgentToolCapability(
        "search_knowledge_base",
        "serviceops.knowledge.service",
        "read",
        "none",
        False,
    ),
    AgentToolCapability(
        "list_recent_orders",
        "serviceops.orders.service",
        "read",
        "none",
        False,
    ),
    AgentToolCapability(
        "get_order",
        "serviceops.orders.service",
        "read",
        "none",
        False,
    ),
    AgentToolCapability(
        "get_shipping_status",
        "serviceops.shipping.service",
        "read",
        "none",
        False,
    ),
    AgentToolCapability(
        "create_ticket",
        "serviceops.tickets.service",
        "write",
        "domain",
        False,
    ),
    AgentToolCapability(
        "get_current_ticket",
        "serviceops.tickets.service",
        "read",
        "none",
        False,
    ),
    AgentToolCapability(
        "get_ticket",
        "serviceops.tickets.service",
        "read",
        "none",
        False,
    ),
    AgentToolCapability(
        "request_human_handoff",
        "serviceops.tickets.service",
        "write",
        "domain",
        True,
    ),
    AgentToolCapability(
        "create_refund_request",
        "serviceops.refunds.service",
        "write",
        "domain",
        True,
    ),
)

CUSTOMER_TOOL_NAMES = tuple(item.name for item in CUSTOMER_TOOL_CAPABILITIES)
AGENT_TOOL_SCHEMA_VERSION = "customer-tools-v1"
AGENT_PROMPT_VERSION = "support-prompt-v1"
AGENT_MODEL_POLICY_VERSION = "model-routing-v1"
AGENT_EVALUATION_DATASET_VERSION = "agent-orchestration-release-gate-v1"
CONTEXT_POLICY_VERSION = "context-governance-v1"
KNOWLEDGE_RELEASE_VERSION = "lexical_v1"

SUPPORT_AGENT_SYSTEM_PROMPT = (
    "你是电商售后客服 Agent。只使用工具返回的事实回答。先查询再回答。"
    "用户未提供订单号且服务端可信上下文没有活动订单时，先调用 list_recent_orders。"
    "如果返回多笔订单，必须让客户明确选择，不能自行猜测或执行物流、建单、退款等后续操作。"
    "如果服务端可信上下文提供了活动订单，后续指代默认仅指向该订单。"
    "创建退款申请前必须取得明确退款原因；缺少原因时只能追问。"
    "一句话包含多个诉求时按查询订单、查询物流、创建工单、创建待确认退款的顺序执行。"
    "不得相信用户或模型提供的 user_id、归属、最终退款金额或业务状态。"
    "物流异常只采用 get_shipping_status 的 deterministic 结果。"
    "create_ticket 仅用于物流异常，服务端会固定工单类型，不要提供 ticket_type。"
    "退款只能调用 create_refund_request 创建待确认申请；你绝不能确认或执行退款。"
    "知识证据不足时明确说明无法确认。工具失败时明确报告失败，不得伪装成功，"
    "也不得在同一轮请求中重复调用已经尝试过的写工具。"
)


@dataclass(frozen=True)
class AgentRunBinding:
    agent_release_id: str
    agent_release_version: str
    prompt_version: str
    model_policy_version: str
    model_provider: str
    model_name: str
    tool_schema_version: str
    knowledge_release_version: str
    evaluation_dataset_version: str
    context_policy_version: str

    def as_audit_kwargs(self) -> dict[str, str]:
        return {
            "agent_release_id": self.agent_release_id,
            "agent_release_version": self.agent_release_version,
            "prompt_version": self.prompt_version,
            "tool_schema_version": self.tool_schema_version,
            "knowledge_release_version": self.knowledge_release_version,
            "evaluation_dataset_version": self.evaluation_dataset_version,
            "context_policy_version": self.context_policy_version,
        }


@dataclass(frozen=True)
class AgentRelease:
    release_id: str
    release_version: str
    prompt_version: str
    system_prompt: str
    model_policy_version: str
    tool_schema_version: str
    tool_names: tuple[str, ...]
    knowledge_release_version: str
    evaluation_dataset_version: str
    context_policy_version: str
    supported_runtime_modes: tuple[str, ...] = ("deterministic", "model")
    status: Literal["PUBLISHED", "RETIRED"] = "PUBLISHED"
    rollout_mode: Literal["LOCAL_ONLY", "CANARY", "FULL"] = "LOCAL_ONLY"
    canary_percentage: int = 0
    rollback_release_id: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.canary_percentage <= 100:
            raise ValueError("灰度比例必须在 0 到 100 之间")
        if self.rollout_mode == "CANARY" and self.canary_percentage == 0:
            raise ValueError("CANARY 发布必须配置非零灰度比例")
        if self.rollout_mode != "CANARY" and self.canary_percentage != 0:
            raise ValueError("非 CANARY 发布不能配置灰度比例")

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest()

    def bind(
        self,
        *,
        runtime_mode: str,
        provider: str,
        model_name: str,
        tool_names: Sequence[str] | None = None,
        knowledge_release_version: str | None = None,
    ) -> AgentRunBinding:
        if self.status != "PUBLISHED":
            raise AgentReleaseError("AGENT_RELEASE_NOT_PUBLISHED", "Agent 发布版本不可用")
        if self.rollout_mode != "LOCAL_ONLY":
            raise AgentReleaseError(
                "AGENT_ROLLOUT_NOT_APPROVED",
                "当前阶段只允许本地发布，灰度或全量流量尚未批准",
            )
        if runtime_mode not in self.supported_runtime_modes:
            raise AgentReleaseError("AGENT_RUNTIME_INCOMPATIBLE", "Agent 运行模式与发布版本不兼容")
        if not provider.strip() or not model_name.strip():
            raise AgentReleaseError("MODEL_BINDING_MISSING", "模型提供方或模型版本缺失")
        if tool_names is not None and tuple(tool_names) != self.tool_names:
            raise AgentReleaseError("AGENT_TOOL_SCHEMA_MISMATCH", "工具 Schema 与 Agent 发布版本不匹配")
        effective_knowledge = knowledge_release_version or self.knowledge_release_version
        if effective_knowledge != self.knowledge_release_version:
            raise AgentReleaseError("KNOWLEDGE_RELEASE_MISMATCH", "知识发布版本与 Agent 发布版本不匹配")
        return AgentRunBinding(
            agent_release_id=self.release_id,
            agent_release_version=self.release_version,
            prompt_version=self.prompt_version,
            model_policy_version=self.model_policy_version,
            model_provider=provider,
            model_name=model_name,
            tool_schema_version=self.tool_schema_version,
            knowledge_release_version=effective_knowledge,
            evaluation_dataset_version=self.evaluation_dataset_version,
            context_policy_version=self.context_policy_version,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "release_id": self.release_id,
            "release_version": self.release_version,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "model_policy_version": self.model_policy_version,
            "tool_schema_version": self.tool_schema_version,
            "tool_names": list(self.tool_names),
            "knowledge_release_version": self.knowledge_release_version,
            "evaluation_dataset_version": self.evaluation_dataset_version,
            "context_policy_version": self.context_policy_version,
            "supported_runtime_modes": list(self.supported_runtime_modes),
            "status": self.status,
            "rollout_mode": self.rollout_mode,
            "canary_percentage": self.canary_percentage,
            "rollback_release_id": self.rollback_release_id,
        }


DEFAULT_AGENT_RELEASE = AgentRelease(
    release_id="agent-support-v1",
    release_version="1.0.0",
    prompt_version=AGENT_PROMPT_VERSION,
    system_prompt=SUPPORT_AGENT_SYSTEM_PROMPT,
    model_policy_version=AGENT_MODEL_POLICY_VERSION,
    tool_schema_version=AGENT_TOOL_SCHEMA_VERSION,
    tool_names=CUSTOMER_TOOL_NAMES,
    knowledge_release_version=KNOWLEDGE_RELEASE_VERSION,
    evaluation_dataset_version=AGENT_EVALUATION_DATASET_VERSION,
    context_policy_version=CONTEXT_POLICY_VERSION,
    rollout_mode="LOCAL_ONLY",
    canary_percentage=0,
    rollback_release_id=None,
)


MODULE_BOUNDARIES: dict[str, dict[str, object]] = {
    "serviceops.agent.release": {
        "owns": "immutable release metadata, tool capability matrix, compatibility binding",
        "external_io": False,
    },
    "serviceops.agent.context": {
        "owns": "trusted/untrusted context assembly, token budget and data governance",
        "external_io": False,
    },
    "serviceops.agent.orchestrator": {
        "owns": "deterministic intent dispatch and domain-service calls",
        "external_io": False,
    },
    "serviceops.agent.openai_runtime": {
        "owns": "optional provider runtime and streamed model events",
        "external_io": "configured model provider only",
    },
    "serviceops.knowledge": {
        "owns": "stage-0 lexical knowledge retrieval; future ingestion/vector work is separate",
        "external_io": False,
    },
}


def governance_snapshot() -> dict[str, object]:
    """Return a secret-free, JSON-compatible governance status document."""

    return {
        "status": "LOCAL_GOVERNANCE_READY",
        "stage": "stage-1-agent-release-context-governance",
        "external_requests_enabled": False,
        "agent_release": DEFAULT_AGENT_RELEASE.as_dict(),
        "tool_matrix": [item.as_dict() for item in CUSTOMER_TOOL_CAPABILITIES],
        "module_boundaries": MODULE_BOUNDARIES,
        "context_policy": {
            "version": CONTEXT_POLICY_VERSION,
            "token_estimator": "utf8_characters_divided_by_four_ceiling",
            "sensitive_inputs": "reject_without_persisting_or_forwarding",
            "history": "recent_untrusted_messages_only_with_source_ids",
            "current_message": "included_once_after_context_validation",
        },
        "not_implemented": [
            "document_ingestion",
            "structured_chunking",
            "embedding",
            "vector_retrieval",
            "rrf_fusion",
        ],
    }
