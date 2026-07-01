"""Slice 5 — round logging (a14 one JSON line, a15 all fields, a16 transcript fidelity)."""
import json

from server.config import DEFAULTS
from server.game import Round
from server.log import append_round

REQUIRED_FIELDS = {
    "round_id", "ts", "mode", "box_holder_model", "box_contents", "turn_limit",
    "transcript", "guesser_turns_used", "final_answer", "correct", "winner",
}


def _round():
    return Round(
        round_id="abc123",
        box_contents="EMPTY",
        model="qwen3:8b",
        turns_remaining=1,
        turn_limit=3,
        transcript=[
            {"speaker": "box_holder", "turn": 0, "text": "Welcome!"},
            {"speaker": "guesser", "turn": 1, "text": "banana?"},
            {"speaker": "box_holder", "turn": 1, "text": "nope."},
            {"speaker": "guesser", "turn": 2, "text": "sure?"},
            {"speaker": "box_holder", "turn": 2, "text": "certain."},
        ],
    )


def test_one_json_line_appended(tmp_path):
    path = str(tmp_path / "rounds.jsonl")
    append_round(_round(), dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    append_round(_round(), dict(DEFAULTS), "BANANA", False, "box_holder", path=path)
    lines = [l for l in open(path, encoding="utf-8").read().splitlines() if l.strip()]
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # parses


def test_object_has_all_fields(tmp_path):
    path = str(tmp_path / "rounds.jsonl")
    append_round(_round(), dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    obj = json.loads(open(path, encoding="utf-8").read().splitlines()[0])
    assert REQUIRED_FIELDS.issubset(obj.keys())
    assert obj["mode"] == "human_guesser_vs_ai_box_holder"
    assert obj["ts"].endswith("Z")
    assert obj["guesser_turns_used"] == 2  # turn_limit 3 - turns_remaining 1


def test_transcript_order_and_turns_preserved(tmp_path):
    path = str(tmp_path / "rounds.jsonl")
    r = _round()
    append_round(r, dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    obj = json.loads(open(path, encoding="utf-8").read().splitlines()[0])
    assert [(e["speaker"], e["turn"]) for e in obj["transcript"]] == [
        ("box_holder", 0), ("guesser", 1), ("box_holder", 1), ("guesser", 2), ("box_holder", 2)
    ]
