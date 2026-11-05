"""Contracts between agents and layers (SPEC §5): Pydantic models, versioned.

Changing any field means bumping SCHEMA_VERSION so that old runs stay reproducible.
"""

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    @field_validator("files")
    @classmethod
    def _safe_paths(cls, files: dict[str, str]) -> dict[str, str]:
        """Reject unsafe paths at the contract itself, so no code can build a bad `Patch`.

        The paths come from the model, which is untrusted input: a path like `../../x` or
        `/etc/passwd` would let a patch write outside the project copy, and `.git` must stay
        untouched. Checking here means every consumer (apply, diff, restore) gets safe paths.
        """
        if not files:
            raise ValueError("patch must contain at least one file")
        for name in files:
            path = PurePosixPath(name)
            if not name or "\\" in name or "\0" in name:
                raise ValueError(f"invalid path: {name!r}")
            parts = name.split("/")  # PurePosixPath would hide "." and "//"
            if path.is_absolute() or ".." in parts or "." in parts or "" in parts:
                raise ValueError(f"path must be relative and inside the project: {name!r}")
            if ".git" in path.parts:
                raise ValueError(f"path must not touch .git: {name!r}")
        return files


class TestPlan(_Contract):
    """Tester output: the content of ONE new test file; its path is chosen by code."""

    __test__ = False  # not a pytest class, despite the name

    content: str
    explanation: str

    @field_validator("content")
    @classmethod
    def _not_blank(cls, content: str) -> str:
        if not content.strip():
            raise ValueError("the test file must not be empty")
        return content


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
