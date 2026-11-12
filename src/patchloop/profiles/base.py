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


TestVerdict = Literal["reproduces", "passes", "broken"]


class LanguageProfile(Protocol):
    name: str
    test_framework: str  # named in the Tester prompt
    generated_test_path: str  # where the Tester's file goes; always a new file

    def detect(self, project: Path) -> bool:
        raise NotImplementedError

    def setup(self, project: Path, config: Config) -> ProjectSetup:
        raise NotImplementedError

    def parse_check(
        self, stage: Literal["build", "lint", "tests"], result: ExecResult, tail_lines: int
    ) -> CheckResult:
        raise NotImplementedError

    def test_file_command(self, setup: ProjectSetup, path: str) -> str:
        """The test command narrowed to one file."""
        raise NotImplementedError

    def parse_test_file(self, result: ExecResult, tail_lines: int) -> CheckResult:
        """Like `parse_check("tests")`, but a file in which no test was found is a failure."""
        raise NotImplementedError

    def classify_test_run(self, result: CheckResult, path: str) -> TestVerdict:
        """`reproduces`: fails the way a test of a bug should; `passes`; `broken`: the test
        itself is wrong (import or syntax error, timeout, unparsed output), not the code.
        `path` is the generated test file, to tell its own errors from errors in the code."""
        raise NotImplementedError
