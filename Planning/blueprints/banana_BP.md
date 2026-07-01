# Blueprint: Banana or No Banana — v1 MVP
Spec: Planning/specs/banana_spec.md
Date: 2026-06-30

---

## Builder instructions
- Execute steps in order. Do not skip, reorder, or read ahead into the next slice.
- Check off each step when complete: [ ] → [x]
- One step = one logical concern. If a step can't be tested on its own, it's too small — merge it. If it touches more than one concern, split it.
- Deviation: if you do something differently than the step says, note it inline and keep going.
- Stuck: stop immediately. Do not try alternative approaches. Report exactly where and why.
- Test command for every step: `python -m pytest -q` (run from repo root). Tests live under `tests/`.

---

## Slice 1: Project skeleton & config
**Scope:** The FastAPI app package exists, dependencies are declared, and configuration loads from `config.json` merged over defaults.

### Step 1: Declare dependencies
**Build:** Create `requirements.txt` at repo root listing: `fastapi`, `uvicorn[standard]`, `httpx`, `pytest`, `pytest-asyncio`. Create `server/__init__.py` (empty) and `tests/__init__.py` (empty).
**Test:** `python -c "import fastapi, uvicorn, httpx, pytest"` succeeds (deps installed by the operator via `pip install -r requirements.txt`).
**Done When:** The three files exist and the import check passes.
**Stuck If:** A dependency cannot be installed in the environment.
- [x] Complete
**Deviation:** Dropped `pytest-asyncio` from requirements.txt — the committed tests use the sync FastAPI TestClient and pure-function checks (chat_stream is monkeypatched), so no async test harness is needed. Same observable coverage.

### Step 2: Config loader
**Build:** Create `server/config.py` with a `DEFAULTS` dict (`turn_limit=3`, `box_holder_model="qwen3:8b"`, `temperature=0.9`, `prior=0.5`, `ollama_url="http://127.0.0.1:11434"`, `seat="human_guesser"`) and `load_config(path="config.json") -> dict` that returns DEFAULTS updated by the JSON file if it exists (missing file → defaults unchanged). Create a `config.json` at repo root containing the same defaults. Forward constraint: `ollama_client` (Slice 2) and `game` (Slice 3) read their model/url/turn_limit from this config — keep keys stable.
**Test:** Create `tests/test_config.py`: `load_config` on a missing path returns all defaults; on a temp JSON overriding `turn_limit` returns the override merged over defaults.
**Done When:** `python -m pytest -q tests/test_config.py` passes.
**Stuck If:** N/A.
- [x] Complete

---
End of Slice 1. Builder checkpoint: tests green → continue to Slice 2.

---

## Slice 2: Ollama client & thinking-strip [inspect]
**Scope:** The server can call Ollama's chat API with reasoning disabled and defensively strip any `<think>` reasoning from returned content — the landmine. (Cross-module seam: external service boundary; security-critical reasoning-leak prevention.)

### Step 3: Thinking-strip function
**Build:** In `server/ollama_client.py`, add `strip_think(text: str) -> str` that removes every `<think>…</think>` span, including multi-line spans (regex with DOTALL), and returns the remaining text with surrounding whitespace tidied; text with no think span is returned unchanged.
**Test:** Create `tests/test_strip.py` — covers spec item a4: a multi-line `<think>…</think>` is removed while surrounding visible text remains intact; a string with no think span is unchanged; multiple spans all removed.
**Done When:** `python -m pytest -q tests/test_strip.py` passes.
**Stuck If:** N/A.
- [x] Complete

### Step 4: Ollama chat call (request contract)
**Build:** In `server/ollama_client.py`, add `async def chat_stream(messages, model, url, temperature) -> AsyncIterator[str]` that POSTs to `{url}/api/chat` with body `{"model":model, "messages":messages, "stream":True, "think":False, "options":{"temperature":temperature}}` using `httpx.AsyncClient`, yielding `strip_think`-cleaned content chunks from the streamed NDJSON. Factor the request-body construction into a testable helper `build_chat_request(messages, model, temperature) -> dict`.
**Test:** Create `tests/test_ollama_request.py` — covers spec item a5: `build_chat_request(...)` sets `think` to `False` and `stream` to `True` and carries the given model/temperature. (Streaming I/O itself is exercised against a faked endpoint in Slice 4.)
**Done When:** `python -m pytest -q tests/test_ollama_request.py` passes.
**Stuck If:** N/A.
- [x] Complete

