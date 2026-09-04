from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO_APP = ROOT / "demo" / "app"
CUSTOMER_CLIENT = DEMO_APP / "demo-client.tsx"
STAFF_NAVIGATION = DEMO_APP / "staff" / "staff-navigation.tsx"
E2E = ROOT / "demo" / "e2e" / "core-flows.spec.ts"
ARCHITECTURE = ROOT / "docs" / "architecture.md"


class StaffRouteSeparationTest(unittest.TestCase):
    def test_customer_client_has_no_staff_links(self):
        text = CUSTOMER_CLIENT.read_text(encoding="utf-8")
        for href in ('href="/agent"', 'href="/knowledge"', 'href="/operations"', 'href="/staff'):
            with self.subTest(href=href):
                self.assertNotIn(href, text)
        for label in ("客服工作台", "知识运营", "运营看板"):
            with self.subTest(label=label):
                self.assertNotIn(label, text)

    def test_staff_routes_render_existing_workspaces(self):
        expected = {
            "agent": "AgentWorkbenchClient",
            "knowledge": "KnowledgeClient",
            "operations": "OperationsClient",
        }
        for route, component in expected.items():
            page = DEMO_APP / "staff" / route / "page.tsx"
            with self.subTest(route=route):
                self.assertTrue(page.exists())
                self.assertIn(component, page.read_text(encoding="utf-8"))

    def test_legacy_routes_redirect_to_staff(self):
        for route in ("agent", "knowledge", "operations"):
            page = DEMO_APP / route / "page.tsx"
            text = page.read_text(encoding="utf-8")
            with self.subTest(route=route):
                self.assertIn("redirect", text)
                self.assertIn(f"/staff/{route}", text)

    def test_staff_navigation_only_targets_staff_routes(self):
        text = STAFF_NAVIGATION.read_text(encoding="utf-8")
        self.assertIn('aria-label="客服后台导航"', text)
        for route in ("agent", "knowledge", "operations"):
            with self.subTest(route=route):
                self.assertIn(f"/staff/{route}", text)
        self.assertNotIn('href: "/"', text)
        self.assertNotIn("href: '/'", text)

    def test_e2e_covers_customer_staff_boundary_and_new_routes(self):
        text = E2E.read_text(encoding="utf-8")
        self.assertIn("客户入口不展示后台导航且客服后台内部可稳定跳转", text)
        self.assertIn("旧后台地址兼容跳转到新的 staff 路由", text)
        for route in ("agent", "knowledge", "operations"):
            with self.subTest(route=route):
                self.assertIn(f"/staff/{route}", text)

    def test_architecture_records_route_and_permission_boundary(self):
        text = ARCHITECTURE.read_text(encoding="utf-8")
        self.assertIn("客户服务入口固定为 `/`", text)
        self.assertIn("旧地址 `/agent`、`/knowledge` 和 `/operations`", text)
        self.assertIn("前端隐藏入口不替代服务端授权", text)
        for route in ("agent", "knowledge", "operations"):
            with self.subTest(route=route):
                self.assertIn(f"`/staff/{route}`", text)


if __name__ == "__main__":
    unittest.main()
