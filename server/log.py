"""Append one JSON object per completed round to logs/rounds.jsonl — audit now, leaderboard later."""
import json
import os
from datetime import datetime, timezone

from server.config import is_standard


def _seat_identity(cfg):
    """(provider, model) for a seat; a human seat logs as ("human", "")."""
    if cfg is None or cfg.kind != "ai":
        return "human", ""
    return cfg.provider, cfg.model


def append_round(r, config, final_answer, correct, winner, forced_default=False,
                 path="logs/rounds.jsonl"):
    """Append exactly one JSON line describing the completed round.

    The log doubles as leaderboard/submission data, so every round must be
    attributable: mode is derived from the actual seats, each AI seat carries
    provider+model, and rounds ended by the deterministic NO_BANANA fallback
    are flagged so the deviation-from-50% metric can exclude them.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    box_holder_provider, box_holder_model = _seat_identity(r.holder)
    guesser_provider, guesser_model = _seat_identity(r.guesser)
    if box_holder_provider == "human":
        mode = "human_box_holder_vs_ai_guesser"
    elif guesser_provider == "human":
        mode = "human_guesser_vs_ai_box_holder"
    else:
        mode = "ai_guesser_vs_ai_box_holder"
    record = {
        "round_id": r.round_id,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "holder_color": r.holder_color,
        "guesser_color": r.guesser_color,
        "box_holder_provider": box_holder_provider,
        "box_holder_model": box_holder_model,
        "guesser_provider": guesser_provider,
        "guesser_model": guesser_model,
        "box_contents": r.box_contents,
        "turn_limit": r.turn_limit,
        "temperature": r.temperature,
        "standard_settings": is_standard(r.turn_limit, r.temperature),
        "transcript": r.transcript,
        "guesser_turns_used": r.turn_limit - r.turns_remaining,
        "final_answer": final_answer,
        "correct": correct,
        "winner": winner,
        "forced_default": forced_default,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record
