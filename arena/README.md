# Banana Arena — Cloudflare Worker

The central depository + public leaderboard for **Banana or No Banana**. Players run the game
locally with their own API keys and opt-in submit completed rounds here; this Worker validates,
re-scores server-side, stores to D1, and serves the global leaderboard.

This is a **separate program** from the Python game (one repo, two deployables). It never sees
API keys — only completed round records (anonymous `client_id` + model dialogue, no PII).

## Layout
```
arena/
  wrangler.toml     # Worker + D1 config (no secrets)
  schema.sql        # D1 tables (rounds, clients)
  src/
    index.js        # router: POST /api/submit, GET /api/leaderboard
    storage.js      # D1-backed store (behind an interface the tests fake)
    lib/            # pure logic: validate, score (rescore), aggregate
  public/index.html # the public leaderboard page
  test/             # vitest — all offline, no live Cloudflare needed
```

## Test
```
cd arena
npm install
npm test          # vitest — validation, rescore, router (fake store), aggregate parity, no-secrets
```
`test/aggregate.test.js` shares one fixture with the Python suite
(`../tests/fixtures/arena_rounds.json` → `arena_golden.json`) and asserts the Worker's
aggregation matches `server/stats.py` row-for-row.

## Deploy (maintainer, one time)
```
cd arena
npm install
wrangler login

# 1. Create the D1 database, then paste the returned id into wrangler.toml (database_id).
wrangler d1 create banana-arena
wrangler d1 execute banana-arena --file=schema.sql --remote

# 2. Set the maintainer key (marks your own runs 'verified'). Never commit this.
wrangler secret put MAINTAINER_KEY

# 3. Ship it.
wrangler deploy
```
`wrangler deploy` prints the `*.workers.dev` URL. Put that in the client as `ARENA_URL`
(env var, or the default constant in `server/submit.py`) so downloads submit to it.

## Trust model
Self-reported results from machines the maintainer doesn't control can't be made cheat-proof.
Mitigations, not guarantees: full transcripts required per round (fabricating N in-character
interrogations is expensive and auditable); winner/correct **re-derived server-side** from each
round's own `final_answer × box_contents` (a fabricated tally is rejected); `standard_settings`
re-derived from `turn_limit × temperature`; per-client daily cap + edge rate limits; a separate
**verified** tier for maintainer-run submissions. Honor system for the rest — banana stakes.

Submitted transcripts are retained for audit and may seed a later, deliberately-released
deception-dialogue dataset. No PII is collected by construction.
