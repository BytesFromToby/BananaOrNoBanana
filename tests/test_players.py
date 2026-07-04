"""Player seat config — env/browser-driven; saved secrets are never sent to the browser."""
from server.players import (
    PlayerConfig,
    build_seat,
    load_player,
    load_players,
    migrate_env_file,
    persist_seat_env,
    public_view,
)


def test_load_player_reads_prefixed_env():
    env = {
        "RED_PLAYER_TYPE": "ai",
        "RED_PLAYER_PROVIDER": "anthropic",
        "RED_PLAYER_MODEL": "claude-sonnet",
        "RED_PLAYER_BASE_URL": "https://api.anthropic.com",
        "RED_PLAYER_API_KEY": "sk-secret",
    }
    cfg = load_player("RED_PLAYER", env)
    assert cfg == PlayerConfig(
        seat="red_player",
        kind="ai",
        provider="anthropic",
        model="claude-sonnet",
        base_url="https://api.anthropic.com",
        api_key="sk-secret",
    )


def test_load_player_defaults_when_env_missing():
    cfg = load_player("RED_PLAYER", {}, default_kind="ai")
    assert cfg.kind == "ai"
    assert cfg.provider == "ollama"
    assert cfg.base_url == "http://127.0.0.1:11434"  # ollama default fills in
    assert cfg.api_key == ""

    blue = load_player("BLUE_PLAYER", {}, default_kind="human")
    assert blue.kind == "human"


def test_non_ollama_provider_has_no_default_base_url():
    cfg = load_player("RED_PLAYER", {"RED_PLAYER_PROVIDER": "openai_compat"})
    assert cfg.base_url == ""


def test_load_players_returns_red_and_blue():
    players = load_players({})
    assert set(players) == {"red", "blue"}
    assert players["red"].kind == "ai"  # red defaults to AI (today's Box Holder)
    assert players["blue"].kind == "human"  # blue defaults to human (today's Guesser)
    assert players["red"].seat == "red"
    assert players["blue"].seat == "blue"


def test_red_blue_load_and_legacy_migration(tmp_path):
    """DW6 — new prefixes load both colors, a legacy-only env still loads both via
    fallback, and migrate_env_file rewrites keys in place preserving everything else."""
    # (a) new RED_/BLUE_ prefixes load both colors.
    new_env = {
        "RED_PLAYER_TYPE": "ai", "RED_PLAYER_MODEL": "qwen3:8b",
        "BLUE_PLAYER_TYPE": "ai", "BLUE_PLAYER_MODEL": "gemma4:latest",
    }
    p = load_players(new_env)
    assert p["red"].kind == "ai" and p["red"].model == "qwen3:8b"
    assert p["blue"].kind == "ai" and p["blue"].model == "gemma4:latest"

    # (b) legacy-only env still loads both colors via fallback.
    legacy_env = {
        "LEFT_PLAYER_TYPE": "ai", "LEFT_PLAYER_MODEL": "leg-red",
        "RIGHT_PLAYER_TYPE": "human",
    }
    lp = load_players(legacy_env)
    assert lp["red"].kind == "ai" and lp["red"].model == "leg-red"
    assert lp["blue"].kind == "human"
    assert lp["red"].seat == "red" and lp["blue"].seat == "blue"

    # (c) migrate_env_file rewrites legacy keys in place, preserving comment,
    # unrelated var, and order.
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment stays\n"
        "LEFT_PLAYER_TYPE=ai\n"
        "LEFT_PLAYER_MODEL=qwen3:8b\n"
        "UNRELATED=keep-me\n"
        "RIGHT_PLAYER_TYPE=human\n",
        encoding="utf-8",
    )
    migrate_env_file(str(env_file))
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# comment stays"          # comment preserved, in place
    assert lines[1] == "RED_PLAYER_TYPE=ai"
    assert lines[2] == "RED_PLAYER_MODEL=qwen3:8b"  # value preserved
    assert lines[3] == "UNRELATED=keep-me"          # unrelated var preserved, in place
    assert lines[4] == "BLUE_PLAYER_TYPE=human"
    text = "\n".join(lines)
    assert "LEFT_PLAYER" not in text and "RIGHT_PLAYER" not in text


