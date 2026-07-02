// Wire-format-v1 validation. Everything invalid is rejected loudly with a reason that
// names the offending field. Caps guard against oversized payloads.

export const SCHEMA_VERSION = 1;
export const MAX_ROUNDS_PER_REQUEST = 100;
export const MAX_ROUND_BYTES = 64 * 1024;
export const MAX_PAYLOAD_BYTES = 2 * 1024 * 1024;
export const MAX_STRING_LEN = 128;

const REQUIRED_FIELDS = [
  "round_id", "ts", "mode",
  "box_holder_provider", "box_holder_model",
  "guesser_provider", "guesser_model",
  "box_contents", "turn_limit", "temperature", "standard_settings",
  "transcript", "guesser_turns_used", "final_answer", "correct", "winner",
  "forced_default",
];

const VALID_BOX = new Set(["BANANA", "EMPTY"]);
const VALID_ANSWER = new Set(["BANANA", "NO_BANANA"]);

// Returns { ok: true } or { ok: false, reason: "..." }.
export function validateRound(round) {
  if (typeof round !== "object" || round === null) {
    return { ok: false, reason: "round is not an object" };
  }
  for (const field of REQUIRED_FIELDS) {
    if (!(field in round)) return { ok: false, reason: `missing field: ${field}` };
  }
  if (typeof round.round_id !== "string" || !round.round_id) {
    return { ok: false, reason: "round_id must be a non-empty string" };
  }
  if (!VALID_BOX.has(round.box_contents)) {
    return { ok: false, reason: "box_contents must be BANANA or EMPTY" };
  }
  if (!VALID_ANSWER.has(round.final_answer)) {
    return { ok: false, reason: "final_answer must be BANANA or NO_BANANA" };
  }
  if (typeof round.turn_limit !== "number" || round.turn_limit < 1) {
    return { ok: false, reason: "turn_limit must be a positive number" };
  }
  if (typeof round.temperature !== "number" || round.temperature < 0) {
    return { ok: false, reason: "temperature must be a non-negative number" };
  }
  if (!Array.isArray(round.transcript) || round.transcript.length === 0) {
    return { ok: false, reason: "transcript must be a non-empty array" };
  }
  for (const entry of round.transcript) {
    if (
      typeof entry !== "object" || entry === null ||
      typeof entry.speaker !== "string" ||
      typeof entry.turn !== "number" ||
      typeof entry.text !== "string"
    ) {
      return { ok: false, reason: "transcript entries need speaker/turn/text" };
    }
  }
  for (const f of ["box_holder_provider", "box_holder_model",
                   "guesser_provider", "guesser_model"]) {
    if (typeof round[f] !== "string") return { ok: false, reason: `${f} must be a string` };
    if (round[f].length > MAX_STRING_LEN) return { ok: false, reason: `${f} too long` };
  }
  if (jsonBytes(round) > MAX_ROUND_BYTES) {
    return { ok: false, reason: "round exceeds size cap" };
  }
  return { ok: true };
}

// Returns { ok: true } or { ok: false, reason } for whole-payload problems (schema,
// envelope, caps). Per-round validity is checked separately by validateRound.
export function validatePayload(payload) {
  if (typeof payload !== "object" || payload === null) {
    return { ok: false, reason: "payload is not an object" };
  }
  if (payload.schema_version !== SCHEMA_VERSION) {
    return { ok: false, reason: `unsupported schema_version (need ${SCHEMA_VERSION})` };
  }
  if (typeof payload.client_id !== "string" || !payload.client_id) {
    return { ok: false, reason: "client_id must be a non-empty string" };
  }
  if (!Array.isArray(payload.rounds) || payload.rounds.length === 0) {
    return { ok: false, reason: "rounds must be a non-empty array" };
  }
  if (payload.rounds.length > MAX_ROUNDS_PER_REQUEST) {
    return { ok: false, reason: `too many rounds (max ${MAX_ROUNDS_PER_REQUEST})` };
  }
  if (jsonBytes(payload) > MAX_PAYLOAD_BYTES) {
    return { ok: false, reason: "payload exceeds size cap" };
  }
  return { ok: true };
}

// Normalize the string keys used for grouping (trim; lowercase provider), length-capped.
export function normalizeSeatStrings(round) {
  const clip = (s) => String(s ?? "").trim().slice(0, MAX_STRING_LEN);
  return {
    ...round,
    box_holder_provider: clip(round.box_holder_provider).toLowerCase(),
    box_holder_model: clip(round.box_holder_model),
    guesser_provider: clip(round.guesser_provider).toLowerCase(),
    guesser_model: clip(round.guesser_model),
  };
}

function jsonBytes(obj) {
  // TextEncoder is available in Workers and Node 18+.
  return new TextEncoder().encode(JSON.stringify(obj)).length;
}
