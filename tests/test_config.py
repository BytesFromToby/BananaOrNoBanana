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
