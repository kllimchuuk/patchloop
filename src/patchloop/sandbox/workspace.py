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
ENV_TEMPLATES = (".env.example", ".env.sample", ".env.template")  # no secrets, copied always

_created: set[Path] = set()  # remove_workspace deletes only these


def _ignore(copy_env: bool):
    def ignore(_directory: str, names: list[str]) -> set[str]:
        skipped = {name for name in names if name in IGNORED}
        if not copy_env:
            skipped |= {
                name
                for name in names
                if (name == ".env" or name.startswith(".env.")) and name not in ENV_TEMPLATES
            }
        return skipped

    return ignore


def make_workspace(project: Path, parent: Path | None = None, copy_env: bool = False) -> Path:
    """Copy `project` into a fresh temp directory and return it; remove it with remove_workspace.

    Symlinks are copied as links, not followed, so nothing outside the project gets into the copy.
    The copy is untrusted after a run: code in the container can add symlinks pointing anywhere,
    so host-side code must not follow links from it (decision 23).
    `.env` files are left out unless `copy_env` is set.
    """
    if not project.is_dir():
        raise FileNotFoundError(f"project directory not found: {project}")
    root = Path(tempfile.mkdtemp(prefix=PREFIX, dir=parent))
    _created.add(root)
    shutil.copytree(project, root, symlinks=True, ignore=_ignore(copy_env), dirs_exist_ok=True)
    return root


def remove_workspace(workspace: Path) -> None:
    """Delete a directory made by make_workspace in this process; refuse anything else."""
    if workspace not in _created:
        raise ValueError(f"not a patchloop workspace: {workspace}")
    shutil.rmtree(workspace)
    _created.discard(workspace)


@contextmanager
def workspace(project: Path, parent: Path | None = None, copy_env: bool = False) -> Iterator[Path]:
    path = make_workspace(project, parent, copy_env)
    try:
        yield path
    finally:
        remove_workspace(path)
