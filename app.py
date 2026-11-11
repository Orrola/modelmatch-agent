"""ModelMatch AI FastAPI entry point and compatibility SSE endpoint."""

import json
import os
import uuid
from pathlib import Path
from typing import Literal

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

import uvicorn
from agents import set_tracing_disabled
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse

from modelmatch_web import WebInput, install_modelmatch

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env", override=False)
set_tracing_disabled(True)

app = FastAPI(title="ModelMatch AI", version="0.1.0")
modelmatch_routes = install_modelmatch(app)
analyze_endpoint = next(route.endpoint for route in modelmatch_routes.routes if route.path == "/api/modelmatch/analyze")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "static/modelmatch.html", headers={"Cache-Control": "no-cache"})


@app.get("/run")
async def run(question: str = Query(min_length=3, max_length=6000), mode: Literal["modelmatch"] = "modelmatch"):
    """Retain ModelMatch GET SSE compatibility; use POST analyze for normal UI use."""
    source = await analyze_endpoint(WebInput(question=question, approve_live=True))
    run_id = str(uuid.uuid4())

    async def events():
        try:
            async for frame in source.body_iterator:
                frame = frame.decode() if isinstance(frame, bytes) else frame
                if frame.startswith("data: "):
                    event = json.loads(frame[6:].strip())
                    if event["type"] == "start":
                        event["run_id"] = run_id
                    if event["type"] == "done":
                        event["markdown"] = event["result"]["markdown"]
                    frame = "data: " + json.dumps(event, default=str) + "\n\n"
                yield frame
        finally:
            await source.body_iterator.aclose()

    return StreamingResponse(events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
