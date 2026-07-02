# Spec: Community Arena — result submission, central depository & global leaderboard

*Added 2026-07-01. Realizes SPEC.md §12 item 10.* People run Banana or No Banana locally with their own API keys and **opt-in** submit completed rounds to a central depository; a public page shows the global leaderboard (guesser win-rate vs the 50% coin-flip baseline, per matchup). Central side: one **Cloudflare Worker** + **D1** database + a static leaderboard page — deployed to the maintainer's existing Cloudflare account, free tier. Client side: a `--submit` flag and a small submit module in the existing app. Trust model is honor-system hardened by mandatory full transcripts, validation, dedupe, rate limits, and a quarantine/verified tier split — **not** pretended to be cheat-proof.

## Scope
- Does: define the submission wire format (v1) as an envelope around the existing seat-aware `rounds.jsonl` records — the local log IS the payload.
- Does: client-side opt-in submission (`python -m server.batch --rounds N --submit`, and `python -m server.submit` for already-logged rounds), with local tracking so rounds are never double-submitted.
- Does: Worker ingest (`POST /api/submit`) with hard validation, dedupe, per-client and per-IP rate limits, and tiering (quarantine → included; verified via maintainer key).
- Does: public leaderboard — `GET /api/leaderboard` (JSON, cached) + a static page, with an "all" and a "verified" view, minimum-N threshold to appear.
- Does: keep the depository as a future fine-tuning corpus — full transcripts stored with outcome labels.
- Does NOT: user accounts, logins, or PII — `client_id` is a random UUID generated locally on first submit.
- Does NOT: publicly expose raw transcripts in v1 (aggregates only on the public page; transcripts are for maintainer audit and future dataset releases). Avoids hosting arbitrary submitted text as a public abuse surface.
- Does NOT: cheat-proofing beyond the stated mitigations (impossible when the submitter owns the whole pipeline; banana stakes don't justify attestation machinery).
- Does NOT: streamed/live spectating of remote games, tournaments, matchmaking — out of scope entirely.

## Reference: submission wire format (v1)
One `POST /api/submit` body (JSON, gzip accepted):
```json
{
  "schema_version": 1,
  "client_version": "<app version string>",
  "client_id": "<uuid4, generated locally on first submit, no PII>",
  "rounds": [ { ...one seat-aware rounds.jsonl record, verbatim... } ]
}
```
Round records are exactly the local log schema: `round_id`, `ts`, `mode`, `box_holder_provider`, `box_holder_model`, `guesser_provider`, `guesser_model`, `box_contents`, `turn_limit`, `transcript` (non-empty; ordered speaker/turn/text), `guesser_turns_used`, `final_answer`, `correct`, `winner`, `forced_default`.

Caps (reject the whole request with a per-round error list otherwise): ≤ 100 rounds/request · ≤ 64 KB/round · ≤ 2 MB/request. Model/provider strings are normalized (trim, lowercase provider) and length-capped (128 chars) on ingest.

## Feature: Client submission (opt-in)
The app submits completed rounds to the arena only when explicitly asked. Nothing is ever sent without the flag/command; the arena URL is configurable and the client works fully offline forever if unused.

- Input: `python -m server.batch --rounds N --submit` (submit the batch's rounds when done); `python -m server.submit` (submit all not-yet-submitted rounds from `logs/rounds.jsonl`); `ARENA_URL` env override (default: the deployed Worker URL); `ARENA_MAINTAINER_KEY` env (optional, marks submissions verified).
- Output: POST per the wire format; on success, submitted `round_id`s are recorded locally (`logs/submitted.jsonl`: `{round_id, submitted_at}` per line) and skipped by future submits. `client_id` is created on first submit and stored (`logs/arena_client_id`). Human-only and `ai_guesser` rounds are both eligible (mode is in the record; the leaderboard decides what to show).
- Errors: non-2xx responses are printed with the server's per-round error list; nothing is marked submitted on failure; partial acceptance (server accepted some, rejected dupes) marks only the accepted/duplicate rounds as submitted.

**Done when:**
- Running batch without `--submit`, or the server normally, performs no network call to the arena (verified: no request against a mocked transport).  `[automated]`
- `server.submit` sends exactly the not-yet-submitted rounds in wire format v1 with a stable `client_id`, and marks them submitted only on acceptance (verified against a mocked arena endpoint, including a failure case).  `[automated]`
- A second `server.submit` run sends nothing ("nothing to submit").  `[automated]`
- A real submission from this machine to the deployed Worker lands in D1 and appears in the leaderboard JSON.  `[human-required]`

## Feature: Worker ingest (`POST /api/submit`)
A Cloudflare Worker validates and stores submissions in D1. Everything invalid is rejected loudly; everything accepted is attributable and deduplicated.

- Input: wire format v1. Optional `X-Maintainer-Key` header (secret bound to the Worker) → rounds land `tier="verified"`; otherwise `tier="community"`.
- Validation (per round): all required fields present and type-correct; `transcript` non-empty with ordered `speaker`/`turn`/`text` entries; `winner`/`correct` consistent with `final_answer` × `box_contents` (recomputed server-side — a submitted tally that contradicts its own transcript fields is rejected); caps per the wire-format section.
- Dedupe: `round_id` is unique across the table; resubmitted IDs are reported as `duplicate` (not an error) and not stored twice.
- Rate limits: Cloudflare per-IP rules at the edge, plus application-level per-`client_id` daily round cap (default 500/day) enforced in the Worker.
- Storage (D1): `rounds` table — round fields flattened for aggregation + `transcript` as JSON text + `client_id`, `tier`, `received_at`, `schema_version`, `client_version`. `clients` table — `client_id`, `first_seen`, `tier_override`, `note` (lets the maintainer promote a client to verified or ban one without touching rows).
- Response: `{accepted: n, duplicates: [ids], rejected: [{round_id, reason}]}`.

**Done when:**
- A valid submission stores its rounds and returns the correct accepted count; resubmission returns them all as duplicates with nothing double-stored.  `[automated]` *(Worker test suite — wrangler/vitest)*
- Each validation rule rejects a crafted bad round with a reason naming the field, and a request over caps is rejected whole.  `[automated]`
- A round whose `winner`/`correct` don't match its own `final_answer` × `box_contents` is rejected.  `[automated]`
- Submissions without the maintainer key land `tier="community"`; with it, `tier="verified"`; a banned `client_id` is rejected.  `[automated]`
- The per-`client_id` daily cap rejects round N+1 with a clear message.  `[automated]`

## Feature: Public leaderboard (`GET /api/leaderboard` + page)
The scoreboard and the eval result are the same object: deviation from 50% per matchup, computed with the same rules as the local `server/stats.py`.

- Input: `GET /api/leaderboard?tier=all|verified` (default `all` = community + verified).
- Output: JSON rows — `box_holder` (provider/model), `guesser` (provider/model), `rounds`, `guesser_wins`, `win_rate`, `deviation`, `forced_excluded`, `clients` (distinct submitters) — `forced_default` rounds excluded from the metric, matchups below a minimum N (default 10) omitted. Cached at the edge (5-minute TTL is fine; this is not a stock ticker).
- Page: a static HTML page (Worker-served or Cloudflare Pages) rendering the table with the tier toggle, the deviation explained in one line, and a "run it yourself" link to the repo. Same retro house style as the game if cheap; plain and legible beats fancy.

**Done when:**
- The endpoint aggregates seeded fixture rounds into correct win-rate/deviation rows, excludes forced defaults, applies the min-N threshold, and filters by tier.  `[automated]`
- Aggregation agrees with `server/stats.py` on the same input (shared fixture: same rounds in, same rows out).  `[automated]`
- The public page renders the live leaderboard from the deployed Worker in a browser.  `[human-required]`

## Feature: Arena deployment & repo layout
The Worker lives in this repo — one project, two deployables.

- Layout: `arena/` — `wrangler.toml`, `src/` (Worker), `schema.sql` (D1 migrations), `test/`. Deploy: `wrangler deploy` from `arena/`; secrets (`MAINTAINER_KEY`) via `wrangler secret put`, never in the repo.
- The default `ARENA_URL` baked into the client is set once the Worker has its `workers.dev` URL (custom domain optional, later).

**Done when:**
- `wrangler deploy` from a clean checkout (plus secrets) yields a working ingest + leaderboard on the maintainer's Cloudflare account.  `[human-required]`
- No secret (maintainer key, account IDs beyond what wrangler.toml needs) is committed.  `[automated]` *(grep-able check in CI/test)*

## Assumptions
- Free-tier Cloudflare (Workers + D1 + Pages) is sufficient for the foreseeable scale; no paid features assumed. — proportional; revisit if it ever hurts.
- Worker is written in plain JS/TS with wrangler's standard toolchain; its tests run with wrangler's vitest integration, separate from the Python suite. — conventional; the Python `[automated]` items stay in pytest.
- Transcripts submitted become part of a dataset the maintainer may audit and later publish; the README/page states this in one plain sentence. Submissions carry no PII by construction (UUID + model dialogue).
- Public page shows aggregates only in v1; raw-transcript browsing/dataset export is a later, deliberate release step.
- Client version string comes from a single constant in the app (introduced with this feature).
- Sequencing: build after (or alongside) packaging — the client-side feature is testable now against a mocked endpoint; the Worker can deploy any time; the *default* ARENA_URL ships with the first packaged release.

## Open Questions
- **Leaderboard identity granularity:** group strictly by provider/model string, or maintain a small server-side alias map (e.g. `openai_compat/gpt-4o` submitted via OpenRouter vs OpenAI counted together)? v1 default: strict strings, no alias map — revisit when real collisions appear.
