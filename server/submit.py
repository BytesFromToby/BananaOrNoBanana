"""Opt-in submission of completed rounds to the community arena.

Nothing is ever sent unless the player asks (`python -m server.submit`, or `--submit`
on the batch runner). Submitted round_ids are tracked locally so nothing is sent twice.
API keys/URLs come from env; the transport is injectable so tests never hit the network.
"""
import argparse
import json
import os
import sys

import httpx

from server.arena import build_payload, get_or_create_client_id
from server.stats import load_rounds

DEFAULT_ARENA_URL = "https://banana-arena.example.workers.dev"
_SUBMITTED_PATH = os.path.join("logs", "submitted.jsonl")
_ROUNDS_PATH = os.path.join("logs", "rounds.jsonl")


def load_submitted(path: str = _SUBMITTED_PATH) -> set:
    """The set of round_ids already accepted by the arena."""
    if not os.path.exists(path):
        return set()
    ids = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                ids.add(json.loads(line)["round_id"])
    return ids


def mark_submitted(round_ids, path: str = _SUBMITTED_PATH) -> None:
    """Record round_ids as submitted (one JSON line each) so they're never re-sent."""
    if not round_ids:
        return
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for rid in round_ids:
            f.write(json.dumps({"round_id": rid, "submitted_at": ts}) + "\n")


def unsent_rounds(rounds_path: str = _ROUNDS_PATH, submitted_path: str = _SUBMITTED_PATH) -> list:
    """Round records in the log that haven't been accepted by the arena yet."""
    already = load_submitted(submitted_path)
    return [r for r in load_rounds(rounds_path) if r.get("round_id") not in already]


def _default_transport(url, payload, headers):
    resp = httpx.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def submit(rounds, url, maintainer_key=None, client_id=None, transport=_default_transport,
           submitted_path: str = _SUBMITTED_PATH) -> dict:
    """POST rounds to the arena; mark accepted + duplicate ids submitted. Nothing on failure.

    `transport(url, payload, headers) -> dict` is injectable so tests never touch the network.
    Returns the arena's `{accepted, duplicates, rejected}` response (or a synthetic empty one).
    """
    if not rounds:
        return {"accepted": 0, "duplicates": [], "rejected": []}
    if client_id is None:
        client_id = get_or_create_client_id()
    payload = build_payload(rounds, client_id)
    headers = {"Content-Type": "application/json"}
    if maintainer_key:
        headers["X-Maintainer-Key"] = maintainer_key
    result = transport(f"{url.rstrip('/')}/api/submit", payload, headers)
    # Accepted rounds AND duplicates are "done" — both mean the arena has them.
    accepted_ids = set(result.get("accepted_ids") or [])
    if not accepted_ids and result.get("accepted"):
        # Server reported a count but not ids: treat all non-rejected as accepted.
        rejected_ids = {r.get("round_id") for r in result.get("rejected", [])}
        accepted_ids = {r["round_id"] for r in rounds if r["round_id"] not in rejected_ids}
    done_ids = accepted_ids | set(result.get("duplicates") or [])
    mark_submitted(sorted(done_ids), submitted_path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Submit completed rounds to the community arena.")
    parser.add_argument("--url", default=os.environ.get("ARENA_URL", DEFAULT_ARENA_URL))
    parser.add_argument("--rounds-path", default=_ROUNDS_PATH)
    args = parser.parse_args(argv)

    rounds = unsent_rounds(args.rounds_path)
    if not rounds:
        print("Nothing to submit — all logged rounds are already in the arena.")
        return
    key = os.environ.get("ARENA_MAINTAINER_KEY") or None
    print(f"Submitting {len(rounds)} round(s) to {args.url} ...")
    try:
        result = submit(rounds, args.url, maintainer_key=key)
    except Exception as e:  # network / server error — nothing marked submitted
        sys.exit(f"Submission failed: {e}")
    print(
        f"accepted={result.get('accepted', 0)} "
        f"duplicates={len(result.get('duplicates', []))} "
        f"rejected={len(result.get('rejected', []))}"
    )
    for rej in result.get("rejected", []):
        print(f"  rejected {rej.get('round_id', '?')}: {rej.get('reason', '?')}")


if __name__ == "__main__":
    main()