✅ Inspector: PASS — 2026-06-30 19:58 — slice 2 (Ollama client + thinking-strip). a4 (strip removes multi-line/multiple `<think>` spans, keeps visible text) and a5 (request sets think:false, stream:true) proven by committed tests; fidelity: ok (each test fails if its criterion is violated). Streaming per-chunk strip is belt-and-suspenders atop think:false — noted, not a defect.

---
⛔ End of Slice 2 [inspect]. Inspection due — run **inspector** on this slice before building on it, unless the caller's inspection level defers it to final sign-off.

---

## Slice 3: Round state & coin flip
**Scope:** The server can create a round (fair coin, hidden contents, in-memory state) and elicit a Box Holder opening without leaking the truth or spending a turn.

### Step 5: Round model & fair coin flip
**Build:** In `server/game.py`, define the in-memory round: a `Round` dataclass/dict with `round_id` (uuid4 hex), `box_contents` (`"BANANA"`/`"EMPTY"`), `model`, `turns_remaining`, `transcript` (list), `status` (`"EXCHANGE"` initially). Add `flip_coin(rng=random) -> str` returning `"BANANA"`/`"EMPTY"` at 50/50, and `create_round(config, rng=random) -> Round` setting `turns_remaining = config["turn_limit"]` and `status="EXCHANGE"`. Keep an in-memory `ROUNDS: dict[str, Round]`. Forward constraint: Slice 4 endpoints and Slice 5 scoring mutate this same store — expose `get_round(id)` returning None if absent.
**Test:** Create `tests/test_round.py` — covers a1 (fresh round: `turns_remaining==3` from default config, `box_contents` in {BANANA,EMPTY}) and a2 (over 1000 flips with a seeded rng each outcome is within ±5% of 50%).
**Done When:** `python -m pytest -q tests/test_round.py` passes.
**Stuck If:** N/A.
- [x] Complete

### Step 6: Box Holder prompt fill & opening elicitation
**Build:** In `server/game.py`, add `build_box_holder_system(box_contents) -> str` that reads `prompts/box_holder.md` and replaces `{BOX_CONTENTS}` with `"A BANANA"` when BANANA else `"EMPTY"`. Add `async def elicit_opening(round, config)` that builds the system message + a hidden `user` kickoff ("The round has started; give your opening line.") and drives `chat_stream`, appending the box_holder opening to `transcript` as `{speaker:"box_holder", turn:0, text:...}` — the opening does not decrement `turns_remaining`.
**Test:** Extend `tests/test_round.py` — covers a6: `build_box_holder_system("BANANA")` contains no literal `{BOX_CONTENTS}` and equals the prompt with the token replaced.
**Done When:** `python -m pytest -q tests/test_round.py` passes.
**Stuck If:** `prompts/box_holder.md` is missing or lacks the `{BOX_CONTENTS}` token.
- [x] Complete
**Deviation:** `parse_answer` and `score` (Slice 5 / Step 9) were written into `server/game.py` in this slice too, since they are pure helpers colocated with the round logic. Behavior unchanged; their committed tests are still added in Step 9 as planned.

---
End of Slice 3. Builder checkpoint: tests green → continue to Slice 4.

---

## Slice 4: Conversation API (create + say) [inspect]
**Scope:** The browser can start a round (streamed opening) and exchange messages with the Box Holder, with turns accounted and bad requests rejected. (Cross-module seam: HTTP API boundary browser↔server.)

