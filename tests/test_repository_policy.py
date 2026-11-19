"""Submission text checks. Internal documents and local artifacts are excluded."""

import re
import unittest
from pathlib import Path

from tools.artificial_analysis import load_mock_snapshot
from tools.decision import decide
from tools.model_evidence import OperationalRequirement, RelevanceDecision, Workload, build_candidates

ROOT = Path(__file__).resolve().parents[1]


class RepositoryPolicyTests(unittest.TestCase):
    def test_submission_sources_have_no_cjk_text(self):
        # External API payloads are not submission text. Fixtures are explicitly
        # synthetic and English; local caches and internal docs are not scanned.
        paths = list(ROOT.glob("*.py"))
        paths += [ROOT / name for name in ("README.md", ".gitignore", ".env.example", "pyproject.toml")]
        paths += [ROOT / "WEB_API.md", ROOT / "Dockerfile", ROOT / ".dockerignore", ROOT / ".gcloudignore"]
        for directory in ("tools", "scripts", "tests", "static", "examples"):
            paths.extend((ROOT / directory).rglob("*.py"))
            paths.extend((ROOT / directory).rglob("*.json"))
            for extension in ("*.html", "*.js", "*.css"):
                paths.extend((ROOT / directory).rglob(extension))
        cjk = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")
        violations = [str(path.relative_to(ROOT)) for path in paths if cjk.search(path.read_text())]
        self.assertEqual(violations, [], "Submission text must be English, including messages and notation.")

    def test_readme_has_no_internal_document_links(self):
        text = (ROOT / "README.md").read_text()
        links = re.findall(r"\]\(([^)]+)\)", text)
        self.assertFalse(any("docs/" in link and not link.startswith(("https://", "http://")) for link in links))

    def test_cost_penalty_behavior_is_independent_of_readme_wording(self):
        snapshot = load_mock_snapshot(ROOT / "tests/fixtures/phase2a_synthetic.json")
        relevance = RelevanceDecision("Synthetic finance task", "finance", "strong",
                                      "Synthetic evidence for offline policy verification only.")
        for budget, expected in ((3, 0), (2, -4), (1, -8)):
            with self.subTest(budget=budget):
                prepared = build_candidates(snapshot, relevance,
                                            (OperationalRequirement("monthly_cost_usd", budget),),
                                            workload=Workload(1000, 1000, 1000))
                candidate = decide(prepared)["candidates"]["synthetic-finance"]
                self.assertEqual(candidate["estimated_monthly_cost_usd"], 3)
                self.assertEqual(candidate["operational_penalties"]["cost"]["deduction"], expected)
                self.assertEqual(candidate["O"], expected)

    def test_local_material_is_ignored_and_example_is_allowed(self):
        rules = (ROOT / ".gitignore").read_text().splitlines()
        for rule in (".env", ".env.*", "!.env.example", ".cache/", ".venv/", "/docs/"):
            self.assertIn(rule, rules)


if __name__ == "__main__":
    unittest.main()
