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
    seat: str  # color: "red" | "blue"
    kind: str  # "human" | "ai"
    provider: str = "ollama"
    model: str = ""
    base_url: str = ""
    api_key: str = ""


# Legacy env prefixes kept working via fallback: red was the left seat, blue the right.
_LEGACY_PREFIX = {"RED_PLAYER": "LEFT_PLAYER", "BLUE_PLAYER": "RIGHT_PLAYER"}


def load_player(prefix: str, env: dict, default_kind: str = "human") -> PlayerConfig:
    """Build a PlayerConfig for `prefix` ("RED_PLAYER"/"BLUE_PLAYER") by reading `{prefix}_*` keys from `env`."""
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


def _has_prefix(env: dict, prefix: str) -> bool:
    """True if any `{prefix}_*` key is present in the mapping."""
    return any(k.startswith(f"{prefix}_") for k in env)


def _load_color(color: str, prefix: str, env: dict, default_kind: str) -> PlayerConfig:
    """Load one color from its new prefix, falling back to the legacy prefix when the
    new keys are absent but the legacy ones are present (keeps an existing .env working)."""
    if not _has_prefix(env, prefix) and _has_prefix(env, _LEGACY_PREFIX[prefix]):
        cfg = load_player(_LEGACY_PREFIX[prefix], env, default_kind=default_kind)
        cfg.seat = color
        return cfg
    cfg = load_player(prefix, env, default_kind=default_kind)
    cfg.seat = color
    return cfg


def load_players(env: dict) -> dict:
    """Return {"red": PlayerConfig, "blue": PlayerConfig} from an environ-like mapping.

    Reads the new `RED_PLAYER_*` / `BLUE_PLAYER_*` prefixes; if a color's new keys are
    absent but its legacy prefix (LEFT_PLAYER for red, RIGHT_PLAYER for blue) is present,
    it loads from the legacy prefix so an unmigrated `.env` still works. Default kinds
    preserve today's single-human-vs-AI baseline: red → ai, blue → human.
    """
    return {
        "red": _load_color("red", "RED_PLAYER", env, default_kind="ai"),
        "blue": _load_color("blue", "BLUE_PLAYER", env, default_kind="human"),
    }


def migrate_env_file(path: str = ".env") -> None:
    """Rename legacy seat keys in place: `LEFT_PLAYER_*` → `RED_PLAYER_*`,
    `RIGHT_PLAYER_*` → `BLUE_PLAYER_*`. Values, comments, unrelated lines, and order
    are preserved. No-op if the file is absent or already migrated.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    out = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            key_stripped = key.strip()
            renamed = None
            if key_stripped.startswith("LEFT_PLAYER_"):
                renamed = "RED_PLAYER_" + key_stripped[len("LEFT_PLAYER_"):]
            elif key_stripped.startswith("RIGHT_PLAYER_"):
                renamed = "BLUE_PLAYER_" + key_stripped[len("RIGHT_PLAYER_"):]
            if renamed is not None:
                out.append(f"{renamed}={value}")
                continue
        out.append(line)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


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
    persist_env(values, path=path)


def persist_env(values: dict, path: str = ".env") -> None:
    """Replace-or-append `KEY=value` lines in the .env file; all other lines
    are preserved byte-for-byte."""
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
