"""Run records on disk until the database exists (decision 29, SPEC §10).

`fix` saves one record per run; `apply` reads it. The record is a file the host wrote earlier, so
it is read as input: the id is checked against its format before it becomes a path, and a record
of another schema version is refused instead of guessed at.
"""

import json
import os
import re
import secrets
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from patchloop.config import Config
from patchloop.schemas import SCHEMA_VERSION, RunResult

RUN_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")  # YYYYMMDD-HHMMSS-<4 hex>; also a branch name
RECORD_FILE = "record.json"
HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


class RunRecordError(RuntimeError):
    """A run record cannot be saved or loaded."""


class ApplyError(RuntimeError):
    """A stored fix cannot be put on a branch; the project is left as it was."""


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = SCHEMA_VERSION
    run_id: str
    project: str  # resolved path of the original project
    issue: str | None = None
    result: RunResult


def new_run_id(now: datetime) -> str:
    return f"{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _check_id(run_id: str) -> None:
    if not RUN_ID.fullmatch(run_id):
        raise RunRecordError(f"invalid run id {run_id!r}: expected YYYYMMDD-HHMMSS-xxxx")


def save_record(runs_dir: Path, record: RunRecord) -> Path:
    """Write `<runs_dir>/<run_id>/record.json`; an existing run is never overwritten."""
    _check_id(record.run_id)
    folder = runs_dir.expanduser() / record.run_id
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise RunRecordError(f"run {record.run_id} already exists") from exc
    target = folder / RECORD_FILE
    handle, temp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(record.model_dump_json(indent=2))
        os.replace(temp, target)  # atomic: `apply` never sees half a record
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return target


def load_record(runs_dir: Path, run_id: str) -> RunRecord:
    _check_id(run_id)
    path = runs_dir.expanduser() / run_id / RECORD_FILE
    if not path.is_file():
        raise RunRecordError(f"no run {run_id} in {runs_dir}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise RunRecordError(
                f"run {run_id} has schema version {version}, this patchloop reads {SCHEMA_VERSION}"
            )
        record = RunRecord.model_validate(data)
        if record.run_id != run_id:
            raise RunRecordError(f"run id {record.run_id} in the record does not match {run_id}")
        return record
    except RunRecordError:
        raise
    except (OSError, ValueError, AttributeError, ValidationError) as exc:
        raise RunRecordError(f"record of run {run_id} is unreadable: {exc}") from exc


# ---- apply ------------------------------------------------------------------------------------


def _git(
    project: Path, *args: str, timeout: float, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run git in `project` without a shell; a missing git or a hang is an `ApplyError`."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=project,
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApplyError(f"git could not be run: {exc}") from exc


def _safe_path(name: str) -> str:
    prefix, _, relative = name.partition("/")
    parts = relative.split("/")
    if prefix not in ("a", "b") or not relative:
        raise ApplyError(f"unexpected path in the diff: {name!r}")
    if "\\" in relative or "\0" in relative or relative.startswith("/"):
        raise ApplyError(f"unsafe path in the diff: {name!r}")
    if {"", ".", ".."} & set(parts) or ".git" in (part.lower() for part in parts):
        raise ApplyError(f"path outside the project in the diff: {name!r}")
    return relative


def diff_paths(diff: str) -> list[str]:
    """Files the diff writes, after checking that it holds nothing but plain unified hunks.

    The record is a file on disk, so the diff is input: only `---`/`+++`/`@@` lines and hunk
    bodies are accepted (no renames, modes or binary patches), and every path must stay inside
    the project. Header lines are told from hunk lines by the line counts in `@@`.
    """
    changed: set[str] = set()
    old = new = 0  # lines still expected in the current hunk
    lines = diff.split("\n")  # not splitlines: form feed and the like are inside a line
    if lines[-1] == "":
        lines.pop()
    for line in lines:
        if old > 0 or new > 0:
            if line.startswith("\\"):
                continue
            marker = line[:1]
            old -= marker in ("-", " ", "")
            new -= marker in ("+", " ", "")
            if marker not in ("-", "+", " ", ""):
                raise ApplyError(f"malformed hunk in the diff: {line!r}")
        elif line.startswith("--- "):
            if line[4:] != "/dev/null":
                _safe_path(line[4:])
        elif line.startswith("+++ "):
            if line[4:] == "/dev/null":
                raise ApplyError("the diff deletes a file, which a fix never does")
            changed.add(_safe_path(line[4:]))
        elif match := HUNK.fullmatch(line):
            old = int(match[1]) if match[1] is not None else 1
            new = int(match[2]) if match[2] is not None else 1
        elif not line.startswith("\\"):
            raise ApplyError(f"unexpected line in the diff: {line!r}")
    return sorted(changed)


def apply_record(record: RunRecord, git_timeout_s: float | None = None) -> list[str]:
    """Put the stored fix on the branch `patchloop/<run_id>` as an unstaged working-tree change.

    No commit, no push, no `git add`. Every refusal happens before anything is changed; if the
    last step fails after the branch exists, the original branch is restored and the new one
    deleted. Only the fix is applied: the generated test is not in the diff.
    """
    limit = git_timeout_s if git_timeout_s is not None else Config().git_timeout_s

    def git(project: Path, *args: str, input: str | None = None):
        return _git(project, *args, timeout=limit, input=input)

    diff = record.result.diff
    if not diff:
        raise ApplyError(f"run {record.run_id} has no diff to apply ({record.result.status})")
    changed = diff_paths(diff)
    project = Path(record.project)
    if not project.is_dir():
        raise ApplyError(f"the project {project} no longer exists")
    inside = git(project, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise ApplyError(f"{project} is not a git work tree; apply needs git")
    if git(project, "rev-parse", "--verify", "--quiet", "HEAD").returncode != 0:
        raise ApplyError("the repository has no commits yet")
    status = git(project, "status", "--porcelain")
    if status.returncode != 0 or status.stdout.strip():
        raise ApplyError("the working tree is not clean: commit or stash the changes first")
    branch = f"patchloop/{record.run_id}"
    if git(project, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
        raise ApplyError(f"branch {branch} already exists")
    checked = git(project, "apply", "--check", "-", input=diff)
    if checked.returncode != 0:
        why = checked.stderr.strip()
        raise ApplyError(f"the diff does not apply to the current project: {why}")
    current = git(project, "branch", "--show-current").stdout.strip()
    head = git(project, "rev-parse", "HEAD").stdout.strip()
    created = git(project, "switch", "-c", branch)
    if created.returncode != 0:
        raise ApplyError(f"cannot create branch {branch}: {created.stderr.strip()}")
    try:
        applied = git(project, "apply", "-", input=diff)
        if applied.returncode != 0:
            raise ApplyError(f"git apply failed: {applied.stderr.strip()}")
    except ApplyError:
        back = ["switch", current] if current else ["switch", "--detach", head]
        git(project, *back)
        git(project, "branch", "-D", branch)
        raise
    return changed
