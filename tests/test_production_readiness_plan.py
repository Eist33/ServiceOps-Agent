from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "企业客服与工单执行Agent_生产化开发流程_v1.0.md"


def test_production_plan_covers_ordered_delivery_stages() -> None:
    text = PLAN.read_text(encoding="utf-8")

    stages = [
        "阶段 7：生产安全基线与发布工具",
        "阶段 8：身份、角色与组织权限",
        "阶段 9：真实订单与物流只读适配器",
        "阶段 10：真实工单写入与退款沙箱",
        "阶段 11：生产基础设施、可观测性与灾备",
        "阶段 12：真实模型发布门禁与小范围试点",
    ]
    positions = [text.index(stage) for stage in stages]
    assert positions == sorted(positions)


def test_production_plan_has_security_quality_and_rollback_gates() -> None:
    text = PLAN.read_text(encoding="utf-8")

    for requirement in (
        "演示令牌在生产配置下始终无效",
        "任何客户都无法通过修改订单号查询他人数据",
        "不会产生重复工单或重复退款",
        "备份能够在隔离环境恢复",
        "所有安全计数为 0",
        "一键回滚",
        "每个完成的切片创建独立 Git commit",
    ):
        assert requirement in text
    assert "TODO" not in text


def test_production_plan_documents_non_powershell_commands() -> None:
    text = PLAN.read_text(encoding="utf-8")

    assert "scripts\\start-product.cmd" in text
    assert "scripts\\verify.cmd" in text
    assert "scripts\\verify-release.cmd --cold-start" in text
    assert "--verify-model --evaluate-full-model" in text


def test_production_plan_defines_xianyu_local_read_only_experiment() -> None:
    text = PLAN.read_text(encoding="utf-8")

    required_sections = (
        "阶段 9B：闲鱼个人账号本地只读实验（进行中；9B-1～9B-4 已完成本地模拟验收）",
        "阶段 9B-1：可见登录与本地会话边界",
        "阶段 9B-2：聊天列表只读映射",
        "阶段 9B-3：会话详情只读映射",
        "阶段 9B-4：账号切换、删除和保留期限",
        "阶段 9B 退出条件",
        "阶段 9C：官方只读沙箱适配器（待外部条件）",
    )
    positions = [text.index(section) for section in required_sections]
    assert positions == sorted(positions)

    for safety_rule in (
        "不得读取短信、保存验证码、代替用户通过验证、批量登录或在后台无人值守重试",
        "本阶段不发送消息、不自动回复、不点击商品、不操作订单、不发货、不关单、不退款",
        "不代表闲鱼授权、协议合规、生产稳定性或服务器部署通过",
        "禁止非官方页面接入",
        "实验性闲鱼个人账号连接，仅供本人授权的本地测试",
    ):
        assert safety_rule in text


def test_production_plan_records_xianyu_pilot_decisions_and_retention() -> None:
    text = PLAN.read_text(encoding="utf-8")

    for decision in (
        "首批试点范围为闲鱼客户和客服",
        "员工开发阶段继续使用现有账号体系",
        "不合并不同平台或不同账号的客户身份",
        "先完成本地开发，服务器部署另行决策",
        "聊天消息默认在会话结束后保存 180 天",
        "客服工单和处理结果保存 1 年",
        "登录与安全审计保存 180 天",
        "模型完整输入输出在脱敏后最多保存 30 天",
    ):
        assert decision in text


def test_production_plan_links_the_9b4_lifecycle_delivery() -> None:
    text = PLAN.read_text(encoding="utf-8")

    for requirement in (
        "阶段 9B-4：账号切换、删除和保留期限（已完成本地模拟验收，2026-09-05）",
        "统一的当前标签页实验数据清理",
        "security_audit_events",
        "retention_runs",
        "purge-retention",
        "《9B-4：账号切换、删除和保留期限》",
    ):
        assert requirement in text


def test_future_external_stages_keep_explicit_unconfigured_gates() -> None:
    text = PLAN.read_text(encoding="utf-8")

    for requirement in (
        "9C 的本地交付是平台无关的准入门禁",
        "正式官方适配器仍受外部资质、接口文档和沙箱账号阻塞",
        "阶段 10 的本地交付是平台无关的写入准入门禁",
        "阶段 10 当前不注册 `TicketWriter`、`WebhookReceiver` 或 `RefundGateway`",
        "配置但缺少共同审批时返回 `NOT_APPROVED`",
        "真实写入和资金动作保持关闭",
        "阶段 11 当前没有托管 PostgreSQL、Secret Manager、外部告警或物理备份服务",
        "阶段 12 当前没有真实模型试点或扩大范围签署",
        "不得把本地桩或确定性评测描述为生产就绪",
    ):
        assert requirement in text


def test_future_external_capabilities_are_not_registered_in_runtime() -> None:
    commerce_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "apps" / "api" / "src" / "serviceops" / "integrations"
        ).rglob("*.py")
    )

    for future_boundary in ("TicketWriter", "WebhookReceiver", "RefundGateway"):
        assert future_boundary not in commerce_source
    assert "external_requests_enabled=False" in commerce_source
    assert "NOT_CONFIGURED" in commerce_source
