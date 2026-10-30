import pytest

from patchloop.config import Config, ConfigError, load_config


def test_defaults_load_without_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg == Config()
    assert cfg.max_attempts == 4 and cfg.language == "en"


def test_file_overrides_defaults(tmp_path):
    path = tmp_path / "patchloop.yml"
    path.write_text(
        "max_attempts: 2\nllm:\n  model: ollama_chat/x:1b\n", encoding="utf-8"
    )
    cfg = load_config(path)
    assert cfg.max_attempts == 2
    assert cfg.llm.model == "ollama_chat/x:1b"
    assert (
        cfg.llm.base_url == Config().llm.base_url
    )  # untouched keys keep their defaults


def test_unknown_key_is_an_error(tmp_path):
    path = tmp_path / "patchloop.yml"
    path.write_text("max_atempts: 2\n", encoding="utf-8")  # typo
    with pytest.raises(ConfigError):
        load_config(path)


def test_out_of_range_value_is_an_error(tmp_path):
    path = tmp_path / "patchloop.yml"
    path.write_text("max_attempts: 0\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_empty_file_gives_defaults(tmp_path):
    path = tmp_path / "patchloop.yml"
    path.write_text("", encoding="utf-8")
    assert load_config(path) == Config()


def test_sandbox_defaults_and_override(tmp_path):
    assert Config().sandbox.base_image == "python:3.12-slim"
    path = tmp_path / "patchloop.yml"
    path.write_text("sandbox:\n  memory_mb: 512\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.sandbox.memory_mb == 512
    assert cfg.sandbox.cpus == Config().sandbox.cpus


def test_unknown_sandbox_key_is_an_error(tmp_path):
    path = tmp_path / "patchloop.yml"
    path.write_text("sandbox:\n  memory: 512\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_loop_defaults_and_override(tmp_path):
    cfg = Config()
    assert cfg.loop.total_timeout_s > 0
    assert cfg.loop.tail_lines >= 5
    path = tmp_path / "patchloop.yml"
    path.write_text("loop:\n  tail_lines: 10\n", encoding="utf-8")
    assert load_config(path).loop.tail_lines == 10
    assert load_config(path).loop.total_timeout_s == cfg.loop.total_timeout_s


def test_profile_overrides_default_to_none():
    cfg = Config()
    assert (cfg.image, cfg.install, cfg.build, cfg.test, cfg.lint) == (None,) * 5
    assert cfg.env == {}


def test_profile_overrides_load_from_spec_example(tmp_path):
    path = tmp_path / "patchloop.yml"
    path.write_text(
        "image: python:3.12\n"
        "install: pip install -r requirements.txt\n"
        "test: pytest -x\n"
        "env:\n  DJANGO_SETTINGS_MODULE: config.settings\n  SECRET_KEY: test\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.image == "python:3.12"
    assert cfg.test == "pytest -x"
    assert cfg.build is None
    assert cfg.env == {"DJANGO_SETTINGS_MODULE": "config.settings", "SECRET_KEY": "test"}


@pytest.mark.parametrize(
    "text", ["loop:\n  timeout: 5\n", "loop:\n  tail_lines: 1\n", "tests: x\n"]
)
def test_invalid_loop_or_profile_keys_are_errors(tmp_path, text):
    path = tmp_path / "patchloop.yml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_env_values_must_be_strings(tmp_path):
    path = tmp_path / "patchloop.yml"
    path.write_text("env:\n  DEBUG: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
