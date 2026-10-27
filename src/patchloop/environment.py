"""Environment checks behind `patchloop check`. Each check returns a result, never raises."""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from patchloop.config import Config

MIN_PYTHON = (3, 12)  # requires-python in pyproject.toml (decision 17)


@dataclass(frozen=True)
class CheckItem:
    name: str
    ok: bool
    detail: str
    hint: str = ""


def check_python(version: tuple[int, ...] = tuple(sys.version_info[:3])) -> CheckItem:
    text = ".".join(str(part) for part in version)
    if tuple(version[:2]) >= MIN_PYTHON:
        return CheckItem("Python", True, text)
    return CheckItem("Python", False, text, "patchloop needs Python 3.12 or newer")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)


def check_docker(
    run: Callable[[list[str]], subprocess.CompletedProcess] = _run
) -> CheckItem:
    hint = "start Docker Desktop (or the Docker daemon) and try again"
    try:
        result = run(["docker", "version", "--format", "{{.Server.Version}}"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckItem("Docker", False, str(exc) or "not available", hint)
    if result.returncode != 0:
        return CheckItem("Docker", False, "daemon is not reachable", hint)
    return CheckItem("Docker", True, result.stdout.strip())


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def _model_name(litellm_model: str) -> str:
    return litellm_model.split("/", 1)[1] if "/" in litellm_model else litellm_model


def check_ollama(
    config: Config, http_get: Callable[[str], dict] = _http_get_json
) -> list[CheckItem]:
    base = config.llm.base_url.rstrip("/")
    try:
        tags = http_get(f"{base}/api/tags")
    except (OSError, urllib.error.URLError, ValueError) as exc:
        hint = "install Ollama (https://ollama.com) and start it"
        return [CheckItem("Ollama", False, f"not reachable at {base} ({exc})", hint)]
    items = [CheckItem("Ollama", True, base)]
    wanted = _model_name(config.llm.model)
    installed = {entry.get("name", "") for entry in tags.get("models", [])}
    present = wanted in installed or f"{wanted}:latest" in installed
    if present:
        items.append(CheckItem("Model", True, wanted))
    else:
        detail = f"{wanted} is not installed"
        items.append(CheckItem("Model", False, detail, f"ollama pull {wanted}"))
    return items


def run_checks(config: Config) -> list[CheckItem]:
    return [check_python(), check_docker(), *check_ollama(config)]
