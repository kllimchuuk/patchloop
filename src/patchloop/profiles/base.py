"""Language profile contract (SPEC §6): everything language-specific lives behind it."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from patchloop.config import Config
from patchloop.sandbox.runner import ExecResult
from patchloop.schemas import CheckResult


class ProfileError(RuntimeError):
    """No profile fits the project, or the project cannot be set up."""


@dataclass(frozen=True)
class ProjectSetup:
    """What the sandbox needs to prepare an image and run the checks for one project."""

    profile: str
    variant: Literal["django", "fastapi", "generic"]
    image: str  # base image for phase 1
    manifests: dict[str, bytes]  # relative path -> content, copied into the image build
    install: str
    build: str
    lint: str
    test: str
    env: dict[str, str] = field(default_factory=dict)


class LanguageProfile(Protocol):
    name: str

    def detect(self, project: Path) -> bool: ...

    def setup(self, project: Path, config: Config) -> ProjectSetup: ...

    def parse_check(
        self, stage: Literal["build", "lint", "tests"], result: ExecResult, tail_lines: int
    ) -> CheckResult: ...
