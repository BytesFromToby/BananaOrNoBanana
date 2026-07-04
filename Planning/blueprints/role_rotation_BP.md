# Blueprint: Red/Blue players & role rotation
Spec: Planning/specs/banana_spec.md
Date: 2026-07-02

Target feature block: `## Feature: Red/Blue players & role rotation` (added 2026-07-02) plus
`## Assumptions (Red/Blue rotation)`. Every other feature in that spec is already built and tested —
this blueprint builds only this one feature on top of the existing code.

Real test command (from CLAUDE.md): `python -m pytest -q` (PowerShell). Arena cross-module contract
check (only where noted): `cd arena; npm test`.

Done-when coverage (8 items — 7 `[automated]`, 1 `[human-required]`):
- DW1 alternate holder/guesser + log swap `[automated]` → Slice 2
- DW2 round records colors + `/api/players` both colors, no `api_key` `[automated]` → Slice 2
- DW3 human role choice (guesser → say/guess; holder → say rejected + `/hold`) `[automated]` → Slice 3
- DW4 human-holder reveals box to holder path, never Guesser-facing `[automated]` → Slice 3
- DW5 scoring holds for human holder `[automated]` → Slice 3
- DW6 `RED_PLAYER_*`/`BLUE_PLAYER_*` load + `.env` migration `[automated]` → Slice 1
- DW7 stage renders Red/Blue, shows roles, human-holder controls `[human-required]` → Slice 4 (evidence in Final)
- DW8 even AI batch → equal holds/guesses per model `[automated]` → Slice 2

---

## Builder instructions
- Execute steps in order. Do not skip, reorder, or read ahead into the next slice.
- Check off each step when complete: [ ] → [x]
- One step = one logical concern. If a step can't be tested on its own, it's too small — merge it. If it touches more than one concern, split it.
- Deviation: if you do something differently than the step says, note it inline and keep going.
- Stuck: stop immediately. Do not try alternative approaches. Report exactly where and why.

---

## Slice 1: Rename Left/Right → Red/Blue, `.env` migration, `HUMAN_ROLE`, log colors [inspect]
✅ Inspector: PASS — 2026-07-02 09:17
<!-- [inspect]: schema (log gains holder_color/guesser_color) + destructive operation (in-place .env
     migration) + cross-module seam (players/config/game/app/log all renamed at once). -->
**Scope:** The two seats are persistent colors Red/Blue everywhere (env, config, game, API, log, batch); the role stays the fixed Red=Box-Holder / Blue=Guesser mapping for now, an existing `.env` with legacy `LEFT_/RIGHT_` keys still loads and can be migrated in place, and every completed round logs `holder_color`/`guesser_color`.

### Step 1: Rename seat config to Red/Blue with legacy fallback + in-place `.env` migration
**Build:** In `server/players.py`:
- Update `load_player(prefix, env, default_kind)` docstring to say `prefix` is `"RED_PLAYER"`/`"BLUE_PLAYER"`. Logic unchanged (still reads `{prefix}_*`).
- Rewrite `load_players(env)` to return `{"red": ..., "blue": ...}`. For each color, read the new prefix (`RED_PLAYER`/`BLUE_PLAYER`); if **none** of that color's `{prefix}_*` keys are present in `env` but the legacy prefix (`LEFT_PLAYER` for red, `RIGHT_PLAYER` for blue) has keys, load from the legacy prefix instead (keeps an existing `.env` working). Default kinds: `red` → `"ai"`, `blue` → `"human"` (preserves today's single-human-vs-AI default). Add a small helper `_has_prefix(env, prefix)` returning `True` if any `f"{prefix}_"` key exists.
- Add `migrate_env_file(path=".env")`: read the file; for every `LEFT_PLAYER_*` line rename its key to `RED_PLAYER_*` and every `RIGHT_PLAYER_*` to `BLUE_PLAYER_*`, preserving values, comments, unrelated lines, and order byte-for-byte (mirror the in-place rewrite style of `persist_seat_env`). No-op if the file is absent or already migrated.
- Keep `persist_seat_env(prefix, cfg, path)` as-is (prefix passed by caller; callers pass `RED_PLAYER`/`BLUE_PLAYER` in Step 5).
- `PlayerConfig.seat` now carries the color string (`"red"`/`"blue"`); no field rename needed.
Forward constraint: Slice 2 calls `load_players` expecting `red`/`blue` keys and Slice 3 allows a human holder — do not hardcode color→role here.
**Test:** `python -m pytest -q tests/test_players.py`
**Done When:** `load_players` returns `red`/`blue`; a legacy-only env still loads both colors; `migrate_env_file` rewrites keys in place preserving everything else.
**Stuck If:** The in-place rewrite reorders or drops non-seat lines and you cannot preserve them.
- [x] Complete
  **Deviation:** `tests/test_players.py` still asserts the old `left`/`right` keys at this step (1 failure, `test_load_players_returns_left_and_right`); the blueprint migrates the test files in Step 6, so new-behavior Done When was verified via a scratch check outside the tree. Same for Steps 2–5 — their named test files go fully green at Step 6.

