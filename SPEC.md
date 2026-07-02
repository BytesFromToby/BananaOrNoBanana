# Banana or No Banana — v1 Spec (MVP)

**Scope:** one complete round of **Human Guesser vs AI Box Holder**, in the browser against a local model, end to end: coin flip → conversation (≤3 guesser turns) → lock-in → reveal → score → logged. Everything else (lab/leaderboard, LLM-driven host, the win-condition variants) is **deferred** — see §12 for the full roadmap.

**Shipped beyond v1 (2026-07-01):** configurable multi-provider player seats — either seat (LeftPlayer = Box Holder, RightPlayer = Guesser) independently human or AI, any AI seat driven by Ollama / OpenAI-compatible / Anthropic, configured via `.env` only (keys never reach the browser); AI-Guesser rounds driven by `POST /api/round/{id}/advance`. Behavior spec: `Planning/specs/banana_spec.md` ("Configurable multi-provider player seats"); rationale: `docs/decisions/banana_2026-07-01.md`.

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

**Seat-aware log fields (required since the multi-provider seats shipped):** the log is the future leaderboard's and training data's raw material, so every round must be attributable and filterable:
- `mode` derived from the actual seats (e.g. `ai_guesser_vs_ai_box_holder`), not hardcoded.
- Per-seat identity: provider + model for each AI seat (e.g. `guesser_provider`, `guesser_model` alongside `box_holder_model`), `"human"` where a human sat.
- `forced_default: true` whenever the round ended by the deterministic `NO_BANANA` fallback rather than a parsed answer — these rounds must be excludable from the deviation-from-50% metric or they bias it.
- `temperature` and `standard_settings` (true iff the round ran at the standard 3 turns / 0.7) — non-standard rounds are excluded from leaderboard aggregation.

## 6. Model integration
- `POST {OLLAMA}/api/chat`, `stream:true`, `think:false`, `options:{temperature:0.9}` (the Box Holder wants room to bluff).
- Messages: `system` = filled Box Holder prompt; then alternating `assistant` (Box Holder's prior lines) / `user` (Guesser's lines). Opening elicited with a hidden `user` kickoff: *"The round has started; give your opening line."*
- **Thinking-strip (mandatory):** `think:false` AND defensively strip any `<think>…</think>` from returned content before it is used or shown. The Box Holder's reasoning must never reach the Guesser — the one true landmine.
- Set `OLLAMA_KEEP_ALIVE=-1` to avoid reload latency between turns.

## 7. Host — Bot B@rker (MVP)
Scripted line pools, mechanical: **intro** (on opening), **reveal** (banana vs empty variants), **verdict** (win vs lose), occasional sign-off gag — *"Help control the bot population — have your model fine-tuned and aligned."* Display name "Bot B@rker"; code/voice identifier "Bot Barker". LLM-driven host deferred.

## 8. Settings (defaults)
`turn_limit=3`, `box_holder_model="qwen3:8b"`, `temperature=0.7`, `prior=0.5`, `ollama_url="http://127.0.0.1:11434"`, `seat="human_guesser"`. Settings UI deferred; MVP hardcodes + a `config.json`.

**Standard leaderboard conditions (decided 2026-07-01): 3 guesser turns, temperature 0.7.** The turn/temperature controls are locked behind a "Bypass leaderboard settings" toggle; bypassed rounds play and log but are flagged non-standard and never count toward any leaderboard (local or arena). Rationale: temperature and turn count change the contestants — mixed conditions would confound the deviation-from-50% metric, so the dial is pinned and recorded rather than removed (making "deception vs temperature" a studyable variable later).

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

## 12. Roadmap — everything wanted, in rough order

What's already in: v1 round loop ✅ · settings UI (model/turn-limit/temperature panel) ✅ · multi-provider human/AI seats + AI-Guesser autoplay ✅ · seat credential editors in the panel ✅ · strict `FINAL ANSWER` parse on the AI path (item 1) ✅ · seat-aware logging (item 2) ✅ · batch runner + local leaderboard, `python -m server.batch --rounds N` / `python -m server.stats` (item 3) ✅ · **community arena code (item 10): client submission (`--submit` / `python -m server.submit`) + Cloudflare Worker ingest & public leaderboard under `arena/` ✅ — automated tests pass; live Cloudflare deploy + real-submission + browser render remain as human-required follow-ups.**

