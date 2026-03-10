"""GET /api/nodes/schema"""
from __future__ import annotations

from fastapi import APIRouter, Request

from dct.api.models import SchemaResponse

router = APIRouter()


@router.get("/api/nodes/schema", response_model=SchemaResponse)
async def get_schema(request: Request) -> SchemaResponse:
    cache = request.app.state.schema_cache
    schemas, version, _, _ = cache.get()
    return SchemaResponse(schema_version=version, nodes=schemas)
