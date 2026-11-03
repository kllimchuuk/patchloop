import docker
import pytest
from support.projects import make_buggy_project

from patchloop.config import Config


@pytest.fixture(scope="module")
def docker_client():
    """A live Docker client with the default base image present; skips when there is none."""
    try:
        client = docker.from_env()
        client.ping()
        client.images.pull(Config().sandbox.base_image)
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker is not available: {exc}")
    return client


@pytest.fixture
def buggy_project(tmp_path):
    return make_buggy_project(tmp_path / "proj")
