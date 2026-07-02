// Banana or No Banana — retro stage client. Talks only to the local server.
"use strict";

let roundId = null;
let PLAYERS = { left: { kind: "ai", provider: "ollama", model: "" }, right: { kind: "human" } };

const el = (id) => document.getElementById(id);

// --- Settings ---
async function loadModels() {
  try {
    const resp = await fetch("/api/models");
    if (!resp.ok) return;
    const data = await resp.json();
    const select = el("model-select");
    select.innerHTML = "";
    for (const name of data.models) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      if (name === data.default) opt.selected = true;
      select.appendChild(opt);
    }
    // Same list feeds the seat editors' model fields as suggestions (Ollama only).
    const datalist = el("ollama-models");
    datalist.innerHTML = "";
    for (const name of data.models) {
      const opt = document.createElement("option");
      opt.value = name;
      datalist.appendChild(opt);
    }
  } catch (e) {
    /* Ollama not reachable; dropdown stays empty and the server default is used. */
  }
}

// --- Seat editors (two credential slots: left/Box Holder, right/Guesser) ---
function seatEditor(seat) {
  return el(`seat-${seat}`);
}

function seatField(seat, field) {
  return seatEditor(seat).querySelector(`[data-field="${field}"]`);
}

function fillSeatEditor(seat) {
  const cfg = PLAYERS[seat];
  seatField(seat, "kind").value = cfg.kind;
  seatField(seat, "provider").value = cfg.provider || "ollama";
  seatField(seat, "model").value = cfg.model || "";
  seatField(seat, "base_url").value = cfg.base_url || "";
  const keyInput = seatField(seat, "api_key");
  keyInput.value = "";
  keyInput.placeholder = cfg.has_key
    ? "•••• saved — leave blank to keep"
    : "not needed for Ollama";
  refreshSeatEditor(seat);
}

function refreshSeatEditor(seat) {
  const isAI = seatField(seat, "kind").value === "ai";
  seatEditor(seat).querySelector(".ai-fields").classList.toggle("hidden", !isAI);
}