def test_public_view_omits_api_key():
    cfg = PlayerConfig(seat="red", kind="ai", provider="openai_compat", model="gpt-x",
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
    return PlayerConfig(seat="red", kind="ai", provider="ollama", model="qwen3:8b",
                        base_url="http://127.0.0.1:11434", api_key="old-key")


def test_build_seat_merges_and_validates():
    cfg = build_seat("red", {"provider": "anthropic", "model": "claude-opus-4-8"}, _current())
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-opus-4-8"
    assert cfg.api_key == "old-key"  # omitted key = keep saved key


def test_build_seat_key_semantics():
    kept = build_seat("red", {"model": "m"}, _current())
    assert kept.api_key == "old-key"
    replaced = build_seat("red", {"model": "m", "api_key": "new-key"}, _current())
    assert replaced.api_key == "new-key"
    cleared = build_seat("red", {"model": "m", "api_key": ""}, _current())
    assert cleared.api_key == ""


def test_build_seat_default_base_urls():
    anth = build_seat("red", {"provider": "anthropic", "model": "m", "base_url": ""}, _current())
    assert anth.base_url == "https://api.anthropic.com"


def test_build_seat_rejects_bad_input():
    import pytest
    with pytest.raises(ValueError):
        build_seat("red", {"kind": "robot"}, _current())
    with pytest.raises(ValueError):
        build_seat("red", {"provider": "gemini", "model": "m"}, _current())
    with pytest.raises(ValueError):
        build_seat("red", {"kind": "ai", "model": ""}, _current())  # AI needs a model
    with pytest.raises(ValueError):
        build_seat("red", {"provider": "openai_compat", "model": "m", "base_url": ""}, _current())


def test_build_seat_human_needs_no_model():
    cfg = build_seat("blue", {"kind": "human", "model": ""},
                     PlayerConfig(seat="blue", kind="ai", provider="ollama", model="x"))
    assert cfg.kind == "human"


# --- persist_seat_env: .env round-trip ---

def test_persist_seat_env_updates_in_place_and_preserves_rest(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment stays\nRED_PLAYER_TYPE=ai\nRED_PLAYER_MODEL=qwen3:8b\nUNRELATED=keep-me\n",
        encoding="utf-8",
    )
    cfg = PlayerConfig(seat="red", kind="ai", provider="anthropic",
                       model="claude-opus-4-8", base_url="https://api.anthropic.com", api_key="sk-1")
    persist_seat_env("RED_PLAYER", cfg, path=str(env_file))
    text = env_file.read_text(encoding="utf-8")
    assert "# comment stays" in text
    assert "UNRELATED=keep-me" in text
    assert "RED_PLAYER_MODEL=claude-opus-4-8" in text
    assert "RED_PLAYER_PROVIDER=anthropic" in text  # appended (was missing)
    assert "RED_PLAYER_API_KEY=sk-1" in text
    assert text.count("RED_PLAYER_MODEL=") == 1  # replaced, not duplicated
    # Round-trips through the loader.
    env = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
    assert load_player("RED_PLAYER", env).model == "claude-opus-4-8"


def test_persist_seat_env_creates_file(tmp_path):
    env_file = tmp_path / ".env"
    cfg = PlayerConfig(seat="blue", kind="ai", provider="ollama", model="qwen3:8b",
                       base_url="http://127.0.0.1:11434")
    persist_seat_env("BLUE_PLAYER", cfg, path=str(env_file))
    assert "BLUE_PLAYER_MODEL=qwen3:8b" in env_file.read_text(encoding="utf-8")
