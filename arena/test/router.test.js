// Router tests against an in-memory fake store — no live Cloudflare/D1. Exercises
// ingest (validate → rescore → dedupe → rate-limit → tier) and the leaderboard endpoint.
import { describe, it, expect, beforeEach } from "vitest";
import { handleRequest } from "../src/index.js";

class FakeStore {
  constructor() {
    this.rounds = new Map();
    this.clients = new Map();
  }
  async getClient(id) { return this.clients.get(id) || null; }
  async ensureClient(id, nowISO) {
    if (!this.clients.has(id)) this.clients.set(id, { client_id: id, first_seen: nowISO, tier_override: null });
  }
  async hasRound(id) { return this.rounds.has(id); }
  async clientDailyCount(id, dayPrefix) {
    let n = 0;
    for (const r of this.rounds.values()) {
      if (r.client_id === id && r.received_at.startsWith(dayPrefix)) n += 1;
    }
    return n;
  }
  async insertRound(r) { this.rounds.set(r.round_id, r); }
  async queryRounds({ tier }) {
    const all = [...this.rounds.values()];
    return (tier === "verified" ? all.filter((r) => r.tier === "verified") : all);
  }
}

function round(over = {}) {
  return {
    round_id: "r1", ts: "2026-07-01T00:00:00Z", mode: "ai_guesser_vs_ai_box_holder",
    box_holder_provider: "ollama", box_holder_model: "qwen3:8b",
    guesser_provider: "anthropic", guesser_model: "claude-opus-4-8",
    box_contents: "BANANA", turn_limit: 3, temperature: 0.7, standard_settings: true,
    transcript: [{ speaker: "box_holder", turn: 0, text: "hi" }],
    guesser_turns_used: 1, final_answer: "BANANA", correct: true, winner: "guesser",
    forced_default: false, ...over,
  };
}

function submitReq(payload, headers = {}) {
  return new Request("https://arena.test/api/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(payload),
  });
}

function payload(rounds, over = {}) {
  return { schema_version: 1, client_version: "0.1.0", client_id: "cid", rounds, ...over };
}

const ENV = { MAINTAINER_KEY: "secret-key", DAILY_ROUND_CAP: "500", MIN_ROUNDS: "1" };
let store;
beforeEach(() => { store = new FakeStore(); });

describe("POST /api/submit", () => {
  it("stores a valid round and reports the accepted count", async () => {
    const res = await handleRequest(submitReq(payload([round()])), ENV, store);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.accepted).toBe(1);
    expect(body.accepted_ids).toEqual(["r1"]);
    expect(store.rounds.size).toBe(1);
  });

  it("dedupes resubmissions — nothing double-stored", async () => {
    await handleRequest(submitReq(payload([round()])), ENV, store);
    const res = await handleRequest(submitReq(payload([round()])), ENV, store);
    const body = await res.json();
    expect(body.accepted).toBe(0);
    expect(body.duplicates).toEqual(["r1"]);
    expect(store.rounds.size).toBe(1);
  });

  it("rejects a round with an inconsistent tally, keeps good ones", async () => {
    const bad = round({ round_id: "bad", winner: "box_holder" }); // says guesser-answer but box_holder won
    const res = await handleRequest(submitReq(payload([round(), bad])), ENV, store);
    const body = await res.json();
    expect(body.accepted).toBe(1);
    expect(body.rejected).toHaveLength(1);
    expect(body.rejected[0].round_id).toBe("bad");
    expect(body.rejected[0].reason).toContain("inconsistent");
  });

  it("rejects an invalid round with a field reason", async () => {
    const bad = round({ round_id: "bad", box_contents: "APPLE" });
    const res = await handleRequest(submitReq(payload([bad])), ENV, store);
    const body = await res.json();
    expect(body.rejected[0].reason).toContain("box_contents");
  });

  it("stores canonical (recomputed) winner, not the client's", async () => {
    // Consistent-but-we-verify: submit a losing round; stored winner must be box_holder.
    const r = round({ round_id: "r2", box_contents: "EMPTY", final_answer: "BANANA",
                      winner: "box_holder", correct: false });
    await handleRequest(submitReq(payload([r])), ENV, store);
    expect(store.rounds.get("r2").winner).toBe("box_holder");
    expect(store.rounds.get("r2").correct).toBe(false);
  });

  it("tiers community without the key, verified with it", async () => {
    await handleRequest(submitReq(payload([round({ round_id: "c" })])), ENV, store);
    await handleRequest(
      submitReq(payload([round({ round_id: "v" })]), { "X-Maintainer-Key": "secret-key" }),
      ENV, store
    );
    expect(store.rounds.get("c").tier).toBe("community");
    expect(store.rounds.get("v").tier).toBe("verified");
  });

  it("rejects a banned client", async () => {
    store.clients.set("cid", { client_id: "cid", tier_override: "banned" });
    const res = await handleRequest(submitReq(payload([round()])), ENV, store);
    expect(res.status).toBe(403);
  });

  it("enforces the per-client daily cap", async () => {
    const capEnv = { ...ENV, DAILY_ROUND_CAP: "2" };
    const rounds = [round({ round_id: "x1" }), round({ round_id: "x2" }), round({ round_id: "x3" })];
    const res = await handleRequest(submitReq(payload(rounds)), capEnv, store);
    const body = await res.json();
    expect(body.accepted).toBe(2);
    expect(body.rejected).toHaveLength(1);
    expect(body.rejected[0].reason).toContain("cap");
  });

  it("400s on invalid JSON", async () => {
    const req = new Request("https://arena.test/api/submit", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{not json",
    });
    const res = await handleRequest(req, ENV, store);
    expect(res.status).toBe(400);
  });
});

describe("GET /api/leaderboard", () => {
  async function seed(n, over = {}) {
    const rounds = Array.from({ length: n }, (_, i) => round({ round_id: `s${i}`, ...over }));
    await handleRequest(submitReq(payload(rounds)), ENV, store);
  }

  it("aggregates and applies the min-N threshold", async () => {
    const env = { ...ENV, MIN_ROUNDS: "3" };
    await seed(2); // below threshold
    let res = await handleRequest(new Request("https://arena.test/api/leaderboard"), env, store);
    let body = await res.json();
    expect(body.rows).toHaveLength(0);

    store = new FakeStore();
    await seed(4);
    res = await handleRequest(new Request("https://arena.test/api/leaderboard"), env, store);
    body = await res.json();
    expect(body.rows).toHaveLength(1);
    expect(body.rows[0].rounds).toBe(4);
  });

  it("filters by tier", async () => {
    await handleRequest(
      submitReq(payload([round({ round_id: "v1" })]), { "X-Maintainer-Key": "secret-key" }),
      ENV, store
    );
    await handleRequest(submitReq(payload([round({ round_id: "c1" })])), ENV, store);
    const res = await handleRequest(
      new Request("https://arena.test/api/leaderboard?tier=verified"), ENV, store
    );
    const body = await res.json();
    expect(body.tier).toBe("verified");
    expect(body.rows[0].rounds).toBe(1); // only the verified round
    expect(res.headers.get("Cache-Control")).toContain("max-age");
  });
});

describe("unknown route", () => {
  it("404s", async () => {
    const res = await handleRequest(new Request("https://arena.test/nope"), ENV, store);
    expect(res.status).toBe(404);
  });
});
