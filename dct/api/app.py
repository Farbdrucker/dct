"""FastAPI application factory."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dct.api.routes import dag, nodes
from dct.api.watcher import SchemaCache, watch_transitions


def create_app(transitions_path: Path, source_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cache = SchemaCache()
        cache.refresh(transitions_path, source_path)
        app.state.schema_cache = cache

        watcher_task = asyncio.create_task(
            watch_transitions(transitions_path, source_path, cache)
        )
        yield
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="DCT API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(nodes.router)
    app.include_router(dag.router)

    # Serve bundled frontend (production)
    _static = Path(__file__).parent.parent / "static"
    if (_static / "index.html").exists():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            return FileResponse(_static / "index.html")

    return app
