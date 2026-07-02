// D1-backed storage, behind a small interface the tests fake. All SQL lives here so the
// router (index.js) stays pure request→logic→response and is testable with an in-memory store.

export class D1Store {
  constructor(db) {
    this.db = db;
  }

  async getClient(clientId) {
    return await this.db
      .prepare("SELECT client_id, tier_override FROM clients WHERE client_id = ?")
      .bind(clientId)
      .first();
  }

  async ensureClient(clientId, nowISO) {
    await this.db
      .prepare("INSERT OR IGNORE INTO clients (client_id, first_seen) VALUES (?, ?)")
      .bind(clientId, nowISO)
      .run();
  }

  async hasRound(roundId) {
    const row = await this.db
      .prepare("SELECT 1 FROM rounds WHERE round_id = ?")
      .bind(roundId)
      .first();
    return Boolean(row);
  }

  async clientDailyCount(clientId, dayPrefix) {
    const row = await this.db
      .prepare("SELECT COUNT(*) AS n FROM rounds WHERE client_id = ? AND received_at LIKE ?")
      .bind(clientId, `${dayPrefix}%`)
      .first();
    return row ? row.n : 0;
  }

  async insertRound(r) {
    await this.db
      .prepare(
        `INSERT INTO rounds (
           round_id, client_id, tier, received_at, schema_version, client_version,
           ts, mode, box_holder_provider, box_holder_model, guesser_provider, guesser_model,
           box_contents, turn_limit, temperature, standard_settings, guesser_turns_used,
           final_answer, correct, winner, forced_default, transcript
         ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`
      )
      .bind(
        r.round_id, r.client_id, r.tier, r.received_at, r.schema_version, r.client_version ?? null,
        r.ts ?? null, r.mode ?? null, r.box_holder_provider, r.box_holder_model,
        r.guesser_provider, r.guesser_model, r.box_contents, r.turn_limit, r.temperature,
        r.standard_settings ? 1 : 0, r.guesser_turns_used ?? null, r.final_answer,
        r.correct ? 1 : 0, r.winner, r.forced_default ? 1 : 0, JSON.stringify(r.transcript)
      )
      .run();
  }

  async queryRounds({ tier }) {
    let sql =
      `SELECT client_id, box_holder_provider, box_holder_model, guesser_provider,
              guesser_model, winner, forced_default, standard_settings
       FROM rounds`;
    const binds = [];
    if (tier === "verified") {
      sql += " WHERE tier = ?";
      binds.push("verified");
    }
    const { results } = await this.db.prepare(sql).bind(...binds).all();
    // D1 stores booleans as 0/1 — restore to the shape aggregate() expects.
    return (results || []).map((r) => ({
      ...r,
      forced_default: Boolean(r.forced_default),
      standard_settings: Boolean(r.standard_settings),
    }));
  }
}
