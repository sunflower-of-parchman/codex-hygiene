# Codex Hygiene Tuning Reference

Use these patterns after measurement and explicit approval. Keep edits scoped, reversible, and compatible with the user's current Codex build.

Local telemetry databases, caches, and CLI output are version-dependent diagnostic surfaces. Recheck supported configuration before presenting an observed workaround as general behavior.

## Backup

```bash
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
ts=$(date -u +%Y%m%dT%H%M%SZ)
cp -p "$CODEX_HOME_DIR/config.toml" \
  "$CODEX_HOME_DIR/config.toml.pre-codex-hygiene-$ts"
```

## App Controls

Disable a selected connector with the current documented per-app setting:

```toml
[apps."connector-id"]
enabled = false
```

Per-tool controls are also available when the build supports them. Fresh-thread tool-list rows verify the resulting model-visible surface.

Use the complete Apps/connectors switch for an intended full-surface disable:

```toml
[features]
apps = false
```

Observed fallback: on one July 2026 Desktop build, per-app values were accepted while fresh `codex_apps` tool counts remained around 166 to 167. The global feature switch removed the Apps surface. Treat this as version-specific local evidence and verify the result on a fresh thread.

Cached app-tool files describe inventory. Current enablement needs fresh evidence. Record the cache modification time and compare it with the measurement window.

## MCP Controls

Use the existing local command, path, URL, and environment-variable names. Keep plugin cache paths and credentials grounded in the user's configuration.

```toml
[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/"
bearer_token_env_var = "GITHUB_PAT_TOKEN"
enabled = false

[mcp_servers.openaiDeveloperDocs]
url = "https://developers.openai.com/mcp"
enabled = false
```

For local or plugin MCPs, preserve existing `command`, `args`, `cwd`, and `url` fields. A change to any other field requires a measured reason and approval.

An enabled plugin can contribute skills or other capabilities. Diagnose plugin installation state, MCP state, and model-visible tool rows as separate signals.

## Subagents And Automations

Use these after telemetry or config review shows background or parallel fan-out:

- Lower broad `agents.max_threads` when high fan-out is unnecessary.
- Pause or narrow high-reasoning automations with no recent relevant activity.
- Give subagents bounded assignments tied to the current work.
- Narrow the active thread first. Archive, fork, or replace a long-running goal with user approval.

## Project-Local MCP

Place repository-specific services in a trusted repo's `<repo>/.codex/config.toml`:

```toml
[mcp_servers.supabase]
command = "/absolute/path/to/supabase-mcp"
args = ["--project-ref=<project-ref>"]
```

Keep service-role keys, access tokens, and full `.env` contents private. Confirm that the project is trusted because Codex skips project-scoped configuration for untrusted projects.

## Stale Project Stanzas

Count while keeping paths private:

```bash
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
rg -o '^\[projects\."([^"]+)"\]' -r '$1' "$CODEX_HOME_DIR/config.toml" \
  | while IFS= read -r p; do [ -d "$p" ] || echo missing; done \
  | wc -l
```

Remove confirmed stale stanzas after backup and explicit approval. Report the count, and keep the complete missing-path list private unless the user asks for it.

## Fresh Measurement

Create a fresh tiny thread:

```text
Please reply exactly: OK
```

Then run:

```bash
"<skill-directory>/scripts/measure_codex_context.sh" 5 <fresh_thread_id>
```

Compare tool-list rows, distinct thread counts, snapshot flags, per-thread cumulative token deltas, and cache age. The telemetry provides diagnostic evidence. Billing attribution remains unknown.
