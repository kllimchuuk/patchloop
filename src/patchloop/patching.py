"""Apply a Programmer patch to the workspace copy and compute diffs (SPEC §4, §12).

The workspace is untrusted after any run: code in the container may have replaced a directory or
a file with a symlink to something on the host. So nothing here follows a symlink, and a path that
passes through one is an error.
"""

import difflib
import hashlib
import os
from collections.abc import Iterable
from pathlib import Path

from patchloop.schemas import Patch

NO_NEWLINE = "\\ No newline at end of file\n"


class PatchError(RuntimeError):
    """The patch cannot be applied or compared safely."""


def _resolve(root: Path, relative: str) -> Path:
    """`root/relative`, refusing symlinks anywhere along the way (the file itself may be absent)."""
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise PatchError(f"{relative}: path goes through a symlink")
    return current


def patch_hash(patch: Patch) -> str:
    """Stable hash of the file contents, independent of order and of the explanation."""
    digest = hashlib.sha256()
    for path in sorted(patch.files):
        for chunk in (path, patch.files[path]):
            data = chunk.encode("utf-8")
            digest.update(len(data).to_bytes(8, "big"))  # length prefix: "a"+"bc" != "ab"+"c"
            digest.update(data)
    return digest.hexdigest()


def apply_patch(workdir: Path, patch: Patch) -> None:
    """Write whole files into `workdir`. Paths are checked first: a bad one writes nothing."""
    prepared: dict[str, bytes] = {}
    for relative, content in patch.files.items():
        if _resolve(workdir, relative).is_dir():
            raise PatchError(f"{relative}: is a directory")
        try:
            prepared[relative] = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise PatchError(f"{relative}: content is not valid text") from exc
    for relative, data in prepared.items():
        target = _resolve(workdir, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags, 0o644)  # O_NOFOLLOW: a symlink at the end is an error
        except OSError as exc:
            raise PatchError(f"cannot write {relative}: {exc}") from exc
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)


def read_text(root: Path, relative: str) -> str | None:
    """File text, or None if it does not exist; symlinks and non-UTF-8 files are errors."""
    path = _resolve(root, relative)
    if not path.exists():
        return None
    if not path.is_file():
        raise PatchError(f"{relative}: not a regular file")
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(f"{relative}: not a UTF-8 text file") from exc


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def make_diff(original: Path, changed: Path, paths: Iterable[str]) -> str:
    """Unified diff of `paths` between two trees; files that are identical are left out."""
    out: list[str] = []
    for relative in sorted(set(paths)):
        before, after = read_text(original, relative), read_text(changed, relative)
        if before == after or after is None:
            continue
        old_name = f"a/{relative}" if before is not None else "/dev/null"
        diff = difflib.unified_diff(
            _lines(before or ""), _lines(after), old_name, f"b/{relative}", lineterm="\n"
        )
        for line in diff:
            out.append(line if line.endswith("\n") else line + "\n" + NO_NEWLINE)
    return "".join(out)


def restore_files(original: Path, workdir: Path, paths: Iterable[str]) -> None:
    """Put `paths` in `workdir` back as they are in `original`; files that are new are removed.

    A symlink at the file itself is removed (the link, not what it points to); a symlink in a
    parent directory is an error, as everywhere else in this module.
    """
    for relative in paths:
        text = read_text(original, relative)
        parent = os.path.dirname(relative)
        if parent:
            _resolve(workdir, parent)  # before touching anything: no symlinked directories
        target = workdir / relative
        if target.is_symlink() or (text is None and target.is_file()):
            target.unlink()
        if text is not None:
            apply_patch(workdir, Patch(files={relative: text}, explanation="restore"))
