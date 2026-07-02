"""Configuration for Banana or No Banana — defaults merged over an optional config.json."""
import json
import os

from dotenv import load_dotenv

load_dotenv()

DEFAULTS = {
    "turn_limit": 3,
    "box_holder_model": "qwen3:8b",
    "temperature": 0.7,
    "prior": 0.5,
    "ollama_url": "http://127.0.0.1:11434",
    "seat": "human_guesser",
}

# The published standard conditions for leaderboard play. Rounds run at other
# settings are fine ("bypass leaderboard settings") but are logged non-standard
# and excluded from the deviation-from-50% metric — a hot Box Holder and a cold
# one are different contestants, so mixed conditions would confound the board.
STANDARD_SETTINGS = {"turn_limit": 3, "temperature": 0.7}


def is_standard(turn_limit, temperature) -> bool:
    """True iff a round ran at the standard leaderboard conditions."""
    return (
        turn_limit == STANDARD_SETTINGS["turn_limit"]
        and abs(temperature - STANDARD_SETTINGS["temperature"]) < 1e-9
    )


def load_config(path: str = "config.json") -> dict:
    """Return DEFAULTS updated by the JSON at `path` if it exists; defaults unchanged if absent."""
    config = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    return config
