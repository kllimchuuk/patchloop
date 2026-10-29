"""Parse compileall, ruff and pytest output into `CheckResult` (SPEC §5, §6).

Pure functions over text: no Docker, no files. Output of the checked project is untrusted, so
every path is normalised and anything outside the workspace is dropped.
"""

import posixpath
import re
from typing import Literal

from patchloop.sandbox.runner import ExecResult
from patchloop.schemas import CheckResult, Failure

Stage = Literal["build", "lint", "tests"]
KIND: dict[str, Literal["build", "lint", "test"]] = {
    "build": "build",
    "lint": "lint",
    "tests": "test",
}
WORKDIR = "/work"
PYTEST_NO_TESTS = 5  # pytest exit code: nothing collected, so nothing failed

COMPILE_BLOCK_RE = re.compile(r"^\*\*\* Error compiling '(.+)'\.\.\.$")
COMPILE_LINE_RE = re.compile(r'^\s*File "(.+)", line (\d+)')
COMPILE_ERROR_RE = re.compile(r"^(\w*(?:Error|Warning)): (.*)$")
RUFF_RE = re.compile(r"^(.+?):(\d+):(\d+): (\S+?):? (?:\[\*\] )?(.+)$")
PYTEST_SUMMARY_RE = re.compile(r"^(FAILED|ERROR) (\S+?)(?: - (.*))?$")
PYTEST_SECTION_RE = re.compile(r"^_{3,} (.+?) _{3,}$")
PYTEST_FINAL_RE = re.compile(r"(\d+) (failed|errors?)\b")
PYTEST_FRAME_RE = re.compile(r"^(\S+?\.py):(\d+): (?!in )\S")  # innermost frame of a failure
PYTEST_CALL_RE = re.compile(r"^(\S+?\.py):(\d+): in ")  # one frame of a traceback
PYTEST_FILE_RE = re.compile(r'^E\s+File "(.+)", line (\d+)')  # syntax error in a collected module
PYTEST_MESSAGE_RE = re.compile(r"^E\s+(.+)$")


def relative_path(path: str) -> str | None:
    """A project-relative POSIX path, or None if it points outside the workspace."""
    path = path.strip()
    if path.startswith(WORKDIR + "/"):
        path = path[len(WORKDIR) + 1 :]
    path = posixpath.normpath(path)
    if not path or path == "." or posixpath.isabs(path) or path.startswith(".."):
        return None
    return path


def _tail(text: str, lines: int) -> str:
    return "\n".join(text.splitlines()[-lines:])


def parse_compileall(output: str) -> list[Failure]:
    failures: list[Failure] = []
    block: list[str] = []
    name = ""

    def flush() -> None:
        if not name:
            return
        line = next(
            (int(m.group(2)) for ln in block if (m := COMPILE_LINE_RE.match(ln))), None
        )
        message = next(
            (ln for ln in reversed(block) if COMPILE_ERROR_RE.match(ln.strip())), None
        )
        failures.append(
            Failure(
                kind="build",
                file=relative_path(name),
                line=line if line and line >= 1 else None,
                message=(message or "compilation failed").strip(),
            )
        )

    for raw in output.splitlines():
        match = COMPILE_BLOCK_RE.match(raw)
        if match:
            flush()
            name, block = match.group(1), []
        elif name:
            block.append(raw)
    flush()
    return failures


def parse_ruff(output: str) -> list[Failure]:
    failures = []
    for raw in output.splitlines():
        match = RUFF_RE.match(raw)
        if not match:
            continue  # "Found N errors." and the like
        path, line, _col, code, message = match.groups()
        failures.append(
            Failure(
                kind="lint",
                file=relative_path(path),
                line=max(int(line), 1),
                symbol=code,
                message=f"{code} {message}".strip(),
            )
        )
    return failures


def _pytest_sections(lines: list[str]) -> dict[str, list[str]]:
    """Body of each `____ name ____` block, keyed by its heading."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for raw in lines:
        match = PYTEST_SECTION_RE.match(raw)
        if match:
            current = sections.setdefault(match.group(1), [])
        elif raw.startswith("=") or raw.startswith("!"):
            current = None  # next banner ends the block
        elif current is not None:
            current.append(raw)
    return sections


def _locate(body: list[str]) -> tuple[str | None, int | None]:
    for raw in reversed(body):
        match = PYTEST_FRAME_RE.match(raw)
        if match:
            return relative_path(match.group(1)), int(match.group(2))
    for raw in body:  # a SyntaxError in a collected module names its own file
        match = PYTEST_FILE_RE.match(raw)
        if match:
            return relative_path(match.group(1)), int(match.group(2))
    for raw in reversed(body):  # e.g. an ImportError: the last frame inside the project
        match = PYTEST_CALL_RE.match(raw)
        if match and relative_path(match.group(1)):
            return relative_path(match.group(1)), int(match.group(2))
    return None, None


def parse_pytest(output: str) -> tuple[list[Failure], int]:
    """Failures and the number of failed plus errored tests."""
    lines = output.splitlines()
    sections = _pytest_sections(lines)
    failures: list[Failure] = []
    for raw in lines:
        match = PYTEST_SUMMARY_RE.match(raw)
        if not match:
            continue
        status, test_id, message = match.groups()
        path, _, name = test_id.partition("::")
        heading = name.replace("::", ".") if name else f"ERROR collecting {path}"
        body = sections.get(heading, [])
        file, line = _locate(body)
        if file is None:
            file = relative_path(path) if path.endswith(".py") else None
        if not message:
            message = next(
                (m.group(1) for ln in reversed(body) if (m := PYTEST_MESSAGE_RE.match(ln))),
                f"{status.lower()} in {test_id}",
            )
        symbol = re.sub(r"\[.*\]$", "", name.rsplit("::", 1)[-1]) if name else None
        failures.append(
            Failure(
                kind="test",
                file=file,
                line=line if line and line >= 1 else None,
                symbol=symbol or None,
                message=message,
            )
        )
    last = next((ln for ln in reversed(lines) if ln.strip()), "")  # "2 failed, 1 passed in 0.1s"
    count = sum(int(n) for n, _ in PYTEST_FINAL_RE.findall(last))
    return failures, count or len(failures)


def parse_check(stage: Stage, result: ExecResult, tail_lines: int) -> CheckResult:
    """Turn one container run into a `CheckResult`; a failed run always has a failure."""
    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
    tail = _tail(output, tail_lines)
    if result.timed_out or result.oom_killed:
        reason = "timed out" if result.timed_out else "killed: out of memory"
        failure = Failure(kind="runtime", message=f"{stage} {reason}", raw_tail=tail)
        return CheckResult(
            stage=stage, passed=False, failures=[failure], duration_s=result.duration_s
        )

    passed = result.exit_code == 0 or (stage == "tests" and result.exit_code == PYTEST_NO_TESTS)
    failures: list[Failure] = []
    failing = 0
    if not passed:
        if stage == "build":
            failures = parse_compileall(output)
        elif stage == "lint":
            failures = parse_ruff(output)
        else:
            failures, failing = parse_pytest(output)
        if not failures:
            message = f"{stage} failed with exit code {result.exit_code}"
            failures = [Failure(kind=KIND[stage], message=message, raw_tail=tail)]
        if stage == "tests":
            failing = failing or len(failures)
    return CheckResult(
        stage=stage,
        passed=passed,
        failures=failures,
        failing_tests=failing,
        duration_s=result.duration_s,
    )
