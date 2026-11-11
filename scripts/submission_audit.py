"""Read-only audit of actual Git submission candidates without printing secret values."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PARTS = {".env", ".venv", ".cache", "docs", "__pycache__", ".aws", ".gcloud", "screenshots", "test-results"}
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "aws_access_key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "credential_json": re.compile(r'"type"\s*:\s*"(?:service_account|authorized_user)"'),
}
CJK = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")


def git_files(*args):
    output = subprocess.check_output(["git", "ls-files", *args, "-z"], cwd=ROOT)
    return {p for p in output.decode().split("\0") if p}


def private_path(name):
    path = Path(name)
    if name == ".env.example":
        return False
    return (any(part in PRIVATE_PARTS for part in path.parts)
            or path.name.startswith(".env.") or path.suffix in {".pyc", ".pem", ".key", ".p12", ".pfx", ".log", ".tmp"}
            or (path.suffix == ".json" and any(word in path.name.lower() for word in ("credentials", "service-account", "service_account"))))


def audit():
    tracked = git_files("--cached")
    candidates = tracked | git_files("--others", "--exclude-standard")
    findings = []
    for name in sorted(candidates):
        path = ROOT / name
        if private_path(name):
            findings.append({"path": name, "category": "private_or_generated_submission_file"})
            continue
        if not path.is_file():
            findings.append({"path": name, "category": "missing_submission_file"})
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append({"path": name, "category": "binary_file_requires_manual_review"})
            continue
        if CJK.search(content):
            findings.append({"path": name, "category": "non_english_submission_text"})
        for category, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                findings.append({"path": name, "category": category})
    required = {"app.py", "pyproject.toml", "uv.lock", "README.md", "Dockerfile", ".env.example"}
    for name in sorted(required - candidates):
        findings.append({"path": name, "category": "missing_runtime_deliverable"})
    ignored_tracked = sorted(p for p in tracked if private_path(p))
    return {"source_status": "passed" if not findings else "failed", "tracked_file_count": len(tracked),
            "submission_candidate_count": len(candidates), "tracked_private_files_requiring_untracking": ignored_tracked,
            "findings": findings, "candidate_files": sorted(candidates),
            "course_submission_status": "pending_authoritative_requirements_and_final_manifest",
            "final_manifest_present": "submission.json" in candidates,
            "scope": "Pattern-based local audit; inspect the staged diff manually before publishing. No secret values are printed."}


def main():
    report = audit()
    print(json.dumps(report, indent=2))
    return 0 if report["source_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
