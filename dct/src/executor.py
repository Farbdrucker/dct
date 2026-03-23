"""DAG validation and execution engine."""

from __future__ import annotations

import logging
import time
import traceback
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)

from dct.api.models import (
    DagEdge,
    DagNode,
    DagPayload,
    ExecuteResponse,
    ExecutionError,
    ExecutionResult,
    FailureReport,
    NodeSchema,
    ReplayPayload,
    RowResult,
    ValidateResponse,
    ValidationError,
)
from dct.src.instance_cache import InstanceCache
from dct.src.log_capture import streaming_capture
from dct.src.result import Err, Ok
from dct.src.type_compat import is_compatible

ClassRegistry = dict[str, type]


# ---------------------------------------------------------------------------
# Internal graph helpers
# ---------------------------------------------------------------------------


def _build_graph(
    payload: DagPayload,
) -> tuple[
    dict[str, set[str]],  # adj: node_id -> set of downstream node_ids
    dict[str, int],  # in_degree
    dict[str, dict[str, DagEdge]],  # incoming: target_node_id -> {port: edge}
]:
    adj: dict[str, set[str]] = {n.id: set() for n in payload.nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in payload.nodes}
    incoming: dict[str, dict[str, DagEdge]] = {n.id: {} for n in payload.nodes}

    for edge in payload.edges:
        adj.setdefault(edge.source, set()).add(edge.target)
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1
        incoming.setdefault(edge.target, {})[edge.target_handle] = edge

    return adj, in_degree, incoming


def _topo_sort(
    payload: DagPayload, in_degree: dict[str, int], adj: dict[str, set[str]]
) -> list[str]:
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
# Result helpers
# ---------------------------------------------------------------------------


def _err_to_execution_error(err: Err) -> ExecutionError:
    return ExecutionError(
        node_id=err.node_id,
        node_type=err.node_type,
        exception_type=err.exception_type,
        message=err.message,
        traceback=err.traceback_str,
    )


def _build_failure_report(row_results: list[RowResult]) -> FailureReport:
    failed = [r for r in row_results if not r.success]
    return FailureReport(
        total_rows=len(row_results),
        succeeded_rows=len(row_results) - len(failed),
        failed_rows=len(failed),
        failed_items=failed,
    )


# ---------------------------------------------------------------------------
# Single-step execution of one non-source node
# ---------------------------------------------------------------------------


