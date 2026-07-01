"""Configuration for Banana or No Banana — defaults merged over an optional config.json."""
import json
import os

from dotenv import load_dotenv

load_dotenv()

DEFAULTS = {
    "turn_limit": 3,
    "box_holder_model": "qwen3:8b",
    "temperature": 0.9,
    "prior": 0.5,
    "ollama_url": "http://127.0.0.1:11434",
    "seat": "human_guesser",
}


def load_config(path: str = "config.json") -> dict:
    """Return DEFAULTS updated by the JSON at `path` if it exists; defaults unchanged if absent."""
    config = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    return config
