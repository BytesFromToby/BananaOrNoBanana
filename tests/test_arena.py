"""Community arena — client submission (wire format, client_id, opt-in) and
Python↔Worker aggregation parity via a shared fixture."""
import json
import os

import pytest

from server import arena, submit
from server.stats import aggregate

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


# --- Slice 1: wire format & client_id ---

def test_client_id_created_once_and_stable(tmp_path):
    path = str(tmp_path / "arena_client_id")
    a = arena.get_or_create_client_id(path)
    b = arena.get_or_create_client_id(path)
    assert a == b
    assert len(a) == 32  # uuid4 hex
    # a fresh path mints a different id
    other = arena.get_or_create_client_id(str(tmp_path / "other_id"))
    assert other != a


def test_build_payload_envelope_and_verbatim_rounds():
    rounds = [{"round_id": "x", "winner": "guesser", "transcript": [{"speaker": "box_holder"}]}]
    payload = arena.build_payload(rounds, client_id="cid123")
    assert payload["schema_version"] == arena.SCHEMA_VERSION == 1
    assert payload["client_version"] == arena.CLIENT_VERSION
    assert payload["client_id"] == "cid123"
    assert payload["rounds"] == rounds  # verbatim, no reshaping


# --- Slice 2: submission module & opt-in ---

def _rounds_log(tmp_path, ids):
    p = tmp_path / "rounds.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for i in ids:
            f.write(json.dumps({"round_id": i, "winner": "guesser"}) + "\n")
    return str(p)


def test_unsent_rounds_excludes_already_submitted(tmp_path):
    rounds_path = _rounds_log(tmp_path, ["r1", "r2", "r3"])
    submitted_path = str(tmp_path / "submitted.jsonl")
    submit.mark_submitted(["r1"], submitted_path)
    unsent = submit.unsent_rounds(rounds_path, submitted_path)
    assert [r["round_id"] for r in unsent] == ["r2", "r3"]


def test_submit_sends_unsent_and_marks_accepted(tmp_path):
    rounds_path = _rounds_log(tmp_path, ["r1", "r2"])
    submitted_path = str(tmp_path / "submitted.jsonl")
    sent = {}

    def fake_transport(url, payload, headers):
        sent["url"] = url
        sent["payload"] = payload
        sent["headers"] = headers
        return {"accepted": 2, "accepted_ids": ["r1", "r2"], "duplicates": [], "rejected": []}

    rounds = submit.unsent_rounds(rounds_path, submitted_path)
    result = submit.submit(rounds, "https://arena.test", client_id="cid",
                           transport=fake_transport, submitted_path=submitted_path)
    assert result["accepted"] == 2
    assert sent["url"] == "https://arena.test/api/submit"
    assert [r["round_id"] for r in sent["payload"]["rounds"]] == ["r1", "r2"]
    # both now marked submitted → a second pass sends nothing
    assert submit.unsent_rounds(rounds_path, submitted_path) == []


def test_submit_marks_duplicates_as_done_too(tmp_path):
    rounds_path = _rounds_log(tmp_path, ["r1"])
    submitted_path = str(tmp_path / "submitted.jsonl")

    def fake_transport(url, payload, headers):
        return {"accepted": 0, "accepted_ids": [], "duplicates": ["r1"], "rejected": []}

    rounds = submit.unsent_rounds(rounds_path, submitted_path)
    submit.submit(rounds, "https://arena.test", client_id="cid",
                  transport=fake_transport, submitted_path=submitted_path)
    assert submit.unsent_rounds(rounds_path, submitted_path) == []  # duplicate counts as done


def test_submit_marks_nothing_on_failure(tmp_path):
    rounds_path = _rounds_log(tmp_path, ["r1", "r2"])
    submitted_path = str(tmp_path / "submitted.jsonl")

    def failing_transport(url, payload, headers):
        raise RuntimeError("network down")

    rounds = submit.unsent_rounds(rounds_path, submitted_path)
    with pytest.raises(RuntimeError):
        submit.submit(rounds, "https://arena.test", client_id="cid",
                      transport=failing_transport, submitted_path=submitted_path)
    # nothing marked → still all unsent
    assert len(submit.unsent_rounds(rounds_path, submitted_path)) == 2


def test_maintainer_key_sent_as_header(tmp_path):
    rounds_path = _rounds_log(tmp_path, ["r1"])
    submitted_path = str(tmp_path / "submitted.jsonl")
    captured = {}

    def fake_transport(url, payload, headers):
        captured.update(headers)
        return {"accepted": 1, "accepted_ids": ["r1"], "duplicates": [], "rejected": []}

    rounds = submit.unsent_rounds(rounds_path, submitted_path)
    submit.submit(rounds, "https://arena.test", maintainer_key="mkey", client_id="cid",
                  transport=fake_transport, submitted_path=submitted_path)
    assert captured.get("X-Maintainer-Key") == "mkey"


def test_submit_empty_is_noop():
    result = submit.submit([], "https://arena.test", transport=lambda *a: 1 / 0)
    assert result == {"accepted": 0, "duplicates": [], "rejected": []}


def test_batch_no_submit_makes_no_network_call(monkeypatch):
    """Running batch without --submit must never call the submit path."""
    import server.batch as batch_mod
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1

    monkeypatch.setattr("server.submit.main", boom)

    # Stub the actual round-running so the test stays offline and fast.
    async def fake_run_batch(*a, **k):
        return []

    monkeypatch.setattr(batch_mod, "run_batch", fake_run_batch)
    monkeypatch.setattr(batch_mod.stats, "main", lambda: None)
    from server.players import PlayerConfig
    monkeypatch.setattr(batch_mod, "load_players", lambda env: {
        "left": PlayerConfig(seat="left", kind="ai", provider="ollama", model="m"),
        "right": PlayerConfig(seat="right", kind="ai", provider="ollama", model="m"),
    })
    batch_mod.main(["--rounds", "1"])  # no --submit
    assert called["n"] == 0


# --- Slice 3: Python↔Worker aggregation parity ---

def test_aggregate_matches_golden_fixture():
    """The shared fixture the Worker's vitest also consumes: same rounds in, same rows out.
    Golden rows are hand-specified (the intended answer), so this proves stats.py correct,
    not just self-consistent."""
    rounds = json.load(open(os.path.join(FIXTURE_DIR, "arena_rounds.json"), encoding="utf-8"))
    golden = json.load(open(os.path.join(FIXTURE_DIR, "arena_golden.json"), encoding="utf-8"))
    rows = aggregate(rounds)
    shared_keys = {"box_holder", "guesser", "rounds", "guesser_wins", "win_rate",
                   "deviation", "forced_excluded", "non_standard_excluded"}
    trimmed = [{k: r[k] for k in shared_keys} for r in rows]
    # Compare as sorted-by-rounds-desc lists (both stats.py and the golden use that order).
    assert trimmed == golden
