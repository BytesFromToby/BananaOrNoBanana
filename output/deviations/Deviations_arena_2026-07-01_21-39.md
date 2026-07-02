# Deviations — arena · 2026-07-01 21-39

Two behavior-preserving fixes surfaced during the build (both kept each step's Done-When intact):

- **Slice 3 — float rounding for parity.** `server/stats.py::aggregate` now rounds `win_rate` and
  `deviation` to 6 places, so its JSON output compares exactly with the Worker's `aggregate.js`.
  Display formatting (`render`) and the existing approx-based stats tests are unaffected. *(How, not
  what — the numbers are the same to 6 places; this only makes cross-language equality exact.)*

- **Slice 6 — no-secrets guard scope.** The `MAINTAINER_KEY`-assignment check in
  `arena/test/no_secrets.test.js` was scoped to non-test files after it (correctly) flagged the fake
  `secret-key` used by `router.test.js` to exercise the verified tier. Real provider-key patterns
  (`sk-`, `AKIA`, …) are still scanned tree-wide, including tests. *(How, not what — the guard still
  fails on any real committed secret; it just permits tests to construct fake auth.)*

No `**Stuck**` conditions were hit.
