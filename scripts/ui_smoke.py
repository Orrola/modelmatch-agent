"""Explicit offline Chrome review; no provider, deployment, or external page requests."""

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache/phase4b"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Browser:
    def __init__(self, url):
        from websockets.sync.client import connect
        self.socket = connect(url, proxy=None, max_size=30_000_000, open_timeout=10)
        self.number = 0
        self.errors, self.requests = [], []

    def call(self, method, params=None):
        self.number += 1
        self.socket.send(json.dumps({"id": self.number, "method": method, "params": params or {}}))
        while True:
            response = json.loads(self.socket.recv(timeout=20))
            if response.get("method") == "Runtime.exceptionThrown":
                self.errors.append(response["params"]["exceptionDetails"].get("text", "Browser exception"))
            if response.get("method") == "Network.requestWillBeSent":
                self.requests.append(response["params"]["request"]["url"])
            if response.get("id") == self.number:
                if "error" in response:
                    raise RuntimeError(f"CDP command failed: {method}")
                return response.get("result", {})

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if result.get("exceptionDetails"):
            raise RuntimeError(result["exceptionDetails"].get("text", "Evaluation failed"))
        return result.get("result", {}).get("value")

    def wait(self, expression, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.evaluate(expression):
                return
            time.sleep(.06)
        raise AssertionError(f"Browser condition timed out: {expression}")

    def click(self, selector):
        self.evaluate(f"(()=>{{const e=document.querySelector({json.dumps(selector)});e.focus();e.click();}})()")

    def fill(self, selector, value):
        self.evaluate(f"(()=>{{const e=document.querySelector({json.dumps(selector)}); e.value={json.dumps(value)};e.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")

    def viewport(self, width, height):
        self.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 600})
        self.evaluate("window.scrollTo(0,0)")

    def screenshot(self, name, full=False):
        self.evaluate("window.scrollTo(0,0)")
        time.sleep(.25)
        params = {"format": "png", "captureBeyondViewport": full}
        if full:
            size = self.call("Page.getLayoutMetrics")["cssContentSize"]
            params["clip"] = {"x": 0, "y": 0, "width": size["width"], "height": min(size["height"], 6000), "scale": 1}
        data = self.call("Page.captureScreenshot", params)["data"]
        (OUTPUT / name).write_bytes(base64.b64decode(data))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    chrome = os.getenv("CHROME_BINARY") or shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not Path(chrome).is_file():
        raise RuntimeError("Chrome is required for this explicit browser smoke test.")
    port, debug_port = free_port(), free_port()
    server = browser_process = browser = None
    report = {"mode": "offline_synthetic_browser", "provider_calls": 0, "checks": [], "screenshots": []}
    started = time.monotonic()

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report["checks"].append(name)

    try:
        with tempfile.TemporaryDirectory(prefix="chrome-profile-", dir=OUTPUT) as profile, (OUTPUT / "browser-server.log").open("w") as server_log, (OUTPUT / "chrome.log").open("w") as chrome_log:
            env = {**os.environ, "MODELMATCH_OFFLINE": "1", "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=server_log, stderr=server_log)
            with httpx.Client(trust_env=False, timeout=3) as client:
                for _ in range(100):
                    try:
                        if client.get(f"http://127.0.0.1:{port}/healthz").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Offline server did not start.")
                browser_process = subprocess.Popen([chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                    "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-default-apps",
                    "--metrics-recording-only", "--no-proxy-server", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
                    f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile}", "about:blank"], stdout=chrome_log, stderr=chrome_log)
                for _ in range(100):
                    try:
                        targets = client.get(f"http://127.0.0.1:{debug_port}/json/list").json()
                        page = next(p for p in targets if p.get("type") == "page")
                        break
                    except (httpx.TransportError, ValueError, StopIteration):
                        time.sleep(.1)
                else:
                    raise RuntimeError("Headless Chrome did not start.")
            browser = Browser(page["webSocketDebuggerUrl"])
            browser.call("Page.enable"); browser.call("Runtime.enable"); browser.call("Network.enable")
            browser.call("Network.setBlockedURLs", {"urls": ["https://*"]})
            browser.viewport(1440, 1100)
            browser.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/modelmatch"})
            browser.wait("document.getElementById('mode')?.textContent==='Synthetic offline demo'")
            check("Offline mode is explicit and Wikipedia link is absent", browser.evaluate("!document.querySelector('a[href=\"/\"]')"))
            browser.screenshot("desktop-overview.png", True)
            browser.viewport(390, 844); browser.screenshot("mobile-overview.png", True)
            check("Mobile overview has no page overflow", browser.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
            browser.viewport(1440, 1100)
            browser.click("#analyze")
            check("Empty task invokes native validation", browser.evaluate("document.activeElement.id==='question' && !document.getElementById('analyze').disabled"))
            browser.click("[data-example]")
            browser.click("#analyze")
            browser.wait("!document.getElementById('results').hidden && !document.getElementById('analyze').disabled")
            check("Actual offline SSE produced ranked cards", browser.evaluate("document.querySelectorAll('.model-card').length>=2"))
            check("Parallel label requires observed execution overlap", browser.evaluate("document.getElementById('workflow-status').textContent==='Parallel execution observed'"))
            check("Mock evidence never loses its synthetic banner", browser.evaluate("document.getElementById('data-label').textContent.includes('SYNTHETIC DEMO')"))
            browser.screenshot("desktop-comparison.png", True)
            original_requests = len([u for u in browser.requests if u.endswith("/api/modelmatch/analyze")])
            browser.fill("#alpha", ".73")
            browser.wait("document.getElementById('weight-status').textContent.startsWith('Updated')")
            check("Slider adjusts weights and flags old Writer explanation", browser.evaluate("document.getElementById('alpha-value').textContent==='73%' && document.getElementById('use-case-value').textContent==='27%' && document.getElementById('writer-stale').textContent.includes('has not been regenerated')"))
            browser.fill("#alpha", ".21"); browser.fill("#alpha", ".88")
            browser.wait("document.getElementById('alpha-value').textContent==='88%' && document.getElementById('weight-status').textContent.startsWith('Updated')")
            check("Rapid slider changes retain the latest weights", browser.evaluate("document.getElementById('use-case-value').textContent==='12%'"))
            browser.click("#reset")
            browser.wait("document.getElementById('alpha-value').textContent==='60%' && document.getElementById('weight-status').textContent.startsWith('Updated')")
            check("Reset uses backend task default without research rerun", len([u for u in browser.requests if u.endswith("/api/modelmatch/analyze")]) == original_requests)
            browser.evaluate("document.querySelectorAll('.model-card input[type=checkbox]')[0].click();document.querySelectorAll('.model-card input[type=checkbox]')[1].click()")
            browser.click("#show-comparison")
            check("Side-by-side comparison works", browser.evaluate("!document.getElementById('compare-panel').hidden && document.querySelectorAll('.compare-table th').length===3"))
            browser.evaluate("document.querySelectorAll('.candidate-group input[type=checkbox]')[0].click();document.querySelectorAll('.candidate-group input[type=checkbox]')[1].click()")
            check("Selection is bounded at three", browser.evaluate("document.querySelectorAll('[data-model-select]:checked').length===3 && document.getElementById('selected-count').textContent==='3'"))
            browser.click(".model-card .model-title")
            browser.wait("document.getElementById('model-drawer').open")
            check("Drawer shows breakdown and synthetic source status", browser.evaluate("document.getElementById('drawer-content').textContent.includes('Synthetic fixture') && document.querySelectorAll('.drawer-scores strong').length===4"))
            browser.screenshot("desktop-model-details.png")
            browser.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            browser.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
            browser.wait("!document.getElementById('model-drawer').open")
            check("Escape closes drawer and restores focus", browser.evaluate("document.activeElement.classList.contains('model-title')"))
            browser.click(".nav-item[data-view=evidence]")
            browser.fill("#evidence-search", "no-matching-metric")
            check("Evidence search empty state works", browser.evaluate("document.getElementById('evidence').textContent.includes('No evidence matches')"))
            browser.fill("#evidence-search", "")
            browser.screenshot("desktop-evidence.png")
            browser.click("#technical-details summary")
            check("Technical details reveal original report and traces on demand", browser.evaluate("document.getElementById('technical-data').textContent.includes('snapshot_id') && document.querySelectorAll('.trace-item').length===6 && !!document.getElementById('original-writer-text').textContent"))
            browser.click(".nav-item[data-view=comparison]")
            browser.viewport(834, 1112)
            check("Tablet comparison has no page overflow", browser.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
            browser.viewport(390, 844)
            check("Mobile comparison has no page overflow", browser.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
            browser.screenshot("mobile-comparison.png", True)
            browser.click(".model-card .model-title"); browser.screenshot("mobile-model-details.png")
            check("Mobile drawer fits the viewport", browser.evaluate("document.getElementById('model-drawer').getBoundingClientRect().width<=innerWidth"))
            browser.click("#close-drawer"); browser.click("#clear-selection")
            browser.viewport(1440, 1100); browser.click(".nav-item[data-view=overview]")
            browser.evaluate("document.getElementById('advanced').open=true;document.querySelector('input[name=hard][value=context_window]').checked=true")
            browser.click("#analyze")
            check("Hard requirements require explicit targets", browser.evaluate("!document.getElementById('form-error').hidden"))
            browser.fill("#context-window", "100000"); browser.click("#analyze")
            browser.wait("!document.getElementById('analyze').disabled && document.getElementById('ranking-title').textContent==='No supported numeric shortlist'")
            check("Missing official context remains unverified", browser.evaluate("document.querySelector('[data-status=unverified] .group-count').textContent==='5' && document.querySelectorAll('.model-card').length===0"))
            browser.click(".nav-item[data-view=overview]")
            browser.evaluate("document.getElementById('requirements').reset()")
            browser.fill("#question", "help"); browser.click("#analyze")
            browser.wait("!document.getElementById('clarification').hidden && !document.getElementById('analyze').disabled")
            check("Clarification is readable and later stages are not claimed complete", browser.evaluate("document.getElementById('questions').children.length>0 && document.querySelectorAll('.workflow-node.skipped').length>0"))
            browser.fill("#answer", "Analyze financial documents for a finance team."); browser.click("#clarify")
            browser.wait("!document.getElementById('results').hidden && !document.getElementById('analyze').disabled")
            check("Clarification submission completes a new offline run", browser.evaluate("!document.getElementById('view-comparison').hidden"))
            browser.click(".nav-item[data-view=overview]")
            browser.evaluate("document.getElementById('requirements').reset();document.getElementById('advanced').open=true")
            browser.fill("#question", "Analyze financial documents for a finance team.")
            for selector, value in (("#monthly-budget", "0"), ("#monthly-requests", "1"), ("#input-tokens", "1"), ("#output-tokens", "1")):
                browser.fill(selector, value)
            browser.click("input[name=hard][value=monthly_budget]"); browser.click("#analyze")
            browser.wait("!document.getElementById('analyze').disabled && !document.getElementById('view-comparison').hidden")
            check("Known hard failures remain separate from unknowns", browser.evaluate("Number(document.querySelector('[data-status=ineligible] .group-count').textContent)>0 && Number(document.querySelector('[data-status=unverified] .group-count').textContent)>0"))
            browser.click(".nav-item[data-view=overview]")
            browser.evaluate("document.getElementById('requirements').reset();document.getElementById('question').value='Analyze financial documents for a finance team.';window.savedFetch=window.fetch;window.fetch=(url,options)=>url==='/api/modelmatch/analyze'?Promise.resolve(new Response('data: {\"type\":\"stage\",\"agent\":\"Researcher A\",\"stage\":\"research\",\"status\":\"running\"}\\n\\ndata: {\"type\":\"error\",\"message\":\"Synthetic research failure\"}\\n\\n',{headers:{'Content-Type':'text/event-stream'}})):window.savedFetch(url,options)")
            browser.click("#analyze")
            browser.wait("document.getElementById('status').textContent==='Synthetic research failure' && !document.getElementById('analyze').disabled")
            check("Simulated streamed errors preserve failed and skipped states", browser.evaluate("document.querySelector('.research-track.failed')!==null"))
            browser.evaluate("window.fetch=(url,options)=>url==='/api/modelmatch/analyze'?new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Stopped','AbortError')))):window.savedFetch(url,options)")
            browser.click("#analyze"); browser.wait("!document.getElementById('cancel').disabled"); browser.click("#cancel")
            browser.wait("document.getElementById('analyze').disabled===false && document.getElementById('status').textContent.includes('Analysis stopped')")
            check("Stop cancels a simulated stalled request without completed stages", browser.evaluate("document.getElementById('workflow-status').textContent==='Stopped'"))
            browser.evaluate("window.fetch=window.savedFetch")
            check("No uncaught browser errors", not browser.errors)
            check("Only loopback application requests were observed", all(u.startswith((f"http://127.0.0.1:{port}/", 'data:', 'about:')) for u in browser.requests))
            report.update(status="passed", browser_errors=browser.errors, actual_analysis_requests=len([u for u in browser.requests if u.endswith('/api/modelmatch/analyze')]), screenshots=sorted(p.name for p in OUTPUT.glob('*.png')))
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        if browser:
            try:
                browser.screenshot("failure.png", True)
                report["page_text"] = browser.evaluate("document.body.innerText").splitlines()[-40:]
            except Exception:
                pass
    finally:
        if browser:
            browser.socket.close()
        for process in (browser_process, server):
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (OUTPUT / "browser-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
