# Decisions: Banana or No Banana — AI-Guesser turn-status note (the autoguess fix)
Spec: Planning/specs/banana_spec.md ("Configurable multi-provider player seats", amended)
Date: 2026-07-01

- **Problem (user-reported):** with two local models seated, Auto-Play "autoguesses" — the
  AI Guesser locks in `FINAL ANSWER:` on turn 1 without asking a single question, across
  different local models. Confirmed live: qwen3:8b, given only the system prompt and the
  Box Holder's opening, replies `FINAL ANSWER: BANANA` immediately.
- **Root cause:** the Guesser is never told the turn mechanic exists. The locked prompt
  says "make them talk" and "across a turn limit," but the only concrete, actionable
  format the model ever sees is the lock-in line — so that's what it produces. Not a
  model quirk; a missing game-state channel.
- **Fix: server-side host note, not a prompt edit.** `_messages_for_guesser` appends a
  `[Bot B@rker, host]` note to the model-visible messages while turns remain: "you have
  N of your M questioning turns left; this message is a turn you can spend; lock in only
  if already confident." A/B-tested live against qwen3:8b before implementing: without
  the note → instant `FINAL ANSWER`; with it → "What makes you so sure it's empty? You
  just looked — but you didn't say what you saw." Post-fix, a 4-round live batch used all
  3 turns in all 4 rounds with genuine cross-examination (guesser won 2/4).
- **Why not edit `prompts/guesser.md`:** the prompts are locked v1, and turn state is
  *dynamic* per-turn game state, not static instruction — it belongs with the engine,
  same as the existing `_FORCE_ANSWER` injection at 0 turns (which this mirrors and
  replaces once turns run out).
- **The note is model-visible only** — never appended to `r.transcript`, so logs and the
  future submission format stay pure dialogue. Host-to-contestant talk is on-air by the
  game's "no private channel" principle: the host is a public actor, and the note gives
  the Guesser no information about the box.
- **Early lock-in stays legal** — the note frames it as allowed-when-confident rather
  than forbidden; the goal was to make engagement the default, not to force all turns.
