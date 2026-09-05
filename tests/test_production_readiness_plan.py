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
