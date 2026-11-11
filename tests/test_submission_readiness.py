"""Cleanup boundaries, deployment inputs, and submission hygiene without network calls."""

import ast
import json
import shlex
import unittest
from pathlib import Path

from scripts.submission_audit import CJK, SECRET_PATTERNS, private_path

ROOT = Path(__file__).resolve().parents[1]


class SubmissionReadinessTests(unittest.TestCase):
    def test_private_material_is_distinct_from_legitimate_examples_and_fixtures(self):
        for name in (".env", ".env.local", ".cache/screenshot.png", "docs/PRD.md", ".venv/bin/python",
                     "local-service-account.json", "application_default_credentials.json", "key.pem"):
            self.assertTrue(private_path(name), name)
        for name in (".env.example", "tests/fixtures/aa_free_mock.json", "examples/offline-aa.json", "submission.example.json"):
            self.assertFalse(private_path(name), name)

    def test_audit_patterns_identify_secrets_without_embedding_real_credentials(self):
        samples = {"private_key": "-----BEGIN " + "PRIVATE KEY-----", "google_api_key": "AI" + "za" + "a" * 35,
                   "aws_access_key": "AK" + "IA" + "A" * 16,
                   "credential_json": json.dumps({"type": "service_" + "account"})}
        for name, sample in samples.items():
            self.assertTrue(SECRET_PATTERNS[name].search(sample))
        self.assertFalse(CJK.search("English submission text."))

    def test_no_runtime_import_depends_on_removed_data_layer(self):
        for path in [*ROOT.glob("*.py"), *(ROOT / "tools").glob("*.py"), *(ROOT / "scripts").glob("*.py")]:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    self.assertNotIn("wikipedia", [alias.name for alias in node.names], str(path))
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "wikipedia", str(path))
        for name in ("wikipedia.py", "index.html", "context-panel.js"):
            self.assertFalse((ROOT / name).exists())

    def test_docker_copy_inputs_and_runtime_flags_are_valid_locally(self):
        docker = (ROOT / "Dockerfile").read_text()
        for line in docker.splitlines():
            if line.startswith("COPY "):
                for name in shlex.split(line)[1:-1]:
                    self.assertTrue(list(ROOT.glob(name)), f"Missing Docker COPY input: {name}")
            if line.startswith("CMD "):
                command = json.loads(line[4:])
                self.assertIn("0.0.0.0", command[-1])
                self.assertIn("${PORT:-8080}", command[-1])
                self.assertIn("--workers 1", command[-1])
        self.assertIn("USER appuser", docker)
        for name in (".dockerignore", ".gcloudignore"):
            text = (ROOT / name).read_text()
            self.assertIn("**", text)
            for forbidden in (".env", ".cache", "docs", "tests"):
                self.assertIn(forbidden, text)

    def test_submission_example_does_not_invent_authors_or_deployed_url(self):
        manifest = json.loads((ROOT / "submission.example.json").read_text())
        self.assertIsNone(manifest["deploy_url"])
        self.assertEqual(manifest["authors"], [])
        self.assertEqual(manifest["path"], "research")
        self.assertIn("reported", (ROOT / "README.md").read_text())
        self.assertIn("writer_fallback=true", (ROOT / "README.md").read_text())

    def test_container_installer_is_pinned_and_live_mode_is_explicit(self):
        docker = (ROOT / "Dockerfile").read_text()
        self.assertRegex(docker, r"pip install --no-cache-dir uv==\d+\.\d+\.\d+")
        self.assertIn("uv sync --locked --no-dev", docker)
        self.assertIn("UV_PYTHON_DOWNLOADS=never", docker)
        self.assertIn("MODELMATCH_OFFLINE=0", docker)
        self.assertNotIn("COPY . ", docker)

    def test_deployment_instructions_preserve_unverified_release_gates(self):
        text = (ROOT / "DEPLOYMENT.md").read_text()
        self.assertFalse(CJK.search(text))
        for required in ("approve_live=true", "GET /run", "not authentication", "one worker",
                         "not been verified locally", "Writer failure", "Project 2", "service account"):
            self.assertIn(required, text)
