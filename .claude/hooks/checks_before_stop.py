#!/usr/bin/env python3
"""Stop hook: a turn that changed code does not end quietly with red checks.

Claude Code passes the event as JSON on stdin. If Python files or project config changed in
the working tree, this runs `ruff check` and the unit tests; on failure it exits with code 2,
which sends the output back to the agent instead of ending the turn. It blocks once per stop:
when the agent stops again (`stop_hook_active`), the turn ends, so a red state that needs the
owner's decision can still be reported.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

CHECKS = (
    ("ruff", ["uv", "run", "ruff", "check", "."]),
    ("pytest", ["uv", "run", "pytest", "-q"]),
)
CODE_SUFFIXES = (".py",)
CODE_FILES = ("pyproject.toml", "uv.lock")
TAIL_LINES = 40


def changed_paths(porcelain: str) -> list[str]:
    """Paths from `git status --porcelain` (for a rename, the new name)."""
    paths = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        paths.append(path)
    return paths


def touches_code(paths: list[str]) -> bool:
    return any(path.endswith(CODE_SUFFIXES) or Path(path).name in CODE_FILES for path in paths)


def tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-TAIL_LINES:])


def run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)


def main() -> None:
    event = json.load(sys.stdin)
    if event.get("stop_hook_active"):
        return
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".")

    status = run(["git", "status", "--porcelain", "--untracked-files=all"], root)
    if status.returncode != 0 or not touches_code(changed_paths(status.stdout)):
        return

    failed = []
    for name, command in CHECKS:
        try:
            result = run(command, root)
        except FileNotFoundError:
            failed.append(f"{name}: `{command[0]}` is not installed or not on PATH")
            continue
        if result.returncode != 0:
            failed.append(f"{name} failed:\n{tail(result.stdout + result.stderr)}")

    if failed:
        print(
            "Checks are red after code changes. Fix them, or say plainly in the report what "
            "fails and why.\n\n" + "\n\n".join(failed),
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
