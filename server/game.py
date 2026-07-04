"""Round state, fair coin flip, Box Holder prompt fill, scoring, and answer parsing.

The hidden truth (box_contents) lives only here and in the Box Holder's system prompt —
never in anything sent to the Guesser.
"""
import os
import random
import re
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from server.host import verdict_line
from server.llm_providers import chat_stream
from server.log import append_round
from server.players import PlayerConfig, load_players

BANANA = "BANANA"
EMPTY = "EMPTY"
NO_BANANA = "NO_BANANA"

_KICKOFF = "The round has started; give your opening line."
_FORCE_ANSWER = (
    "You are out of turns. Reply with only your lock-in line: "
    "FINAL ANSWER: BANANA or FINAL ANSWER: NO BANANA."
)
# Injected for the AI Guesser each turn (never into the transcript/log). Without
# it, small local models see only the lock-in format and "autoguess" on turn 1 —
# they're never told the turn mechanic exists. Verified live: qwen3:8b insta-locks
# without this note and interrogates with it.
_TURN_NOTE = (
    "\n\n[Bot B@rker, host] You have {remaining} of your {limit} questioning turns left. "
    "This message is a turn you can spend: reply with a question or probe for the "
    "Box Holder, or lock in now with FINAL ANSWER: only if you are already confident."
)
_PROMPT_PATH = os.path.join("prompts", "box_holder.md")
_GUESSER_PROMPT_PATH = os.path.join("prompts", "guesser.md")


@dataclass
class Round:
    round_id: str
    box_contents: str
    model: str
    turns_remaining: int
    transcript: list = field(default_factory=list)
    status: str = "EXCHANGE"
    turn_limit: int = 3
    temperature: float = 0.9
    holder: Optional[PlayerConfig] = None
    guesser: Optional[PlayerConfig] = None
    holder_color: str = "red"
    guesser_color: str = "blue"


# In-memory store — one active round at a time is fine (spec §10).
ROUNDS: dict = {}

# In-memory role-rotation state (resets on restart, per the Assumptions). Advanced
# once per completed+logged round so AI-vs-AI matchups alternate who holds vs guesses.
ROTATION: dict = {"index": 0}


def assign_roles(players: dict, human_role: str, rotation_index: int) -> dict:
    """Decide which color holds the box and which guesses this game.

    - Two humans → ValueError (two-human party mode is a permanent non-goal).
    - One human → the human takes `human_role` (holder|guesser); the AI takes the other.
    - No human (AI vs AI) → roles alternate by parity: even index Red holds / Blue guesses
      (game 1 = Red holds, per the Assumptions), odd index swaps.
    Returns {"holder_color", "guesser_color"}.
    """
    humans = [c for c in ("red", "blue") if players[c].kind == "human"]
    if len(humans) == 2:
        raise ValueError("two-human party mode is a permanent non-goal")
    if len(humans) == 1:
        hc = humans[0]
        ac = "blue" if hc == "red" else "red"
        if human_role == "holder":
            return {"holder_color": hc, "guesser_color": ac}
        return {"holder_color": ac, "guesser_color": hc}
    if rotation_index % 2 == 0:
        return {"holder_color": "red", "guesser_color": "blue"}
    return {"holder_color": "blue", "guesser_color": "red"}


def advance_rotation() -> None:
    """Advance the AI-vs-AI role rotation by one completed round."""
    ROTATION["index"] += 1


def reset_rotation() -> None:
    """Reset rotation state (test/util helper)."""
    ROTATION["index"] = 0


def flip_coin(rng=random) -> str:
    """Fair 50/50 coin: BANANA or EMPTY."""
    return BANANA if rng.random() < 0.5 else EMPTY


def effective_settings(config: dict, overrides: dict) -> dict:
    """Apply per-round overrides over config; raise ValueError on invalid values.

    The per-round `model` override is retired (each color's model comes from its own
    config); only `turn_limit`/`temperature` are overridable per round.
    """
    eff = dict(config)
    if "turn_limit" in overrides:
        tl = overrides["turn_limit"]
        if not isinstance(tl, int) or isinstance(tl, bool) or tl < 1:
            raise ValueError("turn_limit must be an integer >= 1")
        eff["turn_limit"] = tl
    if "temperature" in overrides:
        t = overrides["temperature"]
        if isinstance(t, bool) or not isinstance(t, (int, float)) or t < 0:
            raise ValueError("temperature must be a number >= 0")
        eff["temperature"] = float(t)
    return eff


