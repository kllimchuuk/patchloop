import os

import pytest

from patchloop.config import Config
from patchloop.profiles import ProfileError, PythonProfile, detect_profile
from patchloop.profiles.python import GENERATED_REQUIREMENTS


def _project(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _setup(root, files, **overrides):
    config = Config(**overrides)
    return PythonProfile().setup(_project(root, files), config)


def test_detects_python_by_manifest_or_source(tmp_path):
    assert detect_profile(_project(tmp_path / "a", {"requirements.txt": ""})).name == "python"
    assert detect_profile(_project(tmp_path / "b", {"pyproject.toml": ""})).name == "python"
    assert detect_profile(_project(tmp_path / "c", {"main.py": "x = 1\n"})).name == "python"


def test_unknown_project_is_an_error(tmp_path):
    with pytest.raises(ProfileError):
        detect_profile(_project(tmp_path, {"README.md": "hi"}))


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
    project = _project(tmp_path / "p", {"main.py": ""})
    os.symlink(secret, project / "requirements.txt")
    assert _setup_manifests(project) == {}


def _setup_manifests(project):
    return PythonProfile().setup(project, Config()).manifests


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
