-- Banana Arena D1 schema. Apply with:
--   wrangler d1 execute banana-arena --file=schema.sql --remote

-- One row per accepted round. round_id is unique → resubmissions dedupe.
-- Round fields are flattened for aggregation; the full transcript is kept as JSON
-- (audit trail + future fine-tuning corpus). winner/correct/standard_settings are the
-- server-recomputed canonical values, not whatever the client submitted.
CREATE TABLE IF NOT EXISTS rounds (
  round_id            TEXT PRIMARY KEY,
  client_id           TEXT NOT NULL,
  tier                TEXT NOT NULL,              -- 'community' | 'verified'
  received_at         TEXT NOT NULL,             -- ISO-8601 UTC
  schema_version      INTEGER NOT NULL,
  client_version      TEXT,
  ts                  TEXT,
  mode                TEXT,
  box_holder_provider TEXT,
  box_holder_model    TEXT,
  guesser_provider    TEXT,
  guesser_model       TEXT,
  box_contents        TEXT,
  turn_limit          INTEGER,
  temperature         REAL,
  standard_settings   INTEGER NOT NULL,          -- 0/1, server-recomputed
  guesser_turns_used  INTEGER,
  final_answer        TEXT,
  correct             INTEGER,                   -- 0/1, server-recomputed
  winner              TEXT,                      -- server-recomputed
  forced_default      INTEGER NOT NULL,          -- 0/1
  transcript          TEXT                       -- JSON array
);

CREATE INDEX IF NOT EXISTS idx_rounds_matchup
  ON rounds (box_holder_provider, box_holder_model, guesser_provider, guesser_model);
CREATE INDEX IF NOT EXISTS idx_rounds_client_day ON rounds (client_id, received_at);
CREATE INDEX IF NOT EXISTS idx_rounds_tier ON rounds (tier);

-- Clients: anonymous UUIDs. Lets the maintainer promote a client to verified or ban
-- one without touching round rows. No PII by construction.
CREATE TABLE IF NOT EXISTS clients (
  client_id     TEXT PRIMARY KEY,
  first_seen    TEXT NOT NULL,
  tier_override TEXT,     -- NULL | 'verified' | 'banned'
  note          TEXT
);
