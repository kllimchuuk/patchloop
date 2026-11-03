"""A minimal stand-in for the docker-py client, enough for the sandbox unit tests."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from docker.errors import APIError, ImageNotFound
from requests.exceptions import ConnectionError
from urllib3.exceptions import ReadTimeoutError


def wait_timeout() -> ConnectionError:
    """What docker-py raises over a unix socket when container.wait times out."""
    return ConnectionError(ReadTimeoutError(None, None, "Read timed out."))


def api_error(status: int) -> APIError:
    return APIError("error", response=SimpleNamespace(status_code=status, reason="", url=""))


class FakeContainer:
    def __init__(self, behavior: dict[str, Any]) -> None:
        self.id = "c0ffee"
        self.behavior = behavior
        self.killed = False
        self.removed = False
        state = {"OOMKilled": behavior.get("oom", False), "ExitCode": behavior.get("exit_code", 0)}
        self.attrs = {"State": state}

    def start(self) -> None:
        pass

    def wait(self, timeout: float) -> dict[str, int]:
        if error := self.behavior.get("wait_error"):
            raise error
        return {"StatusCode": self.behavior.get("exit_code", 0)}

    def kill(self) -> None:
        if error := self.behavior.get("kill_error"):
            raise error
        self.killed = True

    def reload(self) -> None:
        pass

    def logs(
        self, stdout: bool = True, stderr: bool = True, stream: bool = False
    ) -> Iterator[bytes]:
        return iter(self.behavior.get("stdout" if stdout else "stderr", []))

    def remove(self, force: bool = False) -> None:
        if error := self.behavior.get("remove_error"):
            raise error
        self.removed = True


class FakeContainers:
    def __init__(self, behavior: dict[str, Any]) -> None:
        self.behavior = behavior
        self.created: list[tuple[tuple, dict]] = []
        self.last: FakeContainer | None = None

    def create(self, *args: Any, **kwargs: Any) -> FakeContainer:
        self.created.append((args, kwargs))
        self.last = FakeContainer(self.behavior)
        return self.last


class FakeImages:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing

    def get(self, tag: str) -> object:
        if tag not in self.existing:
            raise ImageNotFound(tag)
        return object()


class FakeApi:
    def __init__(self, images: FakeImages, chunks: list[dict] | None) -> None:
        self.images = images
        self.chunks = chunks
        self.builds: list[dict] = []
        self.closed = False

    def build(self, **kwargs: Any) -> Iterator[dict]:
        self.builds.append(kwargs)
        return self._stream(kwargs["tag"])

    def _stream(self, tag: str) -> Iterator[dict]:
        try:
            chunks = self.chunks if self.chunks is not None else [{"stream": "Step 1\n"}]
            yield from chunks
            if not any("error" in chunk for chunk in chunks):
                self.images.existing.add(tag)
        finally:
            self.closed = True


class FakeDocker:
    def __init__(
        self, behavior: dict[str, Any] | None = None, build_chunks: list[dict] | None = None
    ) -> None:
        self.containers = FakeContainers(behavior or {})
        self.images = FakeImages(set())
        self.api = FakeApi(self.images, build_chunks)