### Step 7: FastAPI app, round-create endpoint, static mount
**Build:** In `server/app.py`, create the FastAPI `app`. Add `POST /api/round` that calls `create_round`, kicks off `elicit_opening`, and streams the opening tokens back (StreamingResponse), returning/including the `round_id`. Ensure the response and stream never include the `box_contents` field. Mount `web/` as static at `/` (created in Slice 6; for now serving may 404 until files exist — do not block on it). Forward constraint: keep a module-level app importable as `server.app:app` (the CLAUDE.md run command).
**Test:** Create `tests/test_api.py` using FastAPI `TestClient` and a **faked Ollama** (monkeypatch `chat_stream` to yield canned chunks) — covers a3: the `POST /api/round` response body/stream contains no `box_contents` field/value key.
**Done When:** `python -m pytest -q tests/test_api.py` passes.
**Stuck If:** N/A.
- [x] Complete
**Deviation:** `round_id` is returned via an `X-Round-Id` response header (and `turns_remaining` via `X-Turns-Remaining`) rather than a JSON field, so the body can be a pure token stream. Same observable contract; frontend reads the header.
**Build:** In `server/app.py`, add `POST /api/round/{id}/say` body `{text}`: if id unknown → 404; if `turns_remaining==0` or `status!="EXCHANGE"` → 409 with no state mutation and no Ollama call; else append guesser message `{speaker:"guesser",turn:n,text}`, decrement `turns_remaining` by 1, drive `chat_stream` for the reply, append `{speaker:"box_holder",turn:n,text}`, and end the stream with `{turns_remaining}`.
**Test:** Extend `tests/test_api.py` (faked Ollama) — covers a7 (successful say decrements by 1 and appends both messages), a8 (say at 0 turns and say when status≠EXCHANGE → 409, state unchanged, fake Ollama not called), a9 (unknown id → 404).
**Done When:** `python -m pytest -q tests/test_api.py` passes.
**Stuck If:** N/A.
- [x] Complete

✅ Inspector: PASS — 2026-06-30 20:04 — slice 4 (conversation API). a3 (no box_contents field in body/headers), a7 (say decrements by 1, appends guesser+box_holder at correct turn), a8 (409 at 0 turns and on wrong status, state unmutated, fake Ollama not called), a9 (404 unknown id) all proven by committed tests against a faked Ollama; fidelity: ok (a8 asserts both no-mutation and call-count, so a silent turn spend or stray call would fail). Full suite 14 passed.

---
⛔ End of Slice 4 [inspect]. Inspection due — run **inspector** on this slice before building on it, unless the caller's inspection level defers it to final sign-off.

---

## Slice 5: Lock-in, scoring, reveal & logging [inspect]
**Scope:** The Guesser can lock in an answer at any point; the server scores it mechanically, returns the reveal, and appends the completed round to `logs/rounds.jsonl`. (Schema: the log object contract; destructive: file append.)

### Step 9: FINAL ANSWER parser & scoring
**Build:** In `server/game.py`, add `parse_answer(text) -> "BANANA"|"NO_BANANA"|None` (case-insensitive; accepts bare `BANANA`/`NO BANANA`/`NO_BANANA` and the `FINAL ANSWER: …` form; returns None if unparseable) and `score(answer, box_contents) -> dict` returning `{correct, winner}` where `correct = (answer=="BANANA" and box=="BANANA") or (answer=="NO_BANANA" and box=="EMPTY")`, `winner = "guesser" if correct else "box_holder"`.
**Test:** Extend `tests/test_round.py` — covers a10 (all four answer×box combos score correctly with right winner) and a11 (parser maps both FINAL ANSWER forms; unparseable → None).
**Done When:** `python -m pytest -q tests/test_round.py` passes.
**Stuck If:** N/A.
- [x] Complete

### Step 10: Round logger
**Build:** Create `server/log.py` with `append_round(round, config, final_answer, correct, winner, path="logs/rounds.jsonl")` that creates `logs/` if absent and appends exactly one JSON line with fields: `round_id`, `ts` (ISO-8601 UTC, `Z`), `mode="human_guesser_vs_ai_box_holder"`, `box_holder_model`, `box_contents`, `turn_limit`, `transcript`, `guesser_turns_used` (= turn_limit − turns_remaining), `final_answer`, `correct`, `winner`.
**Test:** Create `tests/test_log.py` — covers a14 (one new line appended, parses as JSON), a15 (object has every required field), a16 (transcript order and turn numbers match the input round).
**Done When:** `python -m pytest -q tests/test_log.py` passes.
**Stuck If:** N/A.
- [x] Complete

