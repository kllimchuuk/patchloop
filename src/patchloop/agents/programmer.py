"""Programmer: turns failures into a `Patch` of whole files (SPEC §4).

The model only proposes. What happens next (apply, re-check, stop, roll back) is decided by code
in the graph. All prompt text of this agent is in this file.
"""

from collections.abc import Collection, Sequence
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
"excerpt" are too big to rewrite, and files shown as "read-only" must not be changed: read \
them, but do not return them.
- Make the smallest change that fixes the problem. Keep the existing style.
- `explanation`: a short description of the cause and of the change, in this language: {language}.
- If earlier attempts are listed, do not repeat them; they did not work.
"""


@dataclass(frozen=True)
class HistoryEntry:
    """One earlier attempt as the Programmer sees it: what it said and what was still wrong."""

    explanation: str  # for a refused answer: why it was refused
    failures: list[Failure]
    refused: bool = False  # the answer was not applied, so no checks ran after it


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


def _history_section(history: Sequence[HistoryEntry]) -> str:
    entries = []
    for number, entry in enumerate(history, 1):
        if entry.refused:
            entries.append(f"Attempt {number} was refused and not applied: {entry.explanation}")
            continue
        left = _format_failures(entry.failures, HISTORY_FAILURES) or "(no errors left)"
        entries.append(f"Attempt {number}: {entry.explanation.strip()}\nErrors after it:\n{left}")
    return "## Earlier attempts (they did not work)\n" + "\n\n".join(entries)


def code_section(files: Sequence[ContextFile], read_only: Collection[str] = ()) -> str:
    def kind(f: ContextFile) -> str:
        return "read-only" if f.path in read_only else "full" if f.whole else "excerpt"

    blocks = [f"### FILE {f.path} ({kind(f)})\n{f.text}\n### END FILE" for f in files]
    return "## Code\n" + ("\n\n".join(blocks) or "(no files could be read)")


def build_messages(
    files: Sequence[ContextFile],
    failures: Sequence[Failure],
    issue: str | None,
    history: Sequence[HistoryEntry],
    review_comments: Sequence[str],
    language: str,
    read_only: Collection[str] = (),
) -> Messages:
    parts: list[str] = []
    if issue:
        parts.append(f"## Bug description\n{issue.strip()}")
    parts.append("## Current errors\n" + (_format_failures(failures, MAX_FAILURES) or "(none)"))
    if history:
        parts.append(_history_section(history))
    if review_comments:
        parts.append("## Reviewer comments\n" + "\n".join(f"- {c}" for c in review_comments))
    parts.append(code_section(files, read_only))
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(language=language)},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _check_patch(
    workdir: Path, patch: Patch, files: Sequence[ContextFile], protected: Collection[str]
) -> str | None:
    """Why the patch must not be applied, or None. The model never overwrites unseen code."""
    full = {f.path for f in files if f.whole}
    changed = False
    for path, content in patch.files.items():
        try:
            current = read_text(workdir, path)
        except PatchError as exc:
            return str(exc)
        if path in protected and current != content:
            return f"the patch changes {path}, a generated test that must not be edited"
        if current is not None and path not in full:
            return f"the patch rewrites {path}, which was not shown in full"
        changed = changed or (current != content and path not in protected)
    return None if changed else "the patch changes nothing"


def _without_echoes(workdir: Path, patch: Patch, protected: Collection[str]) -> Patch:
    """A model often returns a read-only file unchanged next to its fix: drop that copy."""
    kept = {
        path: content
        for path, content in patch.files.items()
        if not (path in protected and _same(workdir, path, content))
    }
    if len(kept) == len(patch.files) or not kept:
        return patch  # nothing dropped, or nothing left (the checks then report it)
    return Patch(files=kept, explanation=patch.explanation)


def _same(workdir: Path, path: str, content: str) -> bool:
    try:
        return read_text(workdir, path) == content
    except PatchError:
        return False


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
    protected: Collection[str] = (),
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
        files, failures, issue, history, review_comments, language, protected
    )
    try:
        patch = llm.complete(messages, Patch)
    except LLMInvalidAnswer as exc:
        return ProgrammerResult(None, str(exc))
    patch = _without_echoes(workdir, patch, protected)
    problem = _check_patch(workdir, patch, files, protected)
    return ProgrammerResult(None, problem) if problem else ProgrammerResult(patch)
