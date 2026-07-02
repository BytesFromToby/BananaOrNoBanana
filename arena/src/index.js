// Banana Arena Worker — ingest (POST /api/submit) + public leaderboard (GET /api/leaderboard).
// The Worker default export wires a D1-backed store into handleRequest; tests call
// handleRequest directly with an in-memory fake store, so no live Cloudflare is needed.

import { validatePayload, validateRound, normalizeSeatStrings } from "./lib/validate.js";
import { recomputeWinner, recomputeStandard, tallyIsConsistent } from "./lib/score.js";
import { aggregate } from "./lib/aggregate.js";
import { D1Store } from "./storage.js";

const DEFAULT_DAILY_CAP = 500;
const DEFAULT_MIN_ROUNDS = 10;

export async function handleRequest(request, env, store, now = new Date()) {
  const url = new URL(request.url);

  if (request.method === "POST" && url.pathname === "/api/submit") {
    return await handleSubmit(request, env, store, now);
  }
  if (request.method === "GET" && url.pathname === "/api/leaderboard") {
    return await handleLeaderboard(url, env, store);
  }
  return json({ error: "not found" }, 404);
}

async function handleSubmit(request, env, store, now) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return json({ error: "invalid JSON" }, 400);
  }

  const pv = validatePayload(payload);
  if (!pv.ok) return json({ error: pv.reason }, 400);

  const clientId = payload.client_id;
  const client = await store.getClient(clientId);
  if (client && client.tier_override === "banned") {
    return json({ error: "client is banned" }, 403);
  }

  // verified iff the request carries the maintainer key (or the client is promoted).
  const key = request.headers.get("X-Maintainer-Key");
  const keyOk = Boolean(env.MAINTAINER_KEY) && key === env.MAINTAINER_KEY;
  const tier = keyOk || (client && client.tier_override === "verified") ? "verified" : "community";

  const nowISO = now.toISOString();
  const dayPrefix = nowISO.slice(0, 10);
  const cap = intVar(env.DAILY_ROUND_CAP, DEFAULT_DAILY_CAP);
  const already = await store.clientDailyCount(clientId, dayPrefix);

  await store.ensureClient(clientId, nowISO);

  const accepted_ids = [];
  const duplicates = [];
  const rejected = [];
  let stored = 0;

  for (const raw of payload.rounds) {
    const rv = validateRound(raw);
    if (!rv.ok) { rejected.push({ round_id: raw && raw.round_id, reason: rv.reason }); continue; }
    if (!tallyIsConsistent(raw)) {
      rejected.push({ round_id: raw.round_id, reason: "winner/correct inconsistent with final_answer x box_contents" });
      continue;
    }
    if (already + stored >= cap) {
      rejected.push({ round_id: raw.round_id, reason: "daily round cap reached for this client" });
      continue;
    }
    if (await store.hasRound(raw.round_id)) { duplicates.push(raw.round_id); continue; }

    const norm = normalizeSeatStrings(raw);
    const { correct, winner } = recomputeWinner(norm);   // canonical, not client-trusted
    const record = {
      ...norm,
      client_id: clientId,
      tier,
      received_at: nowISO,
      schema_version: payload.schema_version,
      client_version: payload.client_version,
      correct,
      winner,
      standard_settings: recomputeStandard(norm),
    };
    await store.insertRound(record);
    accepted_ids.push(raw.round_id);
    stored += 1;
  }

  return json({ accepted: accepted_ids.length, accepted_ids, duplicates, rejected });
}

async function handleLeaderboard(url, env, store) {
  const tierParam = url.searchParams.get("tier") === "verified" ? "verified" : "all";
  const rounds = await store.queryRounds({ tier: tierParam });
  const minRounds = intVar(env.MIN_ROUNDS, DEFAULT_MIN_ROUNDS);
  const rows = aggregate(rounds).filter((r) => r.rounds >= minRounds);
  return json({ tier: tierParam, min_rounds: minRounds, rows }, 200, {
    "Cache-Control": "public, max-age=300",
  });
}

function intVar(v, fallback) {
  const n = parseInt(v, 10);
  return Number.isFinite(n) ? n : fallback;
}

function json(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
}

// Cloudflare entrypoint. Static assets (the leaderboard page) are served by the [assets]
// binding automatically; this handler owns the /api/* routes.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) {
      return handleRequest(request, env, new D1Store(env.DB));
    }
    // Non-API path with assets configured: let the platform serve public/.
    if (env.ASSETS) return env.ASSETS.fetch(request);
    return handleRequest(request, env, new D1Store(env.DB));
  },
};
