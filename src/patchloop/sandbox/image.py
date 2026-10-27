"""Phase 1 (network allowed): an image with the project's dependencies, cached by content hash."""

import hashlib
import io
import json
import tarfile
import time
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from docker.errors import DockerException, ImageNotFound
from requests.exceptions import RequestException

from patchloop.config import SandboxConfig
from patchloop.sandbox.errors import SandboxError

DOCKERFILE = ".patchloop/Dockerfile"  # kept apart from project files, so no manifest can replace it


def _check_manifest_names(manifests: Mapping[str, bytes]) -> None:
    for name in manifests:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise SandboxError(f"manifest path must be relative to the project: {name!r}")
        if path.parts[0] == ".patchloop":
            raise SandboxError(f"manifest path is reserved for patchloop: {name!r}")


def render_dockerfile(
    config: SandboxConfig, manifests: Mapping[str, bytes], install_cmd: str
) -> str:
    lines = [f"FROM {config.base_image}", "WORKDIR /work"]
    # JSON form, so paths with spaces stay one argument
    lines += [f"COPY {json.dumps([name, f'/work/{name}'])}" for name in sorted(manifests)]
    if install_cmd:
        lines.append(f"RUN {install_cmd}")
    return "\n".join(lines) + "\n"


def image_tag(config: SandboxConfig, manifests: Mapping[str, bytes], install_cmd: str) -> str:
    """The tag covers everything the image is built from: the Dockerfile and the manifests."""
    digest = hashlib.sha256(render_dockerfile(config, manifests, install_cmd).encode())
    for name in sorted(manifests):
        digest.update(f"\0{name}\0".encode() + manifests[name])
    return f"{config.image_repository}:{digest.hexdigest()[:16]}"


def _build_context(dockerfile: str, manifests: Mapping[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, data in {**manifests, DOCKERFILE: dockerfile.encode()}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    buffer.seek(0)
    return buffer


def _build(client: Any, config: SandboxConfig, context: io.BytesIO, tag: str) -> None:
    """Stream the build and stop it at prepare_timeout_s.

    The deadline is checked on every output line; a build that prints nothing is stopped by the
    HTTP read timeout, which is set to the same value. Closing the stream makes the daemon cancel
    the build.
    """
    deadline = time.monotonic() + config.prepare_timeout_s
    stream = client.api.build(
        fileobj=context,
        custom_context=True,
        dockerfile=DOCKERFILE,
        tag=tag,
        rm=True,
        forcerm=True,
        decode=True,
        timeout=config.prepare_timeout_s,
    )
    tail: list[str] = []
    try:
        for chunk in stream:
            if "error" in chunk:
                detail = "".join(tail[-20:]) + str(chunk["error"])
                raise SandboxError(f"image build failed:\n{detail.strip()}")
            if text := chunk.get("stream"):
                tail.append(text)
                del tail[:-20]
            if time.monotonic() > deadline:
                raise SandboxError(
                    f"image build exceeded sandbox.prepare_timeout_s ({config.prepare_timeout_s} s)"
                )
    finally:
        close = getattr(stream, "close", None)
        if close is not None:
            close()


def ensure_image(
    client: Any,
    config: SandboxConfig,
    manifests: Mapping[str, bytes],
    install_cmd: str,
) -> str:
    """Return the tag of the dependency image, building it first if it does not exist."""
    _check_manifest_names(manifests)
    tag = image_tag(config, manifests, install_cmd)
    try:
        client.images.get(tag)
        return tag
    except ImageNotFound:
        pass
    except (DockerException, RequestException) as exc:
        raise SandboxError(f"Docker is not available: {exc}") from exc
    context = _build_context(render_dockerfile(config, manifests, install_cmd), manifests)
    try:
        _build(client, config, context, tag)
        client.images.get(tag)  # the build stream can end without an error line on failure
    except ImageNotFound as exc:
        raise SandboxError(f"image build did not produce {tag}") from exc
    except RequestException as exc:
        raise SandboxError(
            f"image build stopped: no response within {config.prepare_timeout_s} s ({exc})"
        ) from exc
    except DockerException as exc:
        raise SandboxError(f"image build failed: {exc}") from exc
    return tag
