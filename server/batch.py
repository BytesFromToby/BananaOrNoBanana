"""AI-vs-AI batch runner — run N unattended rounds under the configured seats,
log each one, and print the local leaderboard.

Usage: python -m server.batch --rounds 10 [--turn-limit 3]
Seats come from .env (or the settings panel, which writes .env); the right seat
must be AI. Drives the same game.advance_round engine as the /advance endpoint.
"""
import argparse
import asyncio
import os
import sys

from server import game, stats
from server.config import load_config
from server.players import load_players


async def run_batch(n: int, config: dict, players: dict, turn_limit=None) -> list:
    """Run n complete rounds; returns the reveal dict of each. Every round
    terminates: lock-in, or the forced NO_BANANA default at 0 turns."""
    results = []
    for i in range(n):
        overrides = {"turn_limit": turn_limit} if turn_limit else {}
        r = game.create_round(config, overrides=overrides, players=players)
        async for _ in game.elicit_opening(r, config):
            pass
        while True:
            out = await game.advance_round(r, config)
            if out["done"]:
                results.append(out)
                print(
                    f"round {i + 1}/{n}: box={out['box_contents']:<6} "
                    f"winner={out['winner']}",
                    flush=True,
                )
                break
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run N AI-vs-AI rounds and print the leaderboard.")
    parser.add_argument("--rounds", type=int, default=10, help="rounds to play (default 10)")
    parser.add_argument("--turn-limit", type=int, default=None, help="guesser turns per round")
    parser.add_argument("--submit", action="store_true",
                        help="opt-in: submit this run's rounds to the community arena when done")
    args = parser.parse_args(argv)

    config = load_config()
    players = load_players(os.environ)
    if players["right"].kind != "ai":
        sys.exit(
            "The right seat (Guesser) is human — a batch needs two AI seats.\n"
            "Set RIGHT_PLAYER_TYPE=ai in .env or flip the seat in the settings panel."
        )
    if players["left"].kind != "ai":
        sys.exit("The left seat (Box Holder) must be AI.")

    print(
        f"Batch: {args.rounds} rounds — "
        f"{players['left'].provider}/{players['left'].model or config['box_holder_model']} (holder) vs "
        f"{players['right'].provider}/{players['right'].model} (guesser)\n"
    )
    asyncio.run(run_batch(args.rounds, config, players, turn_limit=args.turn_limit))
    print()
    stats.main()

    if args.submit:
        # Opt-in only. Submits all not-yet-submitted rounds (this run's included).
        from server import submit as submit_mod

        print()
        submit_mod.main([])


if __name__ == "__main__":
    main()
