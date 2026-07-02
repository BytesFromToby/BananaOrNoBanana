"""Batch runner & local leaderboard — the deviation-from-50% experiment, locally."""
import asyncio

import pytest

import server.game as game
from server.batch import main as batch_main
from server.batch import run_batch
from server.config import DEFAULTS
from server.players import PlayerConfig
from server.stats import aggregate, render


class ScriptedPlayers:
    """chat_stream fake: the guesser follows a per-round script; the box holder banters."""

    def __init__(self, guesser_scripts):
        # guesser_scripts: list of lists — one list of lines per round, consumed in order.
        self.scripts = [list(s) for s in guesser_scripts]
        self.round_idx = -1

    async def __call__(self, messages, cfg, temperature):
        if cfg.seat == "right":
            yield self.scripts[self.round_idx].pop(0)
        else:
            if not messages[1:]:  # opening elicitation happens once per round
                pass
            yield "Trust me."


def _players(guesser_model="qwen3:8b"):
    return {
        "left": PlayerConfig(seat="left", kind="ai", provider="ollama", model="qwen3:8b"),
        "right": PlayerConfig(seat="right", kind="ai", provider="ollama", model=guesser_model),
    }


@pytest.fixture(autouse=True)
def clean_rounds():
    game.ROUNDS.clear()
    yield
    game.ROUNDS.clear()


@pytest.fixture
def captured_log(monkeypatch):
    records = []

    def fake_append(r, config, final_answer, correct, winner, forced_default=False, **kw):
        records.append({
            "final_answer": final_answer, "correct": correct,
            "winner": winner, "forced_default": forced_default,
        })

    monkeypatch.setattr(game, "append_round", fake_append)
    return records


def _fresh_fake(monkeypatch, scripts):
    fake = ScriptedPlayers(scripts)

    orig_create = game.create_round

    def counting_create(*a, **kw):
        fake.round_idx += 1
        return orig_create(*a, **kw)

    monkeypatch.setattr(game, "chat_stream", fake)
    return counting_create, fake


def test_batch_runs_n_rounds_and_logs_each(monkeypatch, captured_log):
    # Round 1: locks in on turn 1. Round 2: banters (banana talk!) then locks.
    # Round 3: never complies — forced default at 0 turns.
    scripts = [
        ["FINAL ANSWER: BANANA"],
        ["banana or no banana, hmm?", "still thinking about that banana...",
         "one more banana question", "FINAL ANSWER: NO BANANA"],
        ["banana?", "banana!", "banana...", "I just can't decide."],
    ]
    counting_create, fake = _fresh_fake(monkeypatch, scripts)
    monkeypatch.setattr(game, "create_round", counting_create)
    # run_batch references game.create_round via the game module, so the counter applies.

    results = asyncio.run(run_batch(3, dict(DEFAULTS), _players()))
    assert len(results) == 3
    assert all(out["done"] for out in results)
    assert len(captured_log) == 3
    assert captured_log[0]["final_answer"] == "BANANA"
    assert captured_log[1]["final_answer"] == "NO_BANANA"
    assert captured_log[1]["forced_default"] is False
    assert captured_log[2]["forced_default"] is True  # never complied
    assert game.ROUNDS == {}  # every round retired


def test_batch_main_refuses_human_right_seat(monkeypatch):
    import server.batch as batch_mod
    monkeypatch.setattr(batch_mod, "load_players", lambda env: {
        "left": PlayerConfig(seat="left", kind="ai", provider="ollama", model="m"),
        "right": PlayerConfig(seat="right", kind="human"),
    })
    with pytest.raises(SystemExit) as exc:
        batch_main(["--rounds", "1"])
    assert "right seat" in str(exc.value).lower()


# --- Leaderboard aggregation ---

def _rec(winner, forced=False, bh=("ollama", "qwen3:8b"), g=("anthropic", "claude-opus-4-8")):
    return {
        "box_holder_provider": bh[0], "box_holder_model": bh[1],
        "guesser_provider": g[0], "guesser_model": g[1],
        "winner": winner, "forced_default": forced,
        "standard_settings": True,
    }


def test_aggregate_groups_and_computes_deviation():
    rounds = (
        [_rec("guesser")] * 6 + [_rec("box_holder")] * 4          # matchup A: 60% guesser
        + [_rec("guesser", g=("human", ""))] * 1                   # matchup B: human guesser
        + [_rec("box_holder", forced=True)] * 3                    # forced: excluded from A
    )
    rows = aggregate(rounds)
    assert len(rows) == 2
    a = next(r for r in rows if r["guesser"] == "anthropic/claude-opus-4-8")
    assert a["rounds"] == 10
    assert a["guesser_wins"] == 6
    assert a["win_rate"] == pytest.approx(0.6)
    assert a["deviation"] == pytest.approx(0.1)
    assert a["forced_excluded"] == 3
    b = next(r for r in rows if r["guesser"] == "human")
    assert b["rounds"] == 1


def test_aggregate_handles_legacy_lines_without_seat_fields():
    # Legacy lines predate both the seat fields and standard_settings: they
    # group under 'unknown' and are excluded from the metric as non-standard.
    rows = aggregate([{"winner": "guesser"}])
    assert rows[0]["box_holder"] == "unknown"
    assert rows[0]["guesser"] == "unknown"
    assert rows[0]["rounds"] == 0
    assert rows[0]["non_standard_excluded"] == 1


def test_render_contains_matchup_and_deviation():
    text = render(aggregate([_rec("guesser"), _rec("box_holder")]))
    assert "ollama/qwen3:8b" in text
    assert "anthropic/claude-opus-4-8" in text
    assert "+0.0%" in text or "-0.0%" in text or "0.0%" in text


def test_render_empty_log():
    assert "No rounds logged yet" in render(aggregate([]))


def test_aggregate_excludes_non_standard_rounds():
    """Bypass-leaderboard-settings rounds play and log but never count."""
    std = _rec("guesser")
    hot = {**_rec("guesser"), "standard_settings": False}
    legacy = {k: v for k, v in _rec("guesser").items() if k != "standard_settings"}
    rows = aggregate([std, std, hot, legacy])
    assert rows[0]["rounds"] == 2
    assert rows[0]["non_standard_excluded"] == 2
