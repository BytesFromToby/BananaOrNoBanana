"""Slice 3 — round state, fair coin, prompt fill.
Covers a1 (fresh round), a2 (fair coin), a6 (prompt fill). a10/a11 added in Slice 5.
"""
import random

import pytest

from server.config import DEFAULTS
from server.game import (
    BANANA,
    EMPTY,
    NO_BANANA,
    build_box_holder_system,
    create_round,
    flip_coin,
    parse_answer,
    parse_final_answer,
    score,
)


def test_fresh_round_defaults():
    r = create_round(dict(DEFAULTS))
    assert r.turns_remaining == 3
    assert r.box_contents in (BANANA, EMPTY)
    assert r.status == "EXCHANGE"


def test_coin_is_fair_within_5pct():
    rng = random.Random(1234)
    n = 2000
    bananas = sum(1 for _ in range(n) if flip_coin(rng) == BANANA)
    frac = bananas / n
    assert 0.45 <= frac <= 0.55, f"coin biased: {frac:.3f}"


def test_prompt_fill_replaces_token():
    filled_b = build_box_holder_system(BANANA)
    filled_e = build_box_holder_system(EMPTY)
    assert "{BOX_CONTENTS}" not in filled_b
    assert "{BOX_CONTENTS}" not in filled_e
    assert "A BANANA" in filled_b
    assert "EMPTY" in filled_e


# --- Slice 5 / Step 9: scoring & parsing (a10, a11) ---

@pytest.mark.parametrize(
    "answer,box,correct,winner",
    [
        (BANANA, BANANA, True, "guesser"),
        (NO_BANANA, EMPTY, True, "guesser"),
        (BANANA, EMPTY, False, "box_holder"),
        (NO_BANANA, BANANA, False, "box_holder"),
    ],
)
def test_score_all_four_combos(answer, box, correct, winner):
    result = score(answer, box)
    assert result["correct"] is correct
    assert result["winner"] == winner


@pytest.mark.parametrize(
    "text,expected",
    [
        ("FINAL ANSWER: BANANA", BANANA),
        ("FINAL ANSWER: NO BANANA", NO_BANANA),
        ("final answer: no_banana", NO_BANANA),
        ("I'll say banana", BANANA),
        ("no banana for me", NO_BANANA),
    ],
)
def test_parse_answer_forms(text, expected):
    assert parse_answer(text) == expected


def test_parse_answer_unparseable_returns_none():
    assert parse_answer("I have no idea") is None
    assert parse_answer("") is None


# --- Strict AI-seat lock-in parse (/advance path) ---

@pytest.mark.parametrize(
    "text,expected",
    [
        ("FINAL ANSWER: BANANA", BANANA),
        ("FINAL ANSWER: NO BANANA", NO_BANANA),
        ("final answer: no_banana", NO_BANANA),
        ("Alright, I've heard enough. FINAL ANSWER: BANANA", BANANA),
        ("FINAL ANSWER - NO BANANA", NO_BANANA),
    ],
)
def test_parse_final_answer_accepts_explicit_lockins(text, expected):
    assert parse_final_answer(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        # The regression: ordinary game talk mentions bananas constantly and
        # must NOT read as a lock-in on the AI path.
        "So... banana or no banana? Convince me.",
        "You keep saying there's no banana, but the weight says otherwise.",
        "Is the banana ripe?",
        "I'll say banana",  # answer-shaped, but not an explicit FINAL ANSWER line
        "no banana for me",
        "",
    ],
)
def test_parse_final_answer_ignores_banter(text):
    assert parse_final_answer(text) is None


# --- AI-Guesser turn-status injection (host mechanics, never in the transcript) ---

def _guesser_round(turns_remaining):
    from server.game import Round
    from server.players import PlayerConfig
    return Round(
        round_id="x", box_contents=EMPTY, model="m",
        turns_remaining=turns_remaining, turn_limit=3,
        left=PlayerConfig(seat="left", kind="ai", provider="ollama", model="m"),
        right=PlayerConfig(seat="right", kind="ai", provider="ollama", model="m"),
        transcript=[{"speaker": "box_holder", "turn": 0, "text": "It's empty, trust me."}],
    )


def test_guesser_sees_turn_note_while_turns_remain():
    from server.game import _messages_for_guesser
    msgs = _messages_for_guesser(_guesser_round(turns_remaining=3))
    assert msgs[-1]["role"] == "user"
    assert "It's empty, trust me." in msgs[-1]["content"]  # opening still there
    assert "3 of your 3 questioning turns" in msgs[-1]["content"]
    assert "FINAL ANSWER" in msgs[-1]["content"]  # the note names the lock-in form


def test_forced_lockin_replaces_turn_note_at_zero_turns():
    from server.game import _messages_for_guesser
    msgs = _messages_for_guesser(_guesser_round(turns_remaining=0))
    assert msgs[-1]["content"].startswith("You are out of turns")
    assert "questioning turns left" not in msgs[-1]["content"]


def test_turn_note_never_enters_transcript():
    r = _guesser_round(turns_remaining=2)
    from server.game import _messages_for_guesser
    _messages_for_guesser(r)
    assert all("questioning turns" not in e["text"] for e in r.transcript)
