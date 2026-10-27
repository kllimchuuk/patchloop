"""Real-container checks. Opt-in: `uv run pytest -m docker`. Needs a running Docker daemon."""

import docker
import pytest

from patchloop.config import SandboxConfig
from patchloop.sandbox import ensure_image, make_workspace, run_in_sandbox, workspace

pytestmark = pytest.mark.docker

BASE = "python:3.12-slim"  # small; the default python:3.12 behaves the same


@pytest.fixture(scope="module")
def client():
    try:
        c = docker.from_env()
        c.ping()
        c.images.pull(BASE)
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker is not available: {exc}")
    return c


def sandbox(client, tmp_path, **limits):
    config = SandboxConfig(base_image=BASE, **limits)
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.txt").write_text("original\n", encoding="utf-8")
    image = ensure_image(client, config, {"requirements.txt": b""}, "")
    return config, image, project, make_workspace(project, parent=tmp_path)


def test_workspace_written_in_the_container_can_be_removed(client, tmp_path):
    config, image, project, _ = sandbox(client, tmp_path)
    code = "import os; os.makedirs('__pycache__/x'); open('__pycache__/x/f','w').write('1')"
    with workspace(project, parent=tmp_path) as work:
        result = run_in_sandbox(client, config, image, work, py(code))
        assert result.exit_code == 0, result.stderr
    assert not work.exists()


def py(code):
    return ["python", "-c", code]


def test_network_is_unreachable(client, tmp_path):
    config, image, _, work = sandbox(client, tmp_path)
    code = "import socket; socket.create_connection(('1.1.1.1', 80), timeout=3)"
    result = run_in_sandbox(client, config, image, work, py(code))
    assert result.exit_code != 0 and "unreachable" in result.stderr.lower()


def test_runs_as_non_root_and_can_write_the_workspace(client, tmp_path):
    config, image, project, work = sandbox(client, tmp_path)
    code = "import os; open('b.txt','w').write(str(os.getuid()))"  # like a pytest cache
    result = run_in_sandbox(client, config, image, work, py(code))
    assert result.exit_code == 0, result.stderr
    assert (work / "b.txt").read_text(encoding="utf-8") != "0"
    assert not (project / "b.txt").exists()  # the original is untouched


def test_timeout_kills_the_container(client, tmp_path):
    config, image, _, work = sandbox(client, tmp_path, run_timeout_s=3)
    result = run_in_sandbox(client, config, image, work, py("while True: pass"))
    assert result.timed_out and result.duration_s < 15


def test_memory_limit_is_enforced(client, tmp_path):
    config, image, _, work = sandbox(client, tmp_path, memory_mb=64)
    result = run_in_sandbox(client, config, image, work, py("x = bytearray(400_000_000)"))
    assert result.exit_code != 0 and (result.oom_killed or result.exit_code == 137)


def test_no_leftover_containers(client, tmp_path):
    before = {c.id for c in client.containers.list(all=True)}
    config, image, _, work = sandbox(client, tmp_path)
    run_in_sandbox(client, config, image, work, py("print('hi')"))
    assert {c.id for c in client.containers.list(all=True)} == before
