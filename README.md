# Codex Hygiene

A Codex skill for auditing Codex Desktop context, tool surfaces, and local work patterns over time.

Use it for compact diagnostics or a privacy-preserving activity review of observed models, reasoning levels, tools, skills, plugins, compactions, subagents, automations, and token changes.

Community skill for local Codex setup hygiene.

## What It Does

- Measures recent Codex Desktop tool-list and per-thread token telemetry with read-only SQLite queries.
- Generates a Markdown or JSON review for a caller-selected lookback window, with comparison to the preceding period.
- Reports retained-source coverage and suppresses comparisons when logs do not cover both periods.
- Separates working-model observations from automatic-review activity and identifies user-thread turns when retained state supports it.
- Measures observed tool-call runtime and, in deep mode, task timing, serialized output weight, verification commands, and `SKILL.md` reads.
- Helps identify whether elevated usage correlates with app surface size, MCP/plugin state, snapshot reuse, stale project stanzas, long-thread replay, or background fan-out.
- Distinguishes actual tool calls from tool availability, enabled state from cached inventory, and thread-local token changes from mixed-thread totals.
- Labels attribution as observed evidence, interpretation, and unknowns.
- Suggests reversible hygiene steps instead of deleting logs, caches, or projects.
- Keeps long-running goal work quality-aware: narrow replay and tool scope without blindly lowering reasoning, banning subagents, or avoiding real source evidence.

## Install

Clone this repo into the current user-level Codex skills folder:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/sunflower-of-parchman/codex-hygiene.git \
  "$HOME/.agents/skills/codex-hygiene"
```

Then invoke `$codex-hygiene`. Codex normally detects newly installed skills automatically; restart Codex only if it does not appear.

## Quick Measurement

From a shell:

```bash
SKILL_DIR="$HOME/.agents/skills/codex-hygiene"
"$SKILL_DIR/scripts/measure_codex_context.sh"
```

Use a specific window or thread id:

```bash
"$SKILL_DIR/scripts/measure_codex_context.sh" 5
"$SKILL_DIR/scripts/measure_codex_context.sh" 30
"$SKILL_DIR/scripts/measure_codex_context.sh" 5 <thread_id>
```

The script prints compact counts only. It does not dump full logs, configs, tool schemas, secrets, or environment values.

## Activity Review

Choose an explicit lookback from 1 to 90 days:

```bash
SKILL_DIR="$HOME/.agents/skills/codex-hygiene"
python3 "$SKILL_DIR/scripts/codex_activity_review.py" --days 1
```

Use any other window or generate machine-readable output:

```bash
python3 "$SKILL_DIR/scripts/codex_activity_review.py" --days 14 --format json
```

The standard report stays on compact SQLite telemetry. It automatically enriches from recent rollout records when their total size is below a safety guard. Use `--deep` to force the additional read-only scan for exact task timing, relative serialized tool-output weight, verification-command counts, and observed `SKILL.md` reads:

```bash
python3 "$SKILL_DIR/scripts/codex_activity_review.py" --days 30 --deep
```

The report excludes prompts, responses, thread titles and IDs, commands, tool results, full paths, and secrets. Token changes are diagnostic local deltas rather than billing totals, and task duration includes tool work. Rollout-derived fields say `not measured` when enrichment does not run; they are never presented as measured zeros.

## Compatibility

- Designed for macOS and Unix-like Codex Desktop environments with Bash, `sqlite3`, Perl, `awk`, and `sort`.
- Uses `jq` and the `codex` CLI when available for app-cache and plugin state summaries.
- The activity review uses Python 3 and only the standard library.
- Treats local telemetry databases and cache layouts as version-dependent diagnostic inputs, not stable APIs or billing records.
- Supports custom Codex data locations through `CODEX_HOME`; use the skill's actual install path when it is not under `$HOME/.agents/skills`.

## Safety Defaults

- Starts read-only.
- Uses `sqlite3 -readonly`.
- Avoids printing full config, full logs, app schemas, MCP schemas, or `.env` values.
- Recommends backing up `~/.codex/config.toml` before any config edit.
- Treats delete/restart/disable actions as explicit-user-approval work.

## Contents

```text
SKILL.md
agents/openai.yaml
scripts/measure_codex_context.sh
scripts/codex_activity_review.py
tests/measure_codex_context_test.sh
tests/codex_activity_review_test.py
references/remediation.md
references/long-thread-replay.md
references/activity-review.md
```

## Codex References

- [Agent Skills](https://developers.openai.com/codex/skills)
- [Configuration reference](https://developers.openai.com/codex/config-reference)
- [MCP configuration](https://developers.openai.com/codex/mcp)

## License

MIT
