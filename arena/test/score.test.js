import { describe, it, expect } from "vitest";
import { recomputeWinner, recomputeStandard, tallyIsConsistent } from "../src/lib/score.js";

describe("recomputeWinner (server-side, not client-trusted)", () => {
  it.each([
    ["BANANA", "BANANA", true, "guesser"],
    ["NO_BANANA", "EMPTY", true, "guesser"],
    ["BANANA", "EMPTY", false, "box_holder"],
    ["NO_BANANA", "BANANA", false, "box_holder"],
  ])("answer=%s box=%s", (final_answer, box_contents, correct, winner) => {
    expect(recomputeWinner({ final_answer, box_contents })).toEqual({ correct, winner });
  });
});

describe("recomputeStandard", () => {
  it("true only at 3 turns / temp 0.7", () => {
    expect(recomputeStandard({ turn_limit: 3, temperature: 0.7 })).toBe(true);
    expect(recomputeStandard({ turn_limit: 5, temperature: 0.7 })).toBe(false);
    expect(recomputeStandard({ turn_limit: 3, temperature: 0.9 })).toBe(false);
  });
});

describe("tallyIsConsistent (anti-tamper)", () => {
  it("accepts a self-consistent tally", () => {
    expect(tallyIsConsistent({
      final_answer: "BANANA", box_contents: "BANANA", winner: "guesser", correct: true,
    })).toBe(true);
  });
  it("rejects a fabricated winner", () => {
    expect(tallyIsConsistent({
      final_answer: "BANANA", box_contents: "BANANA", winner: "box_holder", correct: true,
    })).toBe(false);
  });
  it("rejects a fabricated correct flag", () => {
    expect(tallyIsConsistent({
      final_answer: "BANANA", box_contents: "EMPTY", winner: "box_holder", correct: true,
    })).toBe(false);
  });
});
