"""Player seat config — LeftPlayer (Box Holder) and RightPlayer (Guesser), either
human or driven by any LLM provider. Secrets (API keys) live in `.env` (gitignored)
and in server memory; they are accepted FROM the browser (this is a localhost,
single-user app) but never sent TO it.
"""
import os
from dataclasses import dataclass
from typing import Optional

VALID_PROVIDERS = ("ollama", "openai_compat", "anthropic")
VALID_KINDS = ("human", "ai")
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_ANTHROPIC_URL = "https://api.anthropic.com"
_ENV_SUFFIXES = ("TYPE", "PROVIDER", "MODEL", "BASE_URL", "API_KEY")


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
    """Browser-safe view of a seat's config — never includes api_key.
    `has_key` tells the UI a key is saved without revealing anything about it."""
    return {
        "kind": cfg.kind,
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "has_key": bool(cfg.api_key),
    }


def build_seat(seat: str, body: dict, current: PlayerConfig) -> PlayerConfig:
    """Validate a browser-submitted seat update and merge it over `current`.

    `api_key` semantics: omitted/None = keep the saved key; a string (including "")
    replaces it. Raises ValueError with a human-readable message on invalid input.
    """
    kind = (body.get("kind") or current.kind or "human").strip().lower()
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {VALID_KINDS}")
    provider = (body.get("provider") or current.provider or "ollama").strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"provider must be one of {VALID_PROVIDERS}")
    model = (body.get("model") if body.get("model") is not None else current.model) or ""
    base_url = (body.get("base_url") if body.get("base_url") is not None else current.base_url) or ""
    if not base_url:
        base_url = DEFAULT_OLLAMA_URL if provider == "ollama" else (
            DEFAULT_ANTHROPIC_URL if provider == "anthropic" else ""
        )
    api_key = body.get("api_key")
    if api_key is None:
        api_key = current.api_key
    if kind == "ai":
        if not model.strip():
            raise ValueError("an AI seat needs a model")
        if provider == "openai_compat" and not base_url.strip():
            raise ValueError("openai_compat needs a base_url (e.g. https://api.openai.com/v1)")
    return PlayerConfig(
        seat=seat, kind=kind, provider=provider,
        model=model.strip(), base_url=base_url.strip(), api_key=api_key,
    )


def persist_seat_env(prefix: str, cfg: PlayerConfig, path: str = ".env") -> None:
    """Write a seat's config back to the .env file so it survives restarts.

    Replaces the seat's `{prefix}_*` lines in place and appends any that are
    missing; every other line (comments, the other seat, unrelated vars) is
    preserved byte-for-byte.
    """
    values = {
        f"{prefix}_TYPE": cfg.kind,
        f"{prefix}_PROVIDER": cfg.provider,
        f"{prefix}_MODEL": cfg.model,
        f"{prefix}_BASE_URL": cfg.base_url,
        f"{prefix}_API_KEY": cfg.api_key,
    }
    lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    remaining = dict(values)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
