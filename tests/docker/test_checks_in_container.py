"""Checks in a real container. Opt-in: `uv run pytest -m docker`. Needs Docker and network
for the first image build (pip install)."""

import pytest

from patchloop.checks import run_checks
from patchloop.config import Config
from patchloop.profiles.python import PythonProfile
from patchloop.sandbox import ensure_image, workspace

pytestmark = pytest.mark.docker


def test_buggy_project_fails_on_the_test_and_a_fix_passes(docker_client, buggy_project, tmp_path):
    config = Config()
    project = buggy_project
    profile = PythonProfile()
    setup = profile.setup(project, config)
    image = ensure_image(docker_client, config.sandbox, setup.manifests, setup.install)
    with workspace(project, parent=tmp_path) as work:
        before = run_checks(docker_client, config, profile, setup, image, work)
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
        after = run_checks(docker_client, config, profile, setup, image, work)
        assert all(r.passed for r in after)
    assert (project / "pkg" / "calc.py").read_text(encoding="utf-8").endswith("a - b\n")
