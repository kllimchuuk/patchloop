"""Programmer: turns failures into a `Patch` of whole files (SPEC §4).

The model only proposes. What happens next (apply, re-check, stop, roll back) is decided by code
in the graph. All prompt text of this agent is in this file.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from patchloop.config import LoopConfig
from patchloop.context.files import ContextFile, gather_context
from patchloop.llm.client import LLMClient, LLMInvalidAnswer, Messages
from patchloop.patching import PatchError, read_text
from patchloop.schemas import Failure, Patch

MAX_FAILURES = 10
MAX_MESSAGE_CHARS = 500
HISTORY_FAILURES = 5

SYSTEM_PROMPT = """\
You are the Programmer in an automated bug-fixing system. You receive the errors found by the \
build, the linter and the tests of a project, and the code involved. You reply with a fix.

Rules:
- Fix the cause in the project's own code. Do not edit tests, change test expectations, \
silence the linter or skip checks to make them pass, unless the bug description says that the \
test itself is wrong.
- Reply with WHOLE files: for every file you change, its complete new content. Never use \
placeholders such as "... rest unchanged ...".
- Change only files shown below as "full" (you may also add new files). Files shown as \
"excerpt" are too big to rewrite: read them, but do not return them.
- Make the smallest change that fixes the problem. Keep the existing style.
- `explanation`: a short description of the cause and of the change, in this language: {language}.
- If earlier attempts are listed, do not repeat them; they did not work.
"""


@dataclass(frozen=True)
class HistoryEntry:
    """One earlier attempt as the Programmer sees it: what it said and what was still wrong."""

    explanation: str
    failures: tuple[Failure, ...]


@dataclass(frozen=True)
class ProgrammerResult:
    patch: Patch | None
    error: str | None = None  # why there is no patch; the attempt is spent, the run goes on


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + " ..."


def format_failure(failure: Failure) -> str:
    where = failure.file or "unknown file"
    if failure.line:
        where += f":{failure.line}"
    symbol = f" {failure.symbol}" if failure.symbol else ""
    text = f"- [{failure.kind}] {where}{symbol}: {_clip(failure.message, MAX_MESSAGE_CHARS)}"
    if failure.raw_tail:
        tail = "\n".join(f"    {ln}" for ln in failure.raw_tail.splitlines())
        text += "\n  output tail:\n" + tail
    return text


def _format_failures(failures: Sequence[Failure], limit: int) -> str:
    shown = "\n".join(format_failure(f) for f in failures[:limit])
    if len(failures) > limit:
        shown += f"\n- ... and {len(failures) - limit} more"
    return shown


def build_messages(
    files: Sequence[ContextFile],
    failures: Sequence[Failure],
    *,
    issue: str | None,
    history: Sequence[HistoryEntry],
    review_comments: Sequence[str],
    language: str,
) -> Messages:
    parts: list[str] = []
    if issue:
        parts.append(f"## Bug description\n{issue.strip()}")
    parts.append("## Current errors\n" + (_format_failures(failures, MAX_FAILURES) or "(none)"))
    if history:
        entries = []
        for number, entry in enumerate(history, 1):
            left = _format_failures(entry.failures, HISTORY_FAILURES) or "(no errors left)"
            said = entry.explanation.strip()
            entries.append(f"Attempt {number}: {said}\nErrors after it:\n{left}")
        parts.append("## Earlier attempts (they did not work)\n" + "\n\n".join(entries))
    if review_comments:
        parts.append("## Reviewer comments\n" + "\n".join(f"- {c}" for c in review_comments))
    blocks = [
        f"### FILE {f.path} ({'full' if f.whole else 'excerpt'})\n{f.text}\n### END FILE"
        for f in files
    ]
    parts.append("## Code\n" + ("\n\n".join(blocks) or "(no files could be read)"))
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(language=language)},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _check_patch(workdir: Path, patch: Patch, files: Sequence[ContextFile]) -> str | None:
    """Why the patch must not be applied, or None. The model never overwrites unseen code."""
    full = {f.path for f in files if f.whole}
    changed = False
    for path, content in patch.files.items():
        try:
            current = read_text(workdir, path)
        except PatchError as exc:
            return str(exc)
        if current is not None and path not in full:
            return f"the patch rewrites {path}, which was not shown in full"
        changed = changed or current != content
    return None if changed else "the patch changes nothing"


def propose_patch(
    llm: LLMClient,
    workdir: Path,
    failures: Sequence[Failure],
    loop: LoopConfig,
    *,
    issue: str | None = None,
    history: Sequence[HistoryEntry] = (),
    review_comments: Sequence[str] = (),
    language: str = "en",
) -> ProgrammerResult:
    """Ask the model for a fix. An unusable answer is a spent attempt, not a crash.

    An unreachable model is not caught here: that is a configuration error and ends the run.
    """
    files = gather_context(
        workdir,
        list(failures),
        total_chars=loop.context_chars,
        max_file_chars=loop.max_file_chars,
        excerpt_lines=loop.excerpt_lines,
    )
    messages = build_messages(
        files,
        failures,
        issue=issue,
        history=history,
        review_comments=review_comments,
        language=language,
    )
    try:
        patch = llm.complete(messages, Patch)
    except LLMInvalidAnswer as exc:
        return ProgrammerResult(None, str(exc))
    problem = _check_patch(workdir, patch, files)
    return ProgrammerResult(None, problem) if problem else ProgrammerResult(patch)