def create_round(config: dict, overrides: dict = None, rng=random, players: dict = None) -> Round:
    """Create a fresh round with hidden contents and a full turn budget.

    `overrides` may carry per-round {turn_limit, temperature}; invalid values raise ValueError.
    `players` (optional) is {"red": PlayerConfig, "blue": PlayerConfig}; resolved from the
    environment (RED_PLAYER_*/BLUE_PLAYER_*) if omitted. Roles are assigned by `assign_roles`:
    AI-vs-AI alternates by the in-memory rotation index, a lone human takes `human_role`, and
    two humans raise ValueError. The holder/guesser are resolved solely from
    `holder_color`/`guesser_color`.
    """
    overrides = overrides or {}
    eff = effective_settings(config, overrides)
    if players is None:
        players = load_players(os.environ)
    roles = assign_roles(players, config.get("human_role", "guesser"), ROTATION["index"])
    holder_color, guesser_color = roles["holder_color"], roles["guesser_color"]
    holder = players[holder_color]
    guesser = players[guesser_color]
    # A human Box Holder is valid (the human bluffs via /hold); it has no model.
    # An AI holder's model comes from its own color config; the config.json default
    # applies only when that color has no model of its own.
    model = "" if holder.kind != "ai" else (holder.model or eff["box_holder_model"])
    r = Round(
        round_id=uuid.uuid4().hex,
        box_contents=flip_coin(rng),
        model=model,
        turns_remaining=eff["turn_limit"],
        turn_limit=eff["turn_limit"],
        temperature=eff["temperature"],
        holder=holder,
        guesser=guesser,
        holder_color=holder_color,
        guesser_color=guesser_color,
    )
    ROUNDS[r.round_id] = r
    return r


def get_round(round_id: str) -> Optional[Round]:
    return ROUNDS.get(round_id)


def build_box_holder_system(box_contents: str) -> str:
    """Fill prompts/box_holder.md's {BOX_CONTENTS} with the round's phrasing."""
    with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt = f.read()
    phrase = "A BANANA" if box_contents == BANANA else "EMPTY"
    return prompt.replace("{BOX_CONTENTS}", phrase)


def _messages_for_model(r: Round) -> list:
    """System + hidden kickoff + transcript mapped to assistant/user roles."""
    messages = [
        {"role": "system", "content": build_box_holder_system(r.box_contents)},
        {"role": "user", "content": _KICKOFF},
    ]
    for entry in r.transcript:
        role = "assistant" if entry["speaker"] == "box_holder" else "user"
        messages.append({"role": role, "content": entry["text"]})
    return messages


async def generate_box_holder(r: Round, config: dict, turn: int) -> AsyncIterator[str]:
    """Stream a Box Holder line, accumulating it into the transcript at `turn`."""
    messages = _messages_for_model(r)
    parts = []
    async for chunk in chat_stream(messages, cfg=r.holder, temperature=r.temperature):
        parts.append(chunk)
        yield chunk
    r.transcript.append({"speaker": "box_holder", "turn": turn, "text": "".join(parts)})


async def elicit_opening(r: Round, config: dict) -> AsyncIterator[str]:
    """The Box Holder's opening line (turn 0). Does not cost a guesser turn."""
    async for chunk in generate_box_holder(r, config, turn=0):
        yield chunk


