from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOLUTION = (
    ROOT
    / "docs"
    / "企业客服与工单执行Agent_自然语言统一入口与客服后台隔离方案_v0.2.md"
)


class NaturalLanguageUnifiedEntrySolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOLUTION.read_text(encoding="utf-8")

    def test_exists_and_contains_approved_decisions(self):
        self.assertTrue(SOLUTION.exists())
        self.assertGreater(SOLUTION.stat().st_size, 15_000)

        required = [
            "客户页面只有一个自然语言服务入口",
            "最近三笔订单",
            "活动订单",
            "模拟客户身份",
            "/staff/agent",
            "/staff/knowledge",
            "/staff/operations",
            "deepseek-v4-flash",
            "MODEL_PROVIDER=deepseek",
            "confirm_refund",
            "领域模型与术语",
            "完成定义",
        ]
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_customer_and_staff_capabilities_are_separated(self):
        required = [
            "客户 Agent 不得注册",
            "隐藏按钮不能替代服务端授权",
            "客户 Agent 获得后台工具数量为 0",
            "直接输入后台 URL",
            "不同身份、不同路由、不同 API 权限和不同工具集合",
        ]
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_documents_order_selection_safety(self):
        required = [
            "最多返回三笔",
            "客户完成选择之前，只允许只读查询",
            "一笔自动选中，多笔等待客户选择",
            "新建会话不得复用上一会话的活动订单或工单",
            "多订单未选择时发生写操作的数量为 0",
        ]
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_implementation_phases_are_sequential(self):
        phase_blocks = re.findall(r"^### 阶段 ([0-5])：", self.text, flags=re.MULTILINE)
        self.assertEqual(phase_blocks, [str(number) for number in range(6)])

    def test_preserves_transactional_agent_boundaries(self):
        required = [
            "Agent 传入的订单号、金额、状态、客户 ID、异常结论和工具参数均视为不可信输入",
            "不能直接访问数据库",
            "不能只依赖 Prompt",
            "未经明确确认执行退款数量为 0",
            "前端只消费结构化事件",
        ]
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.text)

    def test_has_no_placeholders_or_internal_tokens(self):
        self.assertNotIn("TODO", self.text)
        self.assertNotIn(":codex-file-citation", self.text)
        self.assertNotRegex(self.text, r"turn\d+(?:search|fetch|view)\d+")


if __name__ == "__main__":
    unittest.main()
