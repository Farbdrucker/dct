"""DCT command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

cli = typer.Typer(name="dct", add_completion=False)
console = Console()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _print_response(response: object, con: Console) -> None:
    """Pretty-print an ExecuteResponse using Rich."""
    from dct.engine.models import ExecuteResponse

    r: ExecuteResponse = response  # type: ignore[assignment]

    if not r.valid:
        con.print("[bold red]Validation failed:[/bold red]")
        for err in r.errors:
            con.print(f"  [red]• {err.message}[/red]")
        return

    if not r.success and not r.failure_report:
        # Complete failure (single-pass, source init, or validation-level error)
        con.print("[bold red]Execution failed[/bold red]")
        if r.error:
            con.print(
                f"  [red]{r.error.node_type} ({r.error.node_id}): {r.error.message}[/red]"
            )
            if r.error.traceback:
                con.print(f"[dim]{r.error.traceback}[/dim]")
        return

    # Batch results (source-driven)
    if r.results or r.failure_report:
        total = len(r.row_results) if r.row_results else len(r.results)
        succeeded = len(r.results)
        color = "green" if r.success else "yellow"
        con.print(f"[{color}]✓ {succeeded}/{total} row(s) succeeded[/{color}]")

        if r.results:
            table = Table(title="Successful Results", show_lines=True)
            table.add_column("Row", style="dim", width=6)
            table.add_column("Node", style="cyan")
            table.add_column("Type", style="dim")
            table.add_column("Value")
            for res in r.results:
                # Find matching row index from row_results
                row_idx = next(
                    (
                        rr.row_index
                        for rr in r.row_results
                        if rr.success and rr.result and rr.result.node_id == res.node_id
                    ),
                    "?",
                )
                table.add_row(
                    str(row_idx), res.node_type, res.value_type, repr(res.value)
                )
            con.print(table)

        if r.failure_report and r.failure_report.failed_rows > 0:
            fail_table = Table(title="Failed Rows", show_lines=True)
            fail_table.add_column("Row", style="dim", width=6)
            fail_table.add_column("Source Values", style="cyan")
            fail_table.add_column("Error", style="red")
            for item in r.failure_report.failed_items:
                src_str = ", ".join(f"{k}={v!r}" for k, v in item.source_values.items())
                err_str = (
                    f"{item.error.node_type}: {item.error.exception_type}: {item.error.message}"
                    if item.error
                    else "unknown"
                )
                fail_table.add_row(str(item.row_index), src_str, err_str)
            con.print(fail_table)
        return

    # Single-pass result
    if r.result:
        con.print(
            f"[green]✓[/green] [cyan]{r.result.node_type}[/cyan] → [bold]{r.result.value!r}[/bold]"
        )
        return

    con.print("[yellow]No output produced[/yellow]")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@cli.command()
def serve(
    transitions: Path = typer.Argument(..., help="Path to transitions.py"),
    source: Path | None = typer.Option(
        None, "--source", "-s", help="Path to source.py"
    ),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8001, "--port"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Serve the DCT UI and API for the given transitions file."""
    try:
        import uvicorn
        from dct.server.app import create_app
    except ImportError:
        raise typer.Exit("Install dct[ui] to use the serve command: pip install dct[ui]")

    transitions_path = transitions.resolve()

    if source is None:
        candidate = transitions_path.parent / "source.py"
        source_path = candidate if candidate.exists() else None
    else:
        source_path = source.resolve()

    app = create_app(transitions_path, source_path)

    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    uvicorn.run(app, host=host, port=port)


@cli.command()
def run(
    transitions: Path = typer.Argument(..., help="Path to transitions.py"),
    dag_json: Path = typer.Argument(..., help="Path to dag_payload.json"),
    source: Path | None = typer.Option(
        None, "--source", "-s", help="Path to source.py"
    ),
    parallel: bool = typer.Option(
        False, "--parallel/--no-parallel", help="Run rows in parallel"
    ),
    capture_logs: bool = typer.Option(
        False, "--capture-logs/--no-capture-logs", help="Capture stdout/stderr"
    ),
    use_dask: bool = typer.Option(False, "--dask/--no-dask", help="Use Dask executor"),
    json_output: bool = typer.Option(
        False, "--json", help="Emit JSON instead of Rich output"
    ),
) -> None:
    """Execute a DAG from the command line without starting the API server."""
    try:
        from dct.engine.models import DagPayload
        from dct.engine.inspector import (
            inspect_module,
            inspect_sources_module,
            load_source_module,
            load_transitions_module,
        )
    except ImportError:
        raise typer.Exit("Install dct[execute] to use the run command: pip install dct[execute]")

    # 1. Load transitions module
    t_module = load_transitions_module(transitions.resolve())
    schemas_list = inspect_module(t_module)
    node_schemas = {s.class_name: s for s in schemas_list}
    class_registry = {
        s.class_name: getattr(t_module, s.class_name) for s in schemas_list
    }

    # 2. Auto-discover source.py or use --source
    source_path = (
        source.resolve() if source else (transitions.resolve().parent / "source.py")
    )
    if source_path.exists():
        s_module = load_source_module(source_path)
        for s in inspect_sources_module(s_module):
            node_schemas[s.class_name] = s
            class_registry[s.class_name] = getattr(s_module, s.class_name)

    # 3. Parse DagPayload JSON
    try:
        payload = DagPayload.model_validate_json(dag_json.read_text())
    except Exception as exc:
        console.print(f"[bold red]Failed to parse {dag_json}:[/bold red] {exc}")
        raise typer.Exit(1)

    if use_dask:
        payload.executor = "dask"
    elif parallel:
        payload.executor = "parallel"
    else:
        payload.executor = "sequential"
    payload.capture_logs = capture_logs

    # 4. Execute
    if use_dask:
        from dct.engine.dask_executor import execute_dag_dask

        response = execute_dag_dask(payload, class_registry, node_schemas)
    else:
        from dct.engine.executor import execute

        response = execute(payload, class_registry, node_schemas)

    # 5. Output
    if json_output:
        print(response.model_dump_json(indent=2))
    else:
        _print_response(response, console)

    raise typer.Exit(0 if response.success else 1)


def main() -> None:
    cli()
