"""DCT command-line interface."""
from __future__ import annotations

from pathlib import Path

import typer

cli = typer.Typer(name="dct", add_completion=False)


@cli.command()
def serve(
    transitions: Path = typer.Argument(..., help="Path to transitions.py"),
    source: Path | None = typer.Option(None, "--source", "-s", help="Path to source.py"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8001, "--port"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Serve the DCT UI and API for the given transitions file."""
    import uvicorn

    from dct.api.app import create_app

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


def main() -> None:
    cli()
