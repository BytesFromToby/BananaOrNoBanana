import { describe, it, expect } from "vitest";
import {
  validateRound, validatePayload, normalizeSeatStrings, MAX_ROUNDS_PER_REQUEST,
} from "../src/lib/validate.js";

function goodRound(over = {}) {
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

describe("validateRound", () => {
  it("accepts a well-formed round", () => {
    expect(validateRound(goodRound()).ok).toBe(true);
  });

  it("names the missing field", () => {
    const r = goodRound();
    delete r.winner;
    const res = validateRound(r);
    expect(res.ok).toBe(false);
    expect(res.reason).toContain("winner");
  });

  it("rejects a bad box_contents", () => {
    expect(validateRound(goodRound({ box_contents: "APPLE" })).ok).toBe(false);
  });

  it("rejects a bad final_answer", () => {
    expect(validateRound(goodRound({ final_answer: "MAYBE" })).ok).toBe(false);
  });

  it("rejects an empty transcript", () => {
    expect(validateRound(goodRound({ transcript: [] })).ok).toBe(false);
  });

  it("rejects a malformed transcript entry", () => {
    expect(validateRound(goodRound({ transcript: [{ speaker: "x" }] })).ok).toBe(false);
  });

  it("rejects an over-long provider string", () => {
    expect(validateRound(goodRound({ box_holder_provider: "x".repeat(200) })).ok).toBe(false);
  });
});

describe("validatePayload", () => {
  const payload = (over = {}) => ({
    schema_version: 1, client_version: "0.1.0", client_id: "cid",
    rounds: [goodRound()], ...over,
  });

  it("accepts a good payload", () => {
    expect(validatePayload(payload()).ok).toBe(true);
  });

  it("rejects a wrong schema_version", () => {
    expect(validatePayload(payload({ schema_version: 2 })).ok).toBe(false);
  });

  it("rejects a missing client_id", () => {
    expect(validatePayload(payload({ client_id: "" })).ok).toBe(false);
  });

  it("rejects too many rounds whole", () => {
    const rounds = Array.from({ length: MAX_ROUNDS_PER_REQUEST + 1 }, () => goodRound());
    const res = validatePayload(payload({ rounds }));
    expect(res.ok).toBe(false);
    expect(res.reason).toContain("too many");
  });
});

describe("normalizeSeatStrings", () => {
  it("trims and lowercases providers", () => {
    const n = normalizeSeatStrings(goodRound({ box_holder_provider: "  OLLAMA " }));
    expect(n.box_holder_provider).toBe("ollama");
  });
});
