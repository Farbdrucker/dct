"""POST /api/dag/validate and POST /api/dag/execute"""
from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from dct.api.models import DagPayload, ExecuteResponse, ValidateResponse
from dct.src.executor import execute, validate

router = APIRouter()


@router.post("/api/dag/validate", response_model=ValidateResponse)
async def validate_dag(payload: DagPayload, request: Request) -> ValidateResponse:
    cache = request.app.state.schema_cache
    schemas, _, class_registry, _ = cache.get()
    schema_map = {s.class_name: s for s in schemas}
    return validate(payload, class_registry, schema_map)


@router.post("/api/dag/execute", response_model=ExecuteResponse)
async def execute_dag(payload: DagPayload, request: Request) -> ExecuteResponse:
    cache = request.app.state.schema_cache
    schemas, _, class_registry, instance_cache = cache.get()
    schema_map = {s.class_name: s for s in schemas}
    return execute(payload, class_registry, schema_map, instance_cache=instance_cache)


@router.post("/api/dag/execute/stream")
async def execute_dag_stream(payload: DagPayload, request: Request) -> StreamingResponse:
    cache = request.app.state.schema_cache
    schemas, _, class_registry, instance_cache = cache.get()
    schema_map = {s.class_name: s for s in schemas}
    log_queue: queue.SimpleQueue = queue.SimpleQueue()

    def log_callback(line: str) -> None:
        log_queue.put(("log", line))

    def run_execution() -> None:
        try:
            result = execute(payload, class_registry, schema_map, log_callback=log_callback, instance_cache=instance_cache)
            log_queue.put(("result", result))
        except Exception as exc:
            log_queue.put(("error", str(exc)))
        finally:
            log_queue.put(None)  # sentinel

    async def event_generator():
        execution_task = asyncio.create_task(asyncio.to_thread(run_execution))
        try:
            while True:
                try:
                    item = log_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue
                if item is None:
                    yield "data: " + json.dumps({"type": "done"}) + "\n\n"
                    break
                kind, value = item
                if kind == "log":
                    yield "data: " + json.dumps({"type": "log", "line": value}) + "\n\n"
                elif kind == "result":
                    yield "data: " + json.dumps({"type": "result", "payload": value.model_dump(mode="json")}) + "\n\n"
                elif kind == "error":
                    yield "data: " + json.dumps({"type": "error", "message": value}) + "\n\n"
                    yield "data: " + json.dumps({"type": "done"}) + "\n\n"
                    break
        finally:
            await execution_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
