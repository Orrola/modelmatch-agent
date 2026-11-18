"""Isolated local Chrome fixture review; never execute a provider or production workflow."""

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

# Use bundled provider metadata even when this offline tool is invoked directly.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from scripts import ui_smoke
from tests.test_recommendation_ui import presentation_fixtures

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache/phase6c-responsive"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ui_smoke.OUTPUT = OUTPUT
    fixtures = presentation_fixtures()
    (OUTPUT / "synthetic-renderings.json").write_text(json.dumps(fixtures, indent=2))
    chrome = shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    report = {"mode": "synthetic_fixture_browser_review_not_live_workflow", "provider_calls": 0, "checks": [], "screenshots": []}
    server = process = browser = None
    port, debug = free_port(), free_port()
    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)
    try:
        with tempfile.TemporaryDirectory(prefix="chrome-fixture-", dir=OUTPUT, ignore_cleanup_errors=True) as profile, (OUTPUT / "browser-server.log").open("w") as log:
            env = {**os.environ, "MODELMATCH_OFFLINE": "1", "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
            with httpx.Client(trust_env=False, timeout=2) as client:
                for _ in range(100):
                    try:
                        if client.get(f"http://127.0.0.1:{port}/healthz").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Local offline server did not start.")
                process = subprocess.Popen([chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                    "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-default-apps",
                    "--metrics-recording-only", "--no-proxy-server", "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
                    f"--remote-debugging-port={debug}", f"--user-data-dir={profile}", "about:blank"], stdout=log, stderr=log)
                for _ in range(100):
                    try:
                        target = next(t for t in client.get(f"http://127.0.0.1:{debug}/json/list").json() if t.get("type") == "page")
                        break
                    except (httpx.TransportError, ValueError, StopIteration):
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Isolated Chrome did not start.")
            browser = ui_smoke.Browser(target["webSocketDebuggerUrl"])
            for method in ("Page.enable", "Runtime.enable", "Network.enable"):
                browser.call(method)
            browser.call("Network.setBlockedURLs", {"urls": ["https://*"]})
            browser.viewport(1440, 1050)
            browser.call("Page.navigate", {"url": f"http://127.0.0.1:{port}/modelmatch"})
            browser.wait("document.getElementById('mode').textContent.includes('Synthetic')")
            browser.evaluate("window.fixtureBundle=" + json.dumps(fixtures))
            browser.evaluate("""window.originalFetch=window.fetch.bind(window);window.fixtureName='three';window.recalcCount=0;
              window.fetch=(url,options)=>{
                if(String(url)==='/api/modelmatch/analyze'){
                  const result=window.fixtureBundle[window.fixtureName];
                  return Promise.resolve(new Response('data: '+JSON.stringify({type:'start',run_id:'synthetic-render-only'})+'\\n\\ndata: '+JSON.stringify({type:'done',analysis_id:'fixture-rendering-only',result})+'\\n\\n',{headers:{'Content-Type':'text/event-stream'}}));
                }
                if(String(url)==='/api/modelmatch/recalculate'){
                  window.recalcCount++; const result=JSON.parse(options.body).user_alpha===null ? window.fixtureBundle.reset : window.fixtureBundle.adjusted;
                  return Promise.resolve(new Response(JSON.stringify({decision:result.decision,selection:result.selection,selector:result.selector,model_identity:result.model_identity,writer_alpha:.5,writer_explanation_stale:true,research_rerun:false})));
                }
                return window.originalFetch(url,options);
              };""")
            for name, count in (("three", 3), ("two", 2), ("one", 1), ("zero", 0), ("failure", 0), ("states", 2), ("policy", 0), ("partial", 3)):
                browser.evaluate("window.fixtureName=" + json.dumps(name))
                browser.fill("#question", "Synthetic financial fixture rendering only.")
                browser.click("#analyze")
                browser.wait("!document.getElementById('analyze').disabled && !document.getElementById('results').hidden")
                check(f"{name}: three honest slots, {count} selected", browser.evaluate(f"document.querySelectorAll('#ranking>article').length===3 && Number(document.getElementById('ranking').dataset.count)==={count}"))
                check(f"{name}: evaluation coverage title and three primary metrics", browser.evaluate("document.getElementById('recommendation-coverage').querySelector('h2').textContent==='Model Evaluation Coverage' && document.querySelectorAll('.coverage-primary>div').length===3 && !document.querySelector('.coverage-secondary').open"))
                check(f"{name}: no empty family expander", browser.evaluate("Array.from(document.querySelectorAll('.family-configurations summary')).every(e=>!e.textContent.includes('(0)'))"))
                check(f"{name}: no expanded empty status panels", browser.evaluate("Array.from(document.querySelectorAll('.empty-alternative-buckets')).every(e=>!e.open)"))
                check(f"{name}: generic caveat is not repeated on cards", browser.evaluate("document.querySelectorAll('#ranking .rationale').length===0"))
                if name == "states":
                    check("Hard failures are distinct from missing evidence in primary metrics", browser.evaluate("Array.from(document.querySelectorAll('.coverage-primary dd')).map(e=>e.textContent).join(',')==='18,4,12' && document.querySelector('.coverage-other').textContent.includes('2 additional')"))
                if name == "policy":
                    check("Policy-only blocking is not reported as missing G/U", browser.evaluate("Array.from(document.querySelectorAll('.coverage-primary dd')).map(e=>e.textContent).join(',')==='6,0,0' && document.querySelector('.coverage-other').textContent.includes('6 additional')"))
                if name == "partial":
                    check("Partial-proxy caveat appears near heading only", browser.evaluate("document.getElementById('ranking-subtitle').textContent.includes('partial proxy') && !document.getElementById('ranking').textContent.includes('partial proxy')"))
                check(f"{name}: desktop three equal-width columns", browser.evaluate("(()=>{const cards=Array.from(document.querySelectorAll('#ranking>article')).map(e=>e.getBoundingClientRect());return cards.length===3 && Math.abs(cards[0].top-cards[2].top)<1 && Math.abs(cards[0].width-cards[2].width)<1;})()"))
                check(f"{name}: fixed recommendation role order", browser.evaluate("Array.from(document.querySelectorAll('#ranking>article')).map(e=>e.dataset.role).join(',')==='best_overall,lower_cost_alternative,different_family'"))
                check(f"{name}: readable alternative headings", browser.evaluate("document.getElementById('potential-alternatives').textContent.includes('Task-specific score available') || !document.getElementById('potential-alternatives').textContent.includes('Backend order:')"))
                browser.screenshot(f"desktop-{name}.png", True); report["screenshots"].append(f"desktop-{name}.png")
            browser.evaluate("window.fixtureName='three'")
            browser.click("#analyze"); browser.wait("document.getElementById('ranking').dataset.count==='3' && !document.getElementById('analyze').disabled")
            browser.click(".family-configurations summary")
            check("Explicit other configuration expands", browser.evaluate("document.querySelector('.family-configurations').open && document.querySelector('.configuration-row').textContent.includes('(b)')"))
            browser.click("#ranking>article:nth-child(2) .model-title")
            check("No empty family expander in model drawer", browser.evaluate("document.getElementById('model-drawer').open && document.querySelectorAll('#drawer-content .family-configurations').length===0"))
            browser.click("#close-drawer")
            browser.fill("#alpha", ".7")
            browser.wait("document.getElementById('alpha-value').textContent==='70%' && document.getElementById('weight-status').textContent.startsWith('Updated')")
            check("Recalculation marks narrative stale", browser.evaluate("window.recalcCount===1 && document.getElementById('writer-stale').textContent.includes('has not been regenerated')"))
            check("Recalculation refreshes canonical role IDs", browser.evaluate("Array.from(document.querySelectorAll('#ranking>article')).map(e=>e.dataset.modelId).join(',')==='a,d,c'"))
            browser.screenshot("desktop-adjusted.png", True); report["screenshots"].append("desktop-adjusted.png")
            browser.click("#reset")
            browser.wait("document.getElementById('alpha-value').textContent==='60%' && document.getElementById('weight-status').textContent.startsWith('Updated')")
            check("Reset uses the existing engine fallback default", browser.evaluate("window.recalcCount===2 && document.getElementById('ranking').dataset.count==='3'"))
            for width, columns in ((1024, 3), (834, 2), (390, 1)):
                browser.viewport(width, 1000)
                check(f"Width {width}: expected {columns} grid columns", browser.evaluate(f"getComputedStyle(document.getElementById('ranking')).gridTemplateColumns.split(' ').length==={columns}"))
                check(f"Width {width}: card content does not overflow", browser.evaluate("Array.from(document.querySelectorAll('#ranking>article')).every(e=>e.scrollWidth<=e.clientWidth+1)"))
                check(f"Width {width}: no page overflow", browser.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
                browser.screenshot(f"comparison-{width}.png", True); report["screenshots"].append(f"comparison-{width}.png")
            browser.click(".model-card .model-title")
            check("Mobile detail drawer retains evidence", browser.evaluate("document.getElementById('model-drawer').open && document.getElementById('drawer-content').textContent.includes('Synthetic fixture')"))
            browser.screenshot("mobile-details.png"); report["screenshots"].append("mobile-details.png")
            check("No application analysis request reached HTTP", not any('/api/modelmatch/analyze' in url for url in browser.requests))
            check("No observed JavaScript exceptions", not browser.errors)
            report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error)[:250])
    finally:
        if browser:
            browser.socket.close()
        for child in (process, server):
            if child:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait()
        (OUTPUT / "browser-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
