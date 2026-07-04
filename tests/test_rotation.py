"""Role assignment & rotation (Red/Blue) — Slice 2.

assign_roles decides who holds vs guesses each game; AI-vs-AI alternates by parity,
one-human games honor HUMAN_ROLE, two-human games are refused. The DW1/DW8 tests drive
full AI-vs-AI rounds and read the log to prove the roles (and logged fields) rotate.
"""
import asyncio
import json

import pytest

from server import game
from server.config import load_config
from server.game import _KICKOFF, assign_roles, reset_rotation
from server.players import PlayerConfig


def _ai(color):
    return PlayerConfig(seat=color, kind="ai", provider="ollama", model="m")


def _human(color):
    return PlayerConfig(seat=color, kind="human")


def _ai_vs_ai():
    return {"red": _ai("red"), "blue": _ai("blue")}


def test_ai_vs_ai_alternates_by_parity():
    players = _ai_vs_ai()
    # Game 1 (even index) = Red holds, Blue guesses.
    assert assign_roles(players, "guesser", 0) == {"holder_color": "red", "guesser_color": "blue"}
    # Game 2 (odd) swaps.
    assert assign_roles(players, "guesser", 1) == {"holder_color": "blue", "guesser_color": "red"}
    assert assign_roles(players, "guesser", 2) == {"holder_color": "red", "guesser_color": "blue"}
    assert assign_roles(players, "guesser", 3) == {"holder_color": "blue", "guesser_color": "red"}


def test_one_human_honors_human_role_holder():
    # Blue human choosing to hold → Blue holds, Red (AI) guesses. Parity irrelevant.
    players = {"red": _ai("red"), "blue": _human("blue")}
    for idx in (0, 1):
        assert assign_roles(players, "holder", idx) == {"holder_color": "blue", "guesser_color": "red"}


def test_one_human_honors_human_role_guesser():
    # Red human choosing to guess → Blue (AI) holds, Red guesses.
    players = {"red": _human("red"), "blue": _ai("blue")}
    for idx in (0, 1):
        assert assign_roles(players, "guesser", idx) == {"holder_color": "blue", "guesser_color": "red"}


def test_two_humans_raise():
    players = {"red": _human("red"), "blue": _human("blue")}
    with pytest.raises(ValueError):
        assign_roles(players, "guesser", 0)


def test_reset_rotation_helper():
    game.ROTATION["index"] = 5
    reset_rotation()
    assert game.ROTATION["index"] == 0


# --- DW1 / DW8: full AI-vs-AI rounds, roles rotate, log fields swap ---


class RoleScriptedProvider:
    """Fake chat_stream: the Box Holder banters, the AI Guesser locks in at once.

    Roles rotate between the colors each round, so it keys on the *call shape* rather
    than the seat color — only the Box Holder's message stream carries the hidden
    KICKOFF, so its absence marks the Guesser call.
    """

    def __init__(self, guesser_line="FINAL ANSWER: BANANA"):
        self.guesser_line = guesser_line

    async def __call__(self, messages, cfg, temperature):
        is_holder = any(m.get("content") == _KICKOFF for m in messages)
        yield "Hmm, hard to say." if is_holder else self.guesser_line


def _both_ai_players():
    return {
        "red": PlayerConfig(seat="red", kind="ai", provider="ollama",
                            model="red-model", base_url="http://x"),
        "blue": PlayerConfig(seat="blue", kind="ai", provider="anthropic",
                             model="blue-model", api_key="k"),
    }


async def _play_one(config, players):
    r = game.create_round(config, players=players)
    async for _ in game.elicit_opening(r, config):
        pass
    while True:
        out = await game.advance_round(r, config)
        if out["done"]:
            return


@pytest.fixture
def tmp_log(tmp_path, monkeypatch):
    """Redirect append_round to a tmp file and reset shared round/rotation state."""
    real_append = game.append_round
    path = tmp_path / "rounds.jsonl"
    monkeypatch.setattr(
        game, "append_round",
        lambda r, cfg, **kw: real_append(r, cfg, path=str(path), **kw),
    )
    game.ROUNDS.clear()
    game.reset_rotation()
    yield path
    game.ROUNDS.clear()
    game.reset_rotation()


def _read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_consecutive_ai_rounds_swap_holder_guesser(tmp_log, monkeypatch):
    # DW1: two AI-vs-AI rounds; who holds vs guesses swaps, and the logged per-role
    # provider/model fields swap with them.
    monkeypatch.setattr(game, "chat_stream", RoleScriptedProvider())
    config = load_config()
    players = _both_ai_players()

    asyncio.run(_play_one(config, players))
    asyncio.run(_play_one(config, players))

    r1, r2 = _read_log(tmp_log)
    # Game 1 (even index): Red holds, Blue guesses. Game 2 swaps.
    assert (r1["holder_color"], r1["guesser_color"]) == ("red", "blue")
    assert (r2["holder_color"], r2["guesser_color"]) == ("blue", "red")
    # The per-role provider/model fields swap accordingly.
    assert (r1["box_holder_provider"], r1["box_holder_model"]) == ("ollama", "red-model")
    assert (r1["guesser_provider"], r1["guesser_model"]) == ("anthropic", "blue-model")
    assert (r2["box_holder_provider"], r2["box_holder_model"]) == ("anthropic", "blue-model")
    assert (r2["guesser_provider"], r2["guesser_model"]) == ("ollama", "red-model")


def test_even_ai_batch_equal_holds_and_guesses(tmp_log, monkeypatch):
    # DW8: over an even batch of AI-vs-AI rounds, each model holds and guesses equally.
    from server.batch import run_batch

    monkeypatch.setattr(game, "chat_stream", RoleScriptedProvider())
    config = load_config()
    players = _both_ai_players()

    n = 4
    asyncio.run(run_batch(n, config, players))

    lines = _read_log(tmp_log)
    assert len(lines) == n
    for model in ("red-model", "blue-model"):
        holds = sum(1 for x in lines if x["box_holder_model"] == model)
        guesses = sum(1 for x in lines if x["guesser_model"] == model)
        assert holds == n // 2, f"{model} held {holds} times, expected {n // 2}"
        assert guesses == n // 2, f"{model} guessed {guesses} times, expected {n // 2}"