async function saveSeat(seat) {
  const status = seatEditor(seat).querySelector(".seat-status");
  const body = {
    kind: seatField(seat, "kind").value,
    provider: seatField(seat, "provider").value,
    model: seatField(seat, "model").value.trim(),
    base_url: seatField(seat, "base_url").value.trim(),
  };
  // Blank key field = keep the saved key; only send a value the user typed.
  const key = seatField(seat, "api_key").value;
  if (key) body.api_key = key;
  status.textContent = "saving…";
  try {
    const resp = await fetch(`/api/players/${seat}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      status.textContent = err.detail || "invalid seat config";
      return;
    }
    status.textContent = "saved ✓";
    await loadPlayers();
  } catch (e) {
    status.textContent = "server unreachable";
  }
}

function describeSeat(seat) {
  if (seat.kind === "human") return "Human (you)";
  return `AI — ${seat.provider}${seat.model ? " / " + seat.model : ""}`;
}

async function loadPlayers() {
  try {
    const resp = await fetch("/api/players");
    if (!resp.ok) return;
    PLAYERS = await resp.json();
  } catch (e) {
    /* Server default (Left=AI/ollama, Right=human) stays in effect. */
  }
  el("seats-summary").textContent =
    `Left (Box Holder): ${describeSeat(PLAYERS.left)} · Right (Guesser): ${describeSeat(PLAYERS.right)}`;
  el("left-sub").textContent = PLAYERS.left.model || PLAYERS.left.provider;
  el("right-title").textContent = PLAYERS.right.kind === "human" ? "You (Guesser)" : "Guesser";
  el("right-sub").textContent = describeSeat(PLAYERS.right);
  // The per-round model dropdown only makes sense for the Ollama-backed Left seat.
  el("model-select-row").classList.toggle("hidden", PLAYERS.left.provider !== "ollama");
  fillSeatEditor("left");
  fillSeatEditor("right");
}

const STANDARD_SETTINGS = { turn_limit: 3, temperature: 0.7 };

function setBypass(on) {
  el("turn-input").disabled = !on;
  el("temp-input").disabled = !on;
  if (!on) {
    // Snap back to the published standard conditions.
    el("turn-input").value = STANDARD_SETTINGS.turn_limit;
    el("temp-input").value = STANDARD_SETTINGS.temperature;
    el("temp-value").textContent = STANDARD_SETTINGS.temperature;
  }
}

function currentSettings() {
  const bypass = el("bypass-check").checked;
  const s = bypass
    ? {
        turn_limit: Number(el("turn-input").value),
        temperature: Number(el("temp-input").value),
      }
    : { ...STANDARD_SETTINGS };
  // The dropdown holds Ollama names — only meaningful when the Left seat IS Ollama;
  // for any other provider the seat's own configured model governs.
  const model = el("model-select").value;
  if (model && PLAYERS.left.provider === "ollama") s.model = model;
  return s;
}
const dialogue = el("dialogue");
const hostLine = el("host-line");
const turnsEl = el("turns");

function hostSays(text) {
  hostLine.textContent = text;
}

function addMessage(speaker, text) {
  const div = document.createElement("div");
  div.className = "msg " + speaker;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = speaker === "box_holder" ? "Box Holder" : "You";
  div.appendChild(who);
  const body = document.createElement("span");
  body.textContent = text;
  div.appendChild(body);
  dialogue.appendChild(div);
  dialogue.scrollTop = dialogue.scrollHeight;
  return body;
}

// Stream a text/plain response body into `target`, returning the full text.
async function streamInto(response, target) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    full += chunk;
    target.textContent += chunk;
    dialogue.scrollTop = dialogue.scrollHeight;
  }
  return full;
}

function setBusy(busy) {
  el("say-btn").disabled = busy;
  el("guess-banana").disabled = busy;
  el("guess-nobanana").disabled = busy;
  el("say-input").disabled = busy;
}

async function startRound() {
  el("start-btn").classList.add("hidden");
  el("reveal").classList.add("hidden");
  dialogue.innerHTML = "";
  el("box").classList.remove("open");
  el("box").classList.add("closed");
  el("box").querySelector(".box-face").textContent = "?";
  hostSays("The Box Holder has peeked inside. Read the liar!");

  const settings = currentSettings();
  const resp = await fetch("/api/round", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!resp.ok) {
    hostSays("Those settings didn't fly — check turns and temperature.");
    el("start-btn").classList.remove("hidden");
    return;
  }
  roundId = resp.headers.get("X-Round-Id");
  const target = addMessage("box_holder", "");
  await streamInto(resp, target);

  el("settings-panel").classList.add("hidden");
  turnsEl.textContent = `Turns remaining: ${settings.turn_limit}`;

  if (PLAYERS.right.kind === "ai") {
    el("play-controls").classList.add("hidden");
    el("autoplay-controls").classList.remove("hidden");
    el("autoplay-btn").disabled = false;
  } else {
    el("autoplay-controls").classList.add("hidden");
    el("play-controls").classList.remove("hidden");
    setBusy(false);
    el("say-input").focus();
  }
}

async function autoPlay() {
  el("autoplay-btn").disabled = true;
  while (true) {
    const resp = await fetch(`/api/round/${roundId}/advance`, { method: "POST" });
    if (!resp.ok) {
      hostSays("The auto-play Guesser hit a snag.");
      break;
    }
    const data = await resp.json();
    addMessage("guesser", data.guesser_text);
    if (data.done) {
      el("autoplay-controls").classList.add("hidden");
      revealBox(data);
      break;
    }
    addMessage("box_holder", data.box_holder_text);
    turnsEl.textContent = `Turns remaining: ${data.turns_remaining}`;
    await new Promise((resolve) => setTimeout(resolve, 600));
  }
}

async function say() {
  const input = el("say-input");
  const text = input.value.trim();
  if (!text) return;
  addMessage("guesser", text);
  input.value = "";
  setBusy(true);

  const resp = await fetch(`/api/round/${roundId}/say`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (resp.status === 409) {
    hostSays("That's the clock! Time to lock in your answer.");
    setBusy(false);
    el("say-btn").disabled = true;
    el("say-input").disabled = true;
    return;
  }
  const remaining = resp.headers.get("X-Turns-Remaining");
  const target = addMessage("box_holder", "");
  await streamInto(resp, target);
  turnsEl.textContent = `Turns remaining: ${remaining}`;
  setBusy(false);
  if (Number(remaining) <= 0) {
    el("say-btn").disabled = true;
    el("say-input").disabled = true;
    hostSays("Out of turns! Lock in — banana, or no banana?");
  } else {
    el("say-input").focus();
  }
}

async function guess(answer) {
  setBusy(true);
  const resp = await fetch(`/api/round/${roundId}/guess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
  if (!resp.ok) {
    hostSays("I couldn't read that answer — try locking in again.");
    setBusy(false);
    return;
  }
  const data = await resp.json();
  revealBox(data);
}

function revealBox(data) {
  el("play-controls").classList.add("hidden");
  const box = el("box");
  box.classList.remove("closed");
  box.classList.add("open");
  box.querySelector(".box-face").textContent = data.box_contents === "BANANA" ? "🍌" : "∅";
  hostSays(data.verdict_line);
  el("reveal-verdict").textContent = data.verdict_line;
  el("reveal-winner").textContent =
    data.winner === "guesser" ? "You win! 🎉" : "The Box Holder wins!";
  el("reveal").classList.remove("hidden");
}

el("start-btn").addEventListener("click", startRound);
el("again-btn").addEventListener("click", startRound);
el("settings-toggle").addEventListener("click", () =>
  el("settings-panel").classList.toggle("hidden")
);
el("temp-input").addEventListener("input", (e) => {
  el("temp-value").textContent = e.target.value;
});
el("bypass-check").addEventListener("change", (e) => setBypass(e.target.checked));
el("autoplay-btn").addEventListener("click", autoPlay);
for (const seat of ["left", "right"]) {
  seatField(seat, "kind").addEventListener("change", () => refreshSeatEditor(seat));
  seatEditor(seat)
    .querySelector(".seat-save")
    .addEventListener("click", () => saveSeat(seat));
}
loadModels().then(loadPlayers);
el("say-btn").addEventListener("click", say);
el("say-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") say();
});
el("guess-banana").addEventListener("click", () => guess("FINAL ANSWER: BANANA"));
el("guess-nobanana").addEventListener("click", () => guess("FINAL ANSWER: NO BANANA"));
