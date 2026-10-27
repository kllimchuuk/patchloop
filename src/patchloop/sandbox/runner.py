"""Phase 2 (no network): one disposable container per command, with limits (SPEC §6)."""

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docker.errors import APIError, DockerException, ImageNotFound, NotFound
from docker.types import Ulimit
from requests.exceptions import ConnectionError, ReadTimeout, RequestException
from urllib3.exceptions import ReadTimeoutError

from patchloop.config import SandboxConfig
from patchloop.sandbox.errors import SandboxError

WORKDIR = "/work"  # shared with the WORKDIR of the prepared image (image.py)
NANO = 1_000_000_000
EXIT_TIMEOUT = 124  # the usual exit code of `timeout`
LABELS = {"patchloop": "sandbox"}  # lets leftovers be found: docker ps -a --filter label=patchloop
MB = 1024 * 1024
BASE_ENV = {"HOME": "/tmp", "USER": "patchloop", "LOGNAME": "patchloop"}


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    oom_killed: bool = False
    truncated: bool = False


def container_user(config: SandboxConfig) -> str:
    """The host user by default: files written in /work stay writable and removable on the host."""
    if config.user is not None:
        user = config.user  # numeric only (validated in config): a name could map to root
    elif hasattr(os, "getuid"):
        user = f"{os.getuid()}:{os.getgid()}"
    else:
        raise SandboxError("cannot detect the host user; set sandbox.user in patchloop.yml")
    if int(user.split(":", 1)[0]) == 0:  # also catches "00"
        raise SandboxError("refusing to run the sandbox as root; set sandbox.user to another uid")
    return user


def _ulimits(config: SandboxConfig) -> list[Ulimit]:
    # no nproc: without user namespaces it counts every process of the host uid; pids_limit is used
    return [
        Ulimit(name="nofile", soft=config.max_open_files, hard=config.max_open_files),
        Ulimit(name="fsize", soft=config.max_file_mb * MB, hard=config.max_file_mb * MB),
        Ulimit(name="core", soft=0, hard=0),
    ]


def _is_wait_timeout(exc: Exception) -> bool:
    # over a unix socket docker-py reports the read timeout as a ConnectionError
    if isinstance(exc, ReadTimeout):
        return True
    return isinstance(exc, ConnectionError) and any(
        isinstance(arg, ReadTimeoutError) for arg in exc.args
    )


def _tail(chunks: Iterable[bytes], limit: int) -> tuple[str, bool]:
    """Keep only the last `limit` bytes while reading, so memory stays bounded."""
    buffer = bytearray()
    total = 0
    for chunk in chunks:
        total += len(chunk)
        buffer += chunk
        if len(buffer) > 2 * limit:
            del buffer[:-limit]
    return bytes(buffer[-limit:]).decode("utf-8", errors="replace"), total > limit


def _exit_code(container: Any) -> int:
    container.reload()
    return int(container.attrs.get("State", {}).get("ExitCode", -1))


def _execute(container: Any, config: SandboxConfig) -> ExecResult:
    started = time.monotonic()
    timed_out = False
    container.start()
    try:
        exit_code = container.wait(timeout=config.run_timeout_s)["StatusCode"]
    except (ReadTimeout, ConnectionError) as exc:
        if not _is_wait_timeout(exc):
            raise SandboxError(f"lost the connection to Docker: {exc}") from exc
        try:
            container.kill()
            timed_out = True
            exit_code = EXIT_TIMEOUT
        except (NotFound, APIError) as kill_exc:
            if isinstance(kill_exc, APIError) and kill_exc.status_code not in (404, 409):
                raise
            exit_code = _exit_code(container)  # it finished on its own just at the deadline
    duration = time.monotonic() - started
    container.reload()
    oom = bool(container.attrs.get("State", {}).get("OOMKilled"))
    limit = config.output_limit_bytes
    out, cut_out = _tail(container.logs(stdout=True, stderr=False, stream=True), limit)
    err, cut_err = _tail(container.logs(stdout=False, stderr=True, stream=True), limit)
    return ExecResult(exit_code, out, err, duration, timed_out, oom, cut_out or cut_err)


def _remove(container: Any) -> Exception | None:
    try:
        container.remove(force=True)
    except NotFound:
        return None
    except (DockerException, RequestException) as exc:
        return exc
    return None


def run_in_sandbox(
    client: Any,
    config: SandboxConfig,
    image: str,
    workdir: Path,
    command: list[str],
    env: dict[str, str] | None = None,
) -> ExecResult:
    """Run `command` in a fresh container with `workdir` mounted at /work, then remove it."""
    limit = config.output_limit_bytes
    try:
        container = client.containers.create(
            image,
            command,
            working_dir=WORKDIR,
            volumes={str(workdir): {"bind": WORKDIR, "mode": "rw"}},
            # the host uid has no /etc/passwd entry; USER/LOGNAME keep getpass.getuser() working
            environment={**BASE_ENV, **(env or {})},
            network_mode="none",
            read_only=True,
            tmpfs={"/tmp": f"size={config.tmp_mb}m,nosuid,nodev"},
            init=True,  # reaps orphaned processes, so zombies do not use up pids_limit
            mem_limit=f"{config.memory_mb}m",
            memswap_limit=f"{config.memory_mb}m",
            nano_cpus=int(config.cpus * NANO),
            pids_limit=config.pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            user=container_user(config),
            ulimits=_ulimits(config),
            labels=LABELS,
            # the daemon keeps at most ~2x the output limit on its disk, not the whole stream
            log_config={"type": "json-file", "config": {"max-size": str(limit), "max-file": "2"}},
        )
    except ImageNotFound as exc:
        raise SandboxError(f"image {image} not found; prepare it with ensure_image") from exc
    except (DockerException, RequestException) as exc:
        raise SandboxError(f"cannot create the container: {exc}") from exc

    cid = container.id
    leftover = f"container {cid} was not removed; remove it with `docker rm -f {cid}`"
    try:
        result = _execute(container, config)
    except (DockerException, RequestException) as exc:
        error = SandboxError(f"container run failed: {exc}")
        if (removal := _remove(container)) is not None:
            error.add_note(f"{leftover} ({removal})")
        raise error from exc
    except BaseException as exc:
        if (removal := _remove(container)) is not None:
            exc.add_note(f"{leftover} ({removal})")
        raise
    if (removal := _remove(container)) is not None:
        raise SandboxError(f"{leftover} ({removal})") from removal
    return result