### Step 11: Guess endpoint — reveal, log, discard
**Build:** In `server/app.py`, add `POST /api/round/{id}/guess` body `{answer}`: 404 if unknown; parse via `parse_answer` → 422 if None; else `score`, call `append_round`, set `status="DONE"` and remove the round from the live store, and return `{correct, box_contents, winner, verdict_line}`. A guess is allowed at any `turns_remaining` including 3 (early lock-in). Forward constraint: `verdict_line` text is a scripted host line — Slice 6 supplies the Bot B@rker pools; for now a plain line is fine.
**Test:** Extend `tests/test_api.py` — covers a12 (guess at turns_remaining==3 returns a valid reveal), a13 (after a guess, further say/guess on that id → 404/409), and 422 on unparseable answer.
**Done When:** `python -m pytest -q tests/test_api.py` passes.
**Stuck If:** N/A.
- [x] Complete
**Deviation:** Slice 6's `verdict_line` was stubbed as `_plain_verdict` in app.py (per the step's own note that a plain line is fine for now); Slice 6 replaces it with the Bot B@rker pools.

✅ Inspector: PASS — 2026-06-30 20:09 — slice 5 (lock-in, scoring, reveal, logging). a10 (all four answer×box combos + winner), a11 (parser forms + None), a12 (early lock-in at turns_remaining==3 returns a valid reveal), a13 (round retired after guess → 404 on further say/guess), plus 422 on unparseable, and a14/a15/a16 (one JSON line, all fields, transcript order/turns). Fidelity: ok — scoring is parametrized over all combos; log tests assert exact field set and transcript tuples; the guess tests use a no-disk logger so they prove control flow, while test_log.py proves the on-disk schema. Full suite 30 passed; no stray logs/ left in the tree.

---
⛔ End of Slice 5 [inspect]. Inspection due — run **inspector** on this slice before building on it, unless the caller's inspection level defers it to final sign-off.

---

## Slice 6: Match settings [inspect]
**Scope:** The player can list installed models and start a round under a chosen model, turn limit, and temperature; invalid settings are rejected. (Cross-module seam: new HTTP endpoints + Ollama `/api/tags` proxy.)

### Step S1: Per-round settings in the game core
**Build:** In `server/game.py`: add a `temperature` field to `Round` (set at creation). Add `effective_settings(config, overrides) -> dict` that copies config and applies `overrides` keys `model`→`box_holder_model`, `turn_limit`, `temperature`, raising `ValueError` if `turn_limit` is not an int ≥ 1 or `temperature` is not a number ≥ 0. Change `create_round(config, overrides=None, rng=random)` to compute `eff = effective_settings(config, overrides or {})` and set the round's `model`, `turn_limit`/`turns_remaining`, and `temperature` from `eff`. Change `generate_box_holder` to use `r.temperature` instead of `config["temperature"]`.
**Test:** Create `tests/test_settings.py` — covers: create_round with `{model,turn_limit,temperature}` sets all three on the round; omitted fields fall back to config defaults; `effective_settings` raises on `turn_limit=0` and on `temperature="hot"`/negative.
**Done When:** `python -m pytest -q tests/test_settings.py` passes.
**Stuck If:** N/A.
- [x] Complete

### Step S2: /api/models and settings-aware /api/round
**Build:** In `server/ollama_client.py`, add `async def list_models(url) -> list[str]` (GET `{url}/api/tags`, return each `models[].name`). In `server/app.py`: add `GET /api/models` returning `{"models": await list_models(CONFIG["ollama_url"]), "default": CONFIG["box_holder_model"]}`; extend `POST /api/round` to accept an optional JSON body `{model?, turn_limit?, temperature?}` (Pydantic model, all fields optional) and pass `overrides` (exclude-none) to `create_round`, returning `422` on `ValueError` from validation.
**Test:** Extend `tests/test_api.py` (fake `list_models` + fake Ollama) — covers: `GET /api/models` returns installed names + default; `POST /api/round` with overrides creates a round whose model/turns_remaining/temperature match; `POST /api/round` with `turn_limit=0` or `temperature=-1` → 422 and no round stored.
**Done When:** `python -m pytest -q tests/test_api.py` passes.
**Stuck If:** N/A.
- [x] Complete

### Step S3: Settings panel in the frontend
**Build:** In `web/index.html` add a settings panel (a "⚙ Settings" toggle) holding a model `<select>`, a turn-limit number input (default 3), and a temperature range slider (0–1.5, default 0.9) with a live value label. In `web/app.js`: on load, `GET /api/models` and populate the dropdown (mark the default); on Start Round, send `{model, turn_limit, temperature}` in the `POST /api/round` body. Style the panel in `web/style.css` to match the retro stage.
**Test:** No new automated test (panel layout/behavior is `[human-required]`, verified in the final step). Manual: open the page, change settings, start a round.
**Done When:** The panel lists installed models and the chosen model/turns/temperature drive the next round.
**Stuck If:** N/A.
- [x] Complete

