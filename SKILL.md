---
name: codex-hygiene
description: Audit Codex Desktop context, tool surfaces, and work patterns with privacy-preserving local telemetry. Use when usage rises unexpectedly; models, reasoning levels, tools, skills, plugins, compactions, subagents, or automations need attribution; or someone wants a retrospective across a specified period.
---

# Codex Hygiene

Audit first, distinguish observed evidence from interpretation, and make reversible changes only when the user asks. Keep required evidence and capabilities available.

## Choose The Review

- For a current usage or tool-surface question, run the compact measurement.
- For reflection across a specified period or comparison with the preceding period, run the activity review.

## Compact Measurement

1. Resolve this skill's directory from the loaded `SKILL.md` path.
2. Run the bundled measurement before making claims:

```bash
"<skill-directory>/scripts/measure_codex_context.sh" 30
"<skill-directory>/scripts/measure_codex_context.sh" 5 <thread_id>
```

3. Classify the strongest measured contributor:
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

The default report uses read-only SQLite telemetry and automatically enriches from rollout files only when their combined size is below the safety guard. Force the deeper local scan when exact task timing, relative serialized tool-output weight, verification-command counts, and observed `SKILL.md` reads are worth the additional disk work:

```bash
python3 "<skill-directory>/scripts/codex_activity_review.py" --days 30 --deep
```

Read [activity-review.md](references/activity-review.md) when interpreting fields, confidence, comparison windows, or the deep-scan boundary.

## Interpret Signals Carefully

- Tool-list and snapshot rows describe context/tool assembly, not actual tool calls.
- Plugin enablement does not prove that plugin tools were attached to the model.
- Cached app inventory can be stale and does not prove current app enablement.
- Per-thread token deltas are local cumulative telemetry, not billing totals.
- Check source coverage before comparing periods; partial or unavailable log windows are not valid zero baselines.
- End-to-end turn and task spans include tool work and are not pure model inference time.
- Summed task runtime can overlap across concurrent work and exceed wall-clock time.
- Serialized rollout bytes are a relative output-weight signal, not model tokens.
- Treat rollout-derived values as not measured when enrichment does not run; reserve zero for a completed scan with no observations.
- Skill metadata selection, `SKILL.md` reads, and confirmed skill invocation are different signals.
- Treat internal SQLite schemas and cache layouts as version-dependent.

## Guardrails

- Use `sqlite3 -readonly` for Codex databases.
- Do not dump full logs, config, app or MCP schemas, secrets, `.env` values, or complete missing-path lists.
- Do not print prompts, responses, thread titles, thread IDs, commands, tool results, or full paths in an activity report.
- Do not delete logs, caches, config, worktrees, or project directories as a first response.
- Do not disable surfaces without explicit user approval or a clear prior preference.
- Preserve small required helpers unless the user asks to remove them. Common examples are `node_repl` and `openai-api-key-local-confirmation`.
- Prefer local `git` and `gh` for ordinary commits, rebases, merges, and pushes when PR, issue, review, CI artifact, or remote API tools are unnecessary.

## App Controls

Use current documented per-app controls when only selected connectors should be disabled:

```toml
[apps."connector-id"]
enabled = false
```

Use the global switch only when the user wants all Apps/connectors unavailable or fresh measurement shows that per-app controls do not shrink the surface on that local build:

```toml
[features]
apps = false
```

Verify either change against fresh-thread `list_all_tools` rows. See the [remediation reference](references/remediation.md) for backups, MCP controls, project-local configuration, and observed fallback behavior.

## Long-Running Goals

Do not treat a valuable long-running goal as the problem by default. Separate:

- runtime-managed resume, compaction, system, or tool context that may already be attached
- agent-chosen rereading of old rollouts, transcripts, broad plugin docs, or unrelated evidence

A narrowing prompt can stop unnecessary agent-chosen reads; it cannot guarantee that runtime-managed context was removed. Compare with a fresh tiny measurement thread when attribution matters, while preserving the active goal unless the user approves a fork, archive, reset, or replacement.

Read the [long-thread reference](references/long-thread-replay.md) when the goal must stay alive or final analysis quality must remain high.

## Verification

Create a fresh measurement thread when useful:

```text
Please reply exactly: OK
```

Then rerun the five-minute measurement with that thread id. Good signs include:

- no `codex_apps` rows when Apps are globally disabled
- only intentionally available MCPs in `list_all_tools`
- fewer or explainable snapshot rows
- lower per-thread cumulative deltas, or a remaining floor attributable to base, system, tool, or thread context

## Final Report

Return:

- measured contributor and confidence
- observed evidence, interpretation, and remaining unknowns as separate statements
- source coverage and any suppressed comparisons
- change made or prepared
- capability intentionally retained
- remaining uncertainty or approval boundary
- verification performed
