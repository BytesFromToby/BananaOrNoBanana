"""FastAPI referee: coin flip, Ollama proxy, static host, scorer, logger.

The server is the only place (besides the Box Holder's prompt) that knows the box contents;
no Guesser-facing response ever carries them.
"""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import game
from server.config import load_config
from server.host import verdict_line
from server.log import append_round
from server.ollama_client import list_models
from server.players import load_players, public_view

CONFIG = load_config()
PLAYERS = load_players(os.environ)

app = FastAPI(title="Banana or No Banana")


class SayBody(BaseModel):
    text: str


class GuessBody(BaseModel):
    answer: str


class RoundBody(BaseModel):
    model: Optional[str] = None
    turn_limit: Optional[int] = None
    temperature: Optional[float] = None


@app.get("/api/models")
async def models():
    return {
        "models": await list_models(CONFIG["ollama_url"]),
        "default": CONFIG["box_holder_model"],
    }


@app.get("/api/players")
async def players():
    """Browser-safe seat info — kind/provider/model only, never api_key."""
    return {"left": public_view(PLAYERS["left"]), "right": public_view(PLAYERS["right"])}


@app.post("/api/round")
async def create_round(body: Optional[RoundBody] = None):
    overrides = body.model_dump(exclude_none=True) if body else {}
    try:
        r = game.create_round(CONFIG, overrides=overrides, players=PLAYERS)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    async def stream():
        async for chunk in game.elicit_opening(r, CONFIG):
            yield chunk

    return StreamingResponse(
        stream(), media_type="text/plain", headers={"X-Round-Id": r.round_id}
    )


@app.post("/api/round/{round_id}/say")
async def say(round_id: str, body: SayBody):
    r = game.get_round(round_id)
    if r is None:
        raise HTTPException(status_code=404, detail="round not found")
    if r.right.kind == "ai":
        raise HTTPException(status_code=409, detail="right seat is AI-controlled; use /advance")
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
    """Drive one AI-Guesser turn (right seat is AI) — non-streamed, one call per turn.

    Either continues the exchange (a guesser line + a box-holder reply) or, if the
    Guesser's line parses as a lock-in, ends the round and returns the reveal directly.
    """
    r = game.get_round(round_id)
    if r is None:
        raise HTTPException(status_code=404, detail="round not found")
    if r.right.kind != "ai":
        raise HTTPException(status_code=409, detail="right seat is not AI-controlled")
    if r.status != "EXCHANGE":
        raise HTTPException(status_code=409, detail="round not in exchange")

    forced = r.turns_remaining <= 0
    guesser_text = await game.generate_guesser_text(r)
    answer = game.parse_answer(guesser_text)
    if answer is None and forced:
        # Safety net: the model didn't comply with the forced lock-in instruction.
        # Default to NO_BANANA rather than loop forever on an out-of-turns round.
        answer = game.NO_BANANA

    if answer is not None:
        result = game.score(answer, r.box_contents)
        append_round(
            r, CONFIG, final_answer=answer, correct=result["correct"], winner=result["winner"]
        )
        r.status = "DONE"
        box_contents = r.box_contents
        game.ROUNDS.pop(round_id, None)
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
    box_holder_text = "".join([c async for c in game.generate_box_holder(r, CONFIG, turn=turn)])
    return {
        "done": False,
        "guesser_text": guesser_text,
        "box_holder_text": box_holder_text,
        "turns_remaining": r.turns_remaining,
    }


# Serve the retro stage if it has been built (Slice 6). Guarded so the app imports without web/.
if os.path.isdir("web"):
    app.mount("/", StaticFiles(directory="web", html=True), name="web")
