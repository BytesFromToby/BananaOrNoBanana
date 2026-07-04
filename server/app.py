"""FastAPI referee: coin flip, Ollama proxy, static host, scorer, logger.

The server is the only place (besides the Box Holder's prompt) that knows the box contents;
no Guesser-facing response ever carries them.
"""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import game
from server.config import load_config
from server.host import verdict_line
from server.log import append_round
from server.ollama_client import list_models
from server.players import build_seat, load_players, persist_seat_env, public_view

CONFIG = load_config()
PLAYERS = load_players(os.environ)
ENV_PATH = ".env"  # seat config is persisted here; tests point this at a tmp file

app = FastAPI(title="Banana or No Banana")


class SayBody(BaseModel):
    text: str


class GuessBody(BaseModel):
    answer: str


class RoundBody(BaseModel):
    model: Optional[str] = None
    turn_limit: Optional[int] = None
    temperature: Optional[float] = None


class SeatBody(BaseModel):
    kind: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # omitted = keep the saved key; "" = clear it


@app.get("/api/models")
async def models():
    return {
        "models": await list_models(CONFIG["ollama_url"]),
        "default": CONFIG["box_holder_model"],
    }


@app.get("/api/players")
async def players():
    """Browser-safe seat info — kind/provider/model/base_url/has_key, never api_key."""
    return {"red": public_view(PLAYERS["red"]), "blue": public_view(PLAYERS["blue"])}


@app.put("/api/players/{seat}")
async def update_player(seat: str, body: SeatBody):
    """Configure a color from the browser (localhost, single user). The API key is
    write-only: accepted here, persisted to .env, never returned. Replaces the seat
    object rather than mutating it, so a round already in flight keeps its config."""
    if seat not in ("red", "blue"):
        raise HTTPException(status_code=404, detail="seat must be 'red' or 'blue'")
    try:
        cfg = build_seat(seat, body.model_dump(exclude_unset=True), current=PLAYERS[seat])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    PLAYERS[seat] = cfg
    persist_seat_env("RED_PLAYER" if seat == "red" else "BLUE_PLAYER", cfg, path=ENV_PATH)
    return public_view(cfg)


@app.post("/api/round")
async def create_round(body: Optional[RoundBody] = None):
    overrides = body.model_dump(exclude_none=True) if body else {}
    try:
        r = game.create_round(CONFIG, overrides=overrides, players=PLAYERS)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if r.holder.kind == "human":
        # The requester IS the Box Holder, so revealing the box here is allowed — the
        # no-leak invariant only bars Guesser-facing responses. No AI opening; the human
        # bluffs via /hold.
        return JSONResponse({
            "round_id": r.round_id,
            "holder_color": r.holder_color,
            "guesser_color": r.guesser_color,
            "box_contents": r.box_contents,
        })

    async def stream():
        async for chunk in game.elicit_opening(r, CONFIG):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/plain",
        headers={
            "X-Round-Id": r.round_id,
            "X-Holder-Color": r.holder_color,
            "X-Guesser-Color": r.guesser_color,
        },
    )


@app.post("/api/round/{round_id}/say")
async def say(round_id: str, body: SayBody):
    r = game.get_round(round_id)
    if r is None:
        raise HTTPException(status_code=404, detail="round not found")
    if r.guesser.kind != "human":
        raise HTTPException(status_code=409, detail="the Guesser is AI-controlled; use /advance")
    if r.turns_remaining <= 0 or r.status != "EXCHANGE":
        raise HTTPException(status_code=409, detail="no turns left or round not in exchange")

    turn = r.turn_limit - r.turns_remaining + 1
    r.transcript.append({"speaker": "guesser", "turn": turn, "text": body.text})
    r.turns_remaining -= 1

    async def stream():
        async for chunk in game.generate_box_holder(r, CONFIG, turn=turn):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/plain",
        headers={"X-Turns-Remaining": str(r.turns_remaining)},
    )


@app.post("/api/round/{round_id}/hold")
async def hold(round_id: str, body: SayBody):
    """Drive one human-Box-Holder turn — the human's bluff in, the AI Guesser's line out.

    The mirror of /advance: /hold requires a human holder (+ AI guesser), /advance requires
    an AI guesser regardless of holder. The reveal is returned directly on lock-in.
    """
    r = game.get_round(round_id)
    if r is None:
        raise HTTPException(status_code=404, detail="round not found")
    if r.holder.kind != "human":
        raise HTTPException(status_code=409, detail="this round has no human Box Holder")
    if r.status != "EXCHANGE":
        raise HTTPException(status_code=409, detail="round not in exchange")

    return await game.hold_round(r, CONFIG, body.text)


@app.post("/api/round/{round_id}/guess")
async def guess(round_id: str, body: GuessBody):
    r = game.get_round(round_id)
    if r is None:
        raise HTTPException(status_code=404, detail="round not found")
    answer = game.parse_answer(body.answer)
    if answer is None:
        raise HTTPException(status_code=422, detail="unparseable answer")

    result = game.score(answer, r.box_contents)
    append_round(
        r, CONFIG, final_answer=answer, correct=result["correct"], winner=result["winner"]
    )
    game.advance_rotation()  # one advance per completed+logged round (human-Guesser path)
    r.status = "DONE"
    box_contents = r.box_contents
    game.ROUNDS.pop(round_id, None)

    return {
        "correct": result["correct"],
        "box_contents": box_contents,
        "winner": result["winner"],
        "verdict_line": verdict_line(result["winner"], box_contents),
    }


@app.post("/api/round/{round_id}/advance")
async def advance(round_id: str):
    """Drive one AI-Guesser turn (the Guesser is AI) — non-streamed, one call per turn.

    Either continues the exchange (a guesser line + a box-holder reply) or, if the
    Guesser's line parses as a lock-in, ends the round and returns the reveal directly.
    """
    r = game.get_round(round_id)
    if r is None:
        raise HTTPException(status_code=404, detail="round not found")
    if r.guesser.kind != "ai":
        raise HTTPException(status_code=409, detail="the Guesser is not AI-controlled")
    if r.status != "EXCHANGE":
        raise HTTPException(status_code=409, detail="round not in exchange")

    return await game.advance_round(r, CONFIG)


# Serve the retro stage if it has been built (Slice 6). Guarded so the app imports without web/.
if os.path.isdir("web"):
    app.mount("/", StaticFiles(directory="web", html=True), name="web")
