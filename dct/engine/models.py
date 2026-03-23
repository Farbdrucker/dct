"""Pydantic models for the DCT API JSON contract."""

from __future__ import annotations

from typing import Any, Literal

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
    kind: str = "transition"  # "transition" | "source" | "sink"
    description: str | None = None
    config_fields: list[ConfigField]
    input_ports: list[Port]
    output_port: Port | None = None  # None for sinks


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
    executor: Literal["sequential", "parallel", "dask"] = "sequential"


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
    error: "ExecutionError | None" = None  # set if this node failed
    skipped: bool = False  # True if bypassed due to upstream error


class ExecutionError(BaseModel):
    node_id: str
    node_type: str
    exception_type: str
    message: str
    traceback: str


class RowResult(BaseModel):
    """Per-row result for batched (source-driven) execution."""

    row_index: int
    success: bool
    result: ExecutionResult | None = None  # last non-sink result if success
    error: ExecutionError | None = None  # first originating error if failure
    trace: list[ExecutionResult] = []  # per-row trace (populated for failed rows only)
    source_values: dict[str, Any] = {}  # source_node_id → yielded value (for replay)


class FailureReport(BaseModel):
    """Summary of failed rows; ``failed_items`` carry source values for re-execution."""

    total_rows: int
    succeeded_rows: int
    failed_rows: int
    failed_items: list[RowResult]


class ReplayPayload(BaseModel):
    """Re-execute a DAG for only the rows that failed in a previous run.

    ``failed_items`` comes directly from ``FailureReport.failed_items``.
    The source nodes in ``nodes`` are ignored during replay — each item's
    ``source_values`` is fed directly into the DAG, bypassing source iteration.
    """

    nodes: list[DagNode]
    edges: list[DagEdge]
    capture_logs: bool = False
    executor: Literal["sequential", "parallel"] = "sequential"
    failed_items: list[RowResult]


class ExecuteResponse(BaseModel):
    success: bool
    result: ExecutionResult | None = None  # single-pass result
    results: list[ExecutionResult] = []  # successful row finals (source-driven)
    execution_trace: list[ExecutionResult] = []  # all nodes across all rows
    error: ExecutionError | None = None
    # If validation failed before execution
    valid: bool = True
    errors: list[ValidationError] = []
    console_output: list[str] = []  # ANSI-encoded lines
    # Per-row tracking (populated for batched execution)
    row_results: list[RowResult] = []
    failure_report: FailureReport | None = None
