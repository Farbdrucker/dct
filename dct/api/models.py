"""Pydantic models for the DCT API JSON contract."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Schema (GET /api/nodes/schema)
# ---------------------------------------------------------------------------


class ConfigField(BaseModel):
    name: str
    type: str  # human-readable, e.g. "int | float"
    type_set: list[str]
    default: Any | None = None
    required: bool
    json_schema: dict[str, Any]


class Port(BaseModel):
    name: str
    type: str  # human-readable
    type_set: list[str]


class NodeSchema(BaseModel):
    class_name: str
    kind: str = "transition"  # "transition" | "source"
    description: str | None = None
    config_fields: list[ConfigField]
    input_ports: list[Port]
    output_port: Port


class SchemaResponse(BaseModel):
    schema_version: str
    nodes: list[NodeSchema]


# ---------------------------------------------------------------------------
# DAG execution (POST /api/dag/execute, POST /api/dag/validate)
# ---------------------------------------------------------------------------


class NodeData(BaseModel):
    config: dict[str, Any] = {}
    constants: dict[str, Any] = {}


class DagNode(BaseModel):
    id: str
    type: str
    data: NodeData


class DagEdge(BaseModel):
    id: str
    source: str
    source_handle: str
    target: str
    target_handle: str


class DagPayload(BaseModel):
    nodes: list[DagNode]
    edges: list[DagEdge]
    capture_logs: bool = False
    parallel: bool = False


# ---------------------------------------------------------------------------
# Validation response
# ---------------------------------------------------------------------------


class ValidationError(BaseModel):
    type: str  # "type_mismatch" | "missing_input" | "cycle_detected" | "unknown_node"
    edge_id: str | None = None
    node_id: str | None = None
    source_node: str | None = None
    target_node: str | None = None
    target_handle: str | None = None
    source_type_set: list[str] | None = None
    target_type_set: list[str] | None = None
    message: str


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidationError] = []


# ---------------------------------------------------------------------------
# Execution response
# ---------------------------------------------------------------------------


class ExecutionResult(BaseModel):
    node_id: str
    node_type: str
    value: Any
    value_type: str


class ExecutionError(BaseModel):
    node_id: str
    node_type: str
    exception_type: str
    message: str
    traceback: str


class ExecuteResponse(BaseModel):
    success: bool
    result: ExecutionResult | None = None          # single-pass result
    results: list[ExecutionResult] = []            # batched results (source-driven)
    execution_trace: list[ExecutionResult] = []
    error: ExecutionError | None = None
    # If validation failed before execution
    valid: bool = True
    errors: list[ValidationError] = []
    console_output: list[str] = []                 # ANSI-encoded lines
