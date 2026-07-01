"""Player seat config — env/browser-driven; saved secrets are never sent to the browser."""
from server.players import (
    PlayerConfig,
    build_seat,
    load_player,
    load_players,
    persist_seat_env,
    public_view,
)


def test_load_player_reads_prefixed_env():
    env = {
        "LEFT_PLAYER_TYPE": "ai",
        "LEFT_PLAYER_PROVIDER": "anthropic",
        "LEFT_PLAYER_MODEL": "claude-sonnet",
        "LEFT_PLAYER_BASE_URL": "https://api.anthropic.com",
        "LEFT_PLAYER_API_KEY": "sk-secret",
    }
    cfg = load_player("LEFT_PLAYER", env)
    assert cfg == PlayerConfig(
        seat="left_player",
        kind="ai",
        provider="anthropic",
        model="claude-sonnet",
        base_url="https://api.anthropic.com",
        api_key="sk-secret",
    )


def test_load_player_defaults_when_env_missing():
    cfg = load_player("LEFT_PLAYER", {}, default_kind="ai")
    assert cfg.kind == "ai"
    assert cfg.provider == "ollama"
    assert cfg.base_url == "http://127.0.0.1:11434"  # ollama default fills in
    assert cfg.api_key == ""

    right = load_player("RIGHT_PLAYER", {}, default_kind="human")
    assert right.kind == "human"


def test_non_ollama_provider_has_no_default_base_url():
    cfg = load_player("LEFT_PLAYER", {"LEFT_PLAYER_PROVIDER": "openai_compat"})
    assert cfg.base_url == ""


def test_load_players_returns_left_and_right():
    players = load_players({})
    assert players["left"].kind == "ai"  # left defaults to AI (today's Box Holder)
    assert players["right"].kind == "human"  # right defaults to human (today's Guesser)


def test_public_view_omits_api_key():
    cfg = PlayerConfig(seat="left", kind="ai", provider="openai_compat", model="gpt-x",
                       base_url="https://api.openai.com/v1", api_key="sk-shh")
    view = public_view(cfg)
    assert view == {
        "kind": "ai",
        "provider": "openai_compat",
        "model": "gpt-x",
        "base_url": "https://api.openai.com/v1",
        "has_key": True,
    }
    assert "api_key" not in view
    assert "sk-shh" not in str(view)


# --- build_seat: browser-submitted seat updates ---

def _current():
    return PlayerConfig(seat="left", kind="ai", provider="ollama", model="qwen3:8b",
                        base_url="http://127.0.0.1:11434", api_key="old-key")


def test_build_seat_merges_and_validates():
    cfg = build_seat("left", {"provider": "anthropic", "model": "claude-opus-4-8"}, _current())
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-opus-4-8"
    assert cfg.api_key == "old-key"  # omitted key = keep saved key


def test_build_seat_key_semantics():
    kept = build_seat("left", {"model": "m"}, _current())
    assert kept.api_key == "old-key"
    replaced = build_seat("left", {"model": "m", "api_key": "new-key"}, _current())
    assert replaced.api_key == "new-key"
    cleared = build_seat("left", {"model": "m", "api_key": ""}, _current())
    assert cleared.api_key == ""


def test_build_seat_default_base_urls():
    anth = build_seat("left", {"provider": "anthropic", "model": "m", "base_url": ""}, _current())
    assert anth.base_url == "https://api.anthropic.com"


def test_build_seat_rejects_bad_input():
    import pytest
    with pytest.raises(ValueError):
        build_seat("left", {"kind": "robot"}, _current())
    with pytest.raises(ValueError):
        build_seat("left", {"provider": "gemini", "model": "m"}, _current())
    with pytest.raises(ValueError):
        build_seat("left", {"kind": "ai", "model": ""}, _current())  # AI needs a model
    with pytest.raises(ValueError):
        build_seat("left", {"provider": "openai_compat", "model": "m", "base_url": ""}, _current())


def test_build_seat_human_needs_no_model():
    cfg = build_seat("right", {"kind": "human", "model": ""},
                     PlayerConfig(seat="right", kind="ai", provider="ollama", model="x"))
    assert cfg.kind == "human"


# --- persist_seat_env: .env round-trip ---

def test_persist_seat_env_updates_in_place_and_preserves_rest(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment stays\nLEFT_PLAYER_TYPE=ai\nLEFT_PLAYER_MODEL=qwen3:8b\nUNRELATED=keep-me\n",
        encoding="utf-8",
    )
    cfg = PlayerConfig(seat="left", kind="ai", provider="anthropic",
                       model="claude-opus-4-8", base_url="https://api.anthropic.com", api_key="sk-1")
    persist_seat_env("LEFT_PLAYER", cfg, path=str(env_file))
    text = env_file.read_text(encoding="utf-8")
    assert "# comment stays" in text
    assert "UNRELATED=keep-me" in text
    assert "LEFT_PLAYER_MODEL=claude-opus-4-8" in text
    assert "LEFT_PLAYER_PROVIDER=anthropic" in text  # appended (was missing)
    assert "LEFT_PLAYER_API_KEY=sk-1" in text
    assert text.count("LEFT_PLAYER_MODEL=") == 1  # replaced, not duplicated
    # Round-trips through the loader.
    env = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
    assert load_player("LEFT_PLAYER", env).model == "claude-opus-4-8"


def test_persist_seat_env_creates_file(tmp_path):
    env_file = tmp_path / ".env"
    cfg = PlayerConfig(seat="right", kind="ai", provider="ollama", model="qwen3:8b",
                       base_url="http://127.0.0.1:11434")
    persist_seat_env("RIGHT_PLAYER", cfg, path=str(env_file))
    assert "RIGHT_PLAYER_MODEL=qwen3:8b" in env_file.read_text(encoding="utf-8")
