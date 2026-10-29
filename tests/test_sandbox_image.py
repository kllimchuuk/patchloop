import pytest
from fake_docker import FakeDocker

from patchloop.config import SandboxConfig
from patchloop.sandbox import SandboxError, ensure_image
from patchloop.sandbox import image as image_module
from patchloop.sandbox.image import DOCKERFILE, image_tag, render_dockerfile

CFG = SandboxConfig()
CMD = "pip install -r requirements.txt"
MANIFESTS = {"requirements.txt": b"pytest==8.0\n"}


def test_tag_is_stable_and_follows_inputs():
    tag = image_tag(CFG, MANIFESTS, CMD)
    assert tag.startswith("patchloop-env:")
    assert tag == image_tag(CFG, dict(MANIFESTS), CMD)
    assert tag != image_tag(CFG, {"requirements.txt": b"pytest==9.0\n"}, CMD)
    assert tag != image_tag(CFG, MANIFESTS, "pip install pytest")
    assert tag != image_tag(SandboxConfig(base_image="python:3.13"), MANIFESTS, CMD)


def test_tag_follows_the_dockerfile_template(monkeypatch):
    tag = image_tag(CFG, MANIFESTS, CMD)
    monkeypatch.setattr(image_module, "render_dockerfile", lambda *_: "FROM other\n")
    assert image_module.image_tag(CFG, MANIFESTS, CMD) != tag


def test_dockerfile_copies_manifests_and_installs():
    text = render_dockerfile(CFG, {"req files/a.txt": b""}, CMD)
    assert text.splitlines()[:2] == [f"FROM {CFG.base_image}",'LABEL patchloop="env"']
    assert 'COPY ["req files/a.txt", "/work/req files/a.txt"]' in text
    assert f"RUN {CMD}" in text


def test_builds_once_then_uses_cache():
    docker = FakeDocker()
    first = ensure_image(docker, CFG, MANIFESTS, CMD)
    second = ensure_image(docker, CFG, MANIFESTS, CMD)
    assert first == second
    assert len(docker.api.builds) == 1
    build = docker.api.builds[0]
    assert build["dockerfile"] == DOCKERFILE
    memory = 2048 * 1024 * 1024
    assert build["container_limits"] == {"memory": memory, "memswap": memory}


@pytest.mark.parametrize("name", ["/etc/passwd", "../x.txt", ".patchloop/Dockerfile"])
def test_bad_manifest_names_are_rejected(name):
    with pytest.raises(SandboxError, match="manifest path"):
        ensure_image(FakeDocker(), CFG, {name: b""}, CMD)


def test_a_manifest_called_dockerfile_does_not_replace_ours():
    docker = FakeDocker()
    ensure_image(docker, CFG, {"Dockerfile": b"FROM evil\n"}, CMD)
    assert docker.api.builds[0]["dockerfile"] == DOCKERFILE


def test_build_failure_is_a_clear_error():
    docker = FakeDocker(build_chunks=[{"stream": "Collecting nope\n"}, {"error": "pip failed"}])
    with pytest.raises(SandboxError, match="pip failed") as info:
        ensure_image(docker, CFG, MANIFESTS, "pip install nope")
    assert "Collecting nope" in str(info.value)
    assert docker.api.closed


def test_build_is_stopped_at_the_deadline(monkeypatch):
    clock = iter(range(0, 10_000, 100))
    monkeypatch.setattr(image_module.time, "monotonic", lambda: next(clock))
    docker = FakeDocker(build_chunks=[{"stream": "."}] * 50)
    config = SandboxConfig(prepare_timeout_s=250)
    with pytest.raises(SandboxError, match="prepare_timeout_s"):
        ensure_image(docker, config, MANIFESTS, CMD)
    assert docker.api.closed  # closing the stream cancels the build in the daemon
