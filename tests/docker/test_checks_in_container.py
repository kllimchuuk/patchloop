"""Checks in a real container. Opt-in: `uv run pytest -m docker`. Needs Docker and network
for the first image build (pip install)."""

import pytest

from patchloop.checks import run_checks, run_test_file
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


def test_generated_tests_are_classified_in_a_container(docker_client, buggy_project, tmp_path):
    config = Config()
    profile = PythonProfile()
    setup = profile.setup(buggy_project, config)
    image = ensure_image(docker_client, config.sandbox, setup.manifests, setup.install)
    generated = {
        "tests/test_gen_repro.py": (
            "from pkg.calc import add\n\n\ndef test_neg():\n    assert add(-1, -2) == -3\n",
            "reproduces",
        ),
        "tests/test_gen_ok.py": (
            "from pkg.calc import add\n\n\ndef test_add_zero():\n    assert add(0, 0) == 0\n",
            "passes",
        ),
        "tests/test_gen_import.py": ("from pkg.nope import add\n", "broken"),
        "tests/test_gen_syntax.py": ("def test_x(:\n", "broken"),
        "tests/test_gen_fixture.py": ("def test_x(client):\n    assert client\n", "broken"),
        "tests/test_gen_attr.py": (
            "import pkg.calc as c\n\n\ndef test_x():\n    assert c.nope(1) == 1\n",
            "broken",
        ),
        "tests/test_gen_empty.py": ("def check_x():\n    assert False\n", "broken"),
    }
    with workspace(buggy_project, parent=tmp_path) as work:
        for path, (text, expected) in generated.items():
            (work / path).write_text(text, encoding="utf-8")
            result = run_test_file(docker_client, config, profile, setup, image, work, path)
            assert profile.classify_test_run(result, path) == expected, (path, result)
