// Parity: the Worker's aggregate() must produce the SAME rows as server/stats.py on the
// SAME shared fixture — proving the global leaderboard can't silently disagree with the
// local one. Golden rows are hand-specified (tests/fixtures/arena_golden.json), the very
// file the Python test asserts against too.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { aggregate } from "../src/lib/aggregate.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = join(here, "..", "..", "tests", "fixtures");
const rounds = JSON.parse(readFileSync(join(fixturesDir, "arena_rounds.json"), "utf-8"));
const golden = JSON.parse(readFileSync(join(fixturesDir, "arena_golden.json"), "utf-8"));

const SHARED_KEYS = [
  "box_holder", "guesser", "rounds", "guesser_wins",
  "win_rate", "deviation", "forced_excluded", "non_standard_excluded",
];

describe("aggregate parity with server/stats.py", () => {
  it("produces the hand-specified golden rows from the shared fixture", () => {
    const rows = aggregate(rounds);
    const trimmed = rows.map((r) =>
      Object.fromEntries(SHARED_KEYS.map((k) => [k, r[k]]))
    );
    expect(trimmed).toEqual(golden);
  });

  it("tracks distinct clients as an arena-only extra", () => {
    const withClients = rounds.map((r, i) => ({ ...r, client_id: i < 5 ? "c1" : "c2" }));
    const rows = aggregate(withClients);
    // matchup A (a1..a7) spans c1/c2 → 2 distinct; matchup B (b1,b2) → c2 only.
    const a = rows.find((r) => r.guesser === "anthropic/claude-opus-4-8");
    expect(a.clients).toBe(2);
  });
});
