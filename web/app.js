// Banana or No Banana — retro stage client. Talks only to the local server.
"use strict";

let roundId = null;
// Two persistent colored seats; roles (holder/guesser) are assigned per round by the server.
let PLAYERS = { red: { kind: "ai", provider: "ollama", model: "" }, blue: { kind: "human" } };
let holderColor = null; // set per round from the server's assignment
let guesserColor = null;
let humanColor = null; // which color (if any) the human occupies

const el = (id) => document.getElementById(id);

// --- Settings ---
async function loadModels() {
  try {
    const resp = await fetch("/api/models");
    if (!resp.ok) return;
    const data = await resp.json();
    // The model list feeds the seat editors' model fields as suggestions (Ollama only).
    const datalist = el("ollama-models");
    datalist.innerHTML = "";
    for (const name of data.models) {
      const opt = document.createElement("option");
      opt.value = name;
      datalist.appendChild(opt);
    }
  } catch (e) {
    /* Ollama not reachable; suggestions stay empty and the server default is used. */
  }
}

// --- Seat editors (two credential slots: Red / Blue) ---
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

// Inline SVG avatars, tinted by the seat's color via CSS `currentColor`.
// The two AI robots are deliberately different builds so an AI-vs-AI match reads as two players.
const AVATAR_HUMAN = `
  <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.5"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <circle cx="24" cy="15" r="8"/>
    <path d="M8 42c2.5-9 8.5-13 16-13s13.5 4 16 13"/>
  </svg>`;

const AVATARS = {
  red: {
    human: AVATAR_HUMAN,
    ai: `
  <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.5"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <line x1="24" y1="10" x2="24" y2="6"/>
    <circle cx="24" cy="4.5" r="2" fill="currentColor" stroke="none"/>
    <rect x="10" y="10" width="28" height="25" rx="6"/>
    <circle cx="18" cy="20" r="2.6" fill="currentColor" stroke="none"/>
    <circle cx="30" cy="20" r="2.6" fill="currentColor" stroke="none"/>
    <path d="M19 27.5v3.5M24 27.5v3.5M29 27.5v3.5"/>
    <path d="M17 40v3M31 40v3" opacity="0.55"/>
  </svg>`,
  },
  blue: {
    human: AVATAR_HUMAN,
    ai: `
  <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.5"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <line x1="16" y1="10" x2="14" y2="5.5"/>
    <circle cx="13.3" cy="4" r="1.9" fill="currentColor" stroke="none"/>
    <line x1="32" y1="10" x2="34" y2="5.5"/>
    <circle cx="34.7" cy="4" r="1.9" fill="currentColor" stroke="none"/>
    <rect x="10" y="10" width="28" height="26" rx="9"/>
    <rect x="16" y="17.5" width="16" height="6.5" rx="3.25" fill="currentColor" stroke="none"/>
    <circle cx="20" cy="30" r="1.4" fill="currentColor" stroke="none"/>
    <circle cx="24" cy="30" r="1.4" fill="currentColor" stroke="none"/>
    <circle cx="28" cy="30" r="1.4" fill="currentColor" stroke="none"/>
    <path d="M5.5 20v8M42.5 20v8" opacity="0.55"/>
  </svg>`,
  },
};

async function loadPlayers() {
  try {
    const resp = await fetch("/api/players");
    if (!resp.ok) return;
    PLAYERS = await resp.json();
  } catch (e) {
    /* Server default (Red=AI/ollama, Blue=human) stays in effect. */
  }
  humanColor =
    PLAYERS.red.kind === "human" ? "red" : PLAYERS.blue.kind === "human" ? "blue" : null;
  el("seats-summary").textContent =
    `Red: ${describeSeat(PLAYERS.red)} · Blue: ${describeSeat(PLAYERS.blue)}`;
  el("red-figure").innerHTML = AVATARS.red[PLAYERS.red.kind] || AVATARS.red.ai;
  el("blue-figure").innerHTML = AVATARS.blue[PLAYERS.blue.kind] || AVATARS.blue.ai;
  el("red-sub").textContent = describeSeat(PLAYERS.red);
  el("blue-sub").textContent = describeSeat(PLAYERS.blue);
  fillSeatEditor("red");
  fillSeatEditor("blue");
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
  return bypass
    ? {
        turn_limit: Number(el("turn-input").value),
        temperature: Number(el("temp-input").value),
      }
    : { ...STANDARD_SETTINGS };
}
const dialogue = el("dialogue");
const hostLine = el("host-line");
const turnsEl = el("turns");

function hostSays(text) {
  hostLine.textContent = text;
}

// Who to name for a transcript line: "You" when the human holds that role, else the role.
function speakerLabel(speaker) {
  const roleColor = speaker === "box_holder" ? holderColor : guesserColor;
  if (humanColor && roleColor === humanColor) return "You";
  return speaker === "box_holder" ? "Box Holder" : "Guesser";
}

