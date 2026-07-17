# Long-Thread Context Hygiene

Use this when a multi-day or multi-week Codex goal should stay active and local telemetry shows unexpectedly high per-thread cumulative token growth.

Start by separating runtime-managed context from agent-chosen rereading. Preserve the goal during diagnosis.

## Context Sources

### Runtime-managed context

Codex may attach conversation history, compacted summaries, system instructions, skill metadata, or tool definitions while starting or resuming a thread. A steering prompt cannot remove context already attached by the runtime.

Use a fresh tiny thread as a comparison, inspect current supported compaction or thread controls, and preserve the active goal unless the user approves a fork, archive, reset, or replacement.

### Agent-chosen rereading

The agent or its subagents may actively reopen old rollout files, transcript exports, broad plugin documentation, unrelated skill instructions, or large generated logs. A narrowing prompt can reduce this work by directing the agent to current repo state and bounded evidence.

Remeasure the same thread and compare it with a fresh-thread baseline. Runtime-managed context may still be present.

## Evidence Sources

Check current local evidence before recommending thread changes:

- `$CODEX_HOME/config.toml` for models, reasoning, plugins, features, agents, and tools
- `$CODEX_HOME/state_*.sqlite` for thread metadata and token records when available
- `$CODEX_HOME/goals_*.sqlite` for goal state when available
- `$CODEX_HOME/logs_*.sqlite` for recent token and tool-list telemetry
- current repo status, ledgers, dashboards, lock files, generated artifacts, and process checks

Use `sqlite3 -readonly` for databases. Treat internal schemas and filenames as version-dependent, and avoid full log or transcript dumps.

## Classify The Signal

| Signal | Candidate contributor | Next check |
| --- | --- | --- |
| Large per-thread cumulative deltas after resume | Runtime context or active rereading | Compare with a fresh tiny thread and inspect agent reads |
| Large rollout file plus repeated explicit rollout reads | Agent-chosen transcript replay | Continue from current ledgers and generated evidence |
| Many unrelated available plugins or tools | Broad capability surface | Compare model-visible tool rows and require approval for any disable action |
| High `agents.max_threads` or many subagents | Parallel context multiplication | Count workers and bound assignments |
| Scheduled high-reasoning automation | Background usage | Inspect current runs and narrow or pause with approval |
| Large source media or project files | Primary source evidence | Use deterministic tools, manifests, and bounded summaries |

Use multiple signals before assigning cause, and state confidence and uncertainty in the final report.

## Preserve Quality

- Keep high reasoning for final synthesis, validation, and quality-sensitive analysis when needed.
- Use subagents when they improve quality, but assign exact bounded units.
- Keep subagents on current repo state and current evidence.
- Continue using large audio, MIDI, video, archive, and project files when they are primary evidence. Process them through established tools and pass bounded results into context.

## Narrowing Prompt

Use or adapt this when the active goal should continue:

```text
Continue the existing goal. Preserve its goal record, timer, and thread.

Operate from current evidence:

- Keep analysis quality high where final judgment, synthesis, or validation requires it.
- Give subagents bounded checks that improve the current work.
- Open old rollout files or transcript exports when a specific missing fact requires them.
- Read the skill and plugin documentation required by the current work.
- Work from current repo state, current ledgers and status files, current generated evidence, and exact bounded units.
- Use deterministic local helpers before model synthesis when practical.
- Process large source media through the established local pipeline and pass bounded results into model context.
- For large text, JSON, or logs, read targeted keys, ledger tails, hashes, manifests, or generated summaries.

Report: current state, bounded action, subagents used, evidence generated or verified, validation, goal status, and next bounded action.

This prompt narrows agent-chosen reads. Runtime-managed resume context may still be present.
```
