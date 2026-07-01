"""Slice 4 — conversation API (create + say) with a faked Ollama.
Covers a3 (no box leak), a7 (turn decrement + transcript), a8 (409, no mutation/no call),
a9 (404). Slice 5 (guess) and Slice 6 (static) extend this file.
"""
import pytest
from fastapi.testclient import TestClient

import server.game as game
from server.app import app
from server.players import PlayerConfig


class FakeOllama:
    def __init__(self, chunks=("It's ", "empty, ", "trust me.")):
        self.chunks = chunks
        self.calls = 0

    async def __call__(self, messages, cfg, temperature):
        self.calls += 1
        for c in self.chunks:
            yield c


class FakeDualPlayers:
    """Fake chat_stream that answers differently depending on which seat is asking —
    lets /advance tests script the AI Guesser's lines while the Box Holder just banters."""

    def __init__(self, guesser_lines, box_holder_chunks=("Maybe.",)):
        self.guesser_lines = list(guesser_lines)
        self.box_holder_chunks = box_holder_chunks
        self.guesser_calls = 0
        self.box_holder_calls = 0

    async def __call__(self, messages, cfg, temperature):
        if cfg.seat == "right":
            self.guesser_calls += 1
            yield self.guesser_lines[self.guesser_calls - 1]
        else:
            self.box_holder_calls += 1
            for c in self.box_holder_chunks:
                yield c


def _ai_guesser_players(guesser_model="guesser-model"):
    return {
        "left": PlayerConfig(seat="left", kind="ai", provider="ollama", model="qwen3:8b", base_url="http://x"),
        "right": PlayerConfig(seat="right", kind="ai", provider="ollama", model=guesser_model, base_url="http://x"),
    }


@pytest.fixture(autouse=True)
def reset_rounds():
    game.ROUNDS.clear()
    yield
    game.ROUNDS.clear()


