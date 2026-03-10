# DCT — DAG Compositional Transitions

![Tests](https://github.com/your-org/dct/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.13%2B-blue)
![React](https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=white)

A visual DAG composer for typed Python transition functions.

## What it does

- Define computational nodes as Python dataclasses with typed inputs/outputs
- Compose them visually into a directed acyclic graph (DAG)
- Validate type compatibility between connected nodes
- Execute the DAG with live log streaming

## Tech Stack

| Layer    | Technologies                                              |
|----------|-----------------------------------------------------------|
| Backend  | Python 3.13, FastAPI, Pydantic, watchfiles                |
| Frontend | React 19, @xyflow/react v12, TanStack Query, Zustand, Tailwind v4 |

## Install

**Prerequisites:** Python ≥ 3.13, [uv](https://github.com/astral-sh/uv)

```bash
uv tool install git+https://github.com/Farbdrucker/dct
```

Or clone and install locally:

```bash
git clone https://github.com/Farbdrucker/dct
cd dct
uv sync
```

## Usage

### 1. Define your transitions

Create a `transitions.py` file with Pydantic dataclasses. Each class must implement `__call__` with typed arguments and a return type:

```python
from pydantic.dataclasses import dataclass

@dataclass
class AddInts:
    """Add two integers."""
    def __call__(self, a: int, b: int) -> int:
        return a + b

@dataclass
class Scale:
    """Multiply by a fixed factor."""
    factor: float  # constructor argument, configured in the UI

    def __call__(self, value: int | float) -> float:
        return value * self.factor
```

Optionally, create a `source.py` next to it with `Source` subclasses that feed data into the graph (see `examples/source.py`).

### 2. Launch DCT

```bash
dct serve path/to/transitions.py
# opens http://localhost:8001 automatically
```

Pass a separate source file and/or change the port:

```bash
dct serve path/to/transitions.py --source path/to/source.py --port 9000
```

DCT **hot-reloads** whenever you save `transitions.py` or `source.py` — no restart needed.

### 3. Compose and run

1. Drag nodes from the library onto the canvas.
2. Connect outputs to inputs — incompatible types are rejected.
3. Click **Validate**, then **Execute** to run the DAG and stream logs.

## Running from source (development)

```bash
# backend
uv run uvicorn dct.api.app:app --reload   # port 8000

# frontend (separate terminal)
cd frontend && npm install && npm run dev  # port 5173, proxies /api → 8000
```

## Tests

```bash
uv run pytest tests/ -v
```
