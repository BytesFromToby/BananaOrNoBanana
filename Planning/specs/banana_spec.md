# Spec: Banana or No Banana — v1 MVP

A local, single-player retro game-show deception web app. A coin flip puts a banana in a box (or leaves it empty); an AI **Box Holder** (`qwen3:8b` via Ollama) is the only one who "looked" and lies across ≤3 turns to make the human **Guesser** call it wrong. A **FastAPI** referee flips the coin, proxies Ollama with reasoning stripped, streams replies, parses and scores the Guesser's `FINAL ANSWER` mechanically against the box, and appends each round to `logs/rounds.jsonl`. A vanilla HTML/CSS/JS retro (80s *Price is Right*) stage with a scripted host, **Bot B@rker**, is the playable seat. This spec adopts `SPEC.md` (repo root) as the authoritative scope source of truth; `PROPOSAL.md` is context; player prompts in `prompts/` are locked v1.

## Scope
- Does: deliver one complete round of **Human Guesser vs AI Box Holder** in the browser against a local model, end to end — coin flip → Box Holder opening → exchange (≤3 guesser turns) → lock-in → reveal → mechanical score → round appended to `logs/rounds.jsonl`.
- Does: run a thin local FastAPI server that is referee + Ollama proxy + static host + logger, with round state held in memory; one active round at a time.
- Does: guarantee the Box Holder's hidden reasoning never reaches the Guesser (`think:false` **and** defensive `<think>…</think>` stripping).
- Does: let the player configure, per round, the Box Holder **model** (chosen from the locally installed Ollama models), the **turn limit**, and the **temperature**, via a settings panel.
- Does NOT: include batch runs or the deviation-from-50% leaderboard (v2, still fully deferred).
- Does NOT: include an LLM-driven host, the win-condition variants (cooperative / hidden), a packaged downloadable, auth, or any multi-user/networked operation.
- Does NOT: persist settings across server restarts (per-round only; the `config.json` defaults remain the baseline).
- Does NOT (permanent non-goal, 2026-07-02): a **two-human party mode**. Every game has at least one AI player — human-vs-AI (either role) or AI-vs-AI only.
- **Superseded (see "Configurable multi-provider player seats" below, added 2026-07-01):** the original v1 lines ruling out AI-vs-AI, the other three seats, and configuring the Guesser seat. Either seat can now be human or AI, and either AI seat can use any of three providers — this was the first step into that v2 territory, taken ahead of the batch/leaderboard work which is still deferred.

## Feature: Round setup & coin flip
Server creates a round on request: flips a fair coin, records the hidden box contents, and initializes in-memory round state. Truth lives only in the server and the Box Holder's prompt — never in anything sent to the Guesser.

- Input: `POST /api/round` (no body).
- Output: a `round_id`; round state `{round_id, box_contents ∈ {BANANA, EMPTY}, model, turns_remaining=3, transcript[], status}` held in memory; the round then produces the Box Holder opening (see next feature).

**Done when:**
- A fresh round sets `turns_remaining` to 3 and `box_contents` to exactly one of `BANANA` or `EMPTY`.  `[automated]`
- Over ≥1000 generated rounds the coin is fair — each outcome lands within a ±5% band of 50% (seedable/mreproducible in the test).  `[automated]`
- No response payload or streamed content from `POST /api/round` (or any Guesser-facing endpoint) ever contains the literal box contents field.  `[automated]`

## Feature: Box Holder via Ollama (proxy + thinking-strip)
The server fills `{BOX_CONTENTS}` into the locked `prompts/box_holder.md` system prompt and drives the Box Holder through Ollama's chat API, streaming tokens back. Reasoning is disabled and defensively stripped — the one true landmine.

- Input: round state (system prompt = filled Box Holder prompt; message history as alternating `assistant`/`user`); opening elicited with a hidden `user` kickoff ("The round has started; give your opening line.").
- Output: the Box Holder's visible reply text, streamed; appended to `transcript`. The opening does **not** cost a guesser turn.
- Integration: `POST {OLLAMA_URL}/api/chat`, `stream:true`, `think:false`, `options:{temperature:0.9}`; `OLLAMA_URL` default `http://127.0.0.1:11434`, model default `qwen3:8b`.

