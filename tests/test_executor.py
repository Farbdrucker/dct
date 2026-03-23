"""Tests for dct.src.executor"""
from pathlib import Path

import pytest

from dct.api.models import DagEdge, DagNode, DagPayload, NodeData
from dct.src.executor import execute, validate
from dct.src.inspector import inspect_module, load_transitions_module

TRANSITIONS_PATH = Path(__file__).parent.parent / "examples" / "transitions.py"


def setup():
    module = load_transitions_module(TRANSITIONS_PATH)
    schemas = {s.class_name: s for s in inspect_module(module)}
    registry = {name: getattr(module, name) for name in schemas}
    return registry, schemas


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def node(id, type_, config=None, constants=None):
    return DagNode(id=id, type=type_, data=NodeData(config=config or {}, constants=constants or {}))

def edge(id, src, src_h, tgt, tgt_h):
    return DagEdge(id=id, source=src, source_handle=src_h, target=tgt, target_handle=tgt_h)


# ---------------------------------------------------------------------------
# Single node
# ---------------------------------------------------------------------------

def test_single_power_node():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[node("n1", "Power", config={"exponent": 2}, constants={"base": 4.0})],
        edges=[],
    )
    resp = execute(payload, registry, schemas)
    assert resp.success is True
    assert resp.result is not None
    assert resp.result.value == pytest.approx(16.0)


# ---------------------------------------------------------------------------
# Chain: Power → Div (divide by 2)
# ---------------------------------------------------------------------------

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
    resp = execute(payload, registry, schemas)
    assert resp.success is True
    assert resp.result.value == pytest.approx(8.0)
    assert len(resp.execution_trace) == 2


# ---------------------------------------------------------------------------
# Diamond: Power + Root → Div
# ---------------------------------------------------------------------------

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
    resp = execute(payload, registry, schemas)
    assert resp.success is True
    assert resp.result.value == pytest.approx(4.5)


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

def test_cycle_detection():
    registry, schemas = setup()
    # n1 → n2 → n1 (cycle via fake edges — validation doesn't care about port names matching for cycle check)
    payload = DagPayload(
        nodes=[
            node("n1", "Power", config={"exponent": 2}, constants={}),
            node("n2", "Power", config={"exponent": 2}, constants={}),
        ],
        edges=[
            edge("e1", "n1", "output", "n2", "base"),
            edge("e2", "n2", "output", "n1", "base"),
        ],
    )
    resp = validate(payload, registry, schemas)
    assert resp.valid is False
    types = [e.type for e in resp.errors]
    assert "cycle_detected" in types


# ---------------------------------------------------------------------------
# Missing constant
# ---------------------------------------------------------------------------

def test_missing_constant():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[node("n1", "Power", config={"exponent": 2}, constants={})],  # no 'base'
        edges=[],
    )
    resp = validate(payload, registry, schemas)
    assert resp.valid is False
    assert any(e.type == "missing_input" for e in resp.errors)


# ---------------------------------------------------------------------------
# Type mismatch edge
# ---------------------------------------------------------------------------

def test_type_mismatch():
    registry, schemas = setup()
    # AddTwoInt outputs int — feeding into a node that only accepts float would be a mismatch
    # AddTwoInt → output: {int}, Power → base: {int, float}  → compatible (subset)
    # Let's use a hack: AddTwoInt output into AddTwoInt.a — output is int, port is int → compatible
    # Instead, manufacture: AddTwoFloats (out: float) → AddTwoInt.a (expects int) — float ⊄ {int}
    payload = DagPayload(
        nodes=[
            node("n1", "AddTwoFloats", config={}, constants={"a": 1.0, "b": 2.0}),
            node("n2", "AddTwoInt",    config={}, constants={"b": 1}),
        ],
        edges=[
            edge("e1", "n1", "output", "n2", "a"),
        ],
    )
    resp = validate(payload, registry, schemas)
    assert resp.valid is False
    assert any(e.type == "type_mismatch" for e in resp.errors)


# ---------------------------------------------------------------------------
# Execution error (runtime)
# ---------------------------------------------------------------------------

def test_execution_error():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[node("n1", "Div", config={}, constants={"nominator": 1.0, "denominator": 0.0})],
        edges=[],
    )
    resp = execute(payload, registry, schemas)
    assert resp.success is False
    assert resp.error is not None
    assert resp.error.exception_type == "ZeroDivisionError"


def test_unknown_node_type():
    registry, schemas = setup()
    payload = DagPayload(
        nodes=[node("n1", "NonExistent", config={}, constants={})],
        edges=[],
    )
    resp = validate(payload, registry, schemas)
    assert resp.valid is False
    assert any(e.type == "unknown_node" for e in resp.errors)


# ---------------------------------------------------------------------------
# Error propagation — downstream nodes must be skipped, not aborted
# ---------------------------------------------------------------------------

def test_error_propagates_downstream():
    """A failing node must skip all downstream nodes (not abort the whole DAG)."""
    registry, schemas = setup()
    # Div(1/0) → Power(exponent=2): Div fails, Power must be skipped
    payload = DagPayload(
        nodes=[
            node("div", "Div", config={}, constants={"nominator": 1.0, "denominator": 0.0}),
            node("pow", "Power", config={"exponent": 2}),
        ],
        edges=[
            edge("e1", "div", "output", "pow", "base"),
        ],
    )
    resp = execute(payload, registry, schemas)
    assert resp.success is False
    assert resp.error is not None
    assert resp.error.exception_type == "ZeroDivisionError"

    # Both nodes must appear in trace
    assert len(resp.execution_trace) == 2
    div_trace = next(t for t in resp.execution_trace if t.node_id == "div")
    pow_trace = next(t for t in resp.execution_trace if t.node_id == "pow")

    # div failed (not a skip)
    assert div_trace.error is not None
    assert div_trace.skipped is False
    assert div_trace.value is None

    # pow was skipped because div failed
    assert pow_trace.skipped is True
    assert pow_trace.error is not None  # carries the upstream error info


def test_independent_branch_succeeds_when_other_fails():
    """If two independent branches exist, the failing one should not affect the other."""
    registry, schemas = setup()
    # n_good: Power(3^2) = 9 — independent
    # n_bad:  Div(1/0) — fails
    # Both nodes feed constants only, no shared dependency
    payload = DagPayload(
        nodes=[
            node("n_good", "Power", config={"exponent": 2}, constants={"base": 3.0}),
            node("n_bad",  "Div",   config={},               constants={"nominator": 1.0, "denominator": 0.0}),
        ],
        edges=[],
    )
    resp = execute(payload, registry, schemas)
    assert resp.success is False  # overall false because n_bad failed
    assert resp.error is not None

    good_trace = next(t for t in resp.execution_trace if t.node_id == "n_good")
    bad_trace  = next(t for t in resp.execution_trace if t.node_id == "n_bad")

    assert good_trace.error is None
    assert good_trace.value == pytest.approx(9.0)
    assert bad_trace.error is not None
    assert bad_trace.skipped is False