### Step 2: Add `HUMAN_ROLE` to config and update `.env.example`
**Build:** In `server/config.py`, in `load_config`, read `HUMAN_ROLE` from the environment (via `os.environ`), lowercase/strip it, default `"guesser"`, validate it is `"guesser"` or `"holder"` (fall back to `"guesser"` on anything else), and set `config["human_role"]`. Add `"human_role": "guesser"` to `DEFAULTS`. In `.env.example`, rename the two seat blocks to `RED_PLAYER_*` (Red — a player identity, role assigned per game) and `BLUE_PLAYER_*`, drop the "the Box Holder"/"the Guesser" wording from the comments (role is no longer welded to color), and add a commented `HUMAN_ROLE=guesser` line explaining `guesser|holder` (applied when one seat is human).
**Test:** `python -m pytest -q tests/test_config.py` if present, else `python -m pytest -q`
**Done When:** `load_config()["human_role"]` is `"guesser"` by default and honors a valid `HUMAN_ROLE` env value; `.env.example` uses Red/Blue and documents `HUMAN_ROLE`.
**Stuck If:** `load_config` has no access to the process env for `HUMAN_ROLE` without breaking existing config-file merge behavior.
- [x] Complete

### Step 3: Round holds role-assigned configs by color; `create_round` uses fixed Red=holder mapping
**Build:** In `server/game.py`:
- In the `Round` dataclass, replace fields `left`/`right` with `holder: Optional[PlayerConfig] = None`, `guesser: Optional[PlayerConfig] = None`, and add `holder_color: str = "red"`, `guesser_color: str = "blue"`. Keep `model`, `turn_limit`, `temperature`, `transcript`, `status`.
- Replace every internal use of `r.left` with `r.holder` and `r.right` with `r.guesser` (in `generate_box_holder`, `generate_guesser_text`, `advance_round`, and any `_messages_*`).
- Rewrite `create_round(config, overrides=None, rng=random, players=None)`: resolve `players = players or load_players(os.environ)`; **fixed mapping this slice** — `holder_color="red"`, `guesser_color="blue"`, `holder=players["red"]`, `guesser=players["blue"]`. Keep the existing guard that a human Box Holder is not yet supported (`if holder.kind != "ai": raise ValueError("a human Box Holder isn't supported yet — set the Red seat to AI")`) — Slice 3 removes it. **Retire the per-round `model` override**: `effective_settings` keeps only `turn_limit`/`temperature` (remove the `model` branch); set `r.model = holder.model or eff["box_holder_model"]`. Set `Round(... holder=holder, guesser=guesser, holder_color="red", guesser_color="blue")`.
Forward constraint: Slice 2 replaces the fixed mapping with `assign_roles(...)`; keep holder/guesser resolution driven only by `holder_color`/`guesser_color` so that swap is a one-line change.
**Test:** `python -m pytest -q tests/test_round.py`
**Done When:** `create_round` builds a `Round` with `holder`/`guesser` configs and `holder_color="red"`/`guesser_color="blue"`; the per-round `model` override is ignored.
**Stuck If:** Something outside `game.py` still references `Round.left`/`Round.right` after this step and you cannot locate it.
- [x] Complete

### Step 4: Log records `holder_color`/`guesser_color`; identities derived from holder/guesser
**Build:** In `server/log.py`, `append_round`: derive `box_holder_provider, box_holder_model = _seat_identity(r.holder)` and `guesser_provider, guesser_model = _seat_identity(r.guesser)` (stop reading `r.left`/`r.right`/`r.model`). Add `"holder_color": r.holder_color` and `"guesser_color": r.guesser_color` to the record. Extend `mode` derivation to three cases: `"human_box_holder_vs_ai_guesser"` when the holder is human, else `"human_guesser_vs_ai_box_holder"` when the guesser is human, else `"ai_guesser_vs_ai_box_holder"`. **Do not remove or rename** any existing field (`box_holder_provider`, `box_holder_model`, `guesser_provider`, `guesser_model`, `winner`, `standard_settings`, `forced_default`, `temperature`, `transcript`, etc.) — `arena/src/lib/aggregate.js` and `server/stats.py` group on them and the shared fixture depends on them.
**Test:** `python -m pytest -q tests/test_log.py`
**Done When:** A logged record carries `holder_color` and `guesser_color`, correct per-role provider/model, and the right `mode` for each seat combination; no existing field removed.
**Stuck If:** `_seat_identity` cannot represent a human holder without changing its signature in a way that breaks the guesser call.
- [x] Complete

