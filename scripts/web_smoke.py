"""Run a loopback HTTP smoke test with an explicitly synthetic, provider-free server."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / ".cache/web-smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "MODELMATCH_OFFLINE": "1", "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
    report = {"mode": "offline_synthetic_http", "provider_calls": 0, "checks": []}
    started = time.monotonic()
    with (ROOT / ".cache/web-smoke-server.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port), "--workers", "1"],
                                   cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=20) as client:
                for _ in range(100):
                    try:
                        if client.get("/healthz").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if process.poll() is not None:
                        raise RuntimeError("Offline server stopped before becoming healthy.")
                    time.sleep(.15)
                else:
                    raise RuntimeError("Offline server startup timed out.")
                for path in ("/", "/modelmatch", "/modelmatch.js", "/modelmatch.css", "/healthz", "/api/modelmatch/config"):
                    assert client.get(path).status_code == 200, path
                    report["checks"].append(f"GET {path}")
                response = client.post("/api/modelmatch/analyze", json={"question": "Analyze financial documents for a finance team."})
                assert response.status_code == 200
                events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                done = events[-1]
                assert done["type"] == "done" and "decision" in done["result"], done
                assert done["result"]["integration_usage"]["model_requests"] == 0
                assert done["result"]["decision"]["data_mode"] == "mock"
                report["checks"].append("SSE analysis with synthetic evidence and no provider calls")
                for alpha in (.7, None):
                    changed = client.post("/api/modelmatch/recalculate", json={"analysis_id": done["analysis_id"], "user_alpha": alpha})
                    assert changed.status_code == 200
                    expected = alpha if alpha is not None else done["result"]["decision"]["weights"]["suggested_alpha"]
                    assert changed.json()["decision"]["weights"]["alpha"] == expected
                    assert changed.json()["research_rerun"] is False
                report["checks"].append("Weight override and task-default reset without research")
                chat = client.post("/chat", json={"message": "Analyze financial documents for a finance team."})
                assert chat.status_code == 200 and chat.json()["contract_verified"] is False
                calls = chat.json()["tool_calls"]
                assert len(calls) == 6 and all(c["status"] == "completed" for c in calls)
                assert all(c["started_at"] is not None and c["elapsed_seconds"] is not None for c in calls)
                assert {c["tool"] for c in calls} == {"research_a", "research_b", "research_c", "get_general_evidence", "get_domain_evidence", "get_operational_evidence"}
                report["checks"].append("Provisional /chat with nested attributed tool parameters, results and timing")
                clarification = client.post("/chat", json={"message": "help"}).json()
                assert clarification["result"]["status"] == "clarification_needed"
                report["checks"].append("Essential task clarification")
                report.update(status="passed", sse_events=len(events), tool_calls=len(calls))
        except Exception as error:
            report.update(status="failed", error_type=type(error).__name__)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
