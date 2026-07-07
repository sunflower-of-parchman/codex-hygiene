# Codex Hygiene Remediation Reference

Use these patterns after measurement and backup. Keep edits scoped and reversible.

## Backup

```bash
ts=$(date -u +%Y%m%dT%H%M%SZ)
cp -p "$HOME/.codex/config.toml" "$HOME/.codex/config.toml.pre-codex-hygiene-$ts"
```

## Disable Global Apps Surface

Use when `codex_apps` dominates fresh-thread `list_all_tools` and per-app disables do not shrink the count.

```toml
[features]
apps = false
```

Optional per-app intent markers can remain for documentation, but the global feature flag is the measured effective switch for removing the Apps tool surface.

## Disable Unused MCPs

Use existing local command/path/url values where present. Do not invent plugin cache paths.

```toml
[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/"
bearer_token_env_var = "GITHUB_PAT_TOKEN"
enabled = false

[mcp_servers.openaiDeveloperDocs]
url = "https://developers.openai.com/mcp"
enabled = false
```

For local/plugin MCPs, preserve any existing `command`, `args`, and `cwd`; only add or change:

```toml
enabled = false
```

Common candidates when unused:

- `codex-security`
- `computer-use`
- `event-stream`
- `xcodebuildmcp`
- `github`
- `openaiDeveloperDocs`

## Subagent And Automation Trimming

Use these only when measurement or config review shows fan-out/background cost.

- Lower broad `agents.max_threads` only when high fan-out is not needed.
- Pause or narrow high-reasoning automations that are not actively useful.
- Prefer bounded subagent assignments over banning subagents completely.
- For long-running goals, prefer an in-thread narrowing prompt before archiving, forking, or restarting.

## Project-Local Service MCP

When a remote service is needed only in specific repositories, disable broad app access globally and add a repo-local MCP in `<repo>/.codex/config.toml`. Supabase-style example:

```toml
[mcp_servers.supabase]
command = "/absolute/path/to/supabase-mcp"
args = ["--project-ref=<project-ref>"]

[sandbox_workspace_write]
network_access = true
```

Do not print service-role keys, access tokens, or full `.env` contents.

## Stale Project Stanzas

Count first:

```bash
rg -o '^\[projects\."([^"]+)"\]' -r '$1' "$HOME/.codex/config.toml" \
  | while IFS= read -r p; do [ -d "$p" ] || echo missing; done | wc -l
```

Remove stale stanzas only after backup. Do not print the full missing path list unless the user asks.

## Fresh Thread Measurement

Create a fresh thread with:

```text
Please reply exactly: OK
```

Then rerun:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/codex-hygiene"
"$SKILL_DIR/scripts/measure_codex_context.sh" 5 <fresh_thread_id>
```

Compare `listed MCP tools`, snapshot cache flags, and `post sampling token usage`.
