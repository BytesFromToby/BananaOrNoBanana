"""Bot B@rker — the scripted host. Display name "Bot B@rker"; code identifier "Bot Barker".

Flavor only; the server scores. Line pools for intro, reveal, and verdict, plus the
running sign-off gag. Not an LLM — pure scripted showbiz.
"""
import random

# Duplicated from game.py rather than imported: game imports verdict_line from
# here, so importing back would be circular. It's a one-word wire constant.
BANANA = "BANANA"

SIGN_OFF = "Help control the bot population — have your model fine-tuned and aligned."

INTRO_LINES = [
    "Come on down! It's time for Banana or No Banana!",
    "Welcome, folks, to the only show where one robot lies and the other pays for it!",
    "Our Box Holder has peeked inside. Can you read a machine's poker face?",
]

_REVEAL_BANANA = [
    "Let's open that box... it's A BANANA!",
    "Doors, please! Behind them — one glorious banana!",
]

_REVEAL_EMPTY = [
    "Let's open that box... it's EMPTY! Not a banana in sight!",
    "Doors, please! And it's... nothing at all — an empty box!",
]

_VERDICT_WIN = [
    "And you called it! The Guesser takes the round!",
    "Give it up for our Guesser — dead on the money!",
]

_VERDICT_LOSE = [
    "The Box Holder had you fooled! This round goes to the liar.",
    "Ohh, so close — the Box Holder sells the con and wins it!",
]


def intro_line(rng=random) -> str:
    return rng.choice(INTRO_LINES)


def verdict_line(winner: str, box_contents: str, rng=random) -> str:
    """A single Bot B@rker reveal-plus-verdict line."""
    reveal = rng.choice(_REVEAL_BANANA if box_contents == BANANA else _REVEAL_EMPTY)
    verdict = rng.choice(_VERDICT_WIN if winner == "guesser" else _VERDICT_LOSE)
    line = f"{reveal} {verdict}"
    if rng.random() < 0.25:
        line = f"{line} {SIGN_OFF}"
    return line
