from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"


def test_readme_is_a_user_facing_product_page() -> None:
    text = README.read_text(encoding="utf-8")

    for marker in (
        "# Harbor Support",
        "## 在线展示",
        "展示地址",
        "这是在线展示地址占位符",
        "## 你可以用它做什么",
        "## 客户网页流程",
        "## 客服网页流程",
        "## 退款保护",
        "## 消息回复体验",
        "## 页面示例",
        "## 运行和网页验收",
        "架构设计",
        "部署与运行指南",
    ):
        assert marker in text

    # README is intentionally a product page; implementation vocabulary belongs
    # in architecture/deployment docs linked from it.
    forbidden_implementation_terms = (
        "fastapi",
        "postgresql",
        "pgvector",
        "sqlalchemy",
        "alembic",
        "docker",
        "vinext",
        "react",
        "pnpm",
        "powershell",
        "pytest",
        "migration",
        "docker compose",
    )
    lowered = text.lower()
    for term in forbidden_implementation_terms:
        assert term not in lowered


def test_readme_links_and_screenshot_placeholders_are_safe() -> None:
    text = README.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)#]+)\)", text)

    for link in links:
        if link.startswith(("http://", "https://")):
            continue
        assert (ROOT / link).is_file(), link

    screenshot_links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    expected_screenshots = {
        "imgs/客户服务入口.png",
        "imgs/客服工作台.png",
        "imgs/退款确认.png",
        "imgs/时间信息线.png",
    }
    assert set(screenshot_links) == expected_screenshots
    for screenshot in expected_screenshots:
        assert (ROOT / screenshot).is_file(), screenshot


def test_architecture_has_renderable_boundary_diagram_and_security_scope() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")

    for marker in (
        "## 系统边界与分层",
        "```mermaid",
        "flowchart LR",
        "客户浏览器",
        "客服与运营浏览器",
        "API 与领域服务",
        "Agent 编排与工具契约",
        "知识与检索",
        "审批与幂等",
        "审计与可观测性",
        "PostgreSQL / pgvector",
        "闲鱼官方页面与外部平台",
        "## 部署与安全边界",
        "USER_CONTROLLED/NOT_CONFIGURED",
        "external_requests_enabled=false",
        "当前没有任何平台满足这些外部条件",
    ):
        assert marker in text

    assert text.count("```mermaid") == 1
    assert text.count("```") % 2 == 0
    assert "已接入闲鱼官方" not in text
