"""Player seat config — LeftPlayer (Box Holder) and RightPlayer (Guesser), either
human or driven by any LLM provider. Secrets (API keys) come only from environment
variables (.env, gitignored) and are never sent to the browser.
"""
from dataclasses import dataclass

VALID_PROVIDERS = ("ollama", "openai_compat", "anthropic")
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


@dataclass
class PlayerConfig:
    seat: str  # "left" | "right"
    kind: str  # "human" | "ai"
    provider: str = "ollama"
    model: str = ""
    base_url: str = ""
    api_key: str = ""


def load_player(prefix: str, env: dict, default_kind: str = "human") -> PlayerConfig:
    """Build a PlayerConfig for `prefix` ("LEFT"/"RIGHT") by reading `{prefix}_*` keys from `env`."""
    kind = (env.get(f"{prefix}_TYPE") or default_kind).strip().lower()
    provider = (env.get(f"{prefix}_PROVIDER") or "ollama").strip().lower()
    base_url = env.get(f"{prefix}_BASE_URL") or (
        DEFAULT_OLLAMA_URL if provider == "ollama" else ""
    )
    return PlayerConfig(
        seat=prefix.lower(),
        kind=kind,
        provider=provider,
        model=env.get(f"{prefix}_MODEL") or "",
        base_url=base_url,
        api_key=env.get(f"{prefix}_API_KEY") or "",
    )


def load_players(env: dict) -> dict:
    """Return {"left": PlayerConfig, "right": PlayerConfig} from an environ-like mapping."""
    return {
        "left": load_player("LEFT_PLAYER", env, default_kind="ai"),
        "right": load_player("RIGHT_PLAYER", env, default_kind="human"),
    }


def public_view(cfg: PlayerConfig) -> dict:
    """Browser-safe view of a seat's config — never includes api_key."""
    return {"kind": cfg.kind, "provider": cfg.provider, "model": cfg.model}
