"""DAG validation and execution engine."""
from __future__ import annotations

import traceback
from collections import deque
from typing import Any, Callable

from dct.api.models import (
    DagEdge,
    DagNode,
    DagPayload,
    ExecuteResponse,
    ExecutionError,
    ExecutionResult,
    NodeSchema,
    ValidateResponse,
    ValidationError,
)
from dct.src.instance_cache import InstanceCache
from dct.src.log_capture import streaming_capture
from dct.src.type_compat import is_compatible

ClassRegistry = dict[str, type]


# ---------------------------------------------------------------------------
# Internal graph helpers
# ---------------------------------------------------------------------------


def _build_graph(payload: DagPayload) -> tuple[
    dict[str, set[str]],           # adj: node_id -> set of downstream node_ids
    dict[str, int],                 # in_degree
    dict[str, dict[str, DagEdge]], # incoming: target_node_id -> {port: edge}
]:
    adj: dict[str, set[str]] = {n.id: set() for n in payload.nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in payload.nodes}
    incoming: dict[str, dict[str, DagEdge]] = {n.id: {} for n in payload.nodes}

    for edge in payload.edges:
        adj.setdefault(edge.source, set()).add(edge.target)
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1
        incoming.setdefault(edge.target, {})[edge.target_handle] = edge

    return adj, in_degree, incoming


def _topo_sort(payload: DagPayload, in_degree: dict[str, int], adj: dict[str, set[str]]) -> list[str]:
    temp_in = dict(in_degree)
    queue = deque(nid for nid, d in temp_in.items() if d == 0)
    order: list[str] = []
    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbour in adj.get(nid, set()):
            temp_in[neighbour] -= 1
            if temp_in[neighbour] == 0:
                queue.append(neighbour)
    return order


# ---------------------------------------------------------------------------
# Single-step execution of one non-source node
# ---------------------------------------------------------------------------


def _run_node(
    nid: str,
    node: DagNode,
    class_registry: ClassRegistry,
    value_store: dict[str, Any],
    incoming: dict[str, dict[str, DagEdge]],
    instance_cache: InstanceCache | None = None,
) -> tuple[Any, ExecutionError | None]:
    cls = class_registry[node.type]
    try:
        instance = (
            instance_cache.get_or_create(node.type, cls, node.data.config)
            if instance_cache is not None
            else cls(**node.data.config)
        )
    except Exception as exc:
        return None, ExecutionError(
            node_id=nid, node_type=node.type,
            exception_type=type(exc).__name__, message=str(exc),
            traceback=traceback.format_exc(),
        )

    kwargs: dict[str, Any] = dict(node.data.constants)
    for port_name, edge in incoming.get(nid, {}).items():
        kwargs[port_name] = value_store[edge.source]

    try:
        result_val = instance(**kwargs)
    except Exception as exc:
        return None, ExecutionError(
            node_id=nid, node_type=node.type,
            exception_type=type(exc).__name__, message=str(exc),
            traceback=traceback.format_exc(),
        )

    return result_val, None


# ---------------------------------------------------------------------------
# Per-row execution helper (used by both sequential and parallel paths)
# ---------------------------------------------------------------------------


