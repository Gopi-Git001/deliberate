"""FastAPI app: REST + Server-Sent Events over the LangGraph manager/panel, plus the SPA.

    PYTHONPATH=src uvicorn manager_agent.ui.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from manager_agent.config import PROJECT_ROOT, get_settings
from manager_agent.panel.config import get_panel_settings
from manager_agent.ui.runner import RunRegistry, TooManyRuns

load_dotenv(PROJECT_ROOT / ".env")  # server-side only; keys never reach the browser

WEB_DIST = PROJECT_ROOT / "web" / "dist"
KEEPALIVE_SECONDS = 15

app = FastAPI(title="Multi-Agent Company UI", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Vite dev server
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
registry = RunRegistry()


class RunRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=2000)
    constraints: str = Field(default="", max_length=1000)
    demo: bool = False


@app.get("/api/health")
def health() -> dict:
    settings, panel = get_settings(), get_panel_settings()
    return {
        "status": "ok",
        "openai_key_configured": bool(settings.openai_api_key),
        "tavily_key_configured": bool(settings.tavily_api_key),
        "manager_model": settings.openai_model,
        "panel_model": panel.model,
        "panel_size": settings.panel_size,
        "active_runs": registry.active_count(),
    }


@app.post("/api/runs", status_code=201)
async def create_run(req: RunRequest) -> dict:
    if not req.demo and not get_settings().openai_api_key:
        raise HTTPException(
            400, "OPENAI_API_KEY is not configured on the server. Add it to .env, or enable demo mode."
        )
    try:
        run = registry.start(req.topic.strip(), req.constraints.strip(), req.demo)
    except TooManyRuns as exc:
        raise HTTPException(429, str(exc)) from exc
    return {"run_id": run.id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = registry.get(run_id)
    if not run:
        raise HTTPException(404, "Unknown run")
    return {"run_id": run.id, "topic": run.topic, "finished": run.finished, "reason": run.reason, "events": len(run.events)}


@app.post("/api/runs/{run_id}/stop", status_code=202)
def stop_run(run_id: str) -> dict:
    if not registry.get(run_id):
        raise HTTPException(404, "Unknown run")
    return {"stopping": registry.stop(run_id)}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, after: int = 0) -> StreamingResponse:
    run = registry.get(run_id)
    if not run:
        raise HTTPException(404, "Unknown run")
    last_id = request.headers.get("last-event-id")
    if last_id and last_id.isdigit():
        after = max(after, int(last_id))

    async def stream():
        events = registry.subscribe(run, after).__aiter__()
        yield "retry: 2000\n\n"
        while True:
            try:
                event = await asyncio.wait_for(events.__anext__(), KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            except StopAsyncIteration:
                return
            yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# --- SPA (React build) -------------------------------------------------------------------

@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    if not WEB_DIST.exists():
        raise HTTPException(
            404, "Frontend not built. Run `npm install && npm run build` in web/, or use the Vite dev server."
        )
    file = (WEB_DIST / path).resolve()
    if path and file.is_file() and file.is_relative_to(WEB_DIST.resolve()):
        return FileResponse(file)
    return FileResponse(WEB_DIST / "index.html")
