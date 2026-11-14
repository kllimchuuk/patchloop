"""Run records on disk until the database exists (decision 29, SPEC §10).

`fix` saves one record per run; `apply` reads it. The record is a file the host wrote earlier, so
it is read as input: the id is checked against its format before it becomes a path, and a record
of another schema version is refused instead of guessed at.
"""

import json
import os
import re
import secrets
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from patchloop.schemas import SCHEMA_VERSION, RunResult

RUN_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")  # YYYYMMDD-HHMMSS-<4 hex>; also a branch name
RECORD_FILE = "record.json"


class RunRecordError(RuntimeError):
    """A run record cannot be saved or loaded."""


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
        return RunRecord.model_validate(data)
    except RunRecordError:
        raise
    except (OSError, ValueError, AttributeError, ValidationError) as exc:
        raise RunRecordError(f"record of run {run_id} is unreadable: {exc}") from exc
