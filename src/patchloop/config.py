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


class Config(_Section):
    language: str = "en"  # language of explanations returned by the system
    max_attempts: int = Field(4, ge=1, le=10)  # Programmer attempts (SPEC §8)
    llm: LlmConfig = LlmConfig()


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