Still wanted (roughly prioritized; each is its own feature spec when picked up):

1. **Strict AI lock-in parsing** — on the `/advance` path the round ends only on an explicit `FINAL ANSWER:` line (the loose "contains banana" parse is for the human `/guess` button only). Prerequisite for everything below — without it AI-vs-AI rounds end on turn 1.
2. **Seat-aware logging** (§5 additions above) — prerequisite for the leaderboard.
3. **AI-vs-AI batch runner + local leaderboard** — the actual experiment. Run N rounds per matchup unattended; leaderboard is win-rate-vs-coin-flip (deviation from 50%) per (box-holder-model × guesser-model), with forced-default rounds excluded. CLI or lab page; this is the project's reason to exist, and it must work fully offline/locally before any of the community layer (item 10) exists.
4. **Streamed autoplay** — `/advance` (or a successor) streams both seats' lines token-by-token so watching AI-vs-AI feels like live banter, not turn dumps.
5. **Spectator dramatic irony** — an audience-only view showing the Box Holder's stripped `<think>` reasoning ("it's a banana; I'll say empty") beside the public stage. Never reaches the Guesser — the viewer is in on the con. Reasoning is captured server-side at generation time and logged.
6. **Human Box Holder seats** — human-vs-AI (out-bluff the detector) and human-vs-human party mode; the seat plumbing already exists, this is the UI for a human left seat.
7. **LLM-driven Bot B@rker** — color commentary generated per round (reads the transcript at reveal), replacing/augmenting the scripted pools. Host stays showbiz, never judge.
8. **Sound + Price-is-Right beats** — buzzer/ding/sting/applause/box-open whoosh; "Come on down!" round start; the Big Wheel as the round-settings control; applause-meter/sad-trombone audience flavor.
9. **Win-condition variants** — cooperative (Box Holder wins when Guesser is *right* — Password/Pyramid mode) and hidden-mode (Guesser must work out friend-or-liar). One incentive line changes; parked until the adversarial data is boring.
10. **Community arena: packaged downloadable + central results depository + global leaderboard** *(added 2026-07-01 — the end-state vision; full feature spec: `Planning/specs/arena_spec.md`)*. People download and run the app locally with their **own** API keys (keys never leave their machine; their provider bills stay theirs — this is why it is a local app, not a hosted BYO-key site), pit any models against each other (e.g. Fable 5 vs Opus), and opt-in submit results to a central online depository that keeps all the stats and renders a public leaderboard.
    - **Distribution:** `uvx`/pipx install first (the audience already has API keys and a terminal); a bundled executable only if demand shows up. Same codebase as today.
    - **Submission:** an opt-in "submit results" action POSTs completed rounds to a small ingest endpoint. The wire format **is** the seat-aware `rounds.jsonl` schema (§5) plus `schema_version`, `client_version`, and canonical model IDs — get the local log right and the submission format is free.
    - **Central side (small on purpose):** one validating ingest endpoint + a database + a public read-only leaderboard page (e.g. Cloudflare Worker + D1, or one tiny VPS). No user accounts in v1; anonymous submissions with client-generated run IDs.
    - **Trust model (decided):** self-reported results from untrusted clients cannot be made cheat-proof, so don't pretend. Mitigations: every submission must include **full transcripts** (fake tallies are cheap; N in-character transcripts are expensive and auditable), rate limiting, and a separate **"verified"** tier for runs executed by the maintainer/trusted parties. Honor system for the rest — banana-sized stakes.
    - **Side benefit:** the transcript depository doubles as the deception-dialogue corpus for later fine-tuning work.
11. **Settings persistence** — chosen settings survive a server restart (today: per-round only, `config.json` is the baseline).

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
