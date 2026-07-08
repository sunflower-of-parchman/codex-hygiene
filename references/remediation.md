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

Per-tool controls are also available when the build supports them. Verify the result against fresh-thread tool-list rows instead of assuming that an approval or enablement setting changed the model-visible surface.

Disable the complete Apps/connectors surface only when that is the intended scope:

```toml
[features]
apps = false
```

On one July 2026 Desktop setup, per-app values were parsed but the fresh `codex_apps` tool count remained around `166-167` until the global feature was disabled. Treat that as version-specific local evidence. First use current documented controls, then use the global switch when all Apps should be off or measurement confirms the narrower control is ineffective on that build.

Cached app-tool files are inventory, not enabled-state evidence. Record their modification time and compare it with the measurement window.

## MCP Controls

Use existing local command, path, URL, and environment-variable names. Do not invent plugin cache paths or credentials.

```toml
[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/"
bearer_token_env_var = "GITHUB_PAT_TOKEN"
enabled = false

[mcp_servers.openaiDeveloperDocs]
url = "https://developers.openai.com/mcp"
enabled = false
```

For local or plugin MCPs, preserve existing `command`, `args`, `cwd`, and `url` fields; change only the `enabled` value unless another edit is required and approved.

Common candidates when unused include:

- `codex-security`
- `computer-use`
- `event-stream`
- `xcodebuildmcp`
- `github`
- `openaiDeveloperDocs`

An enabled plugin can contribute skills or other capabilities without attaching an MCP tool surface. Keep plugin installation state, MCP state, and model-visible tool rows separate in the diagnosis.

## Subagents And Automations

Use these only when telemetry or config review shows background or parallel fan-out:

- Lower broad `agents.max_threads` when high fan-out is unnecessary.
- Pause or narrow high-reasoning automations that are not currently useful.
- Prefer bounded subagent assignments over banning subagents.
- Prefer in-thread narrowing before archiving, forking, or replacing a long-running goal.

## Project-Local MCP

When a service is needed only in specific repositories, use a trusted repo's `<repo>/.codex/config.toml`:

```toml
[mcp_servers.supabase]
command = "/absolute/path/to/supabase-mcp"
args = ["--project-ref=<project-ref>"]

[sandbox_workspace_write]
network_access = true
```

Do not print service-role keys, access tokens, or full `.env` contents. Confirm that the project is trusted because Codex skips project-scoped configuration for untrusted projects.

## Stale Project Stanzas

Count without printing paths:

```bash
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
rg -o '^\[projects\."([^"]+)"\]' -r '$1' "$CODEX_HOME_DIR/config.toml" \
  | while IFS= read -r p; do [ -d "$p" ] || echo missing; done \
  | wc -l
```

Remove only confirmed stale stanzas after backup. Do not print the complete missing-path list unless the user asks.

## Fresh Measurement

Create a fresh tiny thread:

```text
Please reply exactly: OK
```

Then run:

```bash
"<skill-directory>/scripts/measure_codex_context.sh" 5 <fresh_thread_id>
```

Compare tool-list rows, distinct thread counts, snapshot flags, per-thread cumulative token deltas, and cache age. Treat the telemetry as diagnostic evidence rather than billing totals.
