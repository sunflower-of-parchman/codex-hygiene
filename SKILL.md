---
name: codex-hygiene
description: Audit Codex Desktop context, tool surfaces, and local activity with privacy-preserving telemetry. Use for compact setup diagnostics, unexpected usage, or a retrospective over a specified period.
---

# Codex Hygiene

Measure first. Separate observed evidence, interpretation, and unknowns. Keep inspection local and read-only until the user approves a change.

## Choose The Review

- Use the compact measurement for current-context diagnostics and requests that omit a retrospective period. This is the original default.
- Use the activity review for a specified period or comparison with the preceding period.

## Compact Measurement

1. Resolve this skill's directory from the loaded `SKILL.md` path.
2. Run the bundled measurement before making claims:

```bash
"<skill-directory>/scripts/measure_codex_context.sh" 30
"<skill-directory>/scripts/measure_codex_context.sh" 5 <thread_id>
```

3. Classify the measured contributors and lead with the clearest one:
   - large `codex_apps` tool surface
   - enabled unused MCPs or plugins
   - repeated tool-list or uncached snapshot rows
   - stale `[projects."..."]` stanzas
   - long-thread context replay or active transcript rereading
   - subagent, automation, or high-reasoning fan-out
4. Return exact timestamps and compact counts with one recommended sequence.
5. Back up `config.toml` before any approved edit.
6. Remeasure the same window and thread scope after the change.

## Activity Review

Choose an explicit lookback from 1 to 90 days that matches the request:

```bash
python3 "<skill-directory>/scripts/codex_activity_review.py" --days 1
```

Use JSON for another local interface or deterministic processing:

```bash
python3 "<skill-directory>/scripts/codex_activity_review.py" --days 14 --format json
```

The review uses read-only SQLite telemetry and enriches it from rollout records inside `CODEX_HOME`. Rollout enrichment runs by default at every candidate size and reads files backward only to the prior comparison boundary. It adds task timing, relative serialized tool-output weight, verification-command counts, explicit compactions, and observed `SKILL.md` reads.

Use `--no-rollouts` only when the user explicitly wants a lightweight report without rollout-derived fields:

```bash
python3 "<skill-directory>/scripts/codex_activity_review.py" --days 30 --no-rollouts
```

Read [activity-review.md](references/activity-review.md) for field definitions, confidence, comparison windows, and rollout-enrichment boundaries.

## Interpret Signals Carefully

- Tool-list and snapshot rows describe context and tool assembly. Retained tool-call events describe observed use.
- Plugin enablement records current availability. Historical model attachment remains unknown.
- Cached app inventory can be stale. Current enablement needs fresh evidence.
- Per-thread token deltas describe local cumulative telemetry. Billing attribution remains unknown.
- Period comparisons require full source coverage. Partial and unavailable windows carry an unavailable comparison state.
- End-to-end turn and task spans include tool work. Model inference time remains unknown.
- Summed task runtime can overlap across concurrent work and exceed wall-clock time.
- Serialized rollout bytes provide a relative output-weight signal. Their relationship to model tokens remains unknown.
- Rollout-derived values carry `not measured` only when enrichment was explicitly skipped or unavailable. Zero belongs to a completed scan with no observations.
- Skill metadata selection, `SKILL.md` reads, and confirmed skill invocation are different signals.
- Treat internal SQLite schemas and cache layouts as version-dependent.

## Guardrails

- Use `sqlite3 -readonly` for Codex databases.
- Keep full logs, config, app and MCP schemas, secrets, `.env` values, and complete missing-path lists private.
- Keep prompts, responses, thread titles, thread IDs, commands, tool results, and full paths out of activity reports.
- Preserve logs, caches, config, worktrees, and project directories during diagnosis.
- Require explicit user approval or a clear prior preference before disabling surfaces.
- Preserve small helpers required by current work or local instructions unless the user asks to remove them.
- Prefer local `git` and `gh` for ordinary commits, rebases, merges, and pushes when PR, issue, review, CI artifact, or remote API tools are unnecessary.

## App Controls

Use current documented per-app controls for selected connectors:

```toml
[apps."connector-id"]
enabled = false
```

Use the global switch when the user wants all Apps/connectors unavailable or fresh measurement shows an unchanged surface after the per-app setting:

```toml
[features]
apps = false
```

Verify either change against fresh-thread `list_all_tools` rows. See the [remediation reference](references/remediation.md) for backups, MCP controls, project-local configuration, and observed fallback behavior.

## Long-Running Goals

Start long-running goal analysis by separating:

- runtime-managed resume, compaction, system, or tool context that may already be attached
- agent-chosen rereading of old rollouts, transcripts, broad plugin docs, or unrelated evidence

A narrowing prompt limits agent-chosen reads. A fresh tiny measurement thread helps estimate runtime-managed context. Preserve the active goal unless the user approves a fork, archive, reset, or replacement.

Read the [long-thread reference](references/long-thread-replay.md) when the goal must stay alive or final analysis quality must remain high.

## Verification

Create a fresh measurement thread when useful:

```text
Please reply exactly: OK
```

Then rerun the five-minute measurement with that thread id. Good signs include:

- no `codex_apps` rows when Apps are globally disabled
- a `list_all_tools` MCP set that matches the intended availability
- fewer or explainable snapshot rows
- lower per-thread cumulative deltas, or a remaining floor attributable to base, system, tool, or thread context

## Final Report

Return:

- what the review examined across retained local Codex activity and the current Codex profile
- comprehensive model, token-change, reasoning-effort, tool, skill, plugin, MCP, task, and context-management statistics
- plugin weight across matched calls, runtime, serialized output, skill reads, and inventoried tools
- observed evidence, interpretation, and remaining unknowns as separate statements
- source coverage and any suppressed comparisons
- exact per-plugin context and billing-token weight as unknown unless directly measured
- end with the exact heading `Optional: Codex optimization` followed by the concise generated prompt in a code block
