"""Working copy of the project: the original is never modified (SPEC §3)."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

PREFIX = "patchloop-"
IGNORED = (
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
)


def make_workspace(project: Path, parent: Path | None = None) -> Path:
    """Copy `project` into a fresh temp directory and return it; remove it with remove_workspace.

    Symlinks are copied as links, not followed, so nothing outside the project gets into the copy.
    """
    if not project.is_dir():
        raise FileNotFoundError(f"project directory not found: {project}")
    root = Path(tempfile.mkdtemp(prefix=PREFIX, dir=parent))
    shutil.copytree(
        project, root, symlinks=True, ignore=shutil.ignore_patterns(*IGNORED), dirs_exist_ok=True
    )
    return root


def remove_workspace(workspace: Path) -> None:
    """Delete a directory made by make_workspace; refuse anything else."""
    if not workspace.name.startswith(PREFIX):
        raise ValueError(f"not a patchloop workspace: {workspace}")
    shutil.rmtree(workspace)


@contextmanager
def workspace(project: Path, parent: Path | None = None) -> Iterator[Path]:
    path = make_workspace(project, parent)
    try:
        yield path
    finally:
        remove_workspace(path)
