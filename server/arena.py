"""Community-arena wire format (v1) and the anonymous client identity.

The submission payload is the seat-aware `logs/rounds.jsonl` records verbatim, wrapped
in a small envelope. No reshaping: the local log schema IS the wire contract, so getting
the log right (seat identity, temperature, standard_settings, forced_default) is all the
arena needs. The client_id is a random UUID minted once and reused — no account, no PII.
"""
import os
import uuid

SCHEMA_VERSION = 1
CLIENT_VERSION = "0.1.0"  # single source of truth for the app version string

_CLIENT_ID_PATH = os.path.join("logs", "arena_client_id")


def get_or_create_client_id(path: str = _CLIENT_ID_PATH) -> str:
    """Return this install's anonymous client_id, minting it once on first call."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read().strip()
        if existing:
            return existing
    client_id = uuid.uuid4().hex
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(client_id + "\n")
    return client_id


def build_payload(rounds: list, client_id: str) -> dict:
    """Wrap round records (verbatim log dicts) in the v1 submission envelope."""
    return {
        "schema_version": SCHEMA_VERSION,
        "client_version": CLIENT_VERSION,
        "client_id": client_id,
        "rounds": list(rounds),
    }
