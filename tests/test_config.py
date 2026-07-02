"""Slice 1 — config loader (spec: none directly; supports a1/a2 defaults)."""
import json

from server.config import DEFAULTS, load_config


def test_missing_file_returns_defaults():
    cfg = load_config("does_not_exist_config.json")
    assert cfg == DEFAULTS


def test_override_merges_over_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"turn_limit": 5}), encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg["turn_limit"] == 5
    # untouched keys keep their defaults
    assert cfg["box_holder_model"] == DEFAULTS["box_holder_model"]
    assert cfg["ollama_url"] == DEFAULTS["ollama_url"]


def test_standard_settings_check():
    from server.config import STANDARD_SETTINGS, is_standard
    assert STANDARD_SETTINGS == {"turn_limit": 3, "temperature": 0.7}
    assert DEFAULTS["temperature"] == 0.7  # defaults ARE the standard conditions
    assert DEFAULTS["turn_limit"] == 3
    assert is_standard(3, 0.7) is True
    assert is_standard(5, 0.7) is False
    assert is_standard(3, 0.9) is False