### Step 5: API + batch use Red/Blue; guards use role, not color
**Build:** In `server/app.py`:
- `PLAYERS = load_players(os.environ)` now yields `red`/`blue`.
- `GET /api/players` → `{"red": public_view(PLAYERS["red"]), "blue": public_view(PLAYERS["blue"])}`.
- `PUT /api/players/{seat}`: accept `seat in ("red","blue")` (404 otherwise); persist with prefix `"RED_PLAYER"` for red, `"BLUE_PLAYER"` for blue.
- `/say` guard: reject `409` when `r.guesser.kind != "human"` (say is the human-Guesser path).
- `/advance` guard: reject `409` when `r.guesser.kind != "ai"`.
- Replace remaining `r.left`/`r.right` references with `r.holder`/`r.guesser`.
In `server/batch.py`, read `players["red"]`/`players["blue"]`; the batch requires the **guesser seat** to be AI — after Slice 2 the guesser color varies, so gate on "at least one AI guesser is possible": for this slice keep gating on `players["blue"].kind == "ai"` and `players["red"].kind == "ai"` (both AI) with a clear message; Slice 2 refines the message wording only.
**Test:** `python -m pytest -q tests/test_api.py`
**Done When:** `/api/players` returns `red`/`blue` (never `api_key`); `PUT /api/players/{red|blue}` works and persists to the right prefix; `/say`/`/advance` guards keyed on role; batch reads Red/Blue.
**Stuck If:** A test still constructs `PLAYERS` or `Round` with `left`/`right` keys after Step 6 and fails at runtime you cannot trace.
- [x] Complete

### Step 6: Update existing tests to Red/Blue and write the DW6 migration test
**Build:**
- `tests/test_players.py`: rename `LEFT_PLAYER`/`RIGHT_PLAYER` expectations to `RED_PLAYER`/`BLUE_PLAYER`, `load_players` keys `left`/`right`→`red`/`blue`, `PlayerConfig(seat="left"...)`→`seat="red"` etc. Add **`test_red_blue_load_and_legacy_migration`** (DW6): (a) an env with `RED_PLAYER_*`/`BLUE_PLAYER_*` loads both colors; (b) an env with only legacy `LEFT_PLAYER_*`/`RIGHT_PLAYER_*` still loads both colors via fallback; (c) `migrate_env_file` on a tmp `.env` containing legacy keys + a comment + an unrelated var rewrites keys to `RED_/BLUE_` while preserving the comment, unrelated var, and order.
- `tests/test_round.py`: update `_guesser_round` and any `Round(...)`/`PlayerConfig(...)` to `holder`/`guesser`/`holder_color`/`guesser_color` and `seat="red"/"blue"`; keep `_messages_for_guesser` assertions.
- `tests/test_api.py`: change every `PLAYERS`/`_ai_guesser_players`/`fresh_players`/`default_players` fixture and inline `PlayerConfig` to `red`/`blue` keys and `seat="red"/"blue"`. Update `test_round_applies_settings_overrides` to drop the `model` assertion (keep `turn_limit`/`temperature`; per-round model override is retired). Update `test_round_uses_left_seat_model_when_no_override` → the holder's model comes from the Red color config (rename to `test_round_uses_holder_color_model`); drop the "explicit override still wins" half (override retired). Rename `test_say_rejected_when_right_seat_is_ai` → `..._when_guesser_is_ai`. Leave `test_round_rejects_human_box_holder` intact for now (fixed mapping still rejects a human Red holder) — Slice 3 replaces it.
- `tests/test_log.py`: update `_round` fixture to `holder`/`guesser`/`holder_color`/`guesser_color`, `seat="red"/"blue"`; add `holder_color`/`guesser_color` to `REQUIRED_FIELDS`; keep the existing mode/human-guesser/forced-default/transcript assertions passing.
**Test:** `python -m pytest -q`
**Done When:** The full suite is green with Red/Blue identifiers; `test_red_blue_load_and_legacy_migration` passes.
**Stuck If:** A pre-existing test encodes a behavior that genuinely conflicts with the renamed model (not just a name) — stop and report which.
- [x] Complete
  **Deviation:** The Step-6 file list named test_players/test_round/test_api/test_log, but the "full suite green with Red/Blue" Done When also required migrating three unlisted files: `tests/test_batch.py` (left/right→red/blue fixture, `ScriptedPlayers` seat key `right`→`blue`, renamed `test_batch_main_refuses_human_right_seat`→`..._human_seat` with the new both-AI message), `tests/test_settings.py` (dropped the retired per-round `model` override assertion in `test_create_round_applies_overrides`), and `tests/test_arena.py` (left/right→red/blue in the `load_players` monkeypatch). Pure name/retirement migrations, no behavior change.