**Done when:**
- The strip function removes any `<think>…</think>` span (including multi-line) from model content and leaves non-think text intact; verified on canned strings with and without think spans.  `[automated]`
- The outbound Ollama request body sets `think` to `false` and `stream` to `true` (verified against a mocked/faked Ollama endpoint capturing the request).  `[automated]`
- The Box Holder system message equals `prompts/box_holder.md` with `{BOX_CONTENTS}` replaced by the round's contents phrasing, and contains no unreplaced `{BOX_CONTENTS}` token.  `[automated]`
- Against a live `qwen3:8b`, a real opening line streams to the stage and reads as in-character game-show banter with no leaked reasoning or narration.  `[human-required]`

## Feature: Conversation exchange & turn accounting
While turns remain and the round is in EXCHANGE, a Guesser message spends one turn and elicits a streamed Box Holder reply. Out-of-state or out-of-turns requests are rejected.

- Input: `POST /api/round/{id}/say` body `{text}`.
- Output: the Box Holder reply, streamed; the turn is decremented; the stream ends with `{turns_remaining}`. Both the Guesser line and the reply are appended to `transcript`.
- Errors: `409` if the round has no turns left or is not in EXCHANGE; a not-found `id` returns `404`.

**Done when:**
- A successful `say` decrements `turns_remaining` by exactly 1 and appends both the guesser message and the box-holder reply to the transcript.  `[automated]`
- A `say` when `turns_remaining == 0`, or when the round is not in EXCHANGE, returns `409` and does not mutate state or call Ollama.  `[automated]`
- A `say` against an unknown `round_id` returns `404`.  `[automated]`
- The Box Holder reply is delivered as a token stream the browser renders incrementally ("live banter"), not a single dumped block.  `[human-required]`

## Feature: Lock-in, scoring & reveal
The Guesser locks in an answer at any point (allowed before spending any turn; forced at 0 turns). The server parses it, scores mechanically against the box, and returns the reveal — no LLM judge.

- Input: `POST /api/round/{id}/guess` body `{answer}` where answer resolves to `BANANA` or `NO_BANANA` (accepts the `FINAL ANSWER: BANANA | NO BANANA` lock-in form).
- Output: `{correct, box_contents, winner, verdict_line}`; the round transitions to REVEAL/scored and its in-memory state is discarded after logging.
- Scoring: `correct = (answer==BANANA && box==BANANA) || (answer==NO_BANANA && box==EMPTY)`; Guesser wins iff correct, else Box Holder wins.

**Done when:**
- Scoring is exactly correct for all four (answer × box) combinations: BANANA/BANANA→correct, NO_BANANA/EMPTY→correct, BANANA/EMPTY→wrong, NO_BANANA/BANANA→wrong; `winner` follows.  `[automated]`
- The `FINAL ANSWER` parser maps `FINAL ANSWER: BANANA` → `BANANA` and `FINAL ANSWER: NO BANANA` → `NO_BANANA` (case-insensitive, tolerant of surrounding text); unparseable input is rejected with `422`, not silently scored.  `[automated]`
- A guess is accepted with `turns_remaining == 3` (early lock-in before any turn) and returns a valid reveal.  `[automated]`
- After a guess the round is logged and its in-memory state is no longer usable for further `say`/`guess` (returns `409`/`404`).  `[automated]`

## Feature: Round logging (JSONL)
Every completed round is appended as exactly one JSON object per line to `logs/rounds.jsonl` — audit now, leaderboard/training data later.

- Input: completed round state at reveal.
- Output: one appended line in `logs/rounds.jsonl` (file/dir created if absent).

