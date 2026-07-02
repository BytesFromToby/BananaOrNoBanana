// Server-side rescoring — the anti-tamper core. winner/correct are re-derived from the
// round's own final_answer x box_contents (never trusted from the client), and
// standard_settings is re-derived from turn_limit x temperature. Mirrors server/game.py
// (score) and server/config.py (is_standard) exactly.

const BANANA = "BANANA";
const EMPTY = "EMPTY";
const NO_BANANA = "NO_BANANA";

const STANDARD_TURN_LIMIT = 3;
const STANDARD_TEMPERATURE = 0.7;

export function recomputeWinner(round) {
  const answer = round.final_answer;
  const box = round.box_contents;
  const correct =
    (answer === BANANA && box === BANANA) || (answer === NO_BANANA && box === EMPTY);
  return { correct, winner: correct ? "guesser" : "box_holder" };
}

export function recomputeStandard(round) {
  return (
    round.turn_limit === STANDARD_TURN_LIMIT &&
    Math.abs((round.temperature ?? -1) - STANDARD_TEMPERATURE) < 1e-9
  );
}

// True iff the client's submitted winner/correct match what the round's own fields imply.
// A contradiction means a fabricated tally → the round is rejected upstream.
export function tallyIsConsistent(round) {
  const { correct, winner } = recomputeWinner(round);
  return round.winner === winner && Boolean(round.correct) === correct;
}