def _run_node(
    nid: str,
    node: DagNode,
    class_registry: ClassRegistry,
    value_store: dict[str, Ok[Any] | Err],
    incoming: dict[str, dict[str, DagEdge]],
    instance_cache: InstanceCache | None = None,
    node_instances: dict[str, Any] | None = None,
) -> Ok[Any] | Err:
    cls = class_registry[node.type]
    try:
        if node_instances is not None and nid in node_instances:
            instance = node_instances[nid]
        elif instance_cache is not None:
            instance = instance_cache.get_or_create(node.type, cls, node.data.config)
        else:
            instance = cls(**node.data.config)
    except Exception as exc:
        return Err(
            node_id=nid,
            node_type=node.type,
            exception_type=type(exc).__name__,
            message=str(exc),
            traceback_str=traceback.format_exc(),
        )

    # Check all upstream values — if any is Err, skip this node.
    for port_name, edge in incoming.get(nid, {}).items():
        upstream = value_store[edge.source]
        if isinstance(upstream, Err):
            return Err(
                node_id=nid,
                node_type=node.type,
                exception_type=upstream.exception_type,
                message=f"Skipped: upstream '{upstream.node_id}' ({upstream.node_type}) failed: {upstream.message}",
                traceback_str=upstream.traceback_str,
                is_skip=True,
            )

    kwargs: dict[str, Any] = dict(node.data.constants)
    for port_name, edge in incoming.get(nid, {}).items():
        kwargs[port_name] = value_store[edge.source].value  # type: ignore[union-attr]

    try:
        result_val = instance(**kwargs)
    except Exception as exc:
        return Err(
            node_id=nid,
            node_type=node.type,
            exception_type=type(exc).__name__,
            message=str(exc),
            traceback_str=traceback.format_exc(),
        )

    return Ok(result_val)


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
    node_instances: dict[str, Any] | None = None,
) -> tuple[list[ExecutionResult], ExecutionError | None]:
    """Execute one source-yielded row through all transition/sink nodes.

    Execution continues past failures: errored nodes are recorded in the trace
    and downstream nodes are skipped (not aborted).  Returns the first
    *originating* error (``is_skip=False``) alongside the full trace.
    """
    value_store: dict[str, Ok[Any] | Err] = {k: Ok(v) for k, v in source_values.items()}
    trace: list[ExecutionResult] = []
    first_error: ExecutionError | None = None

    for nid in transition_order:
        node = node_map[nid]
        node_result = _run_node(
            nid,
            node,
            class_registry,
            value_store,
            incoming,
            instance_cache,
            node_instances,
        )
        value_store[nid] = node_result

        if isinstance(node_result, Err):
            exec_err = _err_to_execution_error(node_result)
            if first_error is None and not node_result.is_skip:
                first_error = exec_err
            trace.append(
                ExecutionResult(
                    node_id=nid,
                    node_type=node.type,
                    value=None,
                    value_type="skipped" if node_result.is_skip else "error",
                    error=exec_err,
                    skipped=node_result.is_skip,
                )
            )
        else:
            trace.append(
                ExecutionResult(
                    node_id=nid,
                    node_type=node.type,
                    value=node_result.value,
                    value_type=type(node_result.value).__name__,
                )
            )

    return trace, first_error


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
            errors.append(
                ValidationError(
                    type="unknown_node",
                    node_id=node.id,
                    message=f"Unknown node type '{node.type}'",
                )
            )

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
        tgt_port = next(
            (p for p in tgt_schema.input_ports if p.name == edge.target_handle), None
        )
        if tgt_port is None:
            errors.append(
                ValidationError(
                    type="unknown_port",
                    edge_id=edge.id,
                    source_node=edge.source,
                    target_node=edge.target,
                    target_handle=edge.target_handle,
                    message=f"Node '{tgt_node.type}' has no input port '{edge.target_handle}'",
                )
            )
            continue

        tgt_type_set = frozenset(tgt_port.type_set)
        if not is_compatible(src_type_set, tgt_type_set):
            errors.append(
                ValidationError(
                    type="type_mismatch",
                    edge_id=edge.id,
                    source_node=edge.source,
                    target_node=edge.target,
                    target_handle=edge.target_handle,
                    source_type_set=sorted(src_type_set),
                    target_type_set=sorted(tgt_type_set),
                    message=(
                        f"Type mismatch: source outputs {sorted(src_type_set)} "
                        f"but target port '{edge.target_handle}' expects {sorted(tgt_type_set)}"
                    ),
                )
            )

    # 3. Missing inputs — sources have no input_ports so they're always fine here
    for node in payload.nodes:
        schema = node_schemas.get(node.type)
        if schema is None:
            continue
        node_incoming = incoming.get(node.id, {})
        for port in schema.input_ports:
            if port.name not in node_incoming and port.name not in node.data.constants:
                errors.append(
                    ValidationError(
                        type="missing_input",
                        node_id=node.id,
                        target_handle=port.name,
                        message=f"Node '{node.id}' (type '{node.type}') is missing input for port '{port.name}'",
                    )
                )

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
        errors.append(
            ValidationError(type="cycle_detected", message="The DAG contains a cycle.")
        )

    return ValidateResponse(valid=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _close_sinks(
    sink_ids: set[str],
    sink_instances: dict[str, Any],
    node_map: dict[str, Any],
    full_trace: list[ExecutionResult],
) -> ExecuteResponse | None:
    """Call close() on every sink in order, sequentially in the caller's thread.

    Returns an ExecuteResponse on failure, None on success.
    """
    for nid in sink_ids:
        node = node_map[nid]
        logger.info("%s closing", node.type)
        try:
            sink_instances[nid].close()
        except Exception as exc:
            return ExecuteResponse(
                success=False,
                execution_trace=full_trace,
                error=ExecutionError(
                    node_id=nid,
                    node_type=node.type,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )
        logger.info("%s closed", node.type)
    return None


def _execute_inner(
    payload: DagPayload,
    class_registry: ClassRegistry,
    node_schemas: dict[str, NodeSchema],
    instance_cache: InstanceCache | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> ExecuteResponse:
    node_map = {n.id: n for n in payload.nodes}
    adj, in_degree, incoming = _build_graph(payload)
    topo_order = _topo_sort(payload, in_degree, adj)

    # Separate source nodes from transition/sink nodes
    source_ids = {
        nid for nid in topo_order if node_schemas[node_map[nid].type].kind == "source"
    }
    sink_ids = {
        nid for nid in topo_order if node_schemas[node_map[nid].type].kind == "sink"
    }
    transition_order = [nid for nid in topo_order if nid not in source_ids]

    # Create one persistent instance per sink node (keyed by node-id, not type)
    sink_instances: dict[str, Any] = {}
    for nid in sink_ids:
        node = node_map[nid]
        cls = class_registry[node.type]
        try:
            sink_instances[nid] = cls(**node.data.config)
        except Exception as exc:
            return ExecuteResponse(
                success=False,
                error=ExecutionError(
                    node_id=nid,
                    node_type=node.type,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )

    # -----------------------------------------------------------------------
    # Single-pass (no sources)
    # -----------------------------------------------------------------------
    if not source_ids:
        value_store: dict[str, Ok[Any] | Err] = {}
        trace: list[ExecutionResult] = []
        first_error: ExecutionError | None = None

        for nid in topo_order:
            node = node_map[nid]
            node_result = _run_node(
                nid,
                node,
                class_registry,
                value_store,
                incoming,
                instance_cache,
                sink_instances,
            )
            value_store[nid] = node_result

            if isinstance(node_result, Err):
                exec_err = _err_to_execution_error(node_result)
                if first_error is None and not node_result.is_skip:
                    first_error = exec_err
                trace.append(
                    ExecutionResult(
                        node_id=nid,
                        node_type=node.type,
                        value=None,
                        value_type="skipped" if node_result.is_skip else "error",
                        error=exec_err,
                        skipped=node_result.is_skip,
                    )
                )
            else:
                trace.append(
                    ExecutionResult(
                        node_id=nid,
                        node_type=node.type,
                        value=node_result.value,
                        value_type=type(node_result.value).__name__,
                    )
                )
            if progress_callback:
                progress_callback({
                    "mode": "single",
                    "nodes_completed": len(trace),
                    "nodes_total": len(topo_order),
                    "node_id": nid,
                    "node_type": node.type,
                    "rows_completed": None,
                    "rows_per_sec": None,
                })

        if sink_ids:
            err_resp = _close_sinks(sink_ids, sink_instances, node_map, trace)
            if err_resp:
                return err_resp

        last = next(
            (
                r
                for r in reversed(trace)
                if r.node_id not in sink_ids and not r.skipped and r.error is None
            ),
            None,
        )
        return ExecuteResponse(
            success=first_error is None,
            result=last,
            execution_trace=trace,
            error=first_error,
        )

    # -----------------------------------------------------------------------
    # Batched pass (sources present)
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
                    node_id=src_id,
                    node_type=src_node.type,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )

    batch_results: list[ExecutionResult] = []
    full_trace: list[ExecutionResult] = []
    row_results: list[RowResult] = []

    source_id_list = list(source_ids)

    if payload.executor == "parallel":
        _batch_start = time.monotonic()
        with ThreadPoolExecutor() as pool:
            futures_with_meta: list[
                tuple[
                    dict[str, Any],
                    Future[tuple[list[ExecutionResult], ExecutionError | None]],
                ]
            ] = []
            for values in zip(*[source_instances[sid] for sid in source_id_list]):
                src_vals = {sid: val for sid, val in zip(source_id_list, values)}
                fut = pool.submit(
                    _execute_row,
                    src_vals,
                    transition_order,
                    node_map,
                    class_registry,
                    incoming,
                    instance_cache,
                    sink_instances,
                )
                futures_with_meta.append((src_vals, fut))

        for row_idx, (src_vals, fut) in enumerate(futures_with_meta):
            step_trace, err = fut.result()
            full_trace.extend(step_trace)
            if progress_callback:
                rows_done = row_idx + 1
                elapsed = time.monotonic() - _batch_start
                progress_callback({
                    "mode": "batched",
                    "nodes_completed": None,
                    "nodes_total": None,
                    "node_id": None,
                    "node_type": None,
                    "rows_completed": rows_done,
                    "rows_per_sec": round(rows_done / elapsed, 2) if elapsed > 0 else None,
                })
            if err is None:
                last = next(
                    (r for r in reversed(step_trace) if r.node_id not in sink_ids), None
                )
                if last:
                    batch_results.append(last)
                row_results.append(
                    RowResult(
                        row_index=row_idx,
                        success=True,
                        result=last,
                        source_values=src_vals,
                    )
                )
            else:
                row_results.append(
                    RowResult(
                        row_index=row_idx,
                        success=False,
                        error=err,
                        trace=step_trace,
                        source_values=src_vals,
                    )
                )

    else:
        # Sequential path
        _batch_start = time.monotonic()
        for row_idx, values in enumerate(
            zip(*[source_instances[sid] for sid in source_id_list])
        ):
            src_vals = {sid: val for sid, val in zip(source_id_list, values)}
            step_trace, err = _execute_row(
                src_vals,
                transition_order,
                node_map,
                class_registry,
                incoming,
                instance_cache,
                sink_instances,
            )
            full_trace.extend(step_trace)
            if progress_callback:
                rows_done = row_idx + 1
                elapsed = time.monotonic() - _batch_start
                progress_callback({
                    "mode": "batched",
                    "nodes_completed": None,
                    "nodes_total": None,
                    "node_id": None,
                    "node_type": None,
                    "rows_completed": rows_done,
                    "rows_per_sec": round(rows_done / elapsed, 2) if elapsed > 0 else None,
                })
            if err is None:
                last = next(
                    (r for r in reversed(step_trace) if r.node_id not in sink_ids), None
                )
                if last:
                    batch_results.append(last)
                row_results.append(
                    RowResult(
                        row_index=row_idx,
                        success=True,
                        result=last,
                        source_values=src_vals,
                    )
                )
            else:
                row_results.append(
                    RowResult(
                        row_index=row_idx,
                        success=False,
                        error=err,
                        trace=step_trace,
                        source_values=src_vals,
                    )
                )

    # close() is always called sequentially in the main thread after all rows
    if sink_ids:
        err_resp = _close_sinks(sink_ids, sink_instances, node_map, full_trace)
        if err_resp:
            return err_resp

    all_ok = all(r.success for r in row_results)
    return ExecuteResponse(
        success=all_ok,
        results=batch_results,
        execution_trace=full_trace,
        row_results=row_results,
        failure_report=_build_failure_report(row_results) if not all_ok else None,
    )


def replay_failed(
    payload: ReplayPayload,
    class_registry: ClassRegistry,
    node_schemas: dict[str, NodeSchema],
    log_callback: Callable[[str], None] | None = None,
    instance_cache: InstanceCache | None = None,
) -> ExecuteResponse:
    """Re-execute a DAG for only the rows that previously failed.

    Uses ``payload.failed_items[i].source_values`` as the initial value_store
    for each row, bypassing source node instantiation and iteration entirely.
    Returns a fresh ``ExecuteResponse`` (with a new ``failure_report`` if any
    rows fail again).
    """
    # Build a DagPayload-like structure for graph helpers
    dag = DagPayload(
        nodes=payload.nodes,
        edges=payload.edges,
        capture_logs=payload.capture_logs,
        executor=payload.executor,
    )

    node_map = {n.id: n for n in dag.nodes}
    adj, in_degree, incoming = _build_graph(dag)
    topo_order = _topo_sort(dag, in_degree, adj)

    source_ids = {
        nid for nid in topo_order if node_schemas[node_map[nid].type].kind == "source"
    }
    sink_ids = {
        nid for nid in topo_order if node_schemas[node_map[nid].type].kind == "sink"
    }
    transition_order = [nid for nid in topo_order if nid not in source_ids]

    sink_instances: dict[str, Any] = {}
    for nid in sink_ids:
        node = node_map[nid]
        cls = class_registry[node.type]
        try:
            sink_instances[nid] = cls(**node.data.config)
        except Exception as exc:
            return ExecuteResponse(
                success=False,
                error=ExecutionError(
                    node_id=nid,
                    node_type=node.type,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )

    def _run() -> ExecuteResponse:
        batch_results: list[ExecutionResult] = []
        full_trace: list[ExecutionResult] = []
        row_results: list[RowResult] = []

        if payload.executor == "parallel":
            from concurrent.futures import Future, ThreadPoolExecutor

            with ThreadPoolExecutor() as pool:
                futures_with_meta: list[tuple[dict[str, Any], Any]] = []
                for item in payload.failed_items:
                    fut = pool.submit(
                        _execute_row,
                        item.source_values,
                        transition_order,
                        node_map,
                        class_registry,
                        incoming,
                        instance_cache,
                        sink_instances,
                    )
                    futures_with_meta.append((item.source_values, fut))

            for row_idx, (src_vals, fut) in enumerate(futures_with_meta):
                step_trace, err = fut.result()
                full_trace.extend(step_trace)
                if err is None:
                    last = next(
                        (r for r in reversed(step_trace) if r.node_id not in sink_ids),
                        None,
                    )
                    if last:
                        batch_results.append(last)
                    row_results.append(
                        RowResult(
                            row_index=row_idx,
                            success=True,
                            result=last,
                            source_values=src_vals,
                        )
                    )
                else:
                    row_results.append(
                        RowResult(
                            row_index=row_idx,
                            success=False,
                            error=err,
                            trace=step_trace,
                            source_values=src_vals,
                        )
                    )
        else:
            for row_idx, item in enumerate(payload.failed_items):
                step_trace, err = _execute_row(
                    item.source_values,
                    transition_order,
                    node_map,
                    class_registry,
                    incoming,
                    instance_cache,
                    sink_instances,
                )
                full_trace.extend(step_trace)
                if err is None:
                    last = next(
                        (r for r in reversed(step_trace) if r.node_id not in sink_ids),
                        None,
                    )
                    if last:
                        batch_results.append(last)
                    row_results.append(
                        RowResult(
                            row_index=row_idx,
                            success=True,
                            result=last,
                            source_values=item.source_values,
                        )
                    )
                else:
                    row_results.append(
                        RowResult(
                            row_index=row_idx,
                            success=False,
                            error=err,
                            trace=step_trace,
                            source_values=item.source_values,
                        )
                    )

        if sink_ids:
            err_resp = _close_sinks(sink_ids, sink_instances, node_map, full_trace)
            if err_resp:
                return err_resp

        all_ok = all(r.success for r in row_results)
        return ExecuteResponse(
            success=all_ok,
            results=batch_results,
            execution_trace=full_trace,
            row_results=row_results,
            failure_report=_build_failure_report(row_results) if not all_ok else None,
        )

    collected: list[str] = []
    cb = log_callback if log_callback is not None else collected.append

    if payload.capture_logs or log_callback is not None:
        with streaming_capture(cb):
            response = _run()
    else:
        response = _run()

    if log_callback is None:
        response.console_output = collected

    return response


def execute(
    payload: DagPayload,
    class_registry: ClassRegistry,
    node_schemas: dict[str, NodeSchema],
    log_callback: Callable[[str], None] | None = None,
    instance_cache: InstanceCache | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> ExecuteResponse:
    validation = validate(payload, class_registry, node_schemas)
    if not validation.valid:
        return ExecuteResponse(success=False, valid=False, errors=validation.errors)

    collected: list[str] = []
    cb = log_callback if log_callback is not None else collected.append

    if payload.capture_logs or log_callback is not None:
        with streaming_capture(cb):
            response = _execute_inner(
                payload, class_registry, node_schemas, instance_cache, progress_callback
            )
    else:
        response = _execute_inner(
            payload, class_registry, node_schemas, instance_cache, progress_callback
        )

    if log_callback is None:
        response.console_output = collected

    return response