def _execute_row(
    source_values: dict[str, Any],
    transition_order: list[str],
    node_map: dict[str, DagNode],
    class_registry: ClassRegistry,
    incoming: dict[str, dict[str, DagEdge]],
    instance_cache: InstanceCache | None = None,
) -> tuple[list[ExecutionResult], ExecutionError | None]:
    """Execute one source-yielded row through all transition nodes."""
    value_store = dict(source_values)
    trace: list[ExecutionResult] = []
    for nid in transition_order:
        node = node_map[nid]
        val, err = _run_node(nid, node, class_registry, value_store, incoming, instance_cache)
        if err:
            return trace, err
        value_store[nid] = val
        trace.append(ExecutionResult(
            node_id=nid, node_type=node.type,
            value=val, value_type=type(val).__name__,
        ))
    return trace, None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(
    payload: DagPayload,
    class_registry: ClassRegistry,
    node_schemas: dict[str, NodeSchema],
) -> ValidateResponse:
    errors: list[ValidationError] = []
    node_map = {n.id: n for n in payload.nodes}

    # 1. Unknown node types
    for node in payload.nodes:
        if node.type not in node_schemas:
            errors.append(ValidationError(
                type="unknown_node", node_id=node.id,
                message=f"Unknown node type '{node.type}'",
            ))

    adj, in_degree, incoming = _build_graph(payload)

    # 2. Type-mismatch per edge
    for edge in payload.edges:
        src_node = node_map.get(edge.source)
        tgt_node = node_map.get(edge.target)
        if src_node is None or tgt_node is None:
            continue
        src_schema = node_schemas.get(src_node.type)
        tgt_schema = node_schemas.get(tgt_node.type)
        if src_schema is None or tgt_schema is None:
            continue

        src_type_set = frozenset(src_schema.output_port.type_set)
        tgt_port = next((p for p in tgt_schema.input_ports if p.name == edge.target_handle), None)
        if tgt_port is None:
            errors.append(ValidationError(
                type="unknown_port", edge_id=edge.id,
                source_node=edge.source, target_node=edge.target,
                target_handle=edge.target_handle,
                message=f"Node '{tgt_node.type}' has no input port '{edge.target_handle}'",
            ))
            continue

        tgt_type_set = frozenset(tgt_port.type_set)
        if not is_compatible(src_type_set, tgt_type_set):
            errors.append(ValidationError(
                type="type_mismatch", edge_id=edge.id,
                source_node=edge.source, target_node=edge.target,
                target_handle=edge.target_handle,
                source_type_set=sorted(src_type_set),
                target_type_set=sorted(tgt_type_set),
                message=(
                    f"Type mismatch: source outputs {sorted(src_type_set)} "
                    f"but target port '{edge.target_handle}' expects {sorted(tgt_type_set)}"
                ),
            ))

    # 3. Missing inputs — sources have no input_ports so they're always fine here
    for node in payload.nodes:
        schema = node_schemas.get(node.type)
        if schema is None:
            continue
        node_incoming = incoming.get(node.id, {})
        for port in schema.input_ports:
            if port.name not in node_incoming and port.name not in node.data.constants:
                errors.append(ValidationError(
                    type="missing_input", node_id=node.id,
                    target_handle=port.name,
                    message=f"Node '{node.id}' (type '{node.type}') is missing input for port '{port.name}'",
                ))

    # 4. Cycle detection via Kahn's
    temp_in = dict(in_degree)
    queue = deque(n for n, d in temp_in.items() if d == 0)
    visited = 0
    while queue:
        nid = queue.popleft()
        visited += 1
        for neighbour in adj.get(nid, set()):
            temp_in[neighbour] -= 1
            if temp_in[neighbour] == 0:
                queue.append(neighbour)

    if visited < len(payload.nodes):
        errors.append(ValidationError(type="cycle_detected", message="The DAG contains a cycle."))

    return ValidateResponse(valid=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _execute_inner(
    payload: DagPayload,
    class_registry: ClassRegistry,
    node_schemas: dict[str, NodeSchema],
    instance_cache: InstanceCache | None = None,
) -> ExecuteResponse:
    node_map = {n.id: n for n in payload.nodes}
    adj, in_degree, incoming = _build_graph(payload)
    topo_order = _topo_sort(payload, in_degree, adj)

    # Separate source nodes from transition nodes
    source_ids = {
        nid for nid in topo_order
        if node_schemas[node_map[nid].type].kind == "source"
    }
    transition_order = [nid for nid in topo_order if nid not in source_ids]

    # -----------------------------------------------------------------------
    # Single-pass (no sources)
    # -----------------------------------------------------------------------
    if not source_ids:
        value_store: dict[str, Any] = {}
        trace: list[ExecutionResult] = []

        for nid in topo_order:
            node = node_map[nid]
            val, err = _run_node(nid, node, class_registry, value_store, incoming, instance_cache)
            if err:
                return ExecuteResponse(success=False, execution_trace=trace, error=err)
            value_store[nid] = val
            trace.append(ExecutionResult(
                node_id=nid, node_type=node.type,
                value=val, value_type=type(val).__name__,
            ))

        last = trace[-1] if trace else None
        return ExecuteResponse(success=True, result=last, execution_trace=trace)

    # -----------------------------------------------------------------------
    # Batched pass (sources present)
    # Instantiate all source nodes and zip their iterators.
    # -----------------------------------------------------------------------
    source_instances: dict[str, Any] = {}
    for src_id in source_ids:
        src_node = node_map[src_id]
        cls = class_registry[src_node.type]
        try:
            source_instances[src_id] = cls(**src_node.data.config)
        except Exception as exc:
            return ExecuteResponse(
                success=False,
                error=ExecutionError(
                    node_id=src_id, node_type=src_node.type,
                    exception_type=type(exc).__name__, message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )

    batch_results: list[ExecutionResult] = []
    full_trace: list[ExecutionResult] = []

    source_id_list = list(source_ids)

    if payload.parallel:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor() as pool:
            # Submit futures lazily as the source yields — row dicts are not
            # accumulated; each is handed off to the thread pool immediately.
            futures = [
                pool.submit(
                    _execute_row,
                    {sid: val for sid, val in zip(source_id_list, values)},
                    transition_order, node_map, class_registry, incoming, instance_cache,
                )
                for values in zip(*[source_instances[sid] for sid in source_id_list])
            ]

        # Collect in submission order → deterministic trace even under concurrency
        for fut in futures:
            step_trace, err = fut.result()
            if err:
                return ExecuteResponse(success=False, execution_trace=full_trace, error=err)
            full_trace.extend(step_trace)
            if step_trace:
                batch_results.append(step_trace[-1])

    else:
        # Sequential path (original behavior)
        for values in zip(*[source_instances[sid] for sid in source_id_list]):
            value_store = {sid: val for sid, val in zip(source_id_list, values)}

            step_trace: list[ExecutionResult] = []
            error_resp = None
            for nid in transition_order:
                node = node_map[nid]
                val, err = _run_node(nid, node, class_registry, value_store, incoming, instance_cache)
                if err:
                    error_resp = ExecuteResponse(
                        success=False, execution_trace=full_trace + step_trace, error=err,
                    )
                    break
                value_store[nid] = val
                step_trace.append(ExecutionResult(
                    node_id=nid, node_type=node.type,
                    value=val, value_type=type(val).__name__,
                ))

            if error_resp:
                return error_resp

            full_trace.extend(step_trace)
            if step_trace:
                batch_results.append(step_trace[-1])

    return ExecuteResponse(
        success=True,
        results=batch_results,
        execution_trace=full_trace,
    )


def execute(
    payload: DagPayload,
    class_registry: ClassRegistry,
    node_schemas: dict[str, NodeSchema],
    log_callback: Callable[[str], None] | None = None,
    instance_cache: InstanceCache | None = None,
) -> ExecuteResponse:
    validation = validate(payload, class_registry, node_schemas)
    if not validation.valid:
        return ExecuteResponse(success=False, valid=False, errors=validation.errors)

    collected: list[str] = []
    cb = log_callback if log_callback is not None else collected.append

    if payload.capture_logs or log_callback is not None:
        with streaming_capture(cb):
            response = _execute_inner(payload, class_registry, node_schemas, instance_cache)
    else:
        response = _execute_inner(payload, class_registry, node_schemas, instance_cache)

    if log_callback is None:
        response.console_output = collected

    return response
