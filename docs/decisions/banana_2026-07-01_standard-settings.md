# Decisions: Banana or No Banana — Standard leaderboard conditions (3 turns, temp 0.7)
Spec: Planning/specs/banana_spec.md (Match settings, amended); Planning/specs/arena_spec.md (wire format)
Date: 2026-07-01

- **Problem (user-raised):** temperature "feels like it would obscure natural results."
  Analysis agreed with half of it: there is no "natural" temperature (temp 0 is a
  degenerate sampling mode nobody deploys, and it collapses N rounds into near-identical
  replays — worse measurement, not purer), but temperature IS a confound when it varies
  silently: a hot Box Holder and a cold one are different contestants, and neither
  temperature nor any eligibility marker was being logged.
- **Decision (user):** pin standard leaderboard conditions — **turn_limit 3, temperature
  0.7** — and lock the controls behind a "Bypass leaderboard settings" toggle. Bypassed
  rounds play and log normally but are flagged and never count toward any leaderboard.
  Pin and record the dial rather than remove it: "deception vs temperature" stays a
  studyable variable later.
- **Default temperature changed 0.9 → 0.7** (config.json + DEFAULTS) so the defaults ARE
  the standard conditions. The original 0.9 ("bluff room") predates the leaderboard being
  real; 0.7 matches common provider defaults.
- **Enforcement lives in aggregation, not round creation** — the server accepts any valid
  settings (people's own experiments are welcome); `standard_settings` is computed at log
  time (`is_standard()` in server/config.py) and `server/stats.py` excludes non-standard
  rounds from the metric, reporting the excluded count. The arena ingest will *recompute*
  the flag server-side from the submitted turn_limit/temperature rather than trust it.
- **Legacy log lines** (predating the field) count as non-standard — honest, and they're
  pre-autoguess-fix junk data anyway.
- One temperature still governs both seats (per-seat temperature deliberately not added —
  no demonstrated need; would double the condition matrix the leaderboard must control).
