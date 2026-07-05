import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_APP = ROOT / "apps" / "web"


class FrontendAppScaffoldTest(unittest.TestCase):
    def test_next_app_scaffold_declares_required_stack(self) -> None:
        package_json = WEB_APP / "package.json"
        self.assertTrue(package_json.exists(), "apps/web/package.json is required")

        package = json.loads(package_json.read_text(encoding="utf-8"))
        self.assertEqual(package["private"], True)
        self.assertIn("dev", package["scripts"])
        self.assertIn("build", package["scripts"])
        self.assertIn("test", package["scripts"])

        dependencies = package["dependencies"]
        for dependency in [
            "next",
            "react",
            "react-dom",
            "@tanstack/react-query",
            "zod",
            "react-hook-form",
            "@hookform/resolvers",
            "lucide-react",
        ]:
            self.assertIn(dependency, dependencies)

    def test_required_frontend_routes_exist(self) -> None:
        required_routes = [
            "app/(app)/dashboard/page.tsx",
            "app/(app)/search/new/page.tsx",
            "app/(app)/search/[searchId]/results/page.tsx",
            "app/(app)/search/[searchId]/sources/page.tsx",
            "app/(app)/search/[searchId]/governance/page.tsx",
            "app/(app)/reports/generate/page.tsx",
            "app/(app)/evidence-library/page.tsx",
            "app/(app)/reviews/page.tsx",
        ]

        for route in required_routes:
            self.assertTrue((WEB_APP / route).exists(), f"missing frontend route {route}")

    def test_dashboard_uses_typed_api_boundary_and_fixture(self) -> None:
        dashboard_page = WEB_APP / "app" / "(app)" / "dashboard" / "page.tsx"
        dashboard_api = WEB_APP / "features" / "dashboard" / "api.ts"
        dashboard_fixture = WEB_APP / "tests" / "mocks" / "fixtures" / "dashboard.json"

        self.assertTrue(dashboard_page.exists())
        self.assertTrue(dashboard_api.exists())
        self.assertTrue(dashboard_fixture.exists())

        page_source = dashboard_page.read_text(encoding="utf-8")
        api_source = dashboard_api.read_text(encoding="utf-8")
        fixture = json.loads(dashboard_fixture.read_text(encoding="utf-8"))

        self.assertIn("getDashboardSummary", page_source)
        self.assertIn("/v1/dashboard/summary", api_source)
        self.assertEqual(
            set(fixture["kpis"].keys()),
            {
                "activeResearchProjects",
                "evidenceReportsCreated",
                "pendingReviews",
                "governanceAlerts",
            },
        )

    def test_frontend_production_docs_are_linked(self) -> None:
        frontend_doc = ROOT / "docs" / "production" / "frontend-application-foundation.md"
        production_readme = ROOT / "docs" / "production" / "README.md"
        project_overview = ROOT / "docs" / "project-overview-and-usage.md"

        self.assertTrue(frontend_doc.exists())
        self.assertIn(
            "frontend-application-foundation.md",
            production_readme.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "apps/web",
            project_overview.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
