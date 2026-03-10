"""Tests for source.py and source-driven DAG execution."""
from pathlib import Path

import pytest

from dct.api.models import DagEdge, DagNode, DagPayload, NodeData
from dct.src.executor import execute
from dct.src.inspector import inspect_module, inspect_sources_module, load_source_module, load_transitions_module

TRANSITIONS_PATH = Path(__file__).parent.parent / "examples" / "transitions.py"
SOURCE_PATH = Path(__file__).parent.parent / "examples" / "source.py"


def setup():
    t_mod = load_transitions_module(TRANSITIONS_PATH)
    s_mod = load_source_module(SOURCE_PATH)
    t_schemas = {s.class_name: s for s in inspect_module(t_mod)}
    s_schemas = {s.class_name: s for s in inspect_sources_module(s_mod)}
    schemas = {**t_schemas, **s_schemas}
    registry = {name: getattr(t_mod, name, None) or getattr(s_mod, name) for name in schemas}
    return registry, schemas


def node(id, type_, config=None, constants=None):
    return DagNode(id=id, type=type_, data=NodeData(config=config or {}, constants=constants or {}))

def edge(id, src, src_h, tgt, tgt_h):
    return DagEdge(id=id, source=src, source_handle=src_h, target=tgt, target_handle=tgt_h)


def test_const_source_iter():
    s_mod = load_source_module(SOURCE_PATH)
    ConstSource = s_mod.ConstSource
    src = ConstSource(value=7.0, count=3)
    assert list(src) == [7.0, 7.0, 7.0]


def test_const_source_getitem():
    s_mod = load_source_module(SOURCE_PATH)
    ConstSource = s_mod.ConstSource
    src = ConstSource(value=5.0, count=10)
    assert src[0] == 5.0
    assert src[99] == 5.0


def test_source_schema_kind():
    _, schemas = setup()
    assert schemas["ConstSource"].kind == "source"


def test_source_schema_no_input_ports():
    _, schemas = setup()
    assert schemas["ConstSource"].input_ports == []


def test_source_schema_output_type():
    _, schemas = setup()
    assert "float" in schemas["ConstSource"].output_port.type_set


def test_batched_execution_const_source_to_power():
    """ConstSource(value=3, count=4) → Power(exponent=2) → [9, 9, 9, 9]"""
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[
            node("src", "ConstSource", config={"value": 3.0, "count": 4}),
            node("pow", "Power", config={"exponent": 2}),
        ],
        edges=[edge("e1", "src", "output", "pow", "base")],
    )
    resp = execute(payload, registry, schemas)
    assert resp.success is True
    assert resp.result is None          # batched mode — no single result
    assert len(resp.results) == 4
    assert all(r.value == pytest.approx(9.0) for r in resp.results)


def test_batched_execution_trace_length():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[
            node("src", "ConstSource", config={"value": 2.0, "count": 3}),
            node("pow", "Power", config={"exponent": 3}),
        ],
        edges=[edge("e1", "src", "output", "pow", "base")],
    )
    resp = execute(payload, registry, schemas)
    assert resp.success is True
    # 3 iterations × 1 transition node = 3 trace entries
    assert len(resp.execution_trace) == 3
