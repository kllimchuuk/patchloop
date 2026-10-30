"""Checks in a real container. Opt-in: `uv run pytest -m docker`. Needs Docker and network
for the first image build (pip install)."""

import docker
import pytest

from patchloop.checks import run_checks
from patchloop.config import Config
from patchloop.profiles import PythonProfile
from patchloop.sandbox import ensure_image, workspace

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def client():
    try:
        c = docker.from_env()
        c.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker is not available: {exc}")
    return c


def _project(root):
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "requirements.txt").write_text("", encoding="utf-8")
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "calc.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    (root / "tests" / "test_calc.py").write_text(
        "from pkg.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    return root


def test_buggy_project_fails_on_the_test_and_a_fix_passes(client, tmp_path):
    config = Config()
    project = _project(tmp_path / "proj")
    profile = PythonProfile()
    setup = profile.setup(project, config)
    image = ensure_image(client, config.sandbox, setup.manifests, setup.install)
    with workspace(project, parent=tmp_path) as work:
        before = run_checks(client, config, profile, setup, image, work)
        assert [(r.stage, r.passed) for r in before] == [
            ("build", True),
            ("lint", True),
            ("tests", False),
        ]
        (failure,) = before[2].failures
        assert (failure.file, failure.line, failure.symbol) == ("tests/test_calc.py", 5, "test_add")
        assert before[2].failing_tests == 1

        # Same size as the original, written right after the build stage: with a .pyc in the
        # workspace this fix used to be invisible to pytest (see PYTHONPYCACHEPREFIX).
        fixed = "def add(a, b):\n    return a + b\n"
        (work / "pkg" / "calc.py").write_text(fixed, encoding="utf-8")
        after = run_checks(client, config, profile, setup, image, work)
        assert all(r.passed for r in after)
    assert (project / "pkg" / "calc.py").read_text(encoding="utf-8").endswith("a - b\n")
