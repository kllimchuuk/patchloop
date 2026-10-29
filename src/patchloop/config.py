"""Runtime configuration: defaults below, overridden by `patchloop.yml` (SPEC §6).

Unknown keys are an error, so a typo in `patchloop.yml` never passes silently.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

CONFIG_FILE = "patchloop.yml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmConfig(_Section):
    model: str = "ollama_chat/qwen3.5:9b-q4_K_M"  # LiteLLM name: <provider>/<model>
    base_url: str = "http://localhost:11434"
    timeout_s: float = Field(120.0, gt=0)
    num_ctx: int = Field(16384, ge=2048)  # Ollama default (4096) is too small
    thinking: bool = (
        False  # the model's reasoning mode: slower, not better on small tasks
    )


class SandboxConfig(_Section):
    base_image: str = "python:3.12-slim"
    image_repository: str = "patchloop-env"  # prepared images are tagged <repository>:<hash>
    user: str | None = Field(None, pattern=r"^\d+(:\d+)?$")  # "uid[:gid]"; None = the host user
    memory_mb: int = Field(1024, ge=64)
    cpus: float = Field(1.0, gt=0)
    pids_limit: int = Field(256, ge=16)
    tmp_mb: int = Field(256, ge=16)  # tmpfs at /tmp; the root filesystem is read-only
    max_open_files: int = Field(1024, ge=64)
    max_file_mb: int = Field(512, ge=1)  # largest file a process may write
    run_timeout_s: float = Field(120.0, gt=0)  # one container run, not the whole task
    prepare_timeout_s: float = Field(900.0, gt=0)  # image build, with network
    build_memory_mb: int = Field(2048, ge=256)  # the build runs dependency install code too
    output_limit_bytes: int = Field(200_000, ge=1024)  # the tail is kept
    copy_env: bool = False  # copy the project's .env into the sandbox (it may hold real secrets)


class LoopConfig(_Section):
    total_timeout_s: float = Field(1800.0, gt=0)  # whole run, not one container (SPEC §8)
    tail_lines: int = Field(40, ge=5)  # lines of raw output kept when the parser finds nothing


class Config(_Section):
    language: str = "en"  # language of explanations returned by the system
    max_attempts: int = Field(4, ge=1, le=10)  # Programmer attempts (SPEC §8)
    llm: LlmConfig = LlmConfig()
    sandbox: SandboxConfig = SandboxConfig()
    loop: LoopConfig = LoopConfig()
    # Per-project overrides of the language profile defaults (SPEC §6); None = keep the default.
    image: str | None = None
    install: str | None = None
    build: str | None = None
    test: str | None = None
    lint: str | None = None
    env: dict[str, str] = {}  # only these variables reach the container, never the host's


class ConfigError(ValueError):
    """The configuration file is unreadable or invalid."""


def load_config(path: Path | None = None) -> Config:
    """Load `path`, or `./patchloop.yml` if it exists, or return the defaults."""
    if path is None:
        candidate = Path(CONFIG_FILE)
        path = candidate if candidate.is_file() else None
    if path is None:
        return Config()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    try:
        return Config.model_validate(raw)
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
