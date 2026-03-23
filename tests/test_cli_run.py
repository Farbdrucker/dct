"""Tests for `dct run` CLI command."""
import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dct.cli import cli

TRANSITIONS_PATH = Path(__file__).parent.parent / "examples" / "transitions.py"
SOURCE_PATH = Path(__file__).parent.parent / "examples" / "source.py"

runner = CliRunner()


def _write_payload(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "dag_payload.json"
    p.write_text(json.dumps(payload))
    return p


# ---------------------------------------------------------------------------
# Single-pass DAG (no source)
# ---------------------------------------------------------------------------

SINGLE_PASS_PAYLOAD = {
    "nodes": [
        {"id": "n1", "type": "Power", "data": {"config": {"exponent": 2}, "constants": {"base": 5.0}}},
    ],
    "edges": [],
}


def test_run_single_pass(tmp_path):
    dag_file = _write_payload(tmp_path, SINGLE_PASS_PAYLOAD)
    result = runner.invoke(cli, ["run", str(TRANSITIONS_PATH), str(dag_file)])
    assert result.exit_code == 0


def test_run_json_output(tmp_path):
    dag_file = _write_payload(tmp_path, SINGLE_PASS_PAYLOAD)
    result = runner.invoke(cli, ["run", str(TRANSITIONS_PATH), str(dag_file), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["success"] is True
    assert data["result"]["value"] == pytest.approx(25.0)


def test_run_dask(tmp_path):
    dag_file = _write_payload(tmp_path, SINGLE_PASS_PAYLOAD)
    result = runner.invoke(cli, ["run", str(TRANSITIONS_PATH), str(dag_file), "--dask", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["success"] is True
    assert data["result"]["value"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Source-driven DAG
# ---------------------------------------------------------------------------

SOURCE_PAYLOAD = {
    "nodes": [
        {"id": "src", "type": "ConstSource", "data": {"config": {"value": 2.0, "count": 3}, "constants": {}}},
        {"id": "pow", "type": "Power", "data": {"config": {"exponent": 3}, "constants": {}}},
    ],
    "edges": [
        {"id": "e1", "source": "src", "source_handle": "output", "target": "pow", "target_handle": "base"},
    ],
}


def test_run_source_driven(tmp_path):
    dag_file = _write_payload(tmp_path, SOURCE_PAYLOAD)
    result = runner.invoke(cli, [
        "run", str(TRANSITIONS_PATH), str(dag_file),
        "--source", str(SOURCE_PATH),
        "--json",
    ])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["success"] is True
    assert len(data["results"]) == 3
    assert all(r["value"] == pytest.approx(8.0) for r in data["results"])


def test_run_invalid_payload(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not json at all")
    result = runner.invoke(cli, ["run", str(TRANSITIONS_PATH), str(bad_file)])
    assert result.exit_code == 1


def test_run_validation_failure(tmp_path):
    payload = {
        "nodes": [{"id": "n1", "type": "NonExistent", "data": {"config": {}, "constants": {}}}],
        "edges": [],
    }
    dag_file = _write_payload(tmp_path, payload)
    result = runner.invoke(cli, ["run", str(TRANSITIONS_PATH), str(dag_file)])
    assert result.exit_code == 1
