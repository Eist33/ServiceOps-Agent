from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_改进计划_v1.0.md"
ADR = ROOT / "docs" / "ADR-0002-采用渐进式混合RAG而非照搬AgentX平台.md"


def test_improvement_plan_classifies_the_current_knowledge_system_honestly() -> None:
    text = PLAN.read_text(encoding="utf-8")

    for statement in (
        "当前知识库在广义上属于 RAG",
        "可评测的规则/词法检索增强问答基线",
        "embedding=None",
        "还不能描述为完整的语义向量 RAG 平台",
        "知识库外问题误答率仍为 0",
    ):
        assert statement in text


def test_improvement_plan_has_ordered_delivery_stages_and_exit_gates() -> None:
    text = PLAN.read_text(encoding="utf-8")
    headings = [f"## 阶段 {number}：" for number in range(7)]
    positions = [text.index(heading) for heading in headings]

    assert positions == sorted(positions)
    for start, end in zip(positions, positions[1:] + [len(text)], strict=True):
        block = text[start:end]
        assert "### 目标" in block
        assert "### 开发动作" in block
        assert "### 测试重点" in block
        assert "### 退出条件" in block


def test_improvement_plan_borrows_agentx_rag_mechanisms_without_platform_scope() -> None:
    text = PLAN.read_text(encoding="utf-8")

    for mechanism in (
        "KnowledgeRelease",
        "AgentRelease",
        "HybridSearchDomainService",
        "pgvector",
        "RRF",
        "Rerank",
        "HyDE",
        "检索 Trace",
        "结构化切块",
        "不可变发布快照",
    ):
        assert mechanism in text
    for boundary in (
        "不重写为 Java/Spring",
        "不建设通用 RAG 市场",
        "不默认启用 HyDE",
        "不在没有指标瓶颈前引入 Elasticsearch",
        "每个完成的切片创建独立 Git commit",
    ):
        assert boundary in text


def test_improvement_plan_preserves_serviceops_safety_and_evaluation_gates() -> None:
    text = PLAN.read_text(encoding="utf-8")

    for gate in (
        "PostgreSQL 是唯一事实源",
        "Prompt Injection",
        "跨客户、跨角色、跨租户知识泄漏数为 0",
        "过期或停用知识召回数为 0",
        "退款确认继续走独立人工确认接口",
        "主分支质量门禁恢复为全绿",
    ):
        assert gate in text


def test_rag_adr_is_accepted_and_records_the_incremental_decision() -> None:
    text = ADR.read_text(encoding="utf-8")

    assert "状态：已接受" in text
    for decision in (
        "属于广义 RAG，但不声称已完成语义向量 RAG",
        "保留模块化单体和 PostgreSQL 唯一事实源",
        "通过 RRF 融合",
        "保留现有 `lexical_v1` 回退路径",
        "暂不引入 Elasticsearch、RabbitMQ、通用 RAG 市场、MCP 社区或 Multi-Agent",
        "出现可测量瓶颈后另立 ADR",
    ):
        assert decision in text


def test_improvement_docs_have_no_placeholders_or_internal_citations() -> None:
    combined = PLAN.read_text(encoding="utf-8") + ADR.read_text(encoding="utf-8")

    for forbidden in ("TODO", "turn0search", ":codex-file-citation"):
        assert forbidden not in combined