✅ Inspector: PASS — 2026-06-30 20:31 — slice 6 (Match settings). GET /api/models (installed names + default), POST /api/round overrides (model/turns/temperature applied to the round), and 422 on turn_limit<1 / temperature<0 with no round created, all proven by committed tests (`test_settings.py`, `test_api.py`) against a faked Ollama + faked list_models; fidelity: ok (bad-settings test asserts both 422 and no-round-created). Settings panel (S3) is `[human-required]` — evidence captured at final sign-off. Full suite 43 passed; logs/ gitignored.

---
⛔ End of Slice 6 [inspect]. Inspection due — run **inspector** on this slice before building on it, unless the caller's inspection level defers it to final sign-off.

---

## Final Slice: Retro frontend & Bot B@rker
**Scope:** The playable 80s Price-is-Right stage served by the server, plus full spec verification.

### Step 12: Frontend page & static serving
**Build:** Create `web/index.html`, `web/style.css`, `web/app.js` — a retro stage (two podiums, the box, a dialogue area, a message input + send, lock-in BANANA / NO BANANA buttons). `app.js` calls `POST /api/round` (renders streamed opening), `POST /api/round/{id}/say` (renders streamed replies incrementally via `fetch`+`ReadableStream`, shows `turns_remaining`), and `POST /api/round/{id}/guess` (renders the reveal + winner). Ensure `server/app.py` serves `web/` at `GET /` and its assets.
**Test:** Extend `tests/test_api.py` — covers a17: `GET /` returns 200 and the referenced static assets (`style.css`, `app.js`) return 200.
**Done When:** `python -m pytest -q tests/test_api.py` passes.
**Stuck If:** N/A.
- [ ] Complete

### Step 13: Bot B@rker scripted host & retro styling
**Build:** Add Bot B@rker scripted line pools (intro on opening, reveal banana/empty variants, verdict win/lose, occasional sign-off gag "Help control the bot population — have your model fine-tuned and aligned.") wired into `app.js`/reveal; display name "Bot B@rker", code identifier "Bot Barker". Apply the 80s Price-is-Right styling in `style.css` (warm/analog palette — harvest gold, orange, brown, wood panel; bold showbiz sans; podiums; the box reveal). Host is flavor, not judge.
**Test:** No new automated test (host wording, tone, and visual style are `[human-required]`). Manual: launch the run command and view the stage.
**Done When:** The page renders the retro stage with Bot B@rker lines and a banana/empty box reveal; no console errors on a click-through.
**Stuck If:** N/A.
- [ ] Complete

### Final Step: Verify spec Done when items
**Build:** No new code. Confirm all spec `**Done when:**` items are met.
**Test:** Run the full suite `python -m pytest -q` — every `[automated]` item (a1–a17) has a committed test from an earlier step. Capture output. For the `[human-required]` items (h1–h5: live qwen3:8b playthrough, incremental streaming feel, Bot B@rker tone, retro look), start the server (`python -m uvicorn server.app:app --host 127.0.0.1 --port 8000`) and capture UI evidence via playwright (python) for the inspector/human to judge.
**Done When:** Every `[automated]` criterion passes via its committed test. Every `[human-required]` criterion has captured evidence.
**Stuck If:** An automated criterion fails and the cause is not clear from the output.
- [ ] Complete

---
⛔ Final slice complete. Run **inspector** for final sign-off.

- [ ] **Fully inspected** — every `[inspect]` slice and the final sign-off passed. Inspector ticks this; never check it by hand. Its absence means inspection is still owed somewhere.

---

## Slice 7: Configurable multi-provider player seats (LeftPlayer/RightPlayer) [inspect]
**Scope:** Either seat (Box Holder / Guesser) is independently human or AI, and any AI seat can run on Ollama, an OpenAI-compatible endpoint, or Anthropic, configured only via `.env`. Retrospective entry — user-directed, built directly (no separate foreman pass); see `docs/decisions/banana_2026-07-01.md`. (Cross-module seam: new provider dispatch layer + a second AI-driven game loop.)

