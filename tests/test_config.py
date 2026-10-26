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
