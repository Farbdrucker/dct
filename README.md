# DCT — DAG Compositional Transitions

![Python](https://img.shields.io/badge/python-3.13%2B-blue)
![React](https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=white)
[![Tests](https://github.com/Farbdrucker/dct/actions/workflows/tests.yml/badge.svg)](https://github.com/Farbdrucker/dct/actions/workflows/tests.yml)

A visual DAG composer for typed Python transition functions.

## What it does

- Define computational nodes as Python dataclasses with typed inputs/outputs
- Compose them visually into a directed acyclic graph (DAG)
- Validate type compatibility between connected nodes
- Execute the DAG with live log streaming
- Partial failure tracking — failed source rows are captured for replay

## Tech Stack

| Layer    | Technologies                                              |
|----------|-----------------------------------------------------------|
| Backend  | Python 3.13, FastAPI, Pydantic, watchfiles                |
| Frontend | React 19, @xyflow/react v12, TanStack Query, Zustand, Tailwind v4 |

## Install

**Prerequisites:** Python ≥ 3.13

DCT is split into three installation scopes so you only pull in what you need.

### Core — define nodes only

Just `Transition`, `Source`, `Sink`. Depends on `pydantic` only.

```bash
pip install "dct @ git+https://github.com/Farbdrucker/dct"
```

### Execute — run DAGs from Python or the CLI

Adds the execution engine, inspector, and `dct run`. Brings in `rich`, `typer`, and `dask`.

```bash
pip install "dct[execute] @ git+https://github.com/Farbdrucker/dct"
```

### UI — visual editor + API server

Full stack: everything above plus the FastAPI server, file watcher, and `dct serve`. Brings in `fastapi`, `uvicorn`, and `watchfiles`.

```bash
pip install "dct[ui] @ git+https://github.com/Farbdrucker/dct"
```

> `[ui]` is a superset of `[execute]`, which is a superset of the bare install.

---

### Install from source

```bash
git clone https://github.com/Farbdrucker/dct
cd dct
uv sync --extra ui   # or: uv sync --extra execute
```

---

## Defining nodes

### Transitions

Create a `transitions.py` file. Each class implements `__call__` with typed arguments and a typed return value. Class-level attributes become configuration fields set in the UI.

```python
from dct import Transition

class AddInts(Transition):
    """Add two integers."""
    def __call__(self, a: int, b: int) -> int:
        return a + b

class Scale(Transition):
    """Multiply by a fixed factor."""
    factor: float  # configured in the UI per-node

    def __call__(self, value: int | float) -> float:
        return value * self.factor
```

You can also use `@Transition` as a decorator on a plain class — equivalent to subclassing.

### Sources

Create a `source.py` next to your transitions. Sources feed rows of data into the DAG; each row flows through all connected transitions independently.

```python
from dct import Source
from typing import Iterator

class RangeSource(Source):
    """Yields integers from start to stop."""
    stop: int
    start: int = 0

    def __iter__(self) -> Iterator[int]:
        yield from range(self.start, self.stop)
```

The type parameter of `__iter__`'s return annotation becomes the output port type seen in the UI.

### Sinks

Sinks are terminal nodes that accumulate state across rows (e.g. writing to a file or collecting results). They implement `__call__` (called once per row) and `close` (called once after all rows).

```python
import threading
from dct import Sink

class Collect(Sink):
    def __call__(self, value: float) -> None:
        with self._lock:
            self._results.append(value)

    def close(self) -> None:
        print(f"Collected {len(self._results)} values")

    def __post_init__(self) -> None:
        self._results: list[float] = []
        self._lock = threading.Lock()
```

> In **parallel** execution mode, `__call__` may be invoked from multiple threads simultaneously. Protect shared state with a lock. `close` is always called sequentially.

---

## CLI

### `dct serve` — launch the visual editor

```
dct serve TRANSITIONS_PATH [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--source PATH` | auto-detected | Path to `source.py`; auto-discovered next to `transitions.py` |
| `--host TEXT` | `127.0.0.1` | Host to bind |
| `--port INT` | `8001` | Port to bind |
| `--open / --no-open` | `--open` | Open browser automatically |

```bash
dct serve transitions.py
dct serve transitions.py --source source.py --port 9000 --no-open
```

DCT **hot-reloads** whenever you save `transitions.py` or `source.py` — no restart needed.

### `dct run` — execute a DAG from the command line

```
dct run TRANSITIONS_PATH DAG_JSON [OPTIONS]
```

`DAG_JSON` is a path to a JSON file containing the DAG payload (use **Export for Run** in the UI to produce one — see [Exporting a DAG](#exporting-a-dag)).

| Option | Default | Description |
|--------|---------|-------------|
| `--source PATH` | auto-detected | Path to `source.py` |
| `--parallel / --no-parallel` | off | Execute rows in parallel with a thread pool |
| `--dask / --no-dask` | off | Execute using Dask (overrides `--parallel`) |
| `--capture-logs / --no-capture-logs` | off | Capture and display stdout/logging output |
| `--json` | off | Emit raw JSON instead of the Rich formatted output |

```bash
# Simple run
dct run transitions.py dag_payload.json

# Source-driven with parallel execution
dct run transitions.py dag_payload.json --source source.py --parallel

# Machine-readable output
dct run transitions.py dag_payload.json --json > result.json
```

**Example output** (source-driven with partial failures):

```
✓ 7/10 row(s) succeeded
┌───────┬────────────────────┬──────────────────────────────────────────────┐
│ Row   │ Source Values      │ Error                                        │
├───────┼────────────────────┼──────────────────────────────────────────────┤
│ 2     │ src=0              │ Div: ZeroDivisionError: float division...    │
│ 7     │ src=0              │ Div: ZeroDivisionError: float division...    │
│ 8     │ src=0              │ Div: ZeroDivisionError: float division...    │
└───────┴────────────────────┴──────────────────────────────────────────────┘
```

---

## Exporting a DAG

The UI provides two export formats from the top bar:

### Export (`.json`)

Saves the full canvas state — node positions, types, configuration, and edges. Use this to save your work and re-import it later with **Import**.

### Export for Run (`dag_payload.json`)

Saves the DAG in the API payload format understood by `dct run` and `POST /api/dag/execute`. This is the file you pass to the CLI:

```bash
dct run transitions.py dag_payload.json --source source.py
```

The payload format:

```json
{
  "nodes": [
    { "id": "src",  "type": "RangeSource", "data": { "config": { "stop": 10 }, "constants": {} } },
    { "id": "scale","type": "Scale",        "data": { "config": { "factor": 2.0 }, "constants": {} } }
  ],
  "edges": [
    { "id": "e1", "source": "src", "source_handle": "output", "target": "scale", "target_handle": "value" }
  ],
  "executor": "sequential"
}
```

---

## Result mechanics: Ok / Err

Every transition is internally wrapped in a `Result` type — either `Ok(value)` on success or `Err(...)` on failure. This shapes how the executor behaves:

### Error propagation (not abort)

When a transition raises an exception, execution **does not stop**. Instead:

- The failing node is recorded as `error` in the trace.
- All nodes that depend on the failed node are **skipped** (marked `skipped: true`).
- Independent branches in the same DAG continue executing normally.
- All source rows are always processed, regardless of failures in previous rows.

### Per-row results

For source-driven DAGs, every row produces a `RowResult`:

```json
{
  "row_index": 2,
  "success": false,
  "error": { "node_type": "Div", "exception_type": "ZeroDivisionError", "message": "...", "traceback": "..." },
  "source_values": { "src": 0 },
  "trace": [ ... ]
}
```

`source_values` maps each source node ID to the value it yielded for that row. This is the key that enables replay.

### Failure report

When at least one row fails, `ExecuteResponse` includes a `failure_report`:

```json
{
  "total_rows": 10,
  "succeeded_rows": 7,
  "failed_rows": 3,
  "failed_items": [ ... ]
}
```

`results` always contains only the successful row finals — the shape is backward-compatible whether all rows succeed or not.

### Replaying failed rows

`failed_items` from a `FailureReport` can be fed back directly into the executor to re-run only those rows — source nodes are bypassed entirely and the captured `source_values` are injected directly.

**Via the UI:** click **Replay Failed** in the result panel after a partial failure.

**Via the API:**

```
POST /api/dag/replay
Content-Type: application/json

{
  "nodes": [ ... ],
  "edges": [ ... ],
  "executor": "sequential",
  "failed_items": <failure_report.failed_items>
}
```

**Via Python:**

```python
from dct.engine.executor import replay_failed
from dct.engine.models import ReplayPayload

response = execute(payload, registry, schemas)

if response.failure_report:
    retry = replay_failed(
        ReplayPayload(
            nodes=payload.nodes,
            edges=payload.edges,
            failed_items=response.failure_report.failed_items,
        ),
        registry,
        schemas,
    )
```

The replay response has the same shape as a normal `ExecuteResponse` — including a new `failure_report` if any rows fail again.

---

## Running from source (development)

```bash
# backend (requires uv sync --extra ui)
uv run uvicorn dct.api.app:app --reload   # port 8000

# frontend (separate terminal)
cd frontend && npm install && npm run dev  # port 5173, proxies /api → 8000
```

## Tests

```bash
uv run pytest tests/ -v
```
