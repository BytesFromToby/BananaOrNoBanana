# BananaOrNoBanana — Handoff (for a terminal-mode Plumbline run)

**Written:** 2026-06-30, from a non-interactive Claude Code session.
**Why:** we started an autonomous Plumbline `homeowner` build here and the plumbline subagents misbehaved (§4). Reopen this project in an **interactive terminal `claude` session** and re-run — the goal is to see whether the same flakiness reproduces, i.e. whether it's the async/non-interactive harness or Plumbline itself.

---

## 1. The project

A local, single-player **retro game-show deception** web app. An AI **Box Holder** (Ollama `qwen3:8b`) looks in a box that holds a banana on a 50/50 coin flip, then lies to make the human **Guesser** call it wrong across 3 turns. A **FastAPI** referee flips the coin, proxies Ollama with thinking-mode stripped, streams replies, scores the Guesser's `FINAL ANSWER` mechanically against the box, and logs each round to `logs/rounds.jsonl`. Vanilla HTML/CSS/JS retro (80s *Price is Right*) front end; scripted host **"Bot B@rker"**. Adversarial/zero-sum; the metric is deviation from a 50% coin-flip baseline.

**Artifacts already on disk (source of truth — do not rebuild):**
- `SPEC.md` — the v1 MVP spec. **Scope source of truth.**
- `PROPOSAL.md` — full design/context.
- `prompts/box_holder.md`, `prompts/guesser.md` — **locked** player system prompts.
- `output/homeowner/HomeownerLog_2026-06-30_19-25.md` — this run's log (halted at Phase 1).

Nothing is built yet.

## 2. Plumbline install (already done — a terminal session inherits it)

v1.0 is installed as the user-scope plugin `plumbline@plumbline` (enabled). We had to add the missing `.claude-plugin/marketplace.json` to `H:\my_skills\plumbline` to make it installable, then `claude plugin marketplace add` + `install`. Stale pre-v1.0 loose agents/skills were retired to `~/.claude/agents-retired-pre-plumbline/` and `~/.claude/skills-retired-pre-plumbline/`. Plugins load at session start, so a fresh terminal `claude` has the full `plumbline:` roster.

## 3. What we were doing

Ran `/homeowner` (autonomous build orchestrator). Pipeline: **scaffold → architect → [spec gate] → foreman → builder → inspector → commit**. We reached Phase 1 (scaffold) and halted. The brief passed to homeowner:

> Take BananaOrNoBanana from its existing spec to verified code, autonomously. Working directory: H:\BananaOrNoBanana. It already has a complete v1 MVP spec at SPEC.md (source of truth for scope), a design proposal at PROPOSAL.md for context, and locked player prompts at prompts/box_holder.md and prompts/guesser.md. Summary: a local single-player retro game-show deception web app — an AI Box Holder (Ollama, qwen3:8b) looks in a box that holds a banana on a 50/50 coin flip, then lies to make the human Guesser call it wrong across 3 turns; a FastAPI referee flips the coin, proxies Ollama with thinking-mode stripped, streams replies, scores the Guesser's FINAL ANSWER mechanically against the box, and logs each round to logs/rounds.jsonl; vanilla HTML/CSS/JS retro (80s Price is Right) front end; scripted host "Bot B@rker".

## 4. What went wrong (the thing to reproduce)

The `plumbline:scaffold` subagent, in this async/non-interactive environment:

1. **First launch: 0 tool uses.** It returned after one line ("I'll start by reading the scaffold skill…") having done nothing. Had to be resumed with an explicit "actually execute now."
2. **Bash-tool reads failed** on the plugin path — `cat`/`grep`/`find` returned empty for `.../skills/scaffold/SKILL.md`; it worked around with `powershell -Command "Get-Content ..."`.
3. It then wrote a **nonstandard skeleton** that does not match the scaffold skill (§5).

## 5. On-disk state now vs. the correct scaffold

Verified against `skills/scaffold/SKILL.md` (v1.0) and `contract-template.md`.

| Item | Scaffold skill wants | What the agent produced |
|---|---|---|
| `git init` | yes | ✅ done |
| First commit | `Scaffold: project skeleton + contract (Plumbline v1.0)` | ❌ **no commit** |
| `.gitignore` | generic | ✅ ok |
| `CLAUDE.md` | **from `contract-template.md`** (Plumbline v1.0 stamp, `## Stack` / `## Commands` `[pending — architect]`, `## History Mode: git`, Where-things-live table, Change rules, Skills) | ❌ **hand-rolled, not from template** — missing History/Change-rules/Where-things-live/Skills/version stamp; its "Conventions" list names the wrong folders |
| `Planning/specs/` | yes | ✅ |
| `Planning/reference/` | yes | ❌ missing |
| `Planning/blueprints/` | yes (foreman writes here) | ❌ missing |
| `docs/decisions/` | yes (architect writes here) | ❌ missing |
| `output/inspect/`, `output/deviations/`, `output/surveys/`, `output/walkthrough/` | yes | ❌ missing |
| `output/homeowner/` | yes | ✅ |
| `Planning/proposals/`, `Planning/tasks/` | **not in the skill** | ❌ **hallucinated** |
| `.gitkeep` in each empty folder (git mode) | yes | ❌ none |

Net: the agent invented `Planning/{proposals,tasks}`, omitted `Planning/{reference,blueprints}`, `docs/decisions/`, four `output/` subfolders and all `.gitkeep`s, wrote a non-template `CLAUDE.md`, and never committed.

## 6. To continue / test in terminal mode

⚠️ **Reset to greenfield first.** Because `CLAUDE.md` and `Planning/` now exist, a fresh `/homeowner` will classify this as an *existing* project and **skip scaffold entirely** (Phase 1 greenfield check = "neither `Planning/` nor `CLAUDE.md` present"). To re-test scaffold, remove the flaky output first (keeps the design docs + prompts):

```powershell
cd H:\BananaOrNoBanana
Remove-Item -Recurse -Force .git, Planning, CLAUDE.md, .gitignore
# keep: PROPOSAL.md, SPEC.md, prompts\, and (optionally) this HANDOFF.md + output\homeowner\ log
```

Then either:
- **`/homeowner`** with the brief in §3 (full autonomous run), or
- **`plumbline:scaffold`** by hand first, to watch that one agent in isolation and compare its output to the "correct" column in §5.

**The diagnostic question:**
- Scaffolds correctly in terminal (full skeleton + `.gitkeep`s + template `CLAUDE.md` + first commit) → the flakiness was *this async/non-interactive harness*, not Plumbline.
- Reproduces (no-op launch, Bash-read failures, hallucinated skeleton) → it's Plumbline or the model — worth fixing in the framework (scaffold's file-reads, or agent-launch/first-turn behavior).

## 7. Reconciliation note (for architect, Phase 2)

`SPEC.md` is hand-written at the repo root, **not** in Plumbline's `Planning/specs/[feature]_spec.md`. Homeowner's Phase 2 spawns `architect` to write `Planning/specs/banana_spec.md` from the brief. Point architect **explicitly at `SPEC.md` as the source of truth** so it *adopts/converts* our carefully-built spec rather than re-deriving a thinner one from the one-paragraph brief. Suggested feature slug: `banana`.
