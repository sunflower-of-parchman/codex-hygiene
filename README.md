# Codex Hygiene

A small Codex skill for auditing and tuning Codex Desktop context and tool surfaces.

Use it to measure recent Codex Desktop telemetry, review MCP/app/skill availability, and keep long-running goal workflows scoped to the current work.

Community skill for local Codex setup hygiene.

## What It Does

- Measures recent Codex Desktop tool-list and token telemetry with read-only SQLite queries.
- Helps identify whether elevated usage correlates with app surface size, MCP/plugin state, snapshot reuse, stale project stanzas, long-thread replay, or background fan-out.
- Suggests reversible hygiene steps instead of deleting logs, caches, or projects.
- Keeps long-running goal work quality-aware: narrow replay and tool scope without blindly lowering reasoning, banning subagents, or avoiding real source evidence.

## Install

Clone this repo into your Codex skills folder:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/sunflower-of-parchman/codex-hygiene.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/codex-hygiene"
```

Then start a new Codex thread and ask for `$codex-hygiene`.

## Quick Measurement

From a shell:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/codex-hygiene"
"$SKILL_DIR/scripts/measure_codex_context.sh"
```

Use a specific window or thread id:

```bash
"$SKILL_DIR/scripts/measure_codex_context.sh" 5
"$SKILL_DIR/scripts/measure_codex_context.sh" 30
"$SKILL_DIR/scripts/measure_codex_context.sh" 5 <thread_id>
```

The script prints compact counts only. It does not dump full logs, configs, tool schemas, secrets, or environment values.

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
references/remediation.md
references/long-thread-replay.md
```

## License

MIT
