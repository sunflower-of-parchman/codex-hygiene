# Long-Thread Replay Hygiene

Use this when a long-running Codex goal/thread must be preserved and token usage is unexpectedly high.

This especially applies to multi-day or multi-week single `/goal` threads that are repeatedly resumed, where old rollout history may be pulled into context even when current work only needs current ledgers, status files, and generated evidence.

## Portable Evidence Sources

Check current local evidence before recommending reset/archive/removal:

- `$CODEX_HOME/config.toml` for model, reasoning, plugins, features, agents, and tools.
- `$CODEX_HOME/state_*.sqlite` for thread metadata, archived state, rollout paths, and token records when available.
- `$CODEX_HOME/goals_*.sqlite` for active, paused, or completed goal state when available.
- `$CODEX_HOME/logs_*.sqlite` for recent token telemetry and tool-list rows.
- Current repo status, ledgers, dashboards, lock files, generated artifacts, and process checks for the actual work.

Use `sqlite3 -readonly`, `rg`, `sed`, `du`, `ps`, `lsof`, `jq`, `stat`, and repo helper scripts. Do not edit SQLite databases directly.

## Classify Elevated Usage

| Signal | Possible contributor | Hygiene step |
| --- | --- | --- |
| Huge rollout file, old or repeatedly resumed `/goal` thread, millions of input tokens | Thread context replay | Continue from current repo evidence or send a narrowing prompt |
| Many enabled unrelated plugins/skills | Broad runtime surface | Disable unused plugins or tell the active thread not to discover/load them |
| High `agents.max_threads` or many subagents | Parallel context multiplication | Cap subagents and assign bounded work |
| Scheduled automation on high reasoning | Background usage | Pause/lower automation or narrow its prompt |
| Large source media/project files | Usually not the model-context contributor | Process through deterministic tools, hashes, manifests, and generated summaries |

If the user wants the original goal to register as completed, prefer in-thread narrowing over archiving/restarting. Archive or fork only after explicit user approval.

## Preserve Quality

Do not lower reasoning effort when the remaining work is final synthesis, final review, validation, or quality-sensitive analysis.

Do not ban subagents by default. Instead:

- Use subagents only when they improve quality or parallel verification.
- Assign exact bounded units.
- Forbid broad transcript, plugin, and skill reloading inside subagents.
- Keep each subagent on current repo state and current evidence surfaces.

Do not tell agents to avoid large files generally. Large audio, MIDI, video, archives, and project files may be primary evidence. Avoid raw context dumps, not source evidence.

## Narrowing Prompt

Use or adapt this when a long thread should finish without resetting the goal:

```text
Continue the existing goal. Do not create a new goal, reset the timer, fork, or archive this thread.

Operate in final-mile focus mode:

- Keep analysis quality high where final judgment, synthesis, or validation requires it.
- Use subagents only for bounded, work-relevant checks that improve quality.
- Do not use broad exploratory subagents.
- Do not load broad skill lists, plugin docs, old rollout history, or old transcript context.
- Do not use unrelated plugins/apps/tools. Use only the tools already needed for this work.
- Work from current repo state, current ledgers/status files, current generated evidence, and exact bounded units.
- Use deterministic local helpers before model synthesis when possible.
- Large source media/project files are allowed evidence. Analyze them with the established local pipeline; do not paste raw large contents into model context.
- For huge text/JSON/log files, read targeted keys, ledger tails, hashes, manifests, or repo-generated summaries.

Report only: current state, exact bounded action, subagents used if any, evidence generated or verified, validation, goal status, and next safest bounded action.
```

## Common Mistakes

| Mistake | Why it hurts | Better |
| --- | --- | --- |
| "Just start a new thread" | May lose proof of a long-running goal | Offer in-thread narrowing first |
| "Do not use subagents" | Can degrade final analysis quality | Use bounded, relevant subagents |
| "Avoid huge files" | Rejects real media evidence | Avoid raw context dumps, not source evidence |
| "Disable everything" | May remove required project tools | Keep only work-relevant capabilities |
| Trusting stale dashboards | Misreads operational state | Verify live process, ledger, and status files |
| Editing databases directly | Risks corrupting app state | Use read-only SQL and app/config tools |
