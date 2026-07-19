# Codex Hygiene

A compact, read-only Codex skill for current-context diagnostics and private local activity reviews.

The original measurement returns small counts from recent telemetry. An explicit 1-90 day review returns Markdown or JSON that describes how Codex was used, which sources support the report, and where the evidence ends.

## What It Does

- Runs the original compact measurement for recent tool-list and per-thread token telemetry.
- Builds a period review with source coverage and supported prior-window comparisons.
- Separates observed evidence, interpretation, and unknowns.
- Enriches period reviews with task timing, relative output weight, verification commands, explicit compactions, and observed `SKILL.md` reads.
- Reviews the current Codex profile, including every installed plugin, MCP state, Apps availability, and project-stanza counts.
- Suggests scoped, reversible hygiene steps after measurement.

## Install

Clone this repo into the current user-level Codex skills folder:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/sunflower-of-parchman/codex-hygiene.git \
  "$HOME/.agents/skills/codex-hygiene"
```

Then invoke `$codex-hygiene`. Codex usually detects newly installed skills automatically. Restart Codex if the skill has not appeared.

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

The script prints compact counts. Full logs, configs, tool schemas, secrets, and environment values stay private.

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

The review reads compact SQLite telemetry and enriches it from rollout records inside `CODEX_HOME`. Enrichment runs by default at every candidate size and reads files backward only to the prior comparison boundary. It adds task timing, relative serialized tool-output weight, verification-command counts, explicit compactions, and observed `SKILL.md` reads.

Use `--no-rollouts` only when a deliberately lightweight report is needed:

```bash
python3 "$SKILL_DIR/scripts/codex_activity_review.py" --days 30 --no-rollouts
```

Each report keeps prompts, responses, thread titles and IDs, commands, tool results, full paths, and secrets private. Token changes describe local cumulative telemetry. Billing attribution remains unknown. Task duration includes tool work and may overlap across concurrent tasks.

## Example Return

The values below are synthetic. A Markdown activity review contains sections like these:

```markdown
# Codex Activity Review

Window: `2026-07-10T12:00:00Z` through `2026-07-17T12:00:00Z`

## Period at a glance

- **Threads active:** 12; **prior-window change:** +2 (+20.0%)
- **Observed turns:** 48 (prior comparison unavailable)
- **Local cumulative token change:** 124,000 (prior comparison unavailable)
- **Tool calls:** 96 with 6m 12s observed runtime

## Codex profile and plugin weight

| Plugin | State | Tool calls | Runtime | Serialized output | Skill reads |
|---|---|---:|---:|---:|---:|
| example@marketplace | enabled | 18 | 42s | 1.2 MiB | 3 |

## Interpretation

### 1. High confidence

- **Observed:** `exec_command` had the largest observed tool runtime: 3m 41s across 38 calls.
- **Interpretation:** The retained telemetry associates the runtime shown above with this tool.
- **Unknown:** Prompt-schema tokens, result tokens, and the value of the returned evidence remain unknown.

## Coverage and uncertainty

- Rollout detail: **scanned**.
- Log coverage: current **full**; previous **partial**; token baseline **unavailable**.
- Suppressed prior-period comparisons: **observed turns, local cumulative token change, tool calls, and tool runtime**.
```

## Optional: Codex optimization

```text
Use this review to identify up to three ways to reduce unnecessary token use while preserving quality and required capabilities. Tie each suggestion to observed evidence, state uncertainty, and make no changes without approval.
```

This is an excerpt. The complete report includes every measured section and its source warnings.

## Compatibility

- The compact measurement supports macOS and Unix-like Codex Desktop environments with Bash, `sqlite3`, Perl, `awk`, and `sort`.
- `jq` and the `codex` CLI add app-cache and current plugin-state summaries when available.
- The activity review uses Python 3 and the standard library.
- Local telemetry schemas, retained history, cache layouts, and CLI output are version-dependent diagnostic inputs.
- `CODEX_HOME` supports custom Codex data locations. Commands should use the skill's actual install path.

## Safety Defaults

- Starts every measurement read-only.
- Uses `sqlite3 -readonly`.
- Keeps full config, full logs, app schemas, MCP schemas, and `.env` values private.
- Recommends backing up `~/.codex/config.toml` before any config edit.
- Requires explicit user approval for delete, restart, disable, and configuration actions.

## Contents

```text
CHANGELOG.md
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