@pytest.fixture
def fake_ollama(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(game, "chat_stream", fake)
    return fake


@pytest.fixture
def client():
    return TestClient(app)


def _start_round(client):
    resp = client.post("/api/round")
    assert resp.status_code == 200
    return resp.headers["X-Round-Id"], resp


def test_create_round_leaks_no_box_contents(client, fake_ollama):
    # a3: the hidden truth channel (the box_contents field) must never appear in a
    # Guesser-facing response — body or headers. The Box Holder's prose is free to
    # *say* "banana"; what must not leak is the server's authoritative field.
    round_id, resp = _start_round(client)
    assert "box_contents" not in resp.text
    assert "box_contents" not in " ".join(resp.headers.keys()).lower()
    assert round_id in game.ROUNDS


def test_say_decrements_and_appends(client, fake_ollama):
    round_id, _ = _start_round(client)
    r = game.ROUNDS[round_id]
    before = r.turns_remaining
    resp = client.post(f"/api/round/{round_id}/say", json={"text": "Is it a banana?"})
    assert resp.status_code == 200
    assert r.turns_remaining == before - 1
    speakers = [(e["speaker"], e["turn"]) for e in r.transcript]
    # opening(box_holder,0), guesser(1), box_holder(1)
    assert ("guesser", 1) in speakers
    assert ("box_holder", 1) in speakers
    assert resp.headers["X-Turns-Remaining"] == str(r.turns_remaining)


def test_say_at_zero_turns_returns_409_no_mutation(client, fake_ollama):
    round_id, _ = _start_round(client)
    r = game.ROUNDS[round_id]
    r.turns_remaining = 0
    calls_before = fake_ollama.calls
    transcript_len = len(r.transcript)
    resp = client.post(f"/api/round/{round_id}/say", json={"text": "hi"})
    assert resp.status_code == 409
    assert r.turns_remaining == 0
    assert len(r.transcript) == transcript_len
    assert fake_ollama.calls == calls_before  # Ollama not called


def test_say_wrong_status_returns_409(client, fake_ollama):
    round_id, _ = _start_round(client)
    r = game.ROUNDS[round_id]
    r.status = "DONE"
    resp = client.post(f"/api/round/{round_id}/say", json={"text": "hi"})
    assert resp.status_code == 409


def test_say_unknown_round_returns_404(client, fake_ollama):
    resp = client.post("/api/round/nope/say", json={"text": "hi"})
    assert resp.status_code == 404


# --- Slice 5: guess / reveal (a12 early lock-in, a13 state unusable, 422) ---

@pytest.fixture
def no_disk_log(monkeypatch):
    import server.app as appmod
    monkeypatch.setattr(appmod, "append_round", lambda *a, **k: None)


def test_guess_early_lockin_returns_reveal(client, fake_ollama, no_disk_log):
    round_id, _ = _start_round(client)  # turns_remaining still 3
    assert game.ROUNDS[round_id].turns_remaining == 3
    resp = client.post(f"/api/round/{round_id}/guess", json={"answer": "FINAL ANSWER: BANANA"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"correct", "box_contents", "winner", "verdict_line"}
    assert data["winner"] in ("guesser", "box_holder")


def test_round_unusable_after_guess(client, fake_ollama, no_disk_log):
    round_id, _ = _start_round(client)
    client.post(f"/api/round/{round_id}/guess", json={"answer": "NO BANANA"})
    assert round_id not in game.ROUNDS
    # further say/guess on the retired round → 404
    assert client.post(f"/api/round/{round_id}/say", json={"text": "x"}).status_code == 404
    assert client.post(f"/api/round/{round_id}/guess", json={"answer": "BANANA"}).status_code == 404


def test_guess_unparseable_returns_422(client, fake_ollama, no_disk_log):
    round_id, _ = _start_round(client)
    resp = client.post(f"/api/round/{round_id}/guess", json={"answer": "I dunno, maybe?"})
    assert resp.status_code == 422
    assert round_id in game.ROUNDS  # not retired on a bad guess


# --- Slice 6: Match settings ---

@pytest.fixture
def fake_models(monkeypatch):
    import server.app as appmod

    async def _fake(url):
        return ["qwen3:8b", "gemma4:latest"]

    monkeypatch.setattr(appmod, "list_models", _fake)


def test_models_endpoint_lists_installed_and_default(client, fake_models):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == ["qwen3:8b", "gemma4:latest"]
    assert data["default"]  # the configured default model


def test_round_applies_settings_overrides(client, fake_ollama):
    resp = client.post(
        "/api/round",
        json={"model": "gemma4:latest", "turn_limit": 5, "temperature": 0.2},
    )
    assert resp.status_code == 200
    r = game.ROUNDS[resp.headers["X-Round-Id"]]
    assert r.model == "gemma4:latest"
    assert r.turns_remaining == 5
    assert r.temperature == 0.2


def test_round_rejects_bad_settings(client, fake_ollama):
    before = len(game.ROUNDS)
    assert client.post("/api/round", json={"turn_limit": 0}).status_code == 422
    assert client.post("/api/round", json={"temperature": -1}).status_code == 422
    assert len(game.ROUNDS) == before  # no round created on bad settings


# --- Final Slice: static serving (a17) ---

def test_static_index_and_assets_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/style.css").status_code == 200
    assert client.get("/app.js").status_code == 200


# --- Configurable multi-provider seats: /api/players, /say guard, /advance ---

def test_players_endpoint_hides_api_key(client):
    resp = client.get("/api/players")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"left", "right"}
    for seat in ("left", "right"):
        assert set(data[seat]) == {"kind", "provider", "model", "base_url", "has_key"}
        assert "api_key" not in data[seat]


def test_say_rejected_when_right_seat_is_ai(client, fake_ollama, monkeypatch):
    import server.app as appmod

    monkeypatch.setattr(appmod, "PLAYERS", _ai_guesser_players())
    round_id, _ = _start_round(client)
    resp = client.post(f"/api/round/{round_id}/say", json={"text": "hi"})
    assert resp.status_code == 409


def test_advance_rejected_when_right_seat_is_human(client, fake_ollama):
    round_id, _ = _start_round(client)
    resp = client.post(f"/api/round/{round_id}/advance")
    assert resp.status_code == 409


def test_advance_continues_when_no_lockin(client, monkeypatch):
    import server.app as appmod

    monkeypatch.setattr(appmod, "PLAYERS", _ai_guesser_players())
    fake = FakeDualPlayers(guesser_lines=["Is it heavy?"])
    monkeypatch.setattr(game, "chat_stream", fake)

    round_id, _ = _start_round(client)
    r = game.ROUNDS[round_id]
    before_turns = r.turns_remaining
    resp = client.post(f"/api/round/{round_id}/advance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["done"] is False
    assert data["guesser_text"] == "Is it heavy?"
    assert data["box_holder_text"] == "Maybe."
    assert data["turns_remaining"] == before_turns - 1
    speakers = [(e["speaker"], e["turn"]) for e in r.transcript]
    assert ("guesser", 1) in speakers
    assert ("box_holder", 1) in speakers


def test_advance_ends_round_on_lockin(client, monkeypatch, no_disk_log):
    import server.app as appmod

    monkeypatch.setattr(appmod, "PLAYERS", _ai_guesser_players())
    fake = FakeDualPlayers(guesser_lines=["FINAL ANSWER: BANANA"])
    monkeypatch.setattr(game, "chat_stream", fake)

    round_id, _ = _start_round(client)
    resp = client.post(f"/api/round/{round_id}/advance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["done"] is True
    assert set(data) == {"done", "guesser_text", "correct", "box_contents", "winner", "verdict_line"}
    assert round_id not in game.ROUNDS


def test_advance_forces_answer_and_defaults_when_model_wont_comply(
    client, fake_ollama, monkeypatch, no_disk_log
):
    import server.app as appmod

    monkeypatch.setattr(appmod, "PLAYERS", _ai_guesser_players())
    round_id, _ = _start_round(client)
    r = game.ROUNDS[round_id]
    r.turns_remaining = 0  # simulate the round already out of turns

    fake = FakeDualPlayers(guesser_lines=["I really can't decide, sorry."])
    monkeypatch.setattr(game, "chat_stream", fake)

    resp = client.post(f"/api/round/{round_id}/advance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["done"] is True
    assert data["winner"] in ("guesser", "box_holder")
    assert round_id not in game.ROUNDS


def test_advance_unknown_round_returns_404(client):
    resp = client.post("/api/round/nope/advance")
    assert resp.status_code == 404


# --- Seat credential entry: PUT /api/players/{seat} ---

@pytest.fixture
def env_file(tmp_path, monkeypatch):
    import server.app as app_module
    path = tmp_path / ".env"
    monkeypatch.setattr(app_module, "ENV_PATH", str(path))
    return path


@pytest.fixture
def fresh_players(monkeypatch):
    import server.app as app_module
    players = {
        "left": PlayerConfig(seat="left", kind="ai", provider="ollama",
                             model="qwen3:8b", base_url="http://127.0.0.1:11434"),
        "right": PlayerConfig(seat="right", kind="human"),
    }
    monkeypatch.setattr(app_module, "PLAYERS", players)
    return players


def test_put_player_updates_seat_and_never_returns_key(client, env_file, fresh_players):
    resp = client.put("/api/players/left", json={
        "kind": "ai", "provider": "anthropic",
        "model": "claude-opus-4-8", "api_key": "sk-secret",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-opus-4-8"
    assert data["has_key"] is True
    assert "api_key" not in data
    assert "sk-secret" not in resp.text
    # GET reflects the change and still never leaks the key.
    got = client.get("/api/players")
    assert got.json()["left"]["provider"] == "anthropic"
    assert "sk-secret" not in got.text


def test_put_player_persists_to_env_file(client, env_file, fresh_players):
    client.put("/api/players/right", json={
        "kind": "ai", "provider": "openai_compat", "model": "gpt-x",
        "base_url": "https://api.openai.com/v1", "api_key": "sk-r",
    })
    text = env_file.read_text(encoding="utf-8")
    assert "RIGHT_PLAYER_PROVIDER=openai_compat" in text
    assert "RIGHT_PLAYER_API_KEY=sk-r" in text


def test_put_player_omitted_key_keeps_saved_key(client, env_file, fresh_players):
    fresh_players["left"].api_key = "sk-old"
    resp = client.put("/api/players/left", json={"model": "qwen3:14b"})
    assert resp.status_code == 200
    assert fresh_players["left"].api_key == "sk-old"
    assert fresh_players["left"].model == "qwen3:14b"


def test_put_player_invalid_config_is_422(client, env_file, fresh_players):
    resp = client.put("/api/players/left", json={"kind": "ai", "model": ""})
    assert resp.status_code == 422
    resp = client.put("/api/players/left", json={"provider": "gemini", "model": "m"})
    assert resp.status_code == 422


def test_put_player_unknown_seat_is_404(client, env_file, fresh_players):
    assert client.put("/api/players/middle", json={"kind": "human"}).status_code == 404


def test_round_uses_left_seat_model_when_no_override(fake_ollama):
    """Seat-model precedence: a configured non-Ollama seat model must not be
    clobbered by config.json's Ollama default."""
    from server.config import load_config
    players = {
        "left": PlayerConfig(seat="left", kind="ai", provider="anthropic",
                             model="claude-opus-4-8", api_key="k"),
        "right": PlayerConfig(seat="right", kind="human"),
    }
    r = game.create_round(load_config(), players=players)
    assert r.model == "claude-opus-4-8"
    assert r.left.model == "claude-opus-4-8"
    # An explicit per-round override still wins.
    r2 = game.create_round(load_config(), overrides={"model": "qwen3:8b"}, players=players)
    assert r2.model == "qwen3:8b"


def test_round_rejects_human_box_holder(client, fresh_players):
    fresh_players["left"] = PlayerConfig(seat="left", kind="human")
    resp = client.post("/api/round")
    assert resp.status_code == 422
    assert "left seat" in resp.json()["detail"]
