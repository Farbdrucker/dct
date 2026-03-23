"""Tests for dct.src.dask_executor — mirrors test_executor but uses Dask."""
from pathlib import Path

import pytest

from dct.api.models import DagEdge, DagNode, DagPayload, NodeData
from dct.src.dask_executor import execute_dag_dask
from dct.src.inspector import inspect_module, inspect_sources_module, load_source_module, load_transitions_module

TRANSITIONS_PATH = Path(__file__).parent.parent / "examples" / "transitions.py"
SOURCE_PATH = Path(__file__).parent.parent / "examples" / "source.py"


def setup():
    t_module = load_transitions_module(TRANSITIONS_PATH)
    schemas = {s.class_name: s for s in inspect_module(t_module)}
    registry = {name: getattr(t_module, name) for name in schemas}
    return registry, schemas


def setup_with_source():
    registry, schemas = setup()
    s_module = load_source_module(SOURCE_PATH)
    for s in inspect_sources_module(s_module):
        schemas[s.class_name] = s
        registry[s.class_name] = getattr(s_module, s.class_name)
    return registry, schemas


def node(id, type_, config=None, constants=None):
    return DagNode(id=id, type=type_, data=NodeData(config=config or {}, constants=constants or {}))


def edge(id, src, src_h, tgt, tgt_h):
    return DagEdge(id=id, source=src, source_handle=src_h, target=tgt, target_handle=tgt_h)


# ---------------------------------------------------------------------------
# Single node (no-source path)
# ---------------------------------------------------------------------------

def test_single_power_node():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[node("n1", "Power", config={"exponent": 2}, constants={"base": 4.0})],
        edges=[],
    )
    resp = execute_dag_dask(payload, registry, schemas, scheduler="synchronous")
    assert resp.success is True
    assert resp.result is not None
    assert resp.result.value == pytest.approx(16.0)


def test_chain_power_div():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[
            node("n1", "Power", config={"exponent": 2}, constants={"base": 4.0}),
            node("n2", "Div", config={}, constants={"denominator": 2.0}),
        ],
        edges=[
            edge("e1", "n1", "output", "n2", "nominator"),
        ],
    )
    resp = execute_dag_dask(payload, registry, schemas, scheduler="synchronous")
    assert resp.success is True
    assert resp.result.value == pytest.approx(8.0)
    assert len(resp.execution_trace) == 2


def test_diamond():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[
            node("n1", "Power", config={"exponent": 2}, constants={"base": 3.0}),  # 9.0
            node("n2", "Root",  config={"radix": 2},    constants={"value": 4.0}),  # 2.0
            node("n3", "Div",   config={},               constants={}),
        ],
        edges=[
            edge("e1", "n1", "output", "n3", "nominator"),
            edge("e2", "n2", "output", "n3", "denominator"),
        ],
    )
    resp = execute_dag_dask(payload, registry, schemas, scheduler="synchronous")
    assert resp.success is True
    assert resp.result.value == pytest.approx(4.5)


def test_validation_error_propagated():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[node("n1", "NonExistent", config={}, constants={})],
        edges=[],
    )
    resp = execute_dag_dask(payload, registry, schemas)
    assert resp.success is False
    assert resp.valid is False
    assert any(e.type == "unknown_node" for e in resp.errors)


# ---------------------------------------------------------------------------
# Source-driven (batched) path
# ---------------------------------------------------------------------------

def test_source_driven():
    registry, schemas = setup_with_source()
    # ConstSource(value=3.0, count=4) yields 3.0 four times → Power(2) → 9.0 each
    payload = DagPayload(
        nodes=[
            node("src", "ConstSource", config={"value": 3.0, "count": 4}),
            node("pow", "Power", config={"exponent": 2}, constants={}),
        ],
        edges=[
            edge("e1", "src", "output", "pow", "base"),
        ],
    )
    resp = execute_dag_dask(payload, registry, schemas, scheduler="synchronous")
    assert resp.success is True
    assert len(resp.results) == 4
    assert all(r.value == pytest.approx(9.0) for r in resp.results)
