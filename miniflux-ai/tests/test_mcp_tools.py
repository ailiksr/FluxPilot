import unittest

from core.mcp_tools import TOOLS, VERSION, manifest


class TestMcpTools(unittest.TestCase):
    def test_manifest_version(self):
        m = manifest()
        self.assertEqual(m["version"], "mcp-tools-v1")
        self.assertEqual(m["protocol"], "rest-bridge")

    def test_tools_count(self):
        self.assertGreaterEqual(len(TOOLS), 18)

    def test_tool_names_unique(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_all_tools_read_only(self):
        # 所有工具都必须是 GET（只读）
        for t in TOOLS:
            self.assertEqual(t["method"], "GET", f"{t['name']} must be GET/read-only")

    def test_tools_have_required_fields(self):
        for t in TOOLS:
            for field in ("name", "description", "method", "path", "input_schema", "example"):
                self.assertIn(field, t, f"{t.get('name')} missing {field}")
            self.assertIsInstance(t["input_schema"], dict)

    def test_manifest_contains_all_tools(self):
        m = manifest()
        self.assertEqual(len(m["tools"]), len(TOOLS))
        self.assertEqual({t["name"] for t in m["tools"]}, {t["name"] for t in TOOLS})

    def test_key_tools_present(self):
        names = {t["name"] for t in TOOLS}
        for expected in ("get_scores", "get_trends", "get_feed_health", "get_article_detail",
                         "get_system_status", "get_preference_profile",
                         "search_articles", "get_system_health", "get_recommendation_consistency"):
            self.assertIn(expected, names)

    def test_manifest_security_flags(self):
        m = manifest()
        self.assertIn("authentication", m)
        self.assertIn("base_url", m)


if __name__ == "__main__":
    unittest.main()
