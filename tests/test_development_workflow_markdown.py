from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "docs" / "企业客服与工单执行Agent_MVP开发流程_v0.1.md"


class DevelopmentWorkflowMarkdownTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_exists_and_contains_required_sections(self):
        self.assertTrue(WORKFLOW.exists())
        self.assertGreater(WORKFLOW.stat().st_size, 10_000)

        required = [
            "模块化单体",
            "纵向全栈切片",
            "开发前置决策",
            "阶段 0：冻结场景、契约和验收标准",
            "阶段 1：工程骨架",
            "阶段 2：政策问答纵向切片",
            "阶段 3：订单与物流查询纵向切片",
            "阶段 4：物流异常建单纵向切片",
            "阶段 5：退款确认纵向切片",
            "阶段 6：质量与交付",
            "测试分层与质量门禁",
            "Git 提交策略",
            "MVP 完成定义",
        ]
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_phase_order_is_sequential(self):
        positions = [self.text.index(f"## 阶段 {number}：") for number in range(7)]
        self.assertEqual(positions, sorted(positions))

    def test_documents_required_safety_boundaries(self):
        required = [
            "Agent 不直接访问数据库",
            "前端不能从 Agent 自然语言中反向解析",
            "confirm_refund",
            "Idempotency-Key",
            "重复确认返回第一次执行结果",
            "禁止从聊天文本推断最终业务状态",
        ]
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_each_implementation_phase_has_quality_gates(self):
        phase_blocks = re.split(r"(?=^## 阶段 [0-6]：)", self.text, flags=re.MULTILINE)[1:]
        self.assertEqual(len(phase_blocks), 7)
        for block in phase_blocks:
            heading = block.splitlines()[0]
            with self.subTest(phase=heading):
                self.assertIn("### 目标", block)
                self.assertIn("### 开发动作", block)
                self.assertIn("### 测试重点", block)
                self.assertIn("### 退出条件", block)

    def test_has_no_placeholders_or_internal_tokens(self):
        self.assertNotIn("TODO", self.text)
        self.assertNotIn(":codex-file-citation", self.text)
        self.assertNotIn("turn0search", self.text)


if __name__ == "__main__":
    unittest.main()
