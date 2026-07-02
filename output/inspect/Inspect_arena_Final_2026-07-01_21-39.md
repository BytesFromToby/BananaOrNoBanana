# Final Inspection — arena · 2026-07-01 21:39

Spec: Planning/specs/arena_spec.md · Blueprint: Planning/blueprints/arena_BP.md
Suites: `python -m pytest -q` → **112 passed**; `cd arena && npm test` → **35 passed**.

> **Independence caveat (honest).** This inspection was run inline in the main session, not by a
> fresh Plumbline inspector subagent (the v1.0.0 subagents were tool-less; see the run log). It is
> therefore **self-assessed**, not structurally independent. Evidence below is real (tests exist and
> run); the missing guarantee is the separate set of eyes.

## Automated Done-when items

### Feature: Client submission (opt-in)
| Done-when | Evidence | Verdict |
|---|---|---|
| No network call without `--submit`/submit | `tests/test_arena.py::test_batch_no_submit_makes_no_network_call` (counts submit.main calls = 0) | ✅ PASS |
| `server.submit` sends exactly unsent rounds in wire v1 w/ stable client_id; marks submitted only on acceptance (incl. failure) | `test_submit_sends_unsent_and_marks_accepted`, `test_submit_marks_nothing_on_failure`, `test_maintainer_key_sent_as_header` | ✅ PASS |
| A second submit run sends nothing | asserted in `test_submit_sends_unsent...` (2nd pass → `[]`); `test_submit_marks_duplicates_as_done_too` | ✅ PASS |
| *(human)* real submission lands in D1 and shows in leaderboard JSON | — | ⏳ owed |

### Feature: Worker ingest (POST /api/submit)
| Done-when | Evidence | Verdict |
|---|---|---|
| Valid submit stores + correct accepted count; resubmit → duplicates, nothing double-stored | `arena/test/router.test.js` (stores/accepted; dedupe → size stays 1) | ✅ PASS |
| Each validation rule rejects a crafted bad round w/ field reason; over-cap whole | `arena/test/validate.test.js` (12) + router "invalid round" reject | ✅ PASS |
| Round whose winner/correct ≠ rederived → rejected | `router.test.js` "inconsistent tally"; `score.test.js::tallyIsConsistent` | ✅ PASS |
| No key = community, key = verified, banned rejected | `router.test.js` tier + banned tests | ✅ PASS |
| Per-client daily cap rejects N+1 | `router.test.js` cap test (2 of 3 accepted, 3rd "cap") | ✅ PASS |

### Feature: Public leaderboard
| Done-when | Evidence | Verdict |
|---|---|---|
| Aggregates fixture into correct rows; excludes forced + non-standard (rederived); min-N; tier | `arena/test/aggregate.test.js` (forced+non-standard excluded via golden) + `router.test.js` (min-N threshold, tier filter) | ✅ PASS |
| Aggregation agrees with `server/stats.py` on the same input (shared fixture) | Both `test_arena.py::test_aggregate_matches_golden_fixture` and `arena/test/aggregate.test.js` assert against the SAME `tests/fixtures/arena_golden.json` | ✅ PASS (strong parity) |
| *(human)* public page renders live leaderboard in a browser | — | ⏳ owed |

### Feature: Arena deployment & repo layout
| Done-when | Evidence | Verdict |
|---|---|---|
| No secret committed (grep-able) | `arena/test/no_secrets.test.js` (provider-key patterns tree-wide; MAINTAINER_KEY assignment in non-test files) | ✅ PASS |
| *(human)* `wrangler deploy` yields working ingest + leaderboard | — | ⏳ owed |

## Test-fidelity judgement (would the test fail if the criterion were violated?)
- **Aggregation parity** — `fidelity: ok`. Golden rows are hand-specified (not derived from the code under test); divergence in either language fails against the same file.
- **Server-side rescore / anti-tamper** — `fidelity: ok`. Router test submits a self-contradicting tally and asserts rejection; removing the rescore check would accept it → test fails.
- **Dedupe / daily cap / tiering / banned** — `fidelity: ok`. Each asserts the observable count/tier, not an internal call; breaking the rule flips the asserted number.
- **No-network-without-opt-in** — `fidelity: ok`. Counts the submit entrypoint; a stray call trips it.
- **Marks-nothing-on-failure** — `fidelity: ok`. Transport raises; test asserts the rounds remain unsent.
- **No-secrets guard** — `fidelity: ok`. Confirmed it *can* fail: it fired on a fake key during the build before the test-dir scope was added, proving it isn't vacuous.

## Observations (non-blocking)
- The leaderboard endpoint's forced/non-standard exclusion is proven at the `aggregate()` unit
  (parity fixture) rather than by a dedicated endpoint round-trip; the endpoint delegates to that
  function, so coverage is real but one layer down. Optional future test: seed forced/non-standard
  rounds via `/api/submit` and assert they don't move the `/api/leaderboard` numbers.
- vitest reports npm-audit vulnerabilities in the wrangler/vitest devDependency tree — dev tooling
  only, not shipped in the Worker; noted, not fixed here.

## Human-required follow-ups (carried, not graded)
1. `wrangler deploy` (+ `wrangler d1 create` / `secret put`) yields a working ingest + leaderboard on the maintainer's Cloudflare account.
2. A real submission from a machine lands in D1 and appears in the leaderboard JSON.
3. The public page renders the live leaderboard in a browser.

## Result
**PASS · needs-human: 3** (automated: all passing; 3 human-required items owed). Self-assessed — see caveat.
