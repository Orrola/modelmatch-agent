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
    report = {"mode": "synthetic_fixture_browser_review_not_live_workflow", "provider_calls": 0, "checks": [], "screenshots": [], "measurements": {}}
    server = process = browser = None
    port, debug = free_port(), free_port()
    def check(name, condition):
        report["checks"].append({"name": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)
    def capture(name):
        report["measurements"][name] = browser.evaluate("""(()=>{
          const card=document.querySelector('#ranking>article, #ranking>.recommendation-empty').getBoundingClientRect();
          const alternatives=document.getElementById('potential-alternatives').getBoundingClientRect();
          return {viewport:innerWidth,card:{x:card.x,width:card.width,height:card.height},alternatives:{x:alternatives.x,width:alternatives.width}};
        })()""")
        browser.screenshot(name, True)
        report["screenshots"].append(name)
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
            for name, count in (("three", 1), ("two", 1), ("one", 1), ("zero", 0), ("failure", 0), ("states", 1), ("policy", 0), ("partial", 1)):
                browser.evaluate("window.fixtureName=" + json.dumps(name))
                browser.fill("#question", "Synthetic financial fixture rendering only.")
                browser.click("#analyze")
                browser.wait("!document.getElementById('analyze').disabled && !document.getElementById('results').hidden")
                check(f"{name}: one Best Overall card or compact message", browser.evaluate(
                    f"document.querySelectorAll('#ranking>*').length===1 && "
                    f"document.querySelectorAll('#ranking>article[data-role=best_overall]').length==={count} && "
                    f"document.querySelectorAll('#ranking>.recommendation-empty').length==={1 - count}"))
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
                check(f"{name}: bounded recommendation with alternatives immediately below", browser.evaluate(
                    "Math.abs(document.querySelector('.best-overall').getBoundingClientRect().width-document.getElementById('potential-alternatives').getBoundingClientRect().width)<1 && "
                    "document.querySelector('.best-overall').nextElementSibling.id==='potential-alternatives'"))
                check(f"{name}: readable alternative headings", browser.evaluate("document.getElementById('potential-alternatives').textContent.includes('Task-specific score available') || !document.getElementById('potential-alternatives').textContent.includes('Backend order:')"))
                capture(f"desktop-{name}.png")
            browser.evaluate("window.fixtureName='three'")
            browser.click("#analyze"); browser.wait("document.getElementById('ranking').dataset.count==='1' && !document.getElementById('analyze').disabled")
            check("Compact header keeps exact model and score", browser.evaluate("document.querySelector('#ranking .model-title').textContent===window.fixtureBundle.three.decision.candidates.a.name && document.querySelector('#ranking .score-number').textContent==='90'"))
            check("Evidence and eligibility remain visible", browser.evaluate("document.querySelector('#ranking .best-title').textContent.includes('Fully evaluable') && document.querySelector('#ranking .metric-strip').textContent.includes('Eligible')"))
            check("Operational highlights use observed values", browser.evaluate("document.querySelectorAll('#ranking .best-highlights>span').length===3 && document.querySelector('#ranking .best-highlights').textContent.includes('Mean TTFT: 1 s')"))
            browser.click("#ranking .card-evidence-details>summary")
            check("Evidence details expands exact IDs", browser.evaluate("document.querySelector('#ranking .card-evidence-details').open && document.querySelector('#ranking .card-evidence-details').textContent.includes('AA ID: a')"))
            browser.click("#ranking .family-configurations summary")
            check("Explicit other configuration expands", browser.evaluate("document.querySelector('.family-configurations').open && document.querySelector('.configuration-row').textContent.includes('(b)')"))
            browser.click("#raw-ranking .raw-ranking-group summary")
            browser.click("#raw-ranking .raw-ranking-row:nth-of-type(3) .model-title")
            check("No empty family expander in model drawer", browser.evaluate("document.getElementById('model-drawer').open && document.querySelector('#drawer-content .technical-panel pre').textContent.includes('\"aa_model_id\": \"c\"') && document.querySelectorAll('#drawer-content .family-configurations').length===0"))
            browser.click("#close-drawer")
            browser.click("#ranking .card-actions .text-button")
            check("Model detail action opens Best Overall", browser.evaluate("document.getElementById('model-drawer').open && document.querySelector('#drawer-content .technical-panel pre').textContent.includes('\"aa_model_id\": \"a\"')"))
            browser.click("#close-drawer")
            browser.click("#ranking input[type=checkbox]")
            check("Compare checkbox selects canonical candidate", browser.evaluate("document.querySelector('#ranking input[type=checkbox]').checked && !document.getElementById('compare-bar').hidden && document.getElementById('selected-count').textContent==='1'"))
            browser.click("#ranking input[type=checkbox]")
            browser.fill("#alpha", ".7")
            browser.wait("document.getElementById('alpha-value').textContent==='70%' && document.getElementById('weight-status').textContent.startsWith('Updated')")
            check("Recalculation marks narrative stale", browser.evaluate("window.recalcCount===1 && document.getElementById('writer-stale').textContent.includes('has not been regenerated')"))
            check("Recalculation updates Best Overall", browser.evaluate("document.querySelector('#ranking>article').dataset.modelId==='d'"))
            capture("desktop-adjusted.png")
            browser.click("#reset")
            browser.wait("document.getElementById('alpha-value').textContent==='60%' && document.getElementById('weight-status').textContent.startsWith('Updated')")
            check("Reset uses the existing engine fallback default", browser.evaluate("window.recalcCount===2 && document.querySelector('#ranking>article').dataset.modelId==='a'"))
            for width in (1024, 834, 390):
                browser.viewport(width, 1000)
                check(f"Width {width}: single card fits its section", browser.evaluate(
                    "document.querySelector('#ranking>article').getBoundingClientRect().width === "
                    "document.querySelector('.best-overall').getBoundingClientRect().width"))
                check(f"Width {width}: card content does not overflow", browser.evaluate("Array.from(document.querySelectorAll('#ranking>article')).every(e=>e.scrollWidth<=e.clientWidth+1)"))
                check(f"Width {width}: card aligns with alternatives", browser.evaluate("Math.abs(document.querySelector('#ranking>article').getBoundingClientRect().width-document.getElementById('potential-alternatives').getBoundingClientRect().width)<1"))
                check(f"Width {width}: no page overflow", browser.evaluate("document.documentElement.scrollWidth<=innerWidth+1"))
                capture(f"comparison-{width}.png")
            browser.click("#ranking .model-title")
            check("Mobile detail drawer retains evidence", browser.evaluate("document.getElementById('model-drawer').open && document.getElementById('drawer-content').textContent.includes('Synthetic fixture')"))
            browser.screenshot("mobile-details.png"); report["screenshots"].append("mobile-details.png")
            check("No application analysis or recalculation request reached HTTP", not any('/api/modelmatch/analyze' in url or '/api/modelmatch/recalculate' in url for url in browser.requests))
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
