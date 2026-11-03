"""Run the project's checks (build, lint, tests) in the sandbox (SPEC §3 step 3)."""

import shlex
from pathlib import Path
from typing import Any

from patchloop.config import Config
from patchloop.profiles.base import LanguageProfile, ProfileError, ProjectSetup
from patchloop.sandbox import run_in_sandbox
from patchloop.schemas import CheckResult


def _argv(stage: str, command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ProfileError(f"cannot parse the {stage} command {command!r}: {exc}") from exc
    if not argv:
        raise ProfileError(f"the {stage} command is empty")
    return argv


def run_checks(
    client: Any,
    config: Config,
    profile: LanguageProfile,
    setup: ProjectSetup,
    image: str,
    workdir: Path,
) -> list[CheckResult]:
    """Build, then lint, then tests. A failed build stops the run: the rest would only repeat it.

    A failed lint does not stop the tests, since the Programmer needs both. Only the variables
    in `setup.env` reach the container, never the host's environment.
    """
    results: list[CheckResult] = []
    for stage, command in (("build", setup.build), ("lint", setup.lint), ("tests", setup.test)):
        raw = run_in_sandbox(
            client, config.sandbox, image, workdir, _argv(stage, command), env=setup.env
        )
        result = profile.parse_check(stage, raw, config.loop.tail_lines)
        results.append(result)
        if stage == "build" and not result.passed:
            break
    return results
