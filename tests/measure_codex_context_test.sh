#!/usr/bin/env bash
set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$SKILL_ROOT/scripts/measure_codex_context.sh"
TEST_ROOT="$(mktemp -d)"
CODEX_HOME_DIR="$TEST_ROOT/codex-home"
BIN_DIR="$TEST_ROOT/bin"

cleanup() {
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

mkdir -p "$CODEX_HOME_DIR/cache/codex_apps_tools" "$BIN_DIR" "$TEST_ROOT/existing-project"

cat >"$CODEX_HOME_DIR/config.toml" <<EOF
[projects."$TEST_ROOT/existing-project"]
trust_level = "trusted"

[projects."$TEST_ROOT/missing-project"]
trust_level = "trusted"
EOF

cat >"$BIN_DIR/codex" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

case "${1:-} ${2:-}" in
  "features list")
    echo "apps stable false"
    ;;
  "plugin list")
    cat <<'JSON'
{"installed":[{"pluginId":"alpha@local","enabled":true},{"pluginId":"beta@local","enabled":false}]}
JSON
    ;;
  "mcp list")
    printf 'Name Status\nalpha enabled\nbeta disabled\n'
    ;;
  *)
    exit 1
    ;;
esac
EOF
chmod +x "$BIN_DIR/codex"

cat >"$CODEX_HOME_DIR/cache/codex_apps_tools/fixture.json" <<'JSON'
{
  "tools": [
    {"connector_id": "connector-alpha-id", "connector_name": "Alpha"},
    {"connector_id": "connector-alpha-id", "connector_name": "Alpha"},
    {"connector_id": "connector-beta-id", "connector_name": "Beta"}
  ]
}
JSON

now="$(date +%s)"
sqlite3 "$CODEX_HOME_DIR/logs_2.sqlite" <<SQL
create table logs (
  id integer primary key,
  ts integer not null,
  ts_nanos integer not null,
  level text not null,
  target text not null,
  feedback_log_body text,
  module_path text,
  file text,
  line integer,
  thread_id text,
  process_uuid text,
  estimated_bytes integer not null default 0
);

insert into logs (ts, ts_nanos, level, target, feedback_log_body, thread_id) values
  ($((now - 20)), 1, 'INFO', 'mcp', 'listed MCP server tools server_name=alpha tool_count=10', 'thread-a'),
  ($((now - 10)), 2, 'INFO', 'mcp', 'listed MCP server tools server_name=alpha tool_count=10', 'thread-b'),
  ($((now - 20)), 3, 'INFO', 'mcp', 'snapshot server_name=alpha has_cached_tool_info_snapshot=false', 'thread-a'),
  ($((now - 10)), 4, 'INFO', 'mcp', 'snapshot server_name=alpha has_cached_tool_info_snapshot=false', 'thread-b'),
  ($((now - 120)), 5, 'INFO', 'codex_core::session::turn', 'post sampling token usage total_usage_tokens=100 estimated_token_count=Some(100)', 'thread-a'),
  ($((now - 60)), 6, 'INFO', 'codex_core::session::turn', 'post sampling token usage total_usage_tokens=160 estimated_token_count=Some(160)', 'thread-a'),
  ($((now - 40)), 7, 'INFO', 'codex_core::session::turn', 'post sampling token usage total_usage_tokens=200 estimated_token_count=Some(200)', 'thread-b'),
  ($((now - 10)), 8, 'INFO', 'codex_core::session::turn', 'post sampling token usage total_usage_tokens=260 estimated_token_count=Some(260)', 'thread-b');
SQL

output="$(PATH="$BIN_DIR:$PATH" CODEX_HOME="$CODEX_HOME_DIR" "$SCRIPT" 5)"

assert_contains() {
  local expected="$1"

  if ! grep -Fq "$expected" <<<"$output"; then
    echo "missing expected output: $expected" >&2
    echo "$output" >&2
    exit 1
  fi
}

assert_not_contains() {
  local unexpected="$1"

  if grep -Fq "$unexpected" <<<"$output"; then
    echo "unexpected output: $unexpected" >&2
    echo "$output" >&2
    exit 1
  fi
}

assert_contains "installed=2 enabled=1 disabled=1"
assert_contains "note=plugin enablement records current availability; model attachment remains unknown"
assert_contains "enabled=1 names=alpha"
assert_contains "disabled=1 names=beta"
assert_contains "project_stanzas=2 missing_dirs=1"
assert_contains "rows=2 threads=2 server=alpha tools=10"
assert_contains "rows=2 threads=2 server=alpha cached=false"
assert_contains "thread_tail=thread-a rows=2"
assert_contains "elapsed_s=60 cumulative_first=100 cumulative_last=160 delta=60 delta_per_min=60.0"
assert_contains "thread_tail=thread-b rows=2"
assert_contains "elapsed_s=30 cumulative_first=200 cumulative_last=260 delta=60 delta_per_min=120.0"
assert_contains "note=deltas describe local cumulative telemetry; billing attribution remains unknown; negative values may indicate reset or compaction"
assert_contains $'Alpha\t2'
assert_contains $'Beta\t1'
assert_contains "older_than_window=false"
assert_contains "note=cache inventory may be stale; current app enablement remains unknown"
assert_not_contains "connector-alpha-id"
assert_not_contains "connector-beta-id"

if PATH="$BIN_DIR:$PATH" CODEX_HOME="$CODEX_HOME_DIR" "$SCRIPT" 0 >/dev/null 2>&1; then
  echo "zero-minute window should fail" >&2
  exit 1
fi

echo "measure_codex_context_test: PASS"
