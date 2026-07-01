"""Player seat config — env-driven, secrets never touch the browser."""
from server.players import PlayerConfig, load_player, load_players, public_view


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
    cfg = PlayerConfig(seat="left", kind="ai", provider="openai_compat", model="gpt-x", api_key="sk-shh")
    view = public_view(cfg)
    assert view == {"kind": "ai", "provider": "openai_compat", "model": "gpt-x"}
    assert "api_key" not in view
    assert "sk-shh" not in str(view)
