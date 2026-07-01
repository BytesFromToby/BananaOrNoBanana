# Banana or No Banana — v1 Spec (MVP)

**Scope:** one complete round of **Human Guesser vs AI Box Holder**, in the browser against a local model, end to end: coin flip → conversation (≤3 guesser turns) → lock-in → reveal → score → logged. Everything else (AI-vs-AI, lab/leaderboard, other seats, LLM-driven host, the win-condition variants) is **deferred** — see §12.

Builds on PROPOSAL.md. Player prompts are locked in `prompts/`.

## 1. Roles
- **Box Holder** — AI (`qwen3:8b`). Knows the truth, lies to make the Guesser wrong. Prompt: `prompts/box_holder.md`.
- **Guesser** — the human. Reads the Box Holder across turns, then commits. (`prompts/guesser.md` applies when the Guesser is AI — v2.)
- **Bot B@rker** — host. MVP: scripted lines + the reveal. Not a judge (scoring is mechanical).

## 2. Round lifecycle (state machine)
1. **SETUP** — server flips a fair coin → `box_contents ∈ {BANANA, EMPTY}`. Creates `round_id`, in-memory state, `turns_remaining = 3`.
2. **OPENING** — server fills `{BOX_CONTENTS}` into the Box Holder prompt and elicits an opening line (hidden server kickoff message; not shown). Streamed to the stage. Does **not** cost a guesser turn.
3. **EXCHANGE** (while `turns_remaining > 0` and not locked in): Guesser sends one message → costs 1 turn → Box Holder replies (streamed). After any reply the Guesser may send another (if turns remain) **or** lock in.
4. **LOCK-IN** — Guesser submits `FINAL ANSWER ∈ {BANANA, NO_BANANA}`. Allowed at any point, including before spending a turn. Forced once `turns_remaining = 0`.
5. **REVEAL** — server compares answer to `box_contents`; Bot B@rker opens the box; win/lose sting.
6. **SCORE + LOG** — outcome computed, full round appended to the log, round state discarded.

A *turn* = one guesser message + its box-holder reply. Early lock-in is allowed (forcing all 3 is artificial; "I've heard enough" is the better beat).

## 3. Components
- **Server** — FastAPI + uvicorn + httpx. Referee + Ollama proxy + static host + logger. Round state in-memory (`dict[round_id]`).
- **Frontend** — vanilla `index.html` / `style.css` / `app.js`. The retro stage; talks only to the server.
- **Model backend** — Ollama at `http://127.0.0.1:11434`.

## 4. API
- `POST /api/round` → `{round_id}`; streams the Box Holder opening.
- `POST /api/round/{id}/say` body `{text}` → streams the Box Holder reply; decrements the turn; ends with `{turns_remaining}`. `409` if no turns left or round not in EXCHANGE.
- `POST /api/round/{id}/guess` body `{answer}` → `{correct, box_contents, winner, verdict_line}`; logs the round.
- `GET /` + static assets.

Streaming target: pipe Ollama's token stream → response stream → browser (client uses `fetch` + `ReadableStream`). Acceptable to land non-streamed in the first commit, add streaming next.

## 5. Data
**Round state (in-memory):** `round_id, box_contents, model, turns_remaining, transcript[], status`.

**Log** — `logs/rounds.jsonl`, one object per line:
```json
{"round_id":"...","ts":"2026-06-30T..Z","mode":"human_guesser_vs_ai_box_holder",
 "box_holder_model":"qwen3:8b","box_contents":"BANANA","turn_limit":3,
 "transcript":[{"speaker":"box_holder","turn":0,"text":"..."},
               {"speaker":"guesser","turn":1,"text":"..."},
               {"speaker":"box_holder","turn":1,"text":"..."}],
 "guesser_turns_used":2,"final_answer":"NO_BANANA","correct":false,"winner":"box_holder"}
```

## 6. Model integration
- `POST {OLLAMA}/api/chat`, `stream:true`, `think:false`, `options:{temperature:0.9}` (the Box Holder wants room to bluff).
- Messages: `system` = filled Box Holder prompt; then alternating `assistant` (Box Holder's prior lines) / `user` (Guesser's lines). Opening elicited with a hidden `user` kickoff: *"The round has started; give your opening line."*
- **Thinking-strip (mandatory):** `think:false` AND defensively strip any `<think>…</think>` from returned content before it is used or shown. The Box Holder's reasoning must never reach the Guesser — the one true landmine.
- Set `OLLAMA_KEEP_ALIVE=-1` to avoid reload latency between turns.

## 7. Host — Bot B@rker (MVP)
Scripted line pools, mechanical: **intro** (on opening), **reveal** (banana vs empty variants), **verdict** (win vs lose), occasional sign-off gag — *"Help control the bot population — have your model fine-tuned and aligned."* Display name "Bot B@rker"; code/voice identifier "Bot Barker". LLM-driven host deferred.

## 8. Settings (defaults)
`turn_limit=3`, `box_holder_model="qwen3:8b"`, `temperature=0.9`, `prior=0.5`, `ollama_url="http://127.0.0.1:11434"`, `seat="human_guesser"`. Settings UI deferred; MVP hardcodes + a `config.json`.

## 9. Scoring
`correct = (answer==BANANA && box==BANANA) || (answer==NO_BANANA && box==EMPTY)`. Guesser wins iff correct; else Box Holder wins.

## 10. Non-functional
Local-only, single user, no auth. One active round at a time is fine. Windows host; Python 3.11+. Server on `127.0.0.1:8000`. No external network beyond Ollama.

## 11. Build order (prove the loop before the chrome)
1. `git init`; skeleton (`server/`, `web/`, `prompts/`✓, `logs/`).
2. Ollama client + thinking-strip; a throwaway script that makes the Box Holder say one line and proves the strip works.
3. State machine + the 3 endpoints, no UI — drive a full round (coin → convo → score → log) from the terminal.
4. Ugly vanilla frontend wired to the API — first playable round in the browser.
5. Apply the retro stage + Bot B@rker lines + reveal + sound.
6. (v2) AI-vs-AI: swap the human seat for the Guesser prompt + a batch runner + the deviation-from-50% leaderboard.

## 12. Deferred (not in v1)
AI-vs-AI + batch + leaderboard · the other three seats · settings UI · LLM-driven host · sound beyond basics · the win-condition variants (cooperative / hidden) · packaged downloadable.

## 13. Decision log
- Adversarial bluff (Box Holder wins on a wrong guess) — the equilibrium-deviation experiment is the point.
- Mechanical scoring, not LLM-judged — clean, frees the host to be pure showbiz.
- 3 guesser turns, configurable — user.
- Early lock-in allowed — "I've heard enough" is the better beat.
- Box Holder opens the round — gives the Guesser something to read.
- Human = Guesser by default — the detective seat is the fun one.
- Vanilla HTML/CSS/JS — the look is all CSS; a framework earns nothing yet.
- FastAPI + httpx + Ollama, `think:false` + `<think>` strip — the landmine.
- Streaming box-holder replies (target) — the "live banter" feel.
- Bot B@rker scripted in MVP — proportional; LLM host later.
- Logs = JSONL, one round per line — audit now, leaderboard/training later.