---
⛔ End of Slice 1 [inspect]. Inspection due — run **inspector** on this slice before building on it, unless the caller's inspection level defers it to final sign-off.

---

## Slice 2: Role assignment & rotation (AI-vs-AI alternation, human chooses when present) [inspect]
✅ Inspector: PASS — 2026-07-02 13:56
<!-- [inspect]: cross-module seam — the game engine now assigns roles per game and carries
     in-memory rotation state consumed by create_round, /advance, /guess, and the batch runner. -->
**Scope:** With both seats AI the Box-Holder/Guesser roles alternate every completed round; with one human present the human's chosen role (`HUMAN_ROLE`, default guesser) governs; the round's assigned colors are exposed to the client; two-human games are refused.

### Step 1: `assign_roles` + in-memory rotation state
**Build:** In `server/game.py`, add module state `ROTATION = {"index": 0}` and:
- `assign_roles(players, human_role, rotation_index) -> dict` returning `{"holder_color", "guesser_color"}`:
  - Humans present = colors whose `kind == "human"`. If **both** are human → `raise ValueError("two-human party mode is a permanent non-goal")`.
  - If **one** human (color `hc`, AI color `ac`): `human_role == "holder"` → holder=`hc`, guesser=`ac`; else holder=`ac`, guesser=`hc`.
  - If **no** human (AI vs AI): even `rotation_index` → holder=`"red"`, guesser=`"blue"`; odd → holder=`"blue"`, guesser=`"red"` (game 1 = Red holds, per the Assumptions).
- `advance_rotation()` → `ROTATION["index"] += 1`.
- `reset_rotation()` → `ROTATION["index"] = 0` (test/util helper).
**Test:** `python -m pytest -q tests/test_rotation.py`
**Done When:** `assign_roles` alternates Red/Blue holder by index parity for AI-vs-AI, honors `human_role` when one seat is human, and raises for two humans.
**Stuck If:** The rotation policy in the spec seems to require persistence across restarts (it does not — in-memory per the Assumptions).
- [x] Complete
  **Deviation:** Created `tests/test_rotation.py` at Step 1 (rather than only at Step 4) with the `assign_roles`/`reset_rotation` unit tests, so the Step 1 Test command is meaningful and the rotation policy has a committed test; Steps 4–5 extend the same file with the DW1/DW8 tests as directed.

### Step 2: `create_round` assigns roles via `assign_roles`; completions advance rotation
**Build:** In `server/game.py` `create_round`: replace the fixed Red=holder mapping with `roles = assign_roles(players, config.get("human_role", "guesser"), ROTATION["index"])`; set `holder_color`/`guesser_color` and `holder`/`guesser` from `roles`; wrap `assign_roles`' `ValueError` so it surfaces to the API as a 422 (let it propagate — `app.create_round` already maps `ValueError`→422). Keep the "human Box Holder not yet supported" guard for now (removed in Slice 3), so a human that would be assigned holder still raises this slice. In `advance_round`, on the completion branch (after `append_round`, before/after `ROUNDS.pop`), call `advance_rotation()`. In `server/app.py` `/guess`, call `game.advance_rotation()` after `append_round` and retirement.
**Test:** `python -m pytest -q tests/test_rotation.py tests/test_api.py`
**Done When:** A round's `holder_color`/`guesser_color` follow `assign_roles`; each completed round advances `ROTATION["index"]`.
**Stuck If:** Advancing rotation in two completion sites double-counts a single round — ensure exactly one advance per completed round.
- [x] Complete
  **Deviation:** `advance_rotation()` now fires in exactly two completion sites — `game.advance_round` (AI-Guesser + batch path) and `app.py /guess` (human-Guesser path) — never both for one round (a round takes one path), so no double-count. Also added `game.reset_rotation()` to the autouse `reset_rounds` fixture in `tests/test_api.py` and adjusted `test_round_rejects_human_box_holder` to a one-human + `HUMAN_ROLE=holder` setup (a two-human config now raises the separate two-human error before the human-holder guard); Slice 3 Step 5 replaces that test.

### Step 3: Expose the round's assigned colors to the client
**Build:** In `server/app.py` `POST /api/round`, add response headers `X-Holder-Color: r.holder_color` and `X-Guesser-Color: r.guesser_color` alongside `X-Round-Id` on the streaming (AI-holder) response. (The human-holder JSON branch is added in Slice 3.)
**Test:** `python -m pytest -q tests/test_api.py`
**Done When:** `POST /api/round` returns the assigned holder/guesser colors in headers.
**Stuck If:** Header names collide with existing ones.
- [x] Complete