**Done when:**
- After a full round, exactly one new line is appended to `logs/rounds.jsonl` and it parses as JSON.  `[automated]`
- The logged object contains: `round_id`, `ts` (ISO-8601 UTC), `mode`, `box_holder_model`, `box_contents`, `turn_limit`, `transcript` (ordered speaker/turn/text entries), `guesser_turns_used`, `final_answer`, `correct`, `winner`.  `[automated]`
- The `transcript` in the log preserves speaker order and turn numbers matching the round that was played.  `[automated]`
- *(Amended 2026-07-01, with the multi-provider seats.)* `mode` is derived from the actual seats (`human_guesser_vs_ai_box_holder` when the right seat is human, `ai_guesser_vs_ai_box_holder` when it is AI), not hardcoded.  `[automated]`
- *(Amended 2026-07-01.)* The logged object identifies each AI seat's provider and model (e.g. `guesser_provider`/`guesser_model` alongside `box_holder_model`; `"human"` for a human seat), so leaderboard rows are attributable per matchup.  `[automated]`
- *(Amended 2026-07-01.)* A round that ended via the deterministic `NO_BANANA` fallback (model wouldn't comply with the forced lock-in) is logged with `forced_default: true`; normally-answered rounds carry `forced_default: false` or omit it. These rounds must be distinguishable so the deviation-from-50% metric can exclude them.  `[automated]`

## Feature: Retro frontend & Bot B@rker (playable stage)
A self-contained vanilla HTML/CSS/JS page served by the server is the playable seat: it starts a round, streams the exchange, sends guesses, shows the reveal, and dresses the whole thing as an 80s *Price is Right* stage with the scripted host **Bot B@rker** (display name "Bot B@rker"; code identifier "Bot Barker"). Host is flavor, not judge.

- Input: user interactions (start, type a message, lock in an answer); the API above.
- Output: the rendered retro stage — two podiums, the box, streamed dialogue, scripted host lines (intro / reveal / verdict / occasional sign-off gag), and the reveal (banana vs empty) declaring the winner.
- Served at `GET /` plus static assets; the page talks only to the server.

**Done when:**
- `GET /` returns the page and its static assets load (200) from the running server.  `[automated]`
- A human can play a full round in the browser against a live `qwen3:8b` — start → converse across turns → lock in → see the reveal and the correct winner — with no console errors.  `[human-required]`
- Bot B@rker delivers scripted intro, reveal, and verdict lines that fit the earnest 80s daytime-TV tone; the box reveal (banana/empty) is visually clear.  `[human-required]`
- The stage reads as 80s *Price is Right* (warm/analog palette, podiums, box reveal), legible at a typical desktop width.  `[human-required]`

## Feature: Match settings
A settings panel lets the player choose, before starting a round, which installed Ollama model plays the Box Holder, the guesser turn limit, and the temperature. The chosen values govern that round; omitted values fall back to the `config.json` defaults.

*Amended 2026-07-01 — standard leaderboard conditions.* Turn limit and temperature are pinned to the published standard (**3 turns, temperature 0.7** — `STANDARD_SETTINGS` in `server/config.py`; the `config.json` defaults equal it) and locked in the UI behind a **"Bypass leaderboard settings"** checkbox. Bypassed rounds play and log normally but are flagged non-standard and never count toward any leaderboard — mixed conditions (a hot Box Holder vs a cold one) would confound the deviation-from-50% metric. Unchecking the bypass snaps the controls back to standard.

- Input: `GET /api/models` (no body); `POST /api/round` optional body `{model?, turn_limit?, temperature?}`.
- Output: `GET /api/models` → `{models: [name, …], default: <configured model>}` (installed models from Ollama); a round created with overrides runs under them.

**Done when:**
- `GET /api/models` returns the list of installed Ollama model names plus the configured default model (verified against a faked Ollama `/api/tags`).  `[automated]`
- `POST /api/round` with `{model, turn_limit, temperature}` creates a round whose `model`, `turns_remaining` (= `turn_limit`), and `temperature` equal the supplied values.  `[automated]`
- `POST /api/round` with an omitted field falls back to the `config.json` default for that field.  `[automated]`
- `POST /api/round` with an invalid setting (`turn_limit` < 1, or a non-numeric/negative `temperature`) returns `422` and creates no round.  `[automated]`
- The settings panel lists the installed models in a dropdown alongside turn-limit and temperature controls, and the chosen values visibly drive the next round.  `[human-required]`
- *(Amended 2026-07-01.)* With the bypass unchecked, the turn/temperature controls are disabled and pinned at 3 / 0.7 and rounds are created at exactly those values; checking the bypass enables them and its note states the rounds won't count.  `[human-required]`
- *(Amended 2026-07-01.)* Rounds log `temperature` and a `standard_settings` flag that is true iff turn_limit == 3 and temperature == 0.7; `server/stats.py` excludes non-standard rounds from the metric and reports their count.  `[automated]`

## Feature: Red/Blue players & role rotation
*Added 2026-07-02. Supersedes the fixed Left=Box-Holder / Right=Guesser mapping below, and builds the previously-deferred human Box Holder (old roadmap item 6).* The two players are persistent color identities — **RedPlayer** (was LeftPlayer) and **BluePlayer** (was RightPlayer) — and the **role** (Box Holder vs Guesser) is assigned per game rather than welded to the color. Red renders red in the UI, Blue renders blue. Provider/model/human-or-AI config for each color is unchanged from the seat feature below (env + settings-panel editors), only renamed `RED_PLAYER_*` / `BLUE_PLAYER_*`.

Role-assignment policy:
- **AI vs AI:** the Box Holder/Guesser roles **alternate every completed game**. This cancels role-assignment bias so a Red-vs-Blue matchup measures both directions (Red-holds-Blue-guesses *and* Blue-holds-Red-guesses). Rotation state is in-memory (resets on restart), advanced once per completed+logged round.
- **One human present:** the human **chooses** their role (Guesser or Box Holder) — no auto-rotation; the choice governs until changed. The AI takes the other role.
- Human vs human (party) is a **non-goal — will not be built.** The game is a human against a machine (either role) or machine vs machine; a two-human party mode is explicitly out of scope, permanently.

Human Box Holder mode (new interaction, when the human chooses to hold):
- The server flips the coin and reveals the contents **to the human holder only** (they are the Box Holder — allowed to know). The Guesser-facing no-leak invariant still holds: no *Guesser*-facing response carries `box_contents`.
- The human types the opening + replies (bluffing) via `POST /api/round/{id}/hold` `{text}`; each call feeds the human's line to the AI Guesser and returns the Guesser's response — either a continuation or a `FINAL ANSWER` lock-in ending the round. Mirrors `/advance` with the roles reversed. `prompts/box_holder.md` is not used (the human bluffs themselves); the AI Guesser uses `prompts/guesser.md`.
- Scoring is unchanged: the Guesser wins iff correct, so the human-as-holder wins when the AI Guesser calls it wrong.

- Input: `RED_PLAYER_*` / `BLUE_PLAYER_*` env vars and `PUT /api/players/{red|blue}` (same shape as before). Human role choice via config/settings (`HUMAN_ROLE`=guesser|holder, default guesser) applied when a human is present. `POST /api/round/{id}/hold {text}` for the human-holder path.
- Output: `GET /api/players` → `{"red": {...}, "blue": {...}}` (never `api_key`), plus the round's assigned `holder`/`guesser` colors. Round state carries `holder_color` and `guesser_color`; the log records both colors alongside the existing per-role provider/model (so leaderboard aggregation, which already groups by box_holder×guesser role+model, captures rotation with no change).
- The per-round `model` override (Match settings) is **deprecated** — with rotation, "the box holder's model" is ambiguous; each color's model comes from its own config. `turn_limit`/`temperature` (standard-settings) are unchanged.

**Done when:**
- With both players AI, consecutive rounds alternate which color is Box Holder vs Guesser; the log's `box_holder_*`/`guesser_*` fields swap accordingly.  `[automated]`
- A round records `holder_color` and `guesser_color`, and `GET /api/players` returns both colors' `kind`/`provider`/`model` and never `api_key`.  `[automated]`
- When the human chooses Guesser, play is the existing human-Guesser flow (`/say` + `/guess`); when the human chooses Box Holder, `/say` is rejected and `POST /api/round/{id}/hold` drives an AI-Guesser round to a reveal.  `[automated]`
- A human-holder round reveals `box_contents` to the holder path but never in any Guesser-facing response or streamed Guesser content.  `[automated]`
- Scoring holds for the human-holder case: the AI Guesser locking in wrong makes the human (holder) the winner.  `[automated]`
- Env `RED_PLAYER_*` / `BLUE_PLAYER_*` load the two colors; a migration keeps an existing `.env` working (or is migrated in place).  `[automated]`
- The stage renders Red as red and Blue as blue, shows who is holding vs guessing each game, and — when the human is the Box Holder — presents the secret + a bluff-input control instead of the question/lock-in controls.  `[human-required]`
- Over an AI-vs-AI batch of an even number of rounds between two distinct models, each model holds and guesses an equal number of times.  `[automated]`

## Assumptions (Red/Blue rotation)
- Hard rename `LEFT_PLAYER_*`→`RED_PLAYER_*`, `RIGHT_PLAYER_*`→`BLUE_PLAYER_*`; the local `.env` is migrated in place (single local user; no long back-compat window). — assumed.
- Rotation starts with Red as Box Holder in game 1, then alternates. — arbitrary, low-surprise.
- Rotation state is in-memory and per-process (resets on restart); acceptable since rounds are already ephemeral and one-at-a-time. — from §10.
- Human role choice is a single setting (`HUMAN_ROLE`, default `guesser`). At most one player is human; two-human games are a permanent non-goal (see Scope). — decided.
- The per-round `model` override is retired rather than reinterpreted. — reduces ambiguity under rotation.

## Feature: Configurable multi-provider player seats (Left/Right)
*Added 2026-07-01. **Player naming and the fixed role mapping are superseded by "Red/Blue players & role rotation" above (2026-07-02); the provider/human-or-AI/credential-editor mechanics below still hold, renamed Red/Blue.***  Either seat — **LeftPlayer** (the Box Holder) or **RightPlayer** (the Guesser) — is independently configured as **human** or **AI**, and any AI seat can be driven by **Ollama**, an **OpenAI-compatible** endpoint (OpenAI itself, OpenRouter, vLLM, LM Studio, ...), or **Anthropic**. Configuration lives in environment variables (`.env`, gitignored; `.env.example` committed as the template) and — *amended later on 2026-07-01, superseding "never editable from the browser"* — is also editable from the settings panel: two seat editors (credential slots) covering all three provider types. API keys are **write-only** across the browser boundary: accepted from the settings panel (localhost, single user), persisted server-side to `.env`, and never sent back to the browser in any response.

- Input: `LEFT_PLAYER_*` / `RIGHT_PLAYER_*` env vars (`TYPE`=human|ai, `PROVIDER`=ollama|openai_compat|anthropic, `MODEL`, `BASE_URL`, `API_KEY`); and `PUT /api/players/{left|right}` body `{kind?, provider?, model?, base_url?, api_key?}` (an omitted `api_key` keeps the saved key; `""` clears it).
- Output: `GET /api/players` → `{"left": {kind, provider, model}, "right": {kind, provider, model}}` — never `api_key`. When RightPlayer is AI, `POST /api/round/{id}/advance` drives one AI-Guesser turn per call (non-streamed): generates the Guesser's line via its configured provider, and either ends the round (line parses as `FINAL ANSWER: ...`) or continues (line + a Box Holder reply, transcript updated, turn spent). Turns are force-answered once exhausted, with a deterministic default (`NO_BANANA`) if the model still won't comply, so a round always terminates.
- `POST /api/round/{id}/say` is rejected (`409`) when the right seat is AI-controlled — that seat's lines come from `/advance`, not typed input.
- LeftPlayer's `model` remains overridable per round via `POST /api/round` as before (Match settings feature); `provider`/`base_url`/`api_key`/seat `kind` are fixed at the server-config (`.env`) level, not per-round or browser-editable.

**Done when:**
- `GET /api/players` returns `kind`/`provider`/`model`/`base_url`/`has_key` for both seats and never includes `api_key`, for any configured provider.  `[automated]`
- *(Amended 2026-07-01, seat editors.)* `PUT /api/players/{seat}` validates and applies a seat update (422 on invalid kind/provider/missing AI model/missing openai_compat base_url; 404 on an unknown seat), persists it to `.env` in place (other lines preserved), and never echoes the key; an omitted `api_key` keeps the saved key.  `[automated]`
- *(Amended 2026-07-01.)* A round created with no per-round model override uses the left seat's configured model; the `config.json` `box_holder_model` default applies only when the seat has no model of its own; an explicit override still wins.  `[automated]`
- *(Amended 2026-07-01; superseded 2026-07-02.)* ~~`POST /api/round` with a human left seat returns 422 (human Box Holder not yet playable).~~ Superseded by the Red/Blue feature, which builds the human Box Holder — a human may now hold the box (via `HUMAN_ROLE=holder` + `/hold`).  `[automated]`
- *(Amended 2026-07-01.)* The settings panel shows two seat editors (Box Holder / Guesser), each with Player (human/AI), provider (Ollama local / Anthropic / OpenAI-compatible), model, base URL, and a password-type API-key field whose placeholder indicates when a key is already saved; saving updates the seat summary and the next round.  `[human-required]`
- `POST /api/round/{id}/say` returns `409` when the round's right seat is AI-controlled.  `[automated]`
- `POST /api/round/{id}/advance` on a non-AI right seat, or an unknown round, returns `409`/`404` respectively.  `[automated]`
- A successful `/advance` call that does not parse as a lock-in spends one turn, appends both the guesser and box-holder lines to the transcript in order, and returns `turns_remaining`.  `[automated]`
- A successful `/advance` call whose Guesser line parses as `FINAL ANSWER: ...` ends the round (scored, logged, retired from `ROUNDS`) and returns the same reveal shape as `/guess`.  `[automated]`
- *(Clarified 2026-07-01.)* On the `/advance` path, only an explicit `FINAL ANSWER:` line counts as a lock-in — a Guesser line that merely *mentions* banana/no banana (nearly every line in this game) continues the exchange. The loose parse (bare `BANANA`/`NO BANANA`, tolerant of surrounding text) applies only to the human `/guess` endpoint.  `[automated]`
- Once turns are exhausted, `/advance` forces a lock-in instruction into the Guesser's prompt; if the model still doesn't produce a parseable answer, the round is defaulted to `NO_BANANA` and ends rather than looping.  `[automated]`
- *(Amended 2026-07-01, autoguess fix.)* While turns remain, the AI Guesser's message assembly injects a host turn-status note ("you have N of M questioning turns left...") so the model knows the turn mechanic exists; without it, small local models lock in on turn 1 without asking anything. The note (like the forced-lock-in instruction) is model-visible only — it never appears in the transcript or the log.  `[automated]`
- Against a live cloud provider (OpenAI-compatible or Anthropic) with a real API key, a LeftPlayer or RightPlayer seat produces in-character streamed/generated lines with no leaked reasoning.  `[human-required]`
- The settings panel shows both seats' provider/model (editable since the 2026-07-01 seat-editor amendment) and, when the right seat is AI, replaces the manual say/lock-in controls with an Auto-Play control that plays the round to a visible reveal.  `[human-required]`

## Feature: Batch runner & local leaderboard
*Added 2026-07-01 (roadmap item 3 — the experiment).* A CLI runs N AI-vs-AI rounds unattended under the configured seats and prints the local leaderboard: guesser win-rate versus the 50% coin-flip baseline, per matchup, from `logs/rounds.jsonl`. Fully local — no community/central layer.

- Input: `python -m server.batch --rounds N [--turn-limit T]` (seats from `.env`; requires an AI right seat). `python -m server.stats` prints the leaderboard alone.
- Output: N completed, logged rounds (one JSONL line each, seat-aware fields); a table grouped by (box-holder provider/model × guesser provider/model) with rounds counted, guesser wins, win rate, deviation from 50%, and forced-default rounds counted separately and excluded from the metric.
- The per-turn engine is shared: the `/advance` endpoint and the batch runner drive the same `game.advance_round` (no behavior fork between watching in the browser and batching).

**Done when:**
- The batch runner completes N rounds against a scripted fake provider and appends exactly N seat-aware log lines; every round terminates (lock-in, or forced default).  `[automated]`
- The leaderboard aggregation groups rounds by matchup, computes guesser win-rate and deviation from 50%, and excludes `forced_default` rounds from the metric while reporting their count.  `[automated]`
- `/advance` behavior is unchanged after the refactor (existing endpoint tests pass against the shared engine).  `[automated]`
- The batch CLI refuses to run with a human right seat, with a clear message.  `[automated]`
- A live batch (e.g. 5 rounds, local qwen3-vs-qwen3) runs to completion and the printed leaderboard row matches the log.  `[human-required]`

## Assumptions
- Test framework is **pytest**; API/logic tests exercise the server with a **mocked/faked Ollama endpoint** so the `[automated]` items need no live model. Live `qwen3:8b` is required only for the `[human-required]` playthrough items. — assumed; confirm if a different harness is wanted.
- Backend layout `server/` (Python package, e.g. `server/app.py`) and frontend `web/` (`index.html`, `style.css`, `app.js`), served static by FastAPI. — conventional; cheap to rename.
- Settings come from a `config.json` plus hardcoded defaults per SPEC §8 (`turn_limit=3`, `box_holder_model="qwen3:8b"`, `temperature=0.9`, `prior=0.5`, `ollama_url="http://127.0.0.1:11434"`, `seat="human_guesser"`); no settings UI in v1. — assumed from SPEC.
- One active round at a time, held in a `dict[round_id]` in memory; server on `127.0.0.1:8000`; Python 3.11+ on Windows. — from SPEC §10.
- Streaming lands over `fetch` + `ReadableStream`; it is acceptable for the *first* commit of an endpoint to return non-streamed and add streaming next, provided the shipped feature streams. — from SPEC §4.
- Bot B@rker scripted line *pools* are authored by the builder from the SPEC/PROPOSAL tone; their wording/feel is judged under the `[human-required]` items. — assumed.
- `OLLAMA_KEEP_ALIVE=-1` is set to avoid inter-turn reload latency. — recommended by SPEC §6; environmental, non-blocking.

## Open Questions
<!-- None. SPEC.md settles scope, roles, win conditions, scoring, turn limit (3, early lock-in allowed),
     default seat (human Guesser), stack (FastAPI + httpx + Ollama, vanilla JS), and the thinking-strip
     approach. No fork remained that would change the build. -->
