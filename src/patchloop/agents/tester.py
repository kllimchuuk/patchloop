"""Tester: writes one new test file for the original code (SPEC §4, §9).

The Tester runs before any fix exists, so it cannot adapt the test to a fix. Which path the file
gets, whether it fails on the original code and what happens next are decided by code in the
graph; all prompt text of this agent is in this file.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from patchloop.agents.programmer import code_section
from patchloop.config import LoopConfig
from patchloop.context.files import gather_context
from patchloop.llm.client import LLMClient, LLMInvalidAnswer, Messages
from patchloop.patching import PatchError, read_text
from patchloop.schemas import TestPlan

TesterMode = Literal["issue", "basic"]
MAX_PREVIOUS_CHARS = 6000
MAX_PATH_VARIANTS = 10

SYSTEM_PROMPT = """\
You are the Tester in an automated bug-fixing system. You write ONE new test file for a project. \
You see the project's original code; nobody has fixed anything yet.

Rules:
- Test framework: {framework}. Follow the style of the project's existing tests if any are shown.
- Reply with the complete content of one test file. The file will be saved as `{path}`; \
do not choose a path and do not change any other file.
- Import the project's code the way the existing tests or modules do.
- Use only the standard library, the test framework and packages the project already uses. \
No network, no real services, no files outside a temporary directory.
- {goal}
- Keep the file short and deterministic. `explanation`: one or two sentences about what the \
test checks, in this language: {language}.
"""

GOALS: dict[str, str] = {
    "issue": (
        "The test must FAIL on the current code because of the bug described below, and it must "
        "pass once that bug is fixed. Assert the correct behaviour; do not assert the buggy one. "
        "If the description is vague, test the most likely failing behaviour."
    ),
    "basic": (
        "The project has no tests. Write a few basic tests of the key public functions or "
        "classes, asserting the behaviour their names and docstrings promise. Cover normal use "
        "first, then one or two edge cases. Do not test private details."
    ),
}


@dataclass(frozen=True)
class TesterResult:
    plan: TestPlan | None
    error: str | None = None  # why there is no plan; the attempt is spent, the run goes on


@dataclass(frozen=True)
class PreviousTry:
    """An earlier attempt of the same run and why it was not accepted (`content` may be empty:
    the answer was not a usable test at all)."""

    content: str
    problem: str


def free_path(workdir: Path, preferred: str) -> str | None:
    """`preferred`, or a numbered variant of it: existing project files are never overwritten.

    None when no variant is free (or the directory is a link): there is nowhere safe to put it.
    """
    stem, dot, suffix = preferred.rpartition(".")
    for number in range(1, MAX_PATH_VARIANTS + 1):
        candidate = preferred if number == 1 else f"{stem}_{number}{dot}{suffix}"
        if not _exists(workdir, candidate):
            return candidate
    return None


def _exists(workdir: Path, relative: str) -> bool:
    try:
        return read_text(workdir, relative) is not None
    except PatchError:
        return True  # unreadable or a link: not a free name


def build_messages(
    mode: TesterMode,
    files_section: str,
    issue: str | None,
    path: str,
    framework: str,
    language: str,
    previous: PreviousTry | None,
) -> Messages:
    parts: list[str] = []
    if issue:
        parts.append(f"## Bug description\n{issue.strip()}")
    if previous:
        text = previous.content
        if len(text) > MAX_PREVIOUS_CHARS:
            text = text[:MAX_PREVIOUS_CHARS] + "\n... (cut)"
        rejected = f"## Your previous answer was rejected\nProblem: {previous.problem}"
        if text:
            rejected += f"\n\n### PREVIOUS TEST\n{text}\n### END PREVIOUS TEST"
        parts.append(rejected)
    parts.append(files_section)
    system = SYSTEM_PROMPT.format(
        framework=framework, path=path, goal=GOALS[mode], language=language
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def propose_test(
    llm: LLMClient,
    workdir: Path,
    loop: LoopConfig,
    *,
    mode: TesterMode,
    path: str,
    framework: str,
    issue: str | None = None,
    previous: PreviousTry | None = None,
    language: str = "en",
) -> TesterResult:
    """Ask the model for a test file. An unusable answer is a spent attempt, not a crash."""
    files = gather_context(
        workdir,
        [],
        total_chars=loop.context_chars,
        max_file_chars=loop.max_file_chars,
        excerpt_lines=loop.excerpt_lines,
    )
    messages = build_messages(
        mode, code_section(files), issue, path, framework, language, previous
    )
    try:
        return TesterResult(llm.complete(messages, TestPlan))
    except LLMInvalidAnswer as exc:
        return TesterResult(None, str(exc))
