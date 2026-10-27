from pathlib import Path

import pytest
from fake_docker import FakeDocker, api_error, wait_timeout
from requests.exceptions import ConnectionError

from patchloop.config import SandboxConfig
from patchloop.sandbox import SandboxError, run_in_sandbox
from patchloop.sandbox.runner import container_user

CFG = SandboxConfig(user="1000:1000")


def run(docker, config=CFG):
    return run_in_sandbox(docker, config, "img:1", Path("/tmp/w"), ["pytest", "-x"])


def test_container_is_isolated_and_limited():
    docker = FakeDocker({"stdout": [b"ok\n"]})
    result = run(docker)
    _, kwargs = docker.containers.created[0]
    assert kwargs["network_mode"] == "none"
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["security_opt"] == ["no-new-privileges"]
    assert kwargs["mem_limit"] == "1024m" and kwargs["pids_limit"] == 256
    assert kwargs["user"] == "1000:1000" and kwargs["environment"]["HOME"] == "/tmp"
    assert kwargs["log_config"]["config"]["max-file"] == "2"
    assert (result.exit_code, result.stdout, result.timed_out) == (0, "ok\n", False)
    assert docker.containers.last.removed


def test_default_user_is_the_host_user_and_never_root(monkeypatch):
    monkeypatch.setattr("os.getuid", lambda: 501)
    monkeypatch.setattr("os.getgid", lambda: 20)
    assert container_user(SandboxConfig()) == "501:20"
    monkeypatch.setattr("os.getuid", lambda: 0)
    with pytest.raises(SandboxError, match="root"):
        container_user(SandboxConfig())
    with pytest.raises(SandboxError, match="root"):
        container_user(SandboxConfig(user="0:0"))


def test_failure_exit_code_and_stderr_are_captured():
    docker = FakeDocker({"exit_code": 1, "stderr": [b"bo", b"om"]})
    result = run(docker)
    assert result.exit_code == 1 and result.stderr == "boom"


def test_timeout_kills_and_marks_result():
    docker = FakeDocker({"wait_error": wait_timeout()})
    result = run(docker)
    assert result.timed_out and docker.containers.last.killed
    assert docker.containers.last.removed


def test_exit_just_at_the_deadline_keeps_the_real_result():
    docker = FakeDocker(
        {"wait_error": wait_timeout(), "kill_error": api_error(409), "exit_code": 3}
    )
    result = run(docker)
    assert not result.timed_out and result.exit_code == 3


def test_lost_daemon_connection_is_not_a_timeout():
    docker = FakeDocker({"wait_error": ConnectionError("connection refused")})
    with pytest.raises(SandboxError, match="connection"):
        run(docker)
    assert docker.containers.last.removed


def test_oom_is_reported():
    assert run(FakeDocker({"exit_code": 137, "oom": True})).oom_killed


def test_output_keeps_the_tail():
    config = SandboxConfig(user="1000:1000", output_limit_bytes=1024)
    docker = FakeDocker({"stdout": [b"a" * 1000] * 10 + [b"END"]})
    result = run(docker, config)
    assert result.truncated and len(result.stdout) == 1024 and result.stdout.endswith("END")


def test_failed_removal_is_reported():
    docker = FakeDocker({"remove_error": api_error(500)})
    with pytest.raises(SandboxError, match="docker rm -f c0ffee"):
        run(docker)


def test_daemon_down_at_create_is_a_sandbox_error():
    docker = FakeDocker()

    def refuse(*_, **__):
        raise ConnectionError("connection refused")

    docker.containers.create = refuse
    with pytest.raises(SandboxError, match="cannot create"):
        run(docker)