### Step 14: `.env` scheme + `PlayerConfig` loader
**Build:** `.env.example` (committed) + `.env` (gitignored) documenting `LEFT_PLAYER_*`/`RIGHT_PLAYER_*` (`TYPE`, `PROVIDER`, `MODEL`, `BASE_URL`, `API_KEY`). `server/players.py`: `PlayerConfig` dataclass, `load_player`/`load_players` (env → config, ollama default base URL), `public_view` (strips `api_key`). `server/config.py` calls `load_dotenv()`. `requirements.txt` gains `python-dotenv`.
**Test:** `tests/test_players.py` — env parsing, defaults, ollama base-url fallback, `public_view` never leaks `api_key`.
**Done When:** `python -m pytest -q tests/test_players.py` passes.
- [x] Complete

### Step 15: Multi-provider `chat_stream` dispatch
**Build:** `server/llm_providers.py` — `build_openai_request`/`build_anthropic_request`/`split_system` (pure, testable) + `chat_stream(messages, cfg, temperature)` dispatching to Ollama (reuses `ollama_client`), OpenAI-compatible, and Anthropic via raw `httpx` SSE parsing; think-stripped uniformly.
**Test:** `tests/test_llm_providers.py` — request-shape tests for both new providers, `split_system`, and dispatch-by-provider-name (incl. unknown-provider `ValueError`) via `asyncio.run` (no `pytest-asyncio`, consistent with Slice 1's deviation).
**Done When:** `python -m pytest -q tests/test_llm_providers.py` passes.
- [x] Complete

### Step 16: Wire LeftPlayer through the dispatch layer
**Build:** `server/game.py`: `Round` gains `left`/`right: PlayerConfig`; `create_round` resolves seats via `load_players` (default) or an injected `players` dict, applying the existing per-round `model` override to `left` only; `generate_box_holder` calls `llm_providers.chat_stream(messages, cfg=r.left, ...)` instead of the hardcoded Ollama call. `server/app.py` loads `PLAYERS` at startup and passes it into `create_round`.
**Test:** Existing `tests/test_api.py`/`test_round.py`/`test_settings.py` suite (43 tests) re-run unchanged in behavior; `FakeOllama` fixture signature updated to `(messages, cfg, temperature)` to match the new call contract.
**Done When:** `python -m pytest -q` passes (all pre-existing tests green under the new call shape).
- [x] Complete

### Step 17: AI-Guesser autoplay for RightPlayer
**Build:** `server/game.py`: `build_guesser_system`/`_messages_for_guesser` (forces a lock-in instruction once `turns_remaining <= 0`) / `generate_guesser_text` (non-streamed). `server/app.py`: `GET /api/players` (kind/provider/model, never `api_key`); `POST /api/round/{id}/say` → `409` when right seat is AI; new `POST /api/round/{id}/advance` driving one AI-Guesser turn per call, ending the round on a parsed lock-in (with a deterministic `NO_BANANA` fallback if the forced turn still won't parse).
**Test:** `tests/test_api.py` — `/api/players` shape, `/say` 409-when-ai, `/advance` continue / lock-in / forced-fallback / 404 / 409-when-human, using a `FakeDualPlayers` fake that answers differently per seat.
**Done When:** `python -m pytest -q tests/test_api.py` passes.
- [x] Complete

### Step 18: Frontend — seat info + Auto-Play
**Build:** `web/index.html`/`app.js`: settings panel shows a read-only Left/Right seat summary from `GET /api/players`; model dropdown hidden for non-Ollama LeftPlayer; when RightPlayer is AI, manual say/lock-in controls are replaced by an Auto-Play button that loops `POST /advance` (rendering each exchanged line) until `done`, then reveals. `web/style.css`: settings button + panel repositioned to a fixed lower-right anchor (user request, unrelated styling fix folded into this slice).
**Test:** No new automated test (panel/auto-play UX is `[human-required]`, per spec). Manual: verify pinned settings button and (with `RIGHT_PLAYER_TYPE=ai`) an auto-played round reaching a reveal.
**Done When:** Settings button is fixed bottom-right; seat labels reflect `.env` config; Auto-Play only appears when the right seat is AI and drives a round to reveal.
- [ ] Complete — pending manual browser verification.

---
⛔ End of Slice 7 [inspect]. Inspection due — run **inspector** (or manual verification, per this session's Step 18 note) before treating Auto-Play as proven.
