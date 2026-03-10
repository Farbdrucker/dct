"""Integration tests for the FastAPI app."""
from __future__ import annotations

import pytest

EXPECTED_TRANSITIONS = {"AddTwoInt", "AddTwoFloats", "Div", "Power", "Root"}
EXPECTED_SOURCES = {"ConstSource", "ConstIntSource", "RangeSource"}


def test_get_schema(client):
    resp = client.get("/api/nodes/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "schema_version" in data
    names = {n["class_name"] for n in data["nodes"]}
    assert names == EXPECTED_TRANSITIONS | EXPECTED_SOURCES


def test_schema_nodes_have_required_fields(client):
    """Every node returned must have input_ports, output_port, and config_fields."""
    resp = client.get("/api/nodes/schema")
    nodes = {n["class_name"]: n for n in resp.json()["nodes"]}

    for name in EXPECTED_TRANSITIONS:
        assert name in nodes, f"{name} missing from /api/nodes/schema"
        node = nodes[name]
        assert "input_ports" in node
        assert "output_port" in node
        assert "config_fields" in node
        assert isinstance(node["input_ports"], list)
        assert isinstance(node["config_fields"], list)
        # output_port must have name and type_set
        assert "name" in node["output_port"]
        assert "type_set" in node["output_port"]

    # Specific shapes
    assert {p["name"] for p in nodes["Div"]["input_ports"]} == {"nominator", "denominator"}
    assert nodes["Power"]["config_fields"][0]["name"] == "exponent"
    assert nodes["Root"]["config_fields"][0]["name"] == "radix"
    assert nodes["AddTwoInt"]["config_fields"] == []
    assert nodes["AddTwoFloats"]["config_fields"] == []


def test_execute_power(client):
    payload = {
        "nodes": [{"id": "n1", "type": "Power", "data": {"config": {"exponent": 2}, "constants": {"base": 4.0}}}],
        "edges": [],
    }
    resp = client.post("/api/dag/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["result"]["value"] == pytest.approx(16.0)


def test_validate_type_mismatch(client):
    payload = {
        "nodes": [
            {"id": "n1", "type": "AddTwoFloats", "data": {"config": {}, "constants": {"a": 1.0, "b": 2.0}}},
            {"id": "n2", "type": "AddTwoInt",    "data": {"config": {}, "constants": {"b": 1}}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "source_handle": "output", "target": "n2", "target_handle": "a"},
        ],
    }
    resp = client.post("/api/dag/validate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any(e["type"] == "type_mismatch" for e in data["errors"])
