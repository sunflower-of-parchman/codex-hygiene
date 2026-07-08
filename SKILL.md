---
name: codex-hygiene
description: Audit Codex Desktop context and tool surfaces with compact read-only telemetry. Use when usage rises unexpectedly, `codex_apps` is large, many MCPs or plugins are enabled, snapshot rows repeat, project stanzas are stale, or long-running goals may be reloading unnecessary context.
---

# Codex Hygiene

Audit first, identify the measured contributor, and make reversible changes only when the user asks. Keep required evidence and capabilities available.

## Workflow

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

## Interpret Signals Carefully

- Tool-list and snapshot rows describe context/tool assembly, not actual tool calls.
- Plugin enablement does not prove that plugin tools were attached to the model.
- Cached app inventory can be stale and does not prove current app enablement.
- Per-thread token deltas are local cumulative telemetry, not billing totals.
- Treat internal SQLite schemas and cache layouts as version-dependent.

## Guardrails

- Use `sqlite3 -readonly` for Codex databases.
- Do not dump full logs, config, app or MCP schemas, secrets, `.env` values, or complete missing-path lists.
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
- change made or prepared
- capability intentionally retained
- remaining uncertainty or approval boundary
- verification performed
