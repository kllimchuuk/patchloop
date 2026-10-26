"""Command line interface (SPEC §10)."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from patchloop import __version__
from patchloop.config import ConfigError, load_config
from patchloop.environment import run_checks

app = typer.Typer(
    help="Fix bugs in Python projects with a multi-agent system on a local LLM."
)
console = Console()


def _version(value: bool) -> None:
    if value:
        console.print(f"patchloop {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version, is_eager=True, help="Show the version."
        ),
    ] = False,
) -> None:
    """Fix bugs in Python projects with a multi-agent system on a local LLM."""


@app.command()
def check(
    config: Annotated[
        Path | None, typer.Option("--config", help="Path to patchloop.yml.")
    ] = None,
) -> None:
    """Check Python, Docker, Ollama and the configured model."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]FAIL[/red] config: {exc}")
        raise typer.Exit(1) from exc
    failed = False
    for item in run_checks(cfg):
        mark = "[green]OK  [/green]" if item.ok else "[red]FAIL[/red]"
        console.print(f"{mark} {item.name}: {item.detail}")
        if not item.ok:
            failed = True
            if item.hint:
                console.print(f"     hint: {item.hint}")
    raise typer.Exit(1 if failed else 0)


def main() -> None:
    app()
