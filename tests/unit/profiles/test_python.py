import os

import pytest
from support.projects import write_files

from patchloop.config import Config
from patchloop.profiles.base import ProfileError
from patchloop.profiles.python import GENERATED_REQUIREMENTS, PythonProfile
from patchloop.profiles.registry import detect_profile
from patchloop.schemas import CheckResult, Failure


def _setup(root, files, **overrides):
    return PythonProfile().setup(write_files(root, files), Config(**overrides))


def test_detects_python_by_manifest_or_source(tmp_path):
    assert detect_profile(write_files(tmp_path / "a", {"requirements.txt": ""})).name == "python"
    assert detect_profile(write_files(tmp_path / "b", {"pyproject.toml": ""})).name == "python"
    assert detect_profile(write_files(tmp_path / "c", {"main.py": "x = 1\n"})).name == "python"


def test_unknown_project_is_an_error(tmp_path):
    with pytest.raises(ProfileError):
        detect_profile(write_files(tmp_path, {"README.md": "hi"}))


def test_generic_project_defaults(tmp_path):
    setup = _setup(tmp_path, {"requirements.txt": "requests\n"})
    assert setup.variant == "generic"
    assert setup.image == Config().sandbox.base_image
    assert setup.manifests == {"requirements.txt": b"requests\n"}
    assert setup.install == "pip install --no-cache-dir -r requirements.txt pytest ruff"
    assert setup.build == "python -m compileall -q ."
    assert setup.lint.startswith("ruff check")
    assert setup.test.startswith("pytest")
    assert setup.env["PYTHONPATH"] == "/work:/work/src"
    assert setup.env["PYTHONPYCACHEPREFIX"].startswith("/tmp/")  # not in the workspace


def test_django_detected_by_manage_py_with_settings(tmp_path):
    manage = 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shop.settings")\n'
    setup = _setup(tmp_path, {"manage.py": manage, "requirements.txt": "django\n"})
    assert setup.variant == "django"
    assert setup.env["DJANGO_SETTINGS_MODULE"] == "shop.settings"
    assert "pytest-django" in setup.install


def test_fastapi_detected_in_requirements_and_pyproject(tmp_path):
    a = _setup(tmp_path / "a", {"requirements.txt": "FastAPI==0.110\nuvicorn\n"})
    toml = '[project]\nname = "x"\ndependencies = ["fastapi>=0.1"]\n'
    b = _setup(tmp_path / "b", {"pyproject.toml": toml})
    assert a.variant == b.variant == "fastapi"
    assert "httpx" in a.install


def test_fastapi_name_must_match_exactly(tmp_path):
    setup = _setup(tmp_path, {"requirements.txt": "fastapi-utils\n"})
    assert setup.variant == "generic"


def test_pyproject_dependencies_become_a_generated_requirements_file(tmp_path):
    toml = """
[project]
name = "x"
dependencies = ["requests>=2"]

[project.optional-dependencies]
dev = ["pytest-mock"]
docs = ["sphinx"]

[dependency-groups]
test = ["coverage", {include-group = "dev"}]
"""
    setup = _setup(tmp_path, {"pyproject.toml": toml})
    text = setup.manifests[GENERATED_REQUIREMENTS].decode()
    assert text.splitlines() == ["requests>=2", "pytest-mock", "coverage"]
    assert f"-r {GENERATED_REQUIREMENTS}" in setup.install


def test_bad_pyproject_is_an_error(tmp_path):
    with pytest.raises(ProfileError):
        _setup(tmp_path, {"pyproject.toml": "[project\n"})


def test_requirements_includes_are_followed_inside_the_project_only(tmp_path):
    files = {
        "requirements.txt": "-r requirements/base.txt\n-r ../outside.txt\n",
        "requirements/base.txt": "flask\n",
    }
    setup = _setup(tmp_path / "p", files)
    assert set(setup.manifests) == {"requirements.txt", "requirements/base.txt"}


def test_symlinked_manifest_is_ignored(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOKEN\n", encoding="utf-8")
    project = write_files(tmp_path / "p", {"main.py": ""})
    os.symlink(secret, project / "requirements.txt")
    assert PythonProfile().setup(project, Config()).manifests == {}


def test_patchloop_yml_overrides_win(tmp_path):
    setup = _setup(
        tmp_path,
        {"requirements.txt": "x\n", "manage.py": ""},
        image="python:3.12",
        install="pip install .",
        build="true",
        test="pytest -x",
        lint="ruff check src",
        env={"SECRET_KEY": "test", "PYTHONPATH": "/work"},
    )
    assert setup.image == "python:3.12"
    assert (setup.install, setup.build, setup.test, setup.lint) == (
        "pip install .",
        "true",
        "pytest -x",
        "ruff check src",
    )
    assert setup.env["SECRET_KEY"] == "test"
    assert setup.env["PYTHONPATH"] == "/work"
    assert setup.env["PYTHONDONTWRITEBYTECODE"] == "1"


def _run(*failures, passed=False):
    return CheckResult(stage="tests", passed=passed, failures=list(failures), failing_tests=1)


def _fail(message, symbol="test_a", kind="test"):
    return Failure(kind=kind, file="tests/test_g.py", line=3, symbol=symbol, message=message)


@pytest.mark.parametrize(
    ("result", "verdict"),
    [
        (CheckResult(stage="tests", passed=True), "passes"),
        (_run(_fail("assert -1 == 3")), "reproduces"),
        (_run(_fail("AssertionError: assert 1 == 2")), "reproduces"),
        (_run(_fail("ZeroDivisionError: division by zero")), "reproduces"),  # the bug itself
        (_run(_fail("ModuleNotFoundError: No module named 'x'", symbol=None)), "broken"),
        (_run(_fail("ImportError: cannot import name 'f'")), "broken"),
        (_run(_fail("NameError: name 'y' is not defined")), "broken"),
        (_run(_fail("SyntaxError: invalid syntax", symbol=None)), "broken"),
        (_run(_fail("tests timed out", kind="runtime", symbol=None)), "broken"),
        (_run(_fail("tests failed with exit code 2", symbol=None)), "broken"),  # unparsed output
    ],
)
def test_a_generated_test_run_is_classified(result, verdict):
    assert PythonProfile().classify_test_run(result) == verdict


def test_test_command_for_one_file_is_quoted(tmp_path):
    setup = _setup(tmp_path, {"requirements.txt": ""})
    profile = PythonProfile()
    assert profile.test_file_command(setup, "tests/test_g.py").endswith(" tests/test_g.py")
    assert profile.test_file_command(setup, "a b.py").endswith(" 'a b.py'")
