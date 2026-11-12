"""The Claude Code hooks in `.claude/hooks/` (development tooling, not part of the package)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
REVIEWER_HOOK = HOOKS / "reviewer_readonly.py"
BLOCK_MESSAGE = "Blocked by the reviewer read-only hook"


def run_reviewer_hook(tool_input: dict, tool_name: str = "Bash") -> subprocess.CompletedProcess:
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, str(REVIEWER_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "command",
    [
        "git status --short",
        "git diff main",
        "git diff main...HEAD --stat",
        "git log --format='%h %s' main..HEAD",
        "git show 8542b9b:CLAUDE.md",
        "git ls-files",
        "git branch --show-current",
        "git grep -n network_mode",
        "uv run ruff check .",
        "uv run pytest -q",
        "uv run pytest tests/unit/test_graph.py -q",
        "uv run pytest -m docker tests/docker -q",
        "git log --oneline main..HEAD | head -20",
        "git diff main | wc -l",
    ],
)
def test_reviewer_may_run_read_only_commands(command):
    result = run_reviewer_hook({"command": command})

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "touch notes.txt",
        "rm -rf src",
        "echo hi > file.txt",
        "git commit -m x",
        "git add .",
        "git push origin main",
        "git reset --hard",
        "git switch main",
        "git branch -D feat/project-skeleton",
        "git diff --output=out.patch",
        "git -c core.pager=sh log",
        "git status; rm -rf .",
        "git status && rm -rf .",
        "git status `touch x`",
        "git status $(touch x)",
        "git status\nrm -rf .",
        "git log | sh",
        "git log | tee out.txt",
        "cat .env",
        "uv run ruff check . --fix",
        "uv run ruff check . --output-file out.txt",
        "uv run ruff format .",
        "uv run pytest --junitxml=out.xml",
        "uv run python -c 'open(\"x\",\"w\")'",
        "uv run patchloop fix .",
        "uv add requests",
        "docker run --rm python:3.12-slim",
        "curl https://example.com",
        "sed -i s/a/b/ src/patchloop/graph.py",
    ],
)
def test_reviewer_cannot_change_state(command):
    result = run_reviewer_hook({"command": command})

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


def test_reviewer_hook_leaves_other_tools_alone():
    assert run_reviewer_hook({"file_path": "CLAUDE.md"}, tool_name="Read").returncode == 0


def test_reviewer_hook_blocks_a_missing_command():
    result = run_reviewer_hook({})

    assert result.returncode == 2
    assert BLOCK_MESSAGE in result.stderr


def test_stop_hook_reads_paths_from_git_status():
    hook = load("checks_before_stop")
    porcelain = (
        " M src/patchloop/graph.py\n"
        "?? docs/reports/05-cli.md\n"
        "R  old_name.py -> tests/new_name.py\n"
    )

    assert hook.changed_paths(porcelain) == [
        "src/patchloop/graph.py",
        "docs/reports/05-cli.md",
        "tests/new_name.py",
    ]


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["src/patchloop/graph.py"], True),
        (["docs/SPEC.md", "pyproject.toml"], True),
        (["uv.lock"], True),
        (["docs/SPEC.md", "CLAUDE.md", ".claude/skills/report/SKILL.md"], False),
        ([], False),
    ],
)
def test_stop_hook_runs_checks_only_when_code_changed(paths, expected):
    assert load("checks_before_stop").touches_code(paths) is expected
