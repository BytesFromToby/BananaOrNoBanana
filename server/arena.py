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

# The fields a round must carry to be a valid wire-format-v1 submission — mirrors the
# Worker's REQUIRED_FIELDS (arena/src/lib/validate.js). Rounds logged before seat-aware
# logging existed lack these; they are never submittable and must be filtered locally so
# they aren't sent (and re-rejected) on every submit.
REQUIRED_WIRE_FIELDS = (
    "round_id", "ts", "mode",
    "box_holder_provider", "box_holder_model",
    "guesser_provider", "guesser_model",
    "box_contents", "turn_limit", "temperature", "standard_settings",
    "transcript", "guesser_turns_used", "final_answer", "correct", "winner",
    "forced_default",
)


def is_submittable(round: dict) -> bool:
    """True iff the round carries every wire-format-v1 field the arena requires.
    Legacy rounds (pre-seat-aware logging) fail this and are skipped by the client."""
    return all(field in round for field in REQUIRED_WIRE_FIELDS)


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