function addMessage(speaker, text) {
  const div = document.createElement("div");
  div.className = "msg " + speaker;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = speakerLabel(speaker);
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

function setHoldBusy(busy) {
  el("hold-btn").disabled = busy;
  el("hold-input").disabled = busy;
}

// Show which color holds vs guesses this game.
function showRoles(hc, gc) {
  holderColor = hc;
  guesserColor = gc;
  el("red-role").textContent = hc === "red" ? "Box Holder" : "Guesser";
  el("blue-role").textContent = hc === "blue" ? "Box Holder" : "Guesser";
}

async function startRound() {
  el("start-btn").classList.add("hidden");
  el("reveal").classList.add("hidden");
  el("play-controls").classList.add("hidden");
  el("autoplay-controls").classList.add("hidden");
  el("hold-controls").classList.add("hidden");
  dialogue.innerHTML = "";
  el("box").classList.remove("open");
  el("box").classList.add("closed");
  el("box").querySelector(".box-face").textContent = "?";

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
  el("settings-panel").classList.add("hidden");

  const ctype = resp.headers.get("Content-Type") || "";
  if (ctype.includes("application/json")) {
    // Human is the Box Holder: the server reveals the box to us (the holder), no AI opening.
    const data = await resp.json();
    roundId = data.round_id;
    showRoles(data.holder_color, data.guesser_color);
    startHumanHolder(data, settings.turn_limit);
    return;
  }

  // AI Box Holder: streamed opening bluff, colors carried in headers.
  roundId = resp.headers.get("X-Round-Id");
  showRoles(resp.headers.get("X-Holder-Color"), resp.headers.get("X-Guesser-Color"));
  hostSays("The Box Holder has peeked inside. Read the liar!");
  const target = addMessage("box_holder", "");
  await streamInto(resp, target);
  turnsEl.textContent = `Turns remaining: ${settings.turn_limit}`;

  if (PLAYERS[guesserColor].kind === "ai") {
    el("autoplay-controls").classList.remove("hidden");
    el("autoplay-btn").disabled = false;
  } else {
    el("play-controls").classList.remove("hidden");
    setBusy(false);
    el("say-input").focus();
  }
}

// Human-Box-Holder flow: show the secret to the holder, then take bluffs via /hold.
function startHumanHolder(data, turnLimit) {
  el("hold-secret").textContent =
    data.box_contents === "BANANA"
      ? "🍌 You peeked: there IS a banana. Convince them there isn't."
      : "∅ You peeked: the box is EMPTY. Convince them there is a banana.";
  turnsEl.textContent = `Turns remaining: ${turnLimit}`;
  hostSays("You've peeked in the box! Bluff the Guesser into calling it wrong.");
  el("hold-controls").classList.remove("hidden");
  setHoldBusy(false);
  el("hold-input").focus();
}

async function hold() {
  const input = el("hold-input");
  const text = input.value.trim();
  if (!text) return;
  addMessage("box_holder", text);
  input.value = "";
  setHoldBusy(true);

  const resp = await fetch(`/api/round/${roundId}/hold`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!resp.ok) {
    hostSays("The Guesser hit a snag — try that bluff again.");
    setHoldBusy(false);
    return;
  }
  const data = await resp.json();
  addMessage("guesser", data.guesser_text);
  if (data.done) {
    el("hold-controls").classList.add("hidden");
    revealBox(data);
    return;
  }
  turnsEl.textContent = `Turns remaining: ${data.turns_remaining}`;
  setHoldBusy(false);
  if (data.turns_remaining <= 0) {
    hostSays("Last word! One more bluff and the Guesser must lock in.");
  }
  el("hold-input").focus();
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
  el("hold-controls").classList.add("hidden");
  const box = el("box");
  box.classList.remove("closed");
  box.classList.add("open");
  box.querySelector(".box-face").textContent = data.box_contents === "BANANA" ? "🍌" : "∅";
  hostSays(data.verdict_line);
  el("reveal-verdict").textContent = data.verdict_line;
  // Frame the outcome for whichever role the human played (neutral for AI-vs-AI).
  const humanWon =
    (data.winner === "guesser" && humanColor === guesserColor) ||
    (data.winner === "box_holder" && humanColor === holderColor);
  const winEl = el("reveal-winner");
  winEl.classList.remove("red", "blue");
  if (humanColor) {
    winEl.textContent = humanWon ? "You win! 🎉" : "You lose!";
  } else {
    // Neutral AI-vs-AI: name the winning seat, tinted in its color.
    const winnerColor = data.winner === "guesser" ? guesserColor : holderColor;
    const roleName = data.winner === "guesser" ? "Guesser" : "Box Holder";
    winEl.textContent = `The ${winnerColor === "red" ? "Red" : "Blue"} ${roleName} Wins!`;
    winEl.classList.add(winnerColor);
  }
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
for (const seat of ["red", "blue"]) {
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
el("hold-btn").addEventListener("click", hold);
el("hold-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") hold();
});
el("guess-banana").addEventListener("click", () => guess("FINAL ANSWER: BANANA"));
el("guess-nobanana").addEventListener("click", () => guess("FINAL ANSWER: NO BANANA"));
