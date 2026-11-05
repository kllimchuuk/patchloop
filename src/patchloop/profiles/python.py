"""Python profile: detection, manifests, default commands (SPEC §6)."""

import posixpath
import re
import shlex
import tomllib
from pathlib import Path
from typing import Literal

from patchloop.config import Config
from patchloop.profiles.base import ProfileError, ProjectSetup, TestVerdict
from patchloop.profiles.python_errors import Stage, parse_check
from patchloop.sandbox.runner import ExecResult
from patchloop.schemas import CheckResult

Variant = Literal["django", "fastapi", "generic"]
MAX_MANIFEST_BYTES = 1_000_000
# A failing generated test is a reproduction only if it fails inside the test body. These
# exceptions mean that the test itself is wrong (or cannot be collected).
BROKEN_TEST_ERRORS = (
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "IndentationError",
    "NameError",
    "fixture ",
)
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


def _included_files(name: str, content: bytes) -> list[str]:
    """Files that a requirements file includes with -r, kept inside the project."""
    included = []
    for line in content.decode("utf-8", errors="replace").splitlines():
        match = INCLUDE_RE.match(line)
        if not match:
            continue
        path = posixpath.normpath(posixpath.join(posixpath.dirname(name), match.group(1)))
        if not (path.startswith("..") or posixpath.isabs(path)):
            included.append(path)
    return included


def _requirement_files(project: Path) -> dict[str, bytes]:
    """Top-level requirements*.txt plus the files they include with -r."""
    found: dict[str, bytes] = {}
    queue = sorted(p.name for p in project.glob("requirements*.txt"))
    while queue:
        name = queue.pop(0)
        if name in found:
            continue
        content = _read(project, name)
        if content is not None:
            found[name] = content
            queue += _included_files(name, content)
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


def _add_pyproject_manifest(project: Path, manifests: dict[str, bytes]) -> list[str]:
    """Put the pyproject.toml dependencies into `manifests` as a generated requirements file."""
    pyproject = _read(project, "pyproject.toml")
    generated = _pyproject_requirements(pyproject) if pyproject is not None else []
    if generated:
        manifests[GENERATED_REQUIREMENTS] = ("\n".join(generated) + "\n").encode()
    return generated


def _variant(project: Path, names: set[str]) -> tuple[Variant, dict[str, str], list[str]]:
    """Framework variant, its environment and the extra tools to install next to pytest."""
    env = dict(BASE_ENV)
    tools = ["pytest", "ruff"]  # what the profile itself runs
    manage = _read(project, "manage.py")
    if manage is not None:
        tools.append("pytest-django")
        match = SETTINGS_RE.search(manage.decode("utf-8", errors="replace"))
        if match:
            env["DJANGO_SETTINGS_MODULE"] = match.group(1)
        return "django", env, tools
    if "fastapi" in names:
        return "fastapi", env, [*tools, "httpx"]  # httpx is needed by fastapi.testclient
    return "generic", env, tools


class PythonProfile:
    name = "python"
    test_framework = "pytest"
    generated_test_path = "tests/test_patchloop_generated.py"

    def detect(self, project: Path) -> bool:
        if any((project / m).is_file() for m in ("pyproject.toml", "setup.py", "setup.cfg")):
            return True
        return any(project.glob("requirements*.txt")) or any(project.glob("*.py"))

    def setup(self, project: Path, config: Config) -> ProjectSetup:
        manifests = _requirement_files(project)
        generated = _add_pyproject_manifest(project, manifests)
        variant, env, tools = _variant(project, _dependency_names(manifests, generated))
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

    def test_file_command(self, setup: ProjectSetup, path: str) -> str:
        return f"{setup.test} {shlex.quote(path)}"

    def classify_test_run(self, result: CheckResult) -> TestVerdict:
        if result.passed:
            return "passes"
        for failure in result.failures:
            # No symbol: a collection error or output the parser could not read.
            if failure.kind == "runtime" or failure.symbol is None:
                return "broken"
            if failure.message.startswith(BROKEN_TEST_ERRORS):
                return "broken"
        return "reproduces"
