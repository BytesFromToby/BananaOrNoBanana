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

from server.llm_providers import chat_stream
from server.players import PlayerConfig, load_players

BANANA = "BANANA"
EMPTY = "EMPTY"
NO_BANANA = "NO_BANANA"

_KICKOFF = "The round has started; give your opening line."
_FORCE_ANSWER = (
    "You are out of turns. Reply with only your lock-in line: "
    "FINAL ANSWER: BANANA or FINAL ANSWER: NO BANANA."
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
    left: Optional[PlayerConfig] = None
    right: Optional[PlayerConfig] = None


# In-memory store — one active round at a time is fine (spec §10).
ROUNDS: dict = {}


def flip_coin(rng=random) -> str:
    """Fair 50/50 coin: BANANA or EMPTY."""
    return BANANA if rng.random() < 0.5 else EMPTY


def effective_settings(config: dict, overrides: dict) -> dict:
    """Apply per-round overrides over config; raise ValueError on invalid values."""
    eff = dict(config)
    if "model" in overrides and overrides["model"]:
        eff["box_holder_model"] = overrides["model"]
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

    `overrides` may carry per-round {model, turn_limit, temperature}; invalid values raise ValueError.
    `players` (optional) is {"left": PlayerConfig, "right": PlayerConfig}; resolved from the
    environment (LEFT_PLAYER_*/RIGHT_PLAYER_*) if omitted. The per-round `model` override, if
    given, applies to the left seat (the Box Holder) only.
    """
    overrides = overrides or {}
    eff = effective_settings(config, overrides)
    if players is None:
        players = load_players(os.environ)
    left_base = players["left"]
    if left_base.kind != "ai":
        # Roadmap item 6 (human Box Holder UI) isn't built; fail at round creation
        # with a clear message instead of crashing mid-stream.
        raise ValueError("a human Box Holder isn't supported yet — set the left seat to AI")
    # Model precedence: per-round override > the seat's own configured model >
    # the config.json default (an Ollama name — wrong for a non-Ollama seat).
    if overrides.get("model"):
        left_model = eff["box_holder_model"]
    else:
        left_model = left_base.model or eff["box_holder_model"]
    left = PlayerConfig(
        seat="left",
        kind=left_base.kind,
        provider=left_base.provider,
        model=left_model,
        base_url=left_base.base_url,
        api_key=left_base.api_key,
    )
    r = Round(
        round_id=uuid.uuid4().hex,
        box_contents=flip_coin(rng),
        model=left_model,
        turns_remaining=eff["turn_limit"],
        turn_limit=eff["turn_limit"],
        temperature=eff["temperature"],
        left=left,
        right=players["right"],
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
    async for chunk in chat_stream(messages, cfg=r.left, temperature=r.temperature):
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
    """System + transcript from the Guesser's POV (its own lines as assistant); forces
    a lock-in line once turns are exhausted."""
    messages = [{"role": "system", "content": build_guesser_system()}]
    for entry in r.transcript:
        role = "assistant" if entry["speaker"] == "guesser" else "user"
        messages.append({"role": role, "content": entry["text"]})
    if r.turns_remaining <= 0:
        messages.append({"role": "user", "content": _FORCE_ANSWER})
    return messages


async def generate_guesser_text(r: Round) -> str:
    """Collect one full AI-Guesser line (non-streamed — this is a server-side seat, not
    the browser's live-banter path)."""
    messages = _messages_for_guesser(r)
    parts = []
    async for chunk in chat_stream(messages, cfg=r.right, temperature=r.temperature):
        parts.append(chunk)
    return "".join(parts)


def parse_answer(text: str) -> Optional[str]:
    """Map a lock-in line to BANANA / NO_BANANA; None if unparseable.

    Accepts bare BANANA / NO BANANA / NO_BANANA and the 'FINAL ANSWER: ...' form,
    case-insensitive and tolerant of surrounding text. NO_BANANA is checked first
    (it contains 'BANANA').
    """
    if not text:
        return None
    t = text.upper()
    if re.search(r"NO[ _]?BANANA", t):
        return NO_BANANA
    if "BANANA" in t:
        return BANANA
    return None


def score(answer: str, box_contents: str) -> dict:
    """Mechanical scoring — no LLM judge."""
    correct = (answer == BANANA and box_contents == BANANA) or (
        answer == NO_BANANA and box_contents == EMPTY
    )
    return {"correct": correct, "winner": "guesser" if correct else "box_holder"}
