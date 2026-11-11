"""Execute frontend behavior in an available local JS engine without network access."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.artificial_analysis import load_mock_snapshot
from tools.model_evidence import RelevanceDecision, build_candidates
from tools.decision import decide

ROOT = Path(__file__).resolve().parents[1]
JSC = shutil.which("jsc") or "/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc"


class FrontendJavaScriptTests(unittest.TestCase):
    @unittest.skipUnless(Path(JSC).is_file(), "A local JavaScriptCore interpreter is unavailable.")
    def test_presentation_sse_weights_reset_and_stale_writer(self):
        snapshot = load_mock_snapshot(ROOT / "examples/offline-aa.json")
        prepared = build_candidates(snapshot, RelevanceDecision("Synthetic financial task", "finance", "strong", "Synthetic fixture only."))
        fixture = {"decision": decide(prepared), "markdown": "Synthetic original Writer report.", "status": "supported"}
        source = "const fixture=" + json.dumps(fixture) + ";\n" + (ROOT / "tests/frontend_contract.js").read_text()
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "frontend-test.js"
            script.write_text(source)
            result = subprocess.run([JSC, str(script)], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Frontend contract checks passed", result.stdout)
