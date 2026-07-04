# Deviations — Red/Blue players & role rotation
Blueprint: Planning/blueprints/role_rotation_BP.md
Date: 2026-07-02

Rollup as of Slice 1 completion (feature build stopped at the Slice 1 `[inspect]`
boundary for independent inspection; this file will be re-consolidated across all
slices on the final slice).

| Slice | Step | Deviation | Why |
|-------|------|-----------|-----|
| 1 | 1 | Per-step named test files (test_players/round/log/api) stay red until Step 6, which migrates them; new-behavior Done When verified via scratch checks outside the tree. | Blueprint sequences all test migrations into Step 6, so Steps 1–5 build code against stale test files by design. |
| 1 | 6 | Migrated three test files the Step-6 list did not name — `tests/test_batch.py` (left/right→red/blue, `ScriptedPlayers` seat key `right`→`blue`, renamed `test_batch_main_refuses_human_right_seat`→`..._human_seat` with the new both-AI message), `tests/test_settings.py` (dropped the retired per-round `model` override assertion), `tests/test_arena.py` (left/right→red/blue in a `load_players` monkeypatch). | The "full suite green with Red/Blue" Done When required them; pure name/retirement migrations, no behavior change. |
| 2 | 2 | Added `game.reset_rotation()` to the autouse `reset_rounds` fixture in `tests/test_api.py`, and reworked `test_round_rejects_human_box_holder` to a one-human + `HUMAN_ROLE=holder` setup. | Completions now bump the module-global `ROTATION`; without a per-test reset, AI-vs-AI tests (whose `FakeDualPlayers` keys the guesser on `cfg.seat=="blue"`) lose their Red-holds/Blue-guesses parity. The old rejection test set both seats human, which now raises the *two-human* error before the human-holder guard; recast as one human holder (still 422, same "Red seat" message). Slice 3 Step 5 replaces it. |
| 2 | 4 | The DW1/DW8 fakes (`RoleScriptedProvider` in `tests/test_rotation.py`) and the migrated `ScriptedPlayers` in `tests/test_batch.py` identify the Guesser by **role** (absence of the hidden `_KICKOFF` in the message stream), not seat color; added `reset_rotation()` to `test_batch.py`'s `clean_rounds` fixture. | With rotation the guesser color alternates between rounds, so `cfg.seat`-based identification (the pre-rotation `FakeDualPlayers`/`ScriptedPlayers` design) no longer picks out the guesser. Pure test-fake mechanics; no product behavior change. |
| 3 | 1 | The obsolete `test_round_rejects_human_box_holder` fails at Step 1 (human holder now 200) and is removed at Step 5 — same "test goes green at a later step" sequencing as Slice 1. | The blueprint sequences the test replacement into Step 5. |
| 3 | 3 | Added two endpoint-guard tests (`test_hold_unknown_round_returns_404`, `test_hold_rejected_when_no_human_holder`) beyond the Step-4 DW list. | Step 3's Done When names the /hold 404 and non-human-holder 409 branches; these lock them in. |
| 3 | 4 | Used a dedicated `ScriptedGuesser` fake instead of `FakeDualPlayers`. | On the human-holder path every AI call is the Guesser (no AI Box Holder call), so an in-order line script is simpler and sufficient. No behavior change. |

Notes (not deviations, recorded for the inspector):
- `server/log.py` now derives `box_holder_model` from `_seat_identity(r.holder)` per the
  blueprint's "stop reading `r.model`" instruction, rather than from `r.model`. For a
  validly-configured AI holder (build_seat requires a model) the two are identical; the
  arena parity fixture (`tests/fixtures/arena_rounds.json`) is a static file and is
  unaffected. No existing log field was removed or renamed (forward constraint honored).
- Minor docstring/prose cleanups in `server/app.py` and `server/batch.py` to drop stale
  "left/right seat" wording now that roles are color-independent.
