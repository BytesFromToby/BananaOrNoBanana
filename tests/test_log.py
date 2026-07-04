"""Slice 5 — round logging (a14 one JSON line, a15 all fields, a16 transcript fidelity).
Amended 2026-07-01: seat-aware fields (mode from seats, per-seat provider/model, forced_default)."""
import json

from server.config import DEFAULTS
from server.game import Round
from server.log import append_round
from server.players import PlayerConfig

REQUIRED_FIELDS = {
    "round_id", "ts", "mode", "holder_color", "guesser_color",
    "box_holder_provider", "box_holder_model",
    "guesser_provider", "guesser_model", "box_contents", "turn_limit",
    "transcript", "guesser_turns_used", "final_answer", "correct", "winner",
    "forced_default",
}


def _round(guesser=None):
    return Round(
        round_id="abc123",
        box_contents="EMPTY",
        model="qwen3:8b",
        turns_remaining=1,
        turn_limit=3,
        holder=PlayerConfig(seat="red", kind="ai", provider="ollama", model="qwen3:8b"),
        guesser=guesser or PlayerConfig(seat="blue", kind="human"),
        holder_color="red",
        guesser_color="blue",
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


def test_mode_and_seats_derived_not_hardcoded(tmp_path):
    """Amended Done-when: mode follows the actual seats; each AI seat is attributable."""
    path = str(tmp_path / "rounds.jsonl")
    ai_guesser = PlayerConfig(seat="blue", kind="ai", provider="anthropic", model="claude-opus-4-8")
    append_round(_round(guesser=ai_guesser), dict(DEFAULTS), "BANANA", False, "box_holder", path=path)
    obj = json.loads(open(path, encoding="utf-8").read().splitlines()[0])
    assert obj["mode"] == "ai_guesser_vs_ai_box_holder"
    assert obj["box_holder_provider"] == "ollama"
    assert obj["guesser_provider"] == "anthropic"
    assert obj["guesser_model"] == "claude-opus-4-8"


def test_human_guesser_logged_as_human(tmp_path):
    path = str(tmp_path / "rounds.jsonl")
    append_round(_round(), dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    obj = json.loads(open(path, encoding="utf-8").read().splitlines()[0])
    assert obj["guesser_provider"] == "human"
    assert obj["guesser_model"] == ""


def test_forced_default_flag(tmp_path):
    """Amended Done-when: fallback-ended rounds are distinguishable so the
    deviation-from-50% metric can exclude them."""
    path = str(tmp_path / "rounds.jsonl")
    append_round(_round(), dict(DEFAULTS), "NO_BANANA", True, "guesser",
                 forced_default=True, path=path)
    append_round(_round(), dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    lines = open(path, encoding="utf-8").read().splitlines()
    assert json.loads(lines[0])["forced_default"] is True
    assert json.loads(lines[1])["forced_default"] is False


def test_transcript_order_and_turns_preserved(tmp_path):
    path = str(tmp_path / "rounds.jsonl")
    r = _round()
    append_round(r, dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    obj = json.loads(open(path, encoding="utf-8").read().splitlines()[0])
    assert [(e["speaker"], e["turn"]) for e in obj["transcript"]] == [
        ("box_holder", 0), ("guesser", 1), ("box_holder", 1), ("guesser", 2), ("box_holder", 2)
    ]


def test_temperature_and_standard_flag_logged(tmp_path):
    """Rounds record the conditions they ran under; bypass rounds are marked."""
    path = str(tmp_path / "rounds.jsonl")
    std = _round()  # turn_limit 3; Round default temperature 0.7? set explicitly
    std.temperature = 0.7
    append_round(std, dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    hot = _round()
    hot.temperature = 1.2
    append_round(hot, dict(DEFAULTS), "NO_BANANA", True, "guesser", path=path)
    lines = [json.loads(l) for l in open(path, encoding="utf-8").read().splitlines()]
    assert lines[0]["temperature"] == 0.7
    assert lines[0]["standard_settings"] is True
    assert lines[1]["temperature"] == 1.2
    assert lines[1]["standard_settings"] is False
