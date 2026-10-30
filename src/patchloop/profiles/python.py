"""Python profile: detection, manifests, default commands (SPEC §6)."""

import posixpath
import re
import tomllib
from pathlib import Path

from patchloop.config import Config
from patchloop.profiles.base import ProfileError, ProjectSetup
from patchloop.profiles.python_errors import Stage, parse_check
from patchloop.sandbox.runner import ExecResult
from patchloop.schemas import CheckResult

MAX_MANIFEST_BYTES = 1_000_000
GENERATED_REQUIREMENTS = ".patchloop/pyproject-requirements.txt"
TEST_GROUPS = {"dev", "test", "tests", "testing"}  # extras that usually hold pytest and plugins
# Phase 2 has no network, so the project is not installed: its files are put on the path.
# Bytecode goes to the per-container /tmp, never into the workspace: a stale .pyc (same size, same
# second as the patched source) would make the checks run the code from before the patch.
BASE_ENV = {
    "PYTHONPATH": "/work:/work/src",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPYCACHEPREFIX": "/tmp/pycache",
}
SETTINGS_RE = re.compile(r"""DJANGO_SETTINGS_MODULE["']\s*,\s*["']([\w.]+)["']""")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
INCLUDE_RE = re.compile(r"^\s*(?:-r|--requirement)\s*=?\s*(\S+)")


def _read(project: Path, relative: str) -> bytes | None:
    """Read a regular file inside the project; symlinks and big files are ignored."""
    path = project / relative
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        return None
    return path.read_bytes()


def _requirement_files(project: Path) -> dict[str, bytes]:
    """Top-level requirements*.txt plus the files they include with -r."""
    found: dict[str, bytes] = {}
    queue = sorted(p.name for p in project.glob("requirements*.txt"))
    while queue:
        name = queue.pop(0)
        if name in found:
            continue
        content = _read(project, name)
        if content is None:
            continue
        found[name] = content
        for line in content.decode("utf-8", errors="replace").splitlines():
            match = INCLUDE_RE.match(line)
            if not match:
                continue
            included = posixpath.normpath(posixpath.join(posixpath.dirname(name), match.group(1)))
            if not (included.startswith("..") or posixpath.isabs(included)):
                queue.append(included)
    return found


def _pyproject_requirements(content: bytes) -> list[str]:
    """Dependencies from pyproject.toml, without the project itself (PEP 621 and PEP 735)."""
    try:
        data = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ProfileError(f"cannot parse pyproject.toml: {exc}") from exc
    project = data.get("project", {})
    requirements = [r for r in project.get("dependencies", []) if isinstance(r, str)]
    for name, group in project.get("optional-dependencies", {}).items():
        if name.lower() in TEST_GROUPS:
            requirements += [r for r in group if isinstance(r, str)]
    for name, group in data.get("dependency-groups", {}).items():
        if name.lower() in TEST_GROUPS:
            requirements += [r for r in group if isinstance(r, str)]  # skips include-group tables
    return requirements


def _dependency_names(manifests: dict[str, bytes], generated: list[str]) -> set[str]:
    lines = list(generated)
    for name, content in manifests.items():
        if name.endswith(".txt"):
            lines += content.decode("utf-8", errors="replace").splitlines()
    names = set()
    for line in lines:
        match = NAME_RE.match(line.strip())
        if match:
            names.add(re.sub(r"[-_.]+", "-", match.group(0)).lower())
    return names


class PythonProfile:
    name = "python"

    def detect(self, project: Path) -> bool:
        if any((project / m).is_file() for m in ("pyproject.toml", "setup.py", "setup.cfg")):
            return True
        return any(project.glob("requirements*.txt")) or any(project.glob("*.py"))

    def setup(self, project: Path, config: Config) -> ProjectSetup:
        manifests = _requirement_files(project)
        generated: list[str] = []
        pyproject = _read(project, "pyproject.toml")
        if pyproject is not None:
            generated = _pyproject_requirements(pyproject)
            if generated:
                manifests[GENERATED_REQUIREMENTS] = ("\n".join(generated) + "\n").encode()

        names = _dependency_names(manifests, generated)
        variant = "generic"
        env = dict(BASE_ENV)
        tools = ["pytest", "ruff"]  # what the profile itself runs
        manage = _read(project, "manage.py")
        if manage is not None:
            variant = "django"
            tools.append("pytest-django")
            match = SETTINGS_RE.search(manage.decode("utf-8", errors="replace"))
            if match:
                env["DJANGO_SETTINGS_MODULE"] = match.group(1)
        elif "fastapi" in names:
            variant = "fastapi"
            tools.append("httpx")  # needed by fastapi.testclient

        files = [f"-r {name}" for name in sorted(manifests)]
        install = "pip install --no-cache-dir " + " ".join([*files, *tools])
        return ProjectSetup(
            profile=self.name,
            variant=variant,
            image=config.image or config.sandbox.base_image,
            manifests=manifests,
            install=config.install or install,
            build=config.build or "python -m compileall -q .",
            lint=config.lint or "ruff check --output-format=concise .",
            test=config.test or "pytest -x -q -p no:cacheprovider",
            env={**env, **config.env},
        )

    def parse_check(self, stage: Stage, result: ExecResult, tail_lines: int) -> CheckResult:
        return parse_check(stage, result, tail_lines)
