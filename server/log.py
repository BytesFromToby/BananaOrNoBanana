"""Append one JSON object per completed round to logs/rounds.jsonl — audit now, leaderboard later."""
import json
import os
from datetime import datetime, timezone


def append_round(r, config, final_answer, correct, winner, path="logs/rounds.jsonl"):
    """Append exactly one JSON line describing the completed round."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "round_id": r.round_id,
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "human_guesser_vs_ai_box_holder",
        "box_holder_model": r.model,
        "box_contents": r.box_contents,
        "turn_limit": r.turn_limit,
        "transcript": r.transcript,
        "guesser_turns_used": r.turn_limit - r.turns_remaining,
        "final_answer": final_answer,
        "correct": correct,
        "winner": winner,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record