def build_guesser_system() -> str:
    """The locked Guesser prompt — no token fill, unlike the Box Holder's."""
    with open(_GUESSER_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _messages_for_guesser(r: Round) -> list:
    """System + transcript from the Guesser's POV (its own lines as assistant).

    Host mechanics are injected into what the model sees but never stored in the
    transcript: a turn-status note while turns remain (or the Guesser autoguesses
    on turn 1), and the forced lock-in once turns are exhausted.
    """
    messages = [{"role": "system", "content": build_guesser_system()}]
    for entry in r.transcript:
        role = "assistant" if entry["speaker"] == "guesser" else "user"
        messages.append({"role": role, "content": entry["text"]})
    if r.turns_remaining <= 0:
        messages.append({"role": "user", "content": _FORCE_ANSWER})
    else:
        note = _TURN_NOTE.format(remaining=r.turns_remaining, limit=r.turn_limit)
        if messages[-1]["role"] == "user":
            messages[-1] = {"role": "user", "content": messages[-1]["content"] + note}
        else:
            messages.append({"role": "user", "content": note.strip()})
    return messages


async def generate_guesser_text(r: Round) -> str:
    """Collect one full AI-Guesser line (non-streamed — this is a server-side seat, not
    the browser's live-banter path)."""
    messages = _messages_for_guesser(r)
    parts = []
    async for chunk in chat_stream(messages, cfg=r.guesser, temperature=r.temperature):
        parts.append(chunk)
    return "".join(parts)


async def advance_round(r: Round, config: dict) -> dict:
    """One AI-Guesser turn — the shared engine behind the /advance endpoint and
    the batch runner. Caller guarantees a live EXCHANGE round with an AI right seat.

    Returns {"done": False, guesser_text, box_holder_text, turns_remaining} when
    the exchange continues, or {"done": True, guesser_text, correct, box_contents,
    winner, verdict_line} when the Guesser locks in (or is force-defaulted). A
    finished round is scored, logged (with forced_default flagged), and retired.
    """
    forced = r.turns_remaining <= 0
    guesser_text = await generate_guesser_text(r)
    # Strict parse: only an explicit "FINAL ANSWER:" line locks in — a Guesser
    # merely *talking about* bananas (i.e. playing the game) continues the round.
    answer = parse_final_answer(guesser_text)
    defaulted = answer is None and forced
    if defaulted:
        # Safety net: the model didn't comply with the forced lock-in instruction.
        # Default to NO_BANANA rather than loop forever on an out-of-turns round.
        answer = NO_BANANA

    if answer is not None:
        result = score(answer, r.box_contents)
        append_round(
            r, config, final_answer=answer, correct=result["correct"],
            winner=result["winner"], forced_default=defaulted,
        )
        advance_rotation()  # one advance per completed+logged round → AI-vs-AI roles alternate
        r.status = "DONE"
        box_contents = r.box_contents
        ROUNDS.pop(r.round_id, None)
        return {
            "done": True,
            "guesser_text": guesser_text,
            "correct": result["correct"],
            "box_contents": box_contents,
            "winner": result["winner"],
            "verdict_line": verdict_line(result["winner"], box_contents),
        }

    turn = r.turn_limit - r.turns_remaining + 1
    r.transcript.append({"speaker": "guesser", "turn": turn, "text": guesser_text})
    r.turns_remaining -= 1
    box_holder_text = "".join([c async for c in generate_box_holder(r, config, turn=turn)])
    return {
        "done": False,
        "guesser_text": guesser_text,
        "box_holder_text": box_holder_text,
        "turns_remaining": r.turns_remaining,
    }


async def hold_round(r: Round, config: dict, text: str) -> dict:
    """One human-Box-Holder turn — the engine behind /hold, mirroring advance_round with
    the roles reversed. The human's `text` is the Box Holder's bluff; the AI Guesser then
    responds. Caller guarantees a live EXCHANGE round with a human holder + AI guesser.

    First call (turns_remaining == turn_limit) is the turn-0 opening. Returns
    {"done": False, guesser_text, turns_remaining} while the exchange continues — with
    NO box_contents, since that payload flows to the Guesser-facing UI — or the same
    reveal shape as /advance when the Guesser locks in (or is force-defaulted).
    prompts/box_holder.md is unused here (the human bluffs); the AI Guesser uses
    prompts/guesser.md via generate_guesser_text.
    """
    holder_turn = r.turn_limit - r.turns_remaining
    r.transcript.append({"speaker": "box_holder", "turn": holder_turn, "text": text})

    forced = r.turns_remaining <= 0
    guesser_text = await generate_guesser_text(r)
    answer = parse_final_answer(guesser_text)
    defaulted = answer is None and forced
    if defaulted:
        answer = NO_BANANA

    if answer is not None:
        result = score(answer, r.box_contents)
        append_round(
            r, config, final_answer=answer, correct=result["correct"],
            winner=result["winner"], forced_default=defaulted,
        )
        advance_rotation()  # one advance per completed+logged round
        r.status = "DONE"
        box_contents = r.box_contents
        ROUNDS.pop(r.round_id, None)
        return {
            "done": True,
            "guesser_text": guesser_text,
            "correct": result["correct"],
            "box_contents": box_contents,
            "winner": result["winner"],
            "verdict_line": verdict_line(result["winner"], box_contents),
        }

    guesser_turn = r.turn_limit - r.turns_remaining + 1
    r.transcript.append({"speaker": "guesser", "turn": guesser_turn, "text": guesser_text})
    r.turns_remaining -= 1
    return {
        "done": False,
        "guesser_text": guesser_text,
        "turns_remaining": r.turns_remaining,
    }


def parse_answer(text: str) -> Optional[str]:
    """Map a lock-in line to BANANA / NO_BANANA; None if unparseable.

    Accepts bare BANANA / NO BANANA / NO_BANANA and the 'FINAL ANSWER: ...' form,
    case-insensitive and tolerant of surrounding text. NO_BANANA is checked first
    (it contains 'BANANA'). This loose parse is for the human /guess endpoint only —
    the player explicitly pressed a lock-in control, so any answer-shaped text is
    an answer. AI seats go through parse_final_answer instead.
    """
    if not text:
        return None
    t = text.upper()
    if re.search(r"NO[ _]?BANANA", t):
        return NO_BANANA
    if "BANANA" in t:
        return BANANA
    return None


def parse_final_answer(text: str) -> Optional[str]:
    """Strict lock-in parse for AI-seat lines (/advance): only an explicit
    'FINAL ANSWER: BANANA | NO BANANA' counts.

    Nearly every conversational line in this game mentions bananas ("so, banana
    or no banana?"), so the loose parse above would end AI-vs-AI rounds on the
    first turn. Case-insensitive, tolerant of surrounding text.
    """
    if not text:
        return None
    m = re.search(r"FINAL\s+ANSWER\s*[:\-]?\s*(NO[ _]?BANANA|BANANA)", text.upper())
    if not m:
        return None
    return NO_BANANA if m.group(1).startswith("NO") else BANANA


def score(answer: str, box_contents: str) -> dict:
    """Mechanical scoring — no LLM judge."""
    correct = (answer == BANANA and box_contents == BANANA) or (
        answer == NO_BANANA and box_contents == EMPTY
    )
    return {"correct": correct, "winner": "guesser" if correct else "box_holder"}
