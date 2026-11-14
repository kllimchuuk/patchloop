"""Command line interface (SPEC §10)."""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import docker
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from patchloop import __version__
from patchloop.config import Config, ConfigError, load_config
from patchloop.environment import run_checks
from patchloop.graph import run_fix
from patchloop.llm.client import LiteLLMClient, LLMClient
from patchloop.runs import (
    ApplyError,
    RunRecord,
    RunRecordError,
    apply_record,
    load_record,
    new_run_id,
    save_record,
)
from patchloop.schemas import CheckResult, RunResult

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


EXIT_ERROR = 2  # usage or environment problem (Typer uses 2 for bad arguments too)


def build_clients(config: Config) -> tuple[LLMClient, Any]:
    """The real model client and Docker client; tests replace this function."""
    return LiteLLMClient(config.llm), docker.from_env()


def _fail(message: str) -> typer.Exit:
    console.print(f"[red]error[/red] {message}", markup=True, highlight=False)
    return typer.Exit(EXIT_ERROR)


def _read_issue(issue: str | None, issue_file: Path | None) -> str | None:
    if issue is not None and issue_file is not None:
        raise _fail("use either --issue or --issue-file, not both")
    text = issue
    if issue_file is not None:
        try:
            text = issue_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _fail(f"cannot read the issue file {issue_file}: {exc}") from exc
    if text is not None and not text.strip():
        raise _fail("the issue description is empty")
    return text.strip() if text is not None else None


def _summary(checks: list[CheckResult]) -> str:
    parts = []
    for check in checks:
        if check.passed:
            parts.append(f"{check.stage} ok")
        elif check.stage == "tests":
            parts.append(f"tests {check.failing_tests or len(check.failures)} failing")
        else:
            parts.append(f"{check.stage} failed")
    return ", ".join(parts)


def describe_step(node: str, update: dict[str, Any]) -> str | None:
    """One progress line for a finished graph node; None for nodes that say nothing new."""
    if node == "prepare":
        return "image ready"
    if node == "check_original":
        return f"original code: {_summary(update['original'])}"
    if node == "tester":
        test = update.get("generated_test")
        if test is not None:
            return f"tester: test accepted ({test.path})"
        return "tester: no usable test, going on without one"
    if node == "fix":
        patch = update.get("new_patch")
        if patch is None:
            return "programmer: no usable answer"
        count = len(patch.files)
        return f"programmer: patch with {count} file{'' if count == 1 else 's'}"
    if node == "check":
        attempt = update["attempts"][-1]
        return f"attempt {attempt.index + 1}: {_summary(attempt.checks)}"
    if node == "decide" and "stop_reason" in update:
        return f"stopping: {update['stop_reason']}"
    return None


def _progress(node: str, update: dict[str, Any]) -> None:
    line = describe_step(node, update)
    if line:
        console.print(Text(f"  {line}"))


LABELS = {
    "fixed": "[green]fixed[/green]",
    "partially_fixed": "[yellow]partially fixed[/yellow] (partial: the best attempt, "
    "some checks still fail)",
    "not_fixed": "[red]not fixed[/red]",
    "no_bugs_found": "[green]no bugs found[/green]",
}


def _show(result: RunResult, run_id: str | None) -> None:
    console.print(f"\nStatus: {LABELS[result.status]}")
    console.print(Text(f"Stop reason: {result.stop_reason}, reliability: {result.reliability}"))
    if result.diff:
        console.print(Syntax(result.diff, "diff", word_wrap=True))
    if result.explanation:
        console.print(Panel(Text(result.explanation), title="Explanation"))
    test = result.generated_test
    if test is not None:
        body = Text(f"{test.content}\nFails on the original code with:\n{test.output}")
        console.print(Panel(body, title=f"Generated test {test.path} (not part of the fix)"))
    if run_id:
        console.print(f"Run {run_id}", soft_wrap=True)
    if run_id and result.diff:
        console.print("To put the fix on a branch (no commit):", soft_wrap=True)
        console.print(Text(f"  patchloop apply {run_id}"), soft_wrap=True)


@app.command()
def fix(
    project: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, resolve_path=True, help="Project directory."),
    ],
    issue: Annotated[str | None, typer.Option("--issue", help="Bug description.")] = None,
    issue_file: Annotated[
        Path | None, typer.Option("--issue-file", help="File with the bug description.")
    ] = None,
    config: Annotated[
        Path | None, typer.Option("--config", help="Path to patchloop.yml.")
    ] = None,
) -> None:
    """Find and fix a bug in PROJECT. The project itself is never modified."""
    text = _read_issue(issue, issue_file)
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        raise _fail(f"config: {exc}") from exc
    problems = [item for item in run_checks(cfg) if not item.ok]
    for item in problems:
        console.print(Text(f"FAIL {item.name}: {item.detail}"), style="red")
        if item.hint:
            console.print(Text(f"     hint: {item.hint}"))
    if problems:
        raise typer.Exit(EXIT_ERROR)
    try:
        llm, docker_client = build_clients(cfg)
        console.print(Text(f"Fixing {project}"), soft_wrap=True)
        result = run_fix(project, cfg, llm, docker_client, text, on_step=_progress)
    except (RuntimeError, OSError, docker.errors.DockerException) as exc:
        raise _fail(str(exc)) from exc
    record = RunRecord(
        run_id=new_run_id(datetime.now()), project=str(project), issue=text, result=result
    )
    try:
        save_record(cfg.runs_dir, record)
    except RunRecordError as exc:
        _show(result, None)
        raise _fail(f"the run record was not saved: {exc}") from exc
    _show(result, record.run_id)
    raise typer.Exit(0 if result.status in ("fixed", "no_bugs_found") else 1)


@app.command("apply")
def apply_run(
    run_id: Annotated[str, typer.Argument(help="Run id printed by `patchloop fix`.")],
    config: Annotated[
        Path | None, typer.Option("--config", help="Path to patchloop.yml.")
    ] = None,
) -> None:
    """Put the stored fix of RUN_ID on the git branch patchloop/RUN_ID (no commit, no push)."""
    try:
        cfg = load_config(config)
    except ConfigError as exc:
        raise _fail(f"config: {exc}") from exc
    try:
        record = load_record(cfg.runs_dir, run_id)
        files = apply_record(record)
    except (RunRecordError, ApplyError) as exc:
        raise _fail(str(exc)) from exc
    if record.result.status == "partially_fixed":
        console.print("[yellow]Warning[/yellow]: partial fix, some checks still fail.")
    console.print(Text(f"Branch patchloop/{run_id} has the fix, uncommitted:"), soft_wrap=True)
    for name in files:
        console.print(Text(f"  {name}"), soft_wrap=True)
    console.print("Review it with: git diff")


def main() -> None:
    app()
