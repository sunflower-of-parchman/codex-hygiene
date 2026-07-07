---
name: codex-hygiene
description: Audit and tune Codex Desktop context/tool surfaces so apps, MCPs, skills, project stanzas, subagents, and long-running goals stay intentionally scoped. Use when Codex usage increases unexpectedly, `codex_apps` has a large tool count, MCP tool snapshots appear repeatedly uncached, old project paths accumulate, multi-day or multi-week `/goal` threads are repeatedly resumed, or the user wants a safe hygiene plan for Codex config and context surfaces.
---

# Codex Hygiene

Use this skill to audit and tune Codex context overhead safely. Start read-only, measure first, then make reversible config edits only when the user asks.

Core rule: make context, tool availability, and long-running thread continuation intentional; do not make the agent evidence-avoidant or degrade the work product.

## Quick Start

Run the compact read-only measurement:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/codex-hygiene"
"$SKILL_DIR/scripts/measure_codex_context.sh"
```

Use a shorter or longer window:

```bash
"$SKILL_DIR/scripts/measure_codex_context.sh" 5
"$SKILL_DIR/scripts/measure_codex_context.sh" 30
```

Filter verification to a fresh thread when old active threads may pollute the recent window:

```bash
"$SKILL_DIR/scripts/measure_codex_context.sh" 5 <thread_id>
```

## Workflow

1. Measure current state with the script before making claims.
2. Identify the primary contributor:
   - `codex_apps` large tool count
   - enabled unused MCPs or plugins
   - repeated MCP tool snapshot rows without cache reuse
   - stale `[projects."..."]` stanzas
   - long-lived thread history replay
   - subagent, automation, or high-reasoning background fan-out
3. Keep output small: exact timestamps, counts, and one recommended fix sequence.
4. Back up `~/.codex/config.toml` before any edit.
5. Apply the smallest reversible config change that targets the measured contributor.
6. When useful, start a fresh tiny measurement thread and remeasure the same counters without replacing active work.

## Guardrails

- Use `sqlite3 -readonly` for logs.
- Do not dump full logs, full config, app tool schemas, MCP schemas, secrets, or `.env` values.
- Do not delete logs, caches, config, worktrees, or project directories as a first response.
- Do not disable broad surfaces without either explicit user approval or a clear prior user preference.
- Preserve tiny local helper MCPs unless the user specifically wants them removed. Common examples are `node_repl` and `openai-api-key-local-confirmation`.
- Prefer local `git` and `gh` for normal commits, rebases, merges, and pushes. The GitHub MCP/app surface is mainly for PRs, issues, reviews, CI artifacts, and remote API work.

## Known Tuning Pattern

If `codex_apps` remains large after per-app disables, the per-app config may be parsed but not applied to Desktop tool listing. One observed setup stayed around `166-167` tools until the global Apps feature was disabled. In that case, the effective global switch is:

```toml
[features]
apps = false
```

Use repo-local MCP config for tools that are only needed in specific projects, such as database or deployment services. See `references/remediation.md` for edit patterns.

## Long-Thread Replay Pattern

If a multi-day or multi-week `/goal` thread is repeatedly resumed and shows enormous input token counts, treat it as context replay unless proven otherwise. Fix by continuing from current repo evidence, ledgers, generated artifacts, and status files instead of replaying full transcript history. Disable unrelated plugins/skills, constrain subagents, and reserve high reasoning for final analysis quality rather than every resume.

Read `references/long-thread-replay.md` when the user needs to preserve a goal/thread, avoid losing completion state, or keep quality high while reducing context replay.

## Verification

After tuning, use a fresh tiny measurement thread:

```text
Please reply exactly: OK
```

Then rerun the measurement script. Good signs:

```bash
"$SKILL_DIR/scripts/measure_codex_context.sh" 5 <fresh_thread_id>
```

- No `server_name=codex_apps` rows when Apps are globally disabled.
- Only intentionally enabled MCPs remain in `list_all_tools`.
- Tool snapshot rows are few and explainable.
- Token usage drops or the remaining floor is attributable to base/system/thread context.

## Final Report Shape

Return:

- Observed contributor to elevated usage.
- What changed or what prompt/config was prepared.
- What was intentionally kept for quality.
- What remains risky or user-approved only.
- Verification commands or checks run.
