# Decisions: Banana or No Banana — Seat credential editors in the settings panel
Spec: Planning/specs/banana_spec.md ("Configurable multi-provider player seats", amended)
Date: 2026-07-01

- **Superseded the same-day ".env-only, never browser-editable" decision** — user request
  ("we need spots for 2 LLM credential entries, for all types of models"), and it aligns with
  the community-arena end state (SPEC.md §12 item 10): people who download the app won't edit
  `.env` by hand. The original rationale (don't expose keys client-side) is preserved by making
  keys **write-only** across the browser boundary: `PUT /api/players/{seat}` accepts a key,
  `GET /api/players` returns only `has_key: bool`. Accepting a key *from* the browser is fine
  here because the server is localhost-only, single user — the threat the original decision
  guarded against was keys flowing *to* the browser, which still never happens.
- **Persistence = write back to `.env` in place** (targeted line replace/append, everything
  else preserved byte-for-byte) rather than a second config file — one source of truth for seat
  config, keeps `.env.example` as the documented template, and delivers roadmap item 11
  (settings persistence) for seats without a new mechanism. `python-dotenv` already loads it
  at startup.
- **Omitted `api_key` keeps the saved key; empty string clears it** — lets the UI show a
  password field with a "saved" placeholder and never round-trip the secret just to re-save
  other fields.
- **Seat updates replace the `PLAYERS[seat]` object instead of mutating it** — a round already
  in flight holds a reference to the old config and finishes under it; the new config governs
  the next round. No mid-round provider switcheroo.
- **Fixed in passing (required for non-Ollama left seats to work at all):** `create_round`
  used to stamp `config.json`'s `box_holder_model` (an Ollama name) over the left seat's own
  configured model whenever no per-round override was given, and the frontend sent the Ollama
  dropdown's model even for non-Ollama seats. Precedence is now per-round override > seat
  model > config default, and the dropdown only submits when the left seat is Ollama.
- **Human left seat is rejected at round creation (422)** with a clear message — the engine
  can't drive a human Box Holder yet (roadmap item 6); the config layer stays generic so the
  seat editor doesn't need special-casing later.
