# Handoff — `role_rotation` build (paused)

**Date:** 2026-07-02 · **Status:** paused mid-build (environmental usage limit, resets 10:20am America/Chicago)
**Feature:** Red/Blue players & role rotation — `Planning/specs/banana_spec.md` (`## Feature: Red/Blue players & role rotation`)
**Blueprint:** `Planning/blueprints/role_rotation_BP.md` (5 slices)

## State
- Working tree is **uncommitted and intact** — do not `git stash`/reset; the partial build lives there.
- Suite: **121 passed** (`python -m pytest -q`). Arena: 35 passed (`cd arena; npm test`).

| Slice | Status |
|---|---|
| 1 — rename Left/Right→Red/Blue, `.env` migration, `HUMAN_ROLE`, log colors | ✅ done + inspector PASS (09:17) |
| 2 — role assignment & rotation | ⏳ Step 1 done (`assign_roles` + `tests/test_rotation.py`); **Steps 2–6 remain** |
| 3 — human Box Holder (`/hold`, `/say` guard, holder-only reveal) `[inspect]` | ⬜ not started |
| 4 — retro stage (Red/Blue render, role display, human-holder controls) | ⬜ not started |
| Final — full spec sign-off | ⬜ not started |

## Resume (start here)
Re-run `/homeowner`, or drive the pipeline by hand from **Slice 2, Step 2**:
1. **Slice 2 Steps 2–6:** wire `create_round` → `assign_roles` and advance rotation on each completed+logged round; expose the round's assigned `holder_color`/`guesser_color` to the client; add DW1 (AI rounds alternate, log fields swap), DW8 (even AI batch = equal holds/guesses per model), DW2 (`/api/players` returns both colors, no `api_key`) tests.
2. **Inspect Slice 2** (fresh inspector) → then **Slice 3** `[inspect]` → inspect → **Slice 4** (unflagged) → **Phase 6 final sign-off** (fresh inspector, spec Done-when items, run/demo via `playwright (python)` for DW7).
3. On sign-off: `git add -A` and commit the verified build (git mode).

## Invariants to keep green
- **No-leak:** no Guesser-facing response/stream ever carries `box_contents` (the audit log may). Slice 3's `/hold` reveals contents to the *holder* path only.
- **Arena parity (forward constraint):** never remove/rename existing `logs/rounds.jsonl` fields — `arena/src/lib/aggregate.js` must stay matched to `server/stats.py`. Final slice runs `cd arena; npm test`.
- Rotation state is in-memory/per-process; per-round `model` override is retired.

## Assumptions the human should confirm
In-place `LEFT/RIGHT→RED/BLUE` `.env` rename+migration · Red holds first, then alternates · single `HUMAN_ROLE` (default `guesser`) · per-round `model` override retired.

## Open recommendation (not blocking)
`banana_spec.md` now holds ~10 feature blocks (> 6 size threshold) — consider splitting into per-feature specs + a `Planning/reference/` tier. See `docs/decisions/role_rotation_2026-07-02.md`.

## Pointers
Run log: `output/homeowner/HomeownerLog_2026-07-02_08-21.md` · Deviations: `output/deviations/Deviations_role_rotation_2026-07-02_09-14.md`
