# Blueprint: Community Arena — arena

Spec: Planning/specs/arena_spec.md · Contract: CLAUDE.md (git mode; Test: `python -m pytest -q`)
Worker tests (separate toolchain): `npm test` from `arena/` (vitest).

Built inline (main session) — see docs/decisions/arena_2026-07-01.md. Slice inspection self-assessed.

- [x] **Fully inspected** — ✅ Inspector (self-assessed): PASS — 2026-07-01 21:39 — see output/inspect/Inspect_arena_Final_2026-07-01_21-39.md (needs-human: 3)

---

## Slice 1 — Wire format & client_id foundations (Python)  [inspect]
`[inspect]`: defines the cross-program schema seam (client ↔ Worker) and the shared aggregation contract.

**Scope:** the app can build a wire-format-v1 payload from log records and manage a persistent anonymous client_id, without sending anything.

- **Build:** `server/arena.py` — `SCHEMA_VERSION = 1`, `CLIENT_VERSION` constant; `get_or_create_client_id(path="logs/arena_client_id")` (uuid4 hex, created once, then read); `build_payload(rounds, client_id)` → `{schema_version, client_version, client_id, rounds}`. Reuse the exact round dicts from `logs/rounds.jsonl` (no reshaping).
  - **Test:** `python -m pytest -q tests/test_arena.py`
  - **Done When:** client_id is created once and stable across calls; payload has the four envelope fields and rounds verbatim.
  - **Stuck If:** the log schema and wire format can't be reconciled without reshaping round records.
- [x] Complete

## Slice 2 — Client submission module & CLI (Python)
**Scope:** `python -m server.submit` sends not-yet-submitted rounds; `--submit` on batch does the same after a run; nothing is sent without opting in.

- **Build:** `server/submit.py` — `load_submitted(path)`/`mark_submitted(ids, path)` over `logs/submitted.jsonl`; `unsent_rounds(rounds_path, submitted_path)`; `submit(rounds, url, maintainer_key=None, transport=...)` posting the payload (httpx), returning the server's `{accepted, duplicates, rejected}`; marks accepted+duplicate ids submitted, nothing on failure. `main(argv)` → arena URL from `ARENA_URL` env (default constant), `ARENA_MAINTAINER_KEY` optional header. Wire `--submit` into `server/batch.py` (post-run, guarded by the flag). Injectable transport so tests never hit the network.
  - **Test:** `python -m pytest -q tests/test_arena.py`
  - **Done When:** no network call without `--submit`/submit; exactly unsent rounds sent; accepted marked, failures not; second run sends nothing.
  - **Stuck If:** batch can't expose its just-played round_ids to the submitter.
- [x] Complete

## Slice 3 — Shared aggregation parity (Python reference)
**Scope:** a canonical aggregation used by both the leaderboard test fixture and `server/stats.py`, so Python and the Worker can be proven to agree.

- **Build:** ensure `server/stats.py` `aggregate()` is the reference; add `tests/fixtures/arena_rounds.json` (a mix: standard/non-standard, forced, two matchups, a human seat). Golden expected rows in the fixtures dir. `server/stats.aggregate()` over the fixture must equal the golden.
  - **Test:** `python -m pytest -q tests/test_arena.py`
  - **Done When:** stats.aggregate(fixture) == golden rows (the same fixture the Worker test consumes).
  - **Stuck If:** stats.py can't consume the fixture shape without change.
- [x] Complete

## Slice 4 — Worker project skeleton & pure logic (JS)  [inspect]
`[inspect]`: new cross-module program + the security-relevant validation/rescore logic.

**Scope:** `arena/` exists as a deployable; validation, server-side rescore, and aggregation are pure, tested functions.

- **Build:** `arena/package.json` (vitest, wrangler devDeps), `arena/wrangler.toml` (D1 binding, no secrets), `arena/schema.sql` (rounds + clients tables), `arena/src/lib/validate.js` (`validateRound`, `validatePayload` — required fields, caps, non-empty ordered transcript), `arena/src/lib/score.js` (`recomputeWinner`, `recomputeStandard` — rederive winner/correct + standard_settings from the round's own fields; reject on mismatch), `arena/src/lib/aggregate.js` (same rules as stats.py: group by matchup, exclude forced + non-standard, min-N, tier filter). `arena/test/` vitest specs incl. the SHARED fixture copied/symlinked from tests/fixtures with the same golden.
  - **Test:** `npm test` (from `arena/`)
  - **Done When:** validate rejects each crafted bad round with a field reason + over-cap whole; rescore rejects winner/standard mismatches; aggregate(fixture) equals the Python golden.
  - **Stuck If:** vitest can't run without live Cloudflare bindings (mitigate: pure modules, fake storage).
- [x] Complete

## Slice 5 — Worker HTTP surface: ingest + leaderboard (JS)  [inspect]
`[inspect]`: schema writes (D1), auth tier (maintainer key), rate-limit/dedupe.

**Scope:** `POST /api/submit` and `GET /api/leaderboard` wired over a storage interface, tested against a fake D1.

- **Build:** `arena/src/storage.js` (D1-backed store: insert round if new, dedupe by round_id, per-client daily count, client tier_override/ban, leaderboard query) behind an interface a fake implements in tests. `arena/src/index.js` — router: submit (validate → rescore → dedupe → rate-limit → tier from `X-Maintainer-Key` → store; respond `{accepted, duplicates, rejected}`), leaderboard (`?tier=` → aggregate → JSON, cache header). `arena/test/` specs with a fake store.
  - **Test:** `npm test`
  - **Done When:** valid submit stores + counts; resubmit → all duplicates, nothing double-stored; bad rounds rejected with reasons; no-key=community/key=verified/banned=rejected; daily cap rejects N+1; leaderboard filters tier + min-N.
  - **Stuck If:** a fake store can't stand in for D1's query surface.
- [x] Complete

## Slice 6 — Public page, no-secrets guard, deploy docs (JS + repo)
**Scope:** a static leaderboard page, a committed test that no secret is present, and a deploy README.

- **Build:** `arena/public/index.html` (+ inline CSS/JS) fetching `/api/leaderboard`, tier toggle, one-line deviation explainer, "run it yourself" link; served by the Worker (or Pages). `arena/test/no_secrets.test.js` — grep the arena tree for key patterns / real values, fail if found. `arena/README.md` — `wrangler deploy`, `wrangler secret put MAINTAINER_KEY`, D1 create/migrate, set client `ARENA_URL`. `.gitignore` covers `.dev.vars`, `.wrangler/`, `node_modules/`.
  - **Test:** `npm test` + manual page (human-required)
  - **Done When:** no-secrets test passes; page renders from a stubbed leaderboard response; README deploy steps complete.
  - **Stuck If:** —
- [x] Complete

---

**Human-required (carried to final report, not auto-graded):**
- Live `wrangler deploy` yields working ingest + leaderboard on Cloudflare.
- A real submission from a machine lands in D1 and appears in the leaderboard JSON.
- The public page renders the live leaderboard in a browser.
