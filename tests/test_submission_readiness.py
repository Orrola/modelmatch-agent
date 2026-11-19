"""Cleanup boundaries, deployment inputs, and submission hygiene without network calls."""

import ast
import json
import shlex
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from scripts.submission_audit import CJK, SECRET_PATTERNS, private_path

ROOT = Path(__file__).resolve().parents[1]


class SubmissionReadinessTests(unittest.TestCase):
    def test_private_material_is_distinct_from_legitimate_examples_and_fixtures(self):
        for name in (".env", ".env.local", ".cache/screenshot.png", "docs/PRD.md", ".venv/bin/python",
                     "local-service-account.json", "application_default_credentials.json", "key.pem"):
            self.assertTrue(private_path(name), name)
        for name in (".env.example", "tests/fixtures/aa_free_mock.json", "examples/offline-aa.json", "submission.json"):
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

    def test_submission_manifest_has_required_fields(self):
        manifest = json.loads((ROOT / "submission.json").read_text())
        self.assertIsInstance(manifest, dict)
        self.assertTrue({"deploy_url", "authors", "path"}.issubset(manifest))
        self.assertIsInstance(manifest["deploy_url"], str)
        url = urlsplit(manifest["deploy_url"])
        self.assertEqual(url.scheme, "https")
        self.assertTrue(url.hostname)
        self.assertIsNone(url.username)
        self.assertIsNone(url.password)
        self.assertIsInstance(manifest["authors"], list)
        self.assertTrue(manifest["authors"])
        self.assertTrue(all(isinstance(author, str) and author.strip() for author in manifest["authors"]))
        self.assertEqual(manifest["path"], "research")

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
