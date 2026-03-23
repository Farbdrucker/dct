"""Dask-backed DAG executor for parallel execution."""

from __future__ import annotations

import traceback
from typing import Any

import dask

from dct.engine.models import (
    DagNode,
    DagPayload,
    ExecuteResponse,
    ExecutionError,
    ExecutionResult,
    FailureReport,
    NodeSchema,
    RowResult,
    ValidationError,
)
from dct.engine.executor import (
    ClassRegistry,
    _build_failure_report,
    _build_graph,
    _execute_row,
    _topo_sort,
    validate,
)

# ---------------------------------------------------------------------------
# Dask task adapters
# ---------------------------------------------------------------------------


def _run_transition_delayed(
    node: DagNode,
    class_registry: ClassRegistry,
    constants: dict[str, Any],
    **port_values: Any,
) -> Any:
    """Create an instance and call it; upstream delayed results arrive as kwargs."""
    cls = class_registry[node.type]
    instance = cls(**node.data.config)
    return instance(**{**constants, **port_values})


def _execute_row_delayed(
    source_values: dict[str, Any],
    transition_order: list[str],
    node_map: dict[str, DagNode],
    class_registry: ClassRegistry,
    incoming: dict[str, dict],
) -> tuple[list[ExecutionResult], ExecutionError | None]:
    return _execute_row(
        source_values, transition_order, node_map, class_registry, incoming, None
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_dag_dask(
    payload: DagPayload,
    class_registry: ClassRegistry,
    node_schemas: dict[str, NodeSchema],
    scheduler: str = "threads",
) -> ExecuteResponse:
    """Execute *payload* using Dask for parallelism.

    scheduler: "threads" (default) | "synchronous" | "distributed"
    """
    validation = validate(payload, class_registry, node_schemas)
    if not validation.valid:
        return ExecuteResponse(success=False, valid=False, errors=validation.errors)

    node_map = {n.id: n for n in payload.nodes}
    adj, in_degree, incoming = _build_graph(payload)
    topo_order = _topo_sort(payload, in_degree, adj)

    source_ids = {
        nid for nid in topo_order if node_schemas[node_map[nid].type].kind == "source"
    }
    transition_order = [nid for nid in topo_order if nid not in source_ids]

    # -----------------------------------------------------------------------
    # Single-pass (no sources): per-node dask.delayed graph
    # -----------------------------------------------------------------------
    if not source_ids:
        delayed_store: dict[str, Any] = {}

        for nid in topo_order:
            node = node_map[nid]
            upstream = {
                port: delayed_store[edge.source]
                for port, edge in incoming.get(nid, {}).items()
            }
            delayed_store[nid] = dask.delayed(_run_transition_delayed)(
                node, class_registry, dict(node.data.constants), **upstream
            )

        try:
            computed: tuple[Any, ...] = dask.compute(
                *[delayed_store[nid] for nid in topo_order],
                scheduler=scheduler,
            )
        except Exception as exc:
            return ExecuteResponse(
                success=False,
                error=ExecutionError(
                    node_id="<unknown>",
                    node_type="<unknown>",
                    exception_type=type(exc).__name__,
                    message=str(exc),
                    traceback=traceback.format_exc(),
                ),
            )

        trace = [
            ExecutionResult(
                node_id=nid,
                node_type=node_map[nid].type,
                value=val,
                value_type=type(val).__name__,
            )
            for nid, val in zip(topo_order, computed)
        ]
        return ExecuteResponse(
            success=True, result=trace[-1] if trace else None, execution_trace=trace
        )

    # -----------------------------------------------------------------------
    # Source-driven: per-row dask.delayed
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

    source_id_list = list(source_ids)

    # Materialise all source rows so we can capture source_values per row.
    all_source_rows = list(zip(*[source_instances[sid] for sid in source_id_list]))

    row_delayed = [
        dask.delayed(_execute_row_delayed)(
            {sid: val for sid, val in zip(source_id_list, values)},
            transition_order,
            node_map,
            class_registry,
            incoming,
        )
        for values in all_source_rows
    ]

    try:
        computed_rows: tuple[
            tuple[list[ExecutionResult], ExecutionError | None], ...
        ] = dask.compute(*row_delayed, scheduler=scheduler)
    except Exception as exc:
        return ExecuteResponse(
            success=False,
            error=ExecutionError(
                node_id="<unknown>",
                node_type="<unknown>",
                exception_type=type(exc).__name__,
                message=str(exc),
                traceback=traceback.format_exc(),
            ),
        )

    batch_results: list[ExecutionResult] = []
    full_trace: list[ExecutionResult] = []
    row_results: list[RowResult] = []

    sink_ids = {
        nid for nid in topo_order if node_schemas[node_map[nid].type].kind == "sink"
    }

    for row_idx, ((step_trace, err), raw_values) in enumerate(
        zip(computed_rows, all_source_rows)
    ):
        src_vals = {sid: val for sid, val in zip(source_id_list, raw_values)}
        full_trace.extend(step_trace)
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

    all_ok = all(r.success for r in row_results)
    return ExecuteResponse(
        success=all_ok,
        results=batch_results,
        execution_trace=full_trace,
        row_results=row_results,
        failure_report=_build_failure_report(row_results) if not all_ok else None,
    )
