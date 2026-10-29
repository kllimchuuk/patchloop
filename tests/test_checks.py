from pathlib import Path

import pytest
from fake_docker import FakeDocker

from patchloop import checks
from patchloop.checks import run_checks
from patchloop.config import Config
from patchloop.profiles import ProfileError, PythonProfile
from patchloop.sandbox.runner import ExecResult


def _setup(tmp_path, **overrides):
    (tmp_path / "requirements.txt").write_text("x\n", encoding="utf-8")
    return PythonProfile().setup(tmp_path, Config(**overrides))


def _exec(code=0, out=""):
    return ExecResult(exit_code=code, stdout=out, stderr="", duration_s=0.1)


class Script:
    """Stands in for run_in_sandbox: answers by command, records what was asked."""

    def __init__(self, answers):
        self.answers = answers  # first word of the command -> ExecResult
        self.calls = []

    def __call__(self, client, config, image, workdir, command, env=None):
        self.calls.append((command, env))
        return self.answers.get(command[0], _exec())


def _run(tmp_path, script, monkeypatch, **overrides):
    monkeypatch.setattr(checks, "run_in_sandbox", script)
    setup = _setup(tmp_path, **overrides)
    return run_checks(None, Config(**overrides), PythonProfile(), setup, "img:1", tmp_path)


def test_all_stages_run_in_order_when_everything_passes(tmp_path, monkeypatch):
    script = Script({})
    results = _run(tmp_path, script, monkeypatch)
    assert [r.stage for r in results] == ["build", "lint", "tests"]
    assert all(r.passed for r in results)
    assert [c[0][0] for c in script.calls] == ["python", "ruff", "pytest"]


def test_failed_build_stops_the_run(tmp_path, monkeypatch):
    script = Script({"python": _exec(1, "*** Error compiling './a.py'...\nSyntaxError: x\n")})
    results = _run(tmp_path, script, monkeypatch)
    assert [r.stage for r in results] == ["build"]
    assert not results[0].passed and len(script.calls) == 1


def test_failed_lint_does_not_stop_the_tests(tmp_path, monkeypatch):
    script = Script({"ruff": _exec(1, "a.py:1:1: F401 unused\n"), "pytest": _exec(1, "boom")})
    results = _run(tmp_path, script, monkeypatch)
    assert [(r.stage, r.passed) for r in results] == [
        ("build", True),
        ("lint", False),
        ("tests", False),
    ]


def test_commands_come_from_the_override(tmp_path, monkeypatch):
    script = Script({})
    _run(tmp_path, script, monkeypatch, build="true", lint="ruff check src", test="pytest -k 'a b'")
    assert [c[0] for c in script.calls] == [
        ["true"],
        ["ruff", "check", "src"],
        ["pytest", "-k", "a b"],
    ]


@pytest.mark.parametrize("bad", ["pytest 'unclosed", "   "])
def test_unusable_command_is_a_clear_error(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(checks, "run_in_sandbox", Script({}))
    setup = _setup(tmp_path)
    object.__setattr__(setup, "test", bad)  # ProjectSetup is frozen; simulate a bad override
    with pytest.raises(ProfileError):
        run_checks(None, Config(), PythonProfile(), setup, "img:1", tmp_path)


def test_only_profile_env_reaches_the_container(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "host-secret")
    docker = FakeDocker({"stdout": [b"ok\n"]})
    setup = _setup(tmp_path, env={"SECRET_KEY": "test"})
    run_checks(docker, Config(), PythonProfile(), setup, "img:1", Path(tmp_path))
    assert len(docker.containers.created) == 3
    for _, kwargs in docker.containers.created:
        assert kwargs["environment"]["SECRET_KEY"] == "test"
        assert kwargs["environment"]["PYTHONPATH"] == "/work:/work/src"
        assert "OPENAI_API_KEY" not in kwargs["environment"]
        assert kwargs["network_mode"] == "none"
    assert docker.containers.created[2][0][1] == ["pytest", "-x", "-q", "-p", "no:cacheprovider"]
