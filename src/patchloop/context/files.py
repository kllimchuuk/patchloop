"""Pick the files the Programmer sees: the files named in failures and what they import.

A failing test names the test file, while the bug is usually in the module it imports, so local
imports are followed one level. Whole files are shown while they fit the budget; a bigger file is
an excerpt around the failing line and cannot be rewritten (the model returns whole files only).
"""

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from patchloop.patching import PatchError, read_text
from patchloop.schemas import Failure

SOURCE_ROOTS = ("", "src")
SKIPPED_DIRS = {"__pycache__", "node_modules", "venv", "build", "dist", "site-packages"}


@dataclass(frozen=True)
class ContextFile:
    path: str
    text: str
    whole: bool  # False = an excerpt: shown for reading, must not be rewritten


def _module_files(workdir: Path, module: str) -> list[str]:
    found = []
    for root in SOURCE_ROOTS:
        base = "/".join(p for p in (root, module.replace(".", "/")) if p)
        for candidate in (f"{base}.py", f"{base}/__init__.py"):
            if _exists(workdir, candidate):
                found.append(candidate)
    return found


def _exists(workdir: Path, relative: str) -> bool:
    try:
        return read_text(workdir, relative) is not None
    except PatchError:
        return False


def _imported_modules(tree: ast.AST, relative: str) -> list[str]:
    """Dotted names of every module a parsed file may import, relative imports resolved."""
    package = relative.rsplit("/", 1)[0].replace("/", ".") if "/" in relative else ""
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _from_base(node, package)
            if base:
                modules.append(base)
                modules += [f"{base}.{alias.name}" for alias in node.names]  # "from pkg import mod"
    return modules


def _from_base(node: ast.ImportFrom, package: str) -> str:
    base = node.module or ""
    if not node.level:
        return base
    parts = package.split(".") if package else []
    parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
    return ".".join([*parts, base] if base else parts)


def local_imports(workdir: Path, relative: str, text: str) -> list[str]:
    """Project files imported by `text` (absolute and relative imports), without duplicates."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    files: list[str] = []
    for module in _imported_modules(tree, relative):
        for path in _module_files(workdir, module):
            if path != relative and path not in files:
                files.append(path)
    return files


def project_sources(workdir: Path) -> list[str]:
    """All .py files of the project (symlinks and hidden or build directories skipped)."""
    found = []
    for directory, subdirs, names in os.walk(workdir, followlinks=False):
        subdirs[:] = sorted(
            d for d in subdirs if not d.startswith(".") and d not in SKIPPED_DIRS
            and not (Path(directory) / d).is_symlink()
        )
        base = Path(directory).relative_to(workdir)
        found += [(base / n).as_posix() for n in sorted(names) if n.endswith(".py")]
    return found


def _is_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    in_tests = path.startswith(("tests/", "test/")) or "/tests/" in path
    named = name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
    return in_tests or named


def has_tests(workdir: Path) -> bool:
    """Whether the project has any test file (a lone `conftest.py` is not a test)."""
    return any(_is_test(p) and not p.endswith("conftest.py") for p in project_sources(workdir))


def _excerpt(text: str, line: int | None, radius: int) -> str:
    lines = text.splitlines()
    start = max((line or 1) - 1 - radius, 0)
    return "\n".join(lines[start : start + 2 * radius + 1])


def _read_or_none(workdir: Path, path: str) -> str | None:
    try:
        return read_text(workdir, path)
    except PatchError:
        return None


def _read_candidates(workdir: Path, starts: list[str]) -> dict[str, str]:
    """The start files and what they import (one level), in discovery order."""
    texts: dict[str, str] = {}
    for path in starts:
        text = _read_or_none(workdir, path)
        if text is None:
            continue
        texts[path] = text
        for imported in local_imports(workdir, path, text):
            content = None if imported in texts else _read_or_none(workdir, imported)
            if content is not None:
                texts[imported] = content
    return texts


def _fit_to_budget(
    texts: dict[str, str],
    lines: dict[str, int | None],
    total_chars: int,
    max_file_chars: int,
    excerpt_lines: int,
) -> list[ContextFile]:
    result: list[ContextFile] = []
    remaining = total_chars
    for path in sorted(texts, key=_is_test):  # stable: source files first, in failure order
        text = texts[path]
        if len(text) <= max_file_chars and len(text) <= remaining:
            result.append(ContextFile(path, text, whole=True))
            remaining -= len(text)
            continue
        room = max(min(remaining, max_file_chars), 0)
        excerpt = _excerpt(text, lines.get(path), excerpt_lines)[:room]
        if excerpt:
            result.append(ContextFile(path, excerpt, whole=False))
            remaining -= len(excerpt)
    return result


def gather_context(
    workdir: Path,
    failures: list[Failure],
    *,
    total_chars: int,
    max_file_chars: int,
    excerpt_lines: int,
) -> list[ContextFile]:
    """Files for the prompt, source files before tests, within `total_chars`."""
    lines: dict[str, int | None] = {}
    for failure in failures:
        if failure.file and failure.file not in lines:
            lines[failure.file] = failure.line
    # No failing file to start from (a bug description only): offer the project's own sources.
    texts = _read_candidates(workdir, list(lines) or project_sources(workdir))
    return _fit_to_budget(texts, lines, total_chars, max_file_chars, excerpt_lines)
