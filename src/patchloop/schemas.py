"""Contracts between agents and layers (SPEC §5): Pydantic models, versioned.

Changing any field means bumping SCHEMA_VERSION so that old runs stay reproducible.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Failure(_Contract):
    """One error found by a check."""

    kind: Literal["build", "test", "lint", "runtime"]
    file: str | None = None
    line: int | None = Field(None, ge=1)
    symbol: str | None = None
    message: str
    raw_tail: str = ""  # last lines of the output when the parser found nothing


class CheckResult(_Contract):
    """Result of one check stage in the sandbox."""

    stage: Literal["build", "lint", "tests"]
    passed: bool
    failures: list[Failure] = []
    failing_tests: int = Field(0, ge=0)
    duration_s: float = Field(0.0, ge=0)


class Patch(_Contract):
    """Programmer output: whole new file contents, never partial edits."""

    files: dict[str, str]  # relative path -> full new content
    explanation: str


class Review(_Contract):
    """Reviewer output."""

    approved: bool
    comments: list[str] = []


class Attempt(_Contract):
    """One Programmer attempt with its checks and review."""

    index: int = Field(ge=0)
    patch_hash: str
    checks: list[CheckResult] = []
    review: Review | None = None


class RunResult(_Contract):
    """Final result of a run."""

    schema_version: int = SCHEMA_VERSION
    status: Literal["fixed", "partially_fixed", "not_fixed", "no_bugs_found"]
    best_attempt: int | None = Field(None, ge=0)
    diff: str = ""
    explanation: str = ""
    stop_reason: Literal[
        "success", "iteration_limit", "stagnation", "timeout", "none"
    ] = "none"
    reliability: Literal["normal", "reduced"] = "normal"  # reduced = no generated tests