### Step 4: DW1 — consecutive AI-vs-AI rounds swap holder/guesser and the log fields swap
**Build:** Create/extend `tests/test_rotation.py` with **`test_consecutive_ai_rounds_swap_holder_guesser`** (DW1): pin both seats AI (Red and Blue distinct provider/model), `game.reset_rotation()`, log to a tmp path (monkeypatch `game.append_round`'s path or point `append_round` at a tmp file), run two rounds to completion through `game.advance_round` with a scripted fake `chat_stream` (guesser locks in via `FINAL ANSWER:`), read both logged lines and assert `holder_color`/`guesser_color` swap between round 1 and round 2 and that `box_holder_provider/model` and `guesser_provider/model` swap accordingly.
**Test:** `python -m pytest -q tests/test_rotation.py::test_consecutive_ai_rounds_swap_holder_guesser`
**Done When:** The test passes and encodes DW1.
**Stuck If:** The fake provider cannot distinguish holder vs guesser calls — script it on `cfg.seat`/role as `FakeDualPlayers` does in `tests/test_api.py`.
- [x] Complete
  **Deviation:** The fake (`RoleScriptedProvider`) keys on **role** not seat color (the Box Holder's stream carries the hidden `_KICKOFF`; its absence marks the Guesser call), because with rotation the guesser color alternates between rounds — `FakeDualPlayers`' `cfg.seat == "blue"` assumption no longer identifies the guesser.

### Step 5: DW8 — even AI batch gives each model equal holds and guesses
**Build:** In `tests/test_rotation.py` add **`test_even_ai_batch_equal_holds_and_guesses`** (DW8): two distinct AI models on Red/Blue, `game.reset_rotation()`, run an even N (e.g. 4) rounds via `server.batch.run_batch` (or a loop over `create_round`+`advance_round`) with a scripted fake provider and a tmp log path; read the N log lines and assert each model appears as `box_holder_model` exactly N/2 times and as `guesser_model` exactly N/2 times.
**Test:** `python -m pytest -q tests/test_rotation.py::test_even_ai_batch_equal_holds_and_guesses`
**Done When:** The test passes; both models hold and guess an equal number of times over an even batch.
**Stuck If:** `run_batch` needs a live provider — inject the fake via monkeypatching `game.chat_stream`.
- [x] Complete

### Step 6: DW2 — round records colors; `/api/players` returns both colors without `api_key`
**Build:** In `tests/test_api.py` add **`test_round_records_colors_and_players_endpoint_red_blue`** (DW2): with both seats AI, `POST /api/round` returns `X-Holder-Color`/`X-Guesser-Color` and the in-memory `Round` carries matching `holder_color`/`guesser_color`; `GET /api/players` returns exactly `{"red","blue"}`, each with `{kind, provider, model, base_url, has_key}`, `"api_key"` absent and no saved key value present in the response text.
**Test:** `python -m pytest -q tests/test_api.py::test_round_records_colors_and_players_endpoint_red_blue`
**Done When:** The test passes and encodes DW2.
**Stuck If:** The round is retired before you can read its colors — read the headers, or inspect `game.ROUNDS` before completion.
- [x] Complete

---
⛔ End of Slice 2 [inspect]. Inspection due — run **inspector** on this slice before building on it, unless the caller's inspection level defers it to final sign-off.

---

## Slice 3: Human Box Holder — `/hold` endpoint, `/say` guard, holder-only reveal [inspect]
<!-- [inspect]: cross-module seam (new /hold engine path) + security invariant (box_contents revealed
     to the holder path but never to any Guesser-facing response) + schema (create_round human-holder
     response shape). -->
**Scope:** When the human is the Box Holder, `POST /api/round` reveals the box to the holder only, `/say` is rejected, and `POST /api/round/{id}/hold {text}` feeds the human's bluff to the AI Guesser and drives the round to a scored reveal; scoring makes the human win when the AI Guesser calls it wrong.

### Step 1: Allow the human holder at round creation; branch the create response
**Build:** In `server/game.py` `create_round`, **remove** the "human Box Holder isn't supported yet" guard (a human holder is now valid). Ensure `r.model` is `""` when the holder is human. In `server/app.py` `POST /api/round`, after `game.create_round`, branch: if `r.holder.kind == "human"`, return `JSONResponse({"round_id": r.round_id, "holder_color": r.holder_color, "guesser_color": r.guesser_color, "box_contents": r.box_contents})` — the requester **is** the holder, so revealing the box here is allowed; do **not** call `elicit_opening` (no AI opening). Otherwise keep the existing streaming (AI-holder) response with the color headers from Slice 2.
**Test:** `python -m pytest -q tests/test_api.py`
**Done When:** With a human holder, `POST /api/round` returns JSON carrying `box_contents` and the colors and no AI opening; the AI-holder path is unchanged.
**Stuck If:** The human-holder assignment isn't reachable — confirm `HUMAN_ROLE=holder` with one human seat routes through `assign_roles` to a human holder.
- [x] Complete
  **Deviation:** The obsolete `test_round_rejects_human_box_holder` fails at this step (human holder now returns 200, not 422) — Step 5 removes it, as the blueprint sequences. AI-holder path confirmed unchanged.

### Step 2: `hold_round` engine — human holder line in, AI Guesser response out
**Build:** In `server/game.py` add `async def hold_round(r, config, text) -> dict`, mirroring `advance_round` with roles reversed. Behavior:
- Append the human holder's `text` to `r.transcript` as `{"speaker": "box_holder", "turn": r.turn_limit - r.turns_remaining, "text": text}` (first call = turn 0 opening).
- `forced = r.turns_remaining <= 0`; `guesser_text = await generate_guesser_text(r)` (uses `r.guesser` + `_messages_for_guesser`, which already injects the turn-status note / forced lock-in and never stores it).
- `answer = parse_final_answer(guesser_text)`; `defaulted = answer is None and forced`; if `defaulted`, `answer = NO_BANANA`.
- If `answer is not None`: `result = score(answer, r.box_contents)`; `append_round(r, config, final_answer=answer, correct=result["correct"], winner=result["winner"], forced_default=defaulted)`; `advance_rotation()`; `r.status = "DONE"`; pop from `ROUNDS`; return `{"done": True, "guesser_text": guesser_text, "correct": result["correct"], "box_contents": r.box_contents, "winner": result["winner"], "verdict_line": verdict_line(result["winner"], r.box_contents)}` (same reveal shape as `/advance`).
- Else (continue): append `{"speaker": "guesser", "turn": r.turn_limit - r.turns_remaining + 1, "text": guesser_text}`; `r.turns_remaining -= 1`; return `{"done": False, "guesser_text": guesser_text, "turns_remaining": r.turns_remaining}` — **no `box_contents`** in this continuation payload.
`prompts/box_holder.md` is not used on this path (the human bluffs); the AI Guesser uses `prompts/guesser.md` via `generate_guesser_text`.
**Test:** `python -m pytest -q tests/test_round.py`
**Done When:** `hold_round` continues on a non-lock-in Guesser line (no `box_contents` leaked) and ends on a lock-in/forced-default with the reveal shape; scoring is unchanged (Guesser wins iff correct, so the human holder wins when the Guesser is wrong).
**Stuck If:** Turn accounting double-decrements or the guesser line is never appended on the continue path.
- [x] Complete

### Step 3: `POST /api/round/{id}/hold` endpoint + `/say` rejects a human holder's round
**Build:** In `server/app.py`:
- Reuse `SayBody` (has `text`) for the body. Add `@app.post("/api/round/{round_id}/hold")` `async def hold(round_id, body: SayBody)`: `r = game.get_round(round_id)`; `404` if `None`; `409` if `r.holder.kind != "human"` ("this round has no human Box Holder"); `409` if `r.status != "EXCHANGE"`; else `return await game.hold_round(r, CONFIG, body.text)`.
- In `/say`, in addition to the guesser-AI guard, reject `409` when `r.guesser.kind != "human"` (covers the human-holder round, whose guesser is AI). The existing `/say` guard from Slice 1 Step 5 (`r.guesser.kind != "human"`) already covers this — confirm it does; no double-guard needed.
**Test:** `python -m pytest -q tests/test_api.py`
**Done When:** `/hold` drives a human-holder round; `/say` returns `409` on a human-holder round; unknown round → `404`; non-human-holder round on `/hold` → `409`.
**Stuck If:** `/hold` and `/advance` both try to drive the same round shape — `/hold` requires a human holder + AI guesser, `/advance` requires an AI guesser regardless of holder; keep the guards distinct.
- [x] Complete
  **Deviation:** Confirmed the existing `/say` guard (`r.guesser.kind != "human"`) already 409s a human-holder round; no change needed there (as the blueprint anticipated). Added two extra endpoint-guard tests (`test_hold_unknown_round_returns_404`, `test_hold_rejected_when_no_human_holder`) to cover the /hold 404/409 branches named in this step's Done When.

### Step 4: DW3/DW4/DW5 tests — human role choice, holder-only reveal, holder scoring
**Build:** In `tests/test_api.py`, with a fixture giving one human seat and `HUMAN_ROLE=holder` (monkeypatch `CONFIG["human_role"]` and `PLAYERS` so the human color is holder and the other is AI):
- **`test_human_role_choice_guesser_and_holder_paths`** (DW3): with `HUMAN_ROLE=guesser` the round runs the existing human-Guesser flow (`/say` 200, `/guess` reveal); with `HUMAN_ROLE=holder` `/say` returns `409` and a sequence of `/hold` calls (scripted fake AI Guesser that finally emits `FINAL ANSWER:`) drives the round to a `done:true` reveal and retires it from `ROUNDS`.
- **`test_hold_reveals_to_holder_not_guesser`** (DW4): the `POST /api/round` human-holder JSON contains `box_contents`; every non-final `/hold` continuation payload and the AI Guesser's `guesser_text` contain no `box_contents` field and do not echo the server's authoritative contents string as a leaked field (assert `"box_contents"` key absent from the continuation JSON).
- **`test_human_holder_wins_when_ai_guesser_wrong`** (DW5): force the box (`game.ROUNDS[id].box_contents`) and script the AI Guesser to lock in the wrong answer; assert the final `/hold` reveal has `winner == "box_holder"` (the human holder wins).
Use a scripted fake `chat_stream` (as `FakeDualPlayers`) so the AI Guesser's lines are deterministic.
**Test:** `python -m pytest -q tests/test_api.py`
**Done When:** DW3, DW4, DW5 tests pass.
**Stuck If:** You cannot set the box contents deterministically — set `game.ROUNDS[round_id].box_contents` directly after creation, or seed the rng.
- [x] Complete
  **Deviation:** Used a dedicated `ScriptedGuesser` fake rather than `FakeDualPlayers` — on the human-holder path every AI call IS the Guesser (no AI Box Holder call), so a simple in-order line script is clearer and sufficient.

### Step 5: Replace the obsolete human-Box-Holder-rejection test
**Build:** In `tests/test_api.py`, replace `test_round_rejects_human_box_holder` (the human holder is now built) with `test_round_allows_human_box_holder`: one human seat + `HUMAN_ROLE=holder` → `POST /api/round` returns `200` with holder-only `box_contents` and the human as holder. Keep a `test_round_rejects_two_human_seats`: both seats human → `POST /api/round` returns `422` (two-human party mode is a permanent non-goal).
**Test:** `python -m pytest -q tests/test_api.py`
**Done When:** Human holder is accepted; two-human is rejected `422`; the old rejection test is gone.
**Stuck If:** The two-human `422` does not surface — confirm `assign_roles`' `ValueError` propagates through `app.create_round`'s `except ValueError → 422`.
- [x] Complete

---
⛔ End of Slice 3 [inspect]. Inspection due — run **inspector** on this slice before building on it, unless the caller's inspection level defers it to final sign-off.

---

## Slice 4: Retro stage — Red/Blue rendering, role display, human-holder controls
**Scope:** The stage renders Red as red and Blue as blue, shows which color holds vs guesses each game, and when the human is the Box Holder presents the secret plus a bluff-input control instead of the question/lock-in controls.

### Step 1: Red/Blue podiums and color styling
**Build:** In `web/index.html`, replace the fixed "Box Holder (Left)"/"Guesser (Right)" seat-editor legends and podium labels with color identities — podiums keyed to Red and Blue with elements whose classes/ids allow red vs blue coloring (e.g. `podium-red`/`podium-blue`, a role caption element per podium, e.g. `#red-role`/`#blue-role`). Rename the seat editors to `#seat-red`/`#seat-blue` with legends "Red player" / "Blue player". In `web/style.css`, add `.player-red`/`.player-blue` (or podium color) rules rendering red and blue respectively. In `web/app.js`, change `PLAYERS` shape and every `left`/`right` reference to `red`/`blue`; update `loadPlayers`, `saveSeat`, `fillSeatEditor`, `seatEditor`, the seat-editor event wiring loop (`for (const seat of ["red","blue"])`), and `PUT /api/players/${seat}` to use `red`/`blue`. Update the per-round Box-Holder-model dropdown: since the per-round model override is retired, remove `#model-select-row` handling (or hide it permanently) and drop `s.model` from `currentSettings`.
**Test:** `python -m pytest -q tests/test_api.py::test_static_index_and_assets_served` (assets still serve 200); UI appearance verified in the Final slice via the UI evidence tool.
**Done When:** `GET /`, `/style.css`, `/app.js` return 200; the page references Red/Blue seats and `/api/players` `red`/`blue`.
**Stuck If:** An `id`/class referenced by `app.js` no longer exists in `index.html` after the rename.
- [x] Complete

### Step 2: Show assigned roles per game and drive the human-holder flow
**Build:** In `web/app.js` `startRound`: read the assigned colors. When the response is the human-holder JSON (`resp` is `application/json` carrying `box_contents`), show the secret to the human (e.g. a "You peeked: BANANA / empty" panel) and reveal a **bluff-input control** (`#hold-input` + `#hold-btn`) instead of `#play-controls`/`#autoplay-controls`; each send posts `POST /api/round/${roundId}/hold {text}`, appends the returned `guesser_text` as the Guesser's line, updates turns, and on `done` calls `revealBox(data)`. When the response is the streaming AI-holder path, read `X-Holder-Color`/`X-Guesser-Color` from headers and render which color holds vs guesses; keep the existing human-Guesser (`/say`+`/guess`) and AI-Guesser (auto-play `/advance`) branches, now selected by whether the human is guesser/holder. Add the `#hold-controls` block to `web/index.html` (a secret panel + input + send button, hidden by default) and its `.hidden` styling. Ensure the human-holder view never renders `box_contents` outside the holder's own secret panel.
**Test:** `python -m pytest -q tests/test_api.py::test_static_index_and_assets_served`; full UI behavior captured in the Final slice (human-required, DW7).
**Done When:** The stage shows holder/guesser roles per game; a human holder sees the secret + bluff control and can play to a reveal; a human guesser still uses say/lock-in; an AI guesser still uses auto-play.
**Stuck If:** The JSON-vs-stream branch of `POST /api/round` cannot be distinguished client-side — branch on the `Content-Type` header.
- [x] Complete
  **Deviation:** Step 1 and Step 2 were built together in one pass (both rewrite `web/app.js`, so splitting the file would have been artificial). Role captions render via `#red-role`/`#blue-role` set by `showRoles()`; the human-vs-AI figure (🧑/🤖) is chosen per seat kind in `loadPlayers`. Transcript lines are labeled "You" when the human plays that role, else by role name (`speakerLabel`), which also correctly names lines in AI-vs-AI and human-holder rounds where the old fixed "You = right seat" no longer holds.

---
End of Slice 4. Builder checkpoint: tests green → continue to the Final Slice.

---

## Final Slice: Full spec verification
**Scope:** Confirm the whole feature against the spec's `**Done when:**` items and the cross-module (arena) contract.

### Step 1: Arena log-schema contract still holds
**Build:** No new code. The log gained `holder_color`/`guesser_color` and a third `mode` value but kept every field `arena/src/lib/aggregate.js` and `server/stats.py` group on. Confirm the shared-fixture parity test still passes.
**Test:** `cd arena; npm test`
**Done When:** The arena vitest suite passes (the aggregate/`stats.py` parity on `tests/fixtures/arena_rounds.json` is unaffected by the added fields).
**Stuck If:** A vitest parity test fails — an existing log field was renamed/removed; restore it.
- [x] Complete

### Final Step: Verify spec Done when items
**Build:** No new code. Confirm all `## Feature: Red/Blue players & role rotation` `**Done when:**` items are met. Automated items DW1–DW6 and DW8 each have a committed test written in Slices 1–3; DW7 is `[human-required]` (UI built in Slice 4) — capture evidence with the UI evidence tool (`playwright (python)`, per CLAUDE.md): the stage renders Red as red and Blue as blue, shows who holds vs guesses each game, and, when the human is the Box Holder, presents the secret + a bluff-input control instead of the question/lock-in controls.
**Test:** `python -m pytest -q` (whole suite green — every `[automated]` item has its committed test). For DW7, drive the running stage per the run command (`python -m uvicorn server.app:app --host 127.0.0.1 --port 8000`, then `http://127.0.0.1:8000`) and capture evidence.
**Done When:** Every `[automated]` criterion (DW1–DW6, DW8) passes via its committed test; DW7 has captured UI evidence.
**Stuck If:** An automated criterion fails and the cause is not clear from the output.
- [x] Complete
  **Evidence:** Full suite `python -m pytest -q` → 130 passed (every `[automated]` DW1–DW6, DW8 backed by a committed test). DW7 UI evidence captured with Playwright (`output/inspect/dw7_1_stage_red_blue.png`, `dw7_2_seat_editors.png`, `dw7_3_human_holder.png`): Red podium renders red / Blue renders blue; role captions show the assigned Box Holder vs Guesser per game (Blue=Box Holder, Red=Guesser this round); the human Box Holder sees the secret peek + a bluff-input control ("Send bluff") in place of the question/lock-in controls, while the main box face stays "?" (no leak). Server driven with `BLUE_PLAYER_TYPE=human HUMAN_ROLE=holder` (no Ollama needed on the human-holder create path).

---
⛔ Final slice complete. Run **inspector** for final sign-off.

- [ ] **Fully inspected** — every `[inspect]` slice and the final sign-off passed. Inspector ticks this; never check it by hand. Its absence means inspection is still owed somewhere.
