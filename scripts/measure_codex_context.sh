#!/usr/bin/env bash
set -euo pipefail

MINUTES="${1:-30}"
THREAD_ID="${2:-}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CONFIG="$CODEX_HOME_DIR/config.toml"
DB="$CODEX_HOME_DIR/logs_2.sqlite"
CACHE_DIR="$CODEX_HOME_DIR/cache/codex_apps_tools"

if ! [[ "$MINUTES" =~ ^[0-9]+$ ]]; then
  echo "usage: measure_codex_context.sh [minutes] [thread_id]" >&2
  exit 2
fi

if [ -n "$THREAD_ID" ] && ! [[ "$THREAD_ID" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "thread_id may contain only letters, digits, and hyphens" >&2
  exit 2
fi

if [ ! -f "$DB" ]; then
  echo "missing log db: $DB" >&2
  exit 3
fi

THREAD_SQL=""
if [ -n "$THREAD_ID" ]; then
  THREAD_SQL=" and thread_id='$THREAD_ID'"
fi

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "window_minutes=$MINUTES"
if [ -n "$THREAD_ID" ]; then
  echo "thread_id=$THREAD_ID"
fi

echo
echo "features_apps:"
if command -v codex >/dev/null 2>&1; then
  codex features list 2>/dev/null | awk '$1=="apps"{print $0}' || true
else
  echo "codex command not found"
fi

echo
echo "mcp_focus:"
if command -v codex >/dev/null 2>&1; then
  codex mcp list 2>/dev/null \
    | awk '
      $1 != "Name" && NF > 1 {
        status="";
        for (i=1; i<=NF; i++) {
          if ($i=="enabled" || $i=="disabled") status=$i;
        }
        if (status!="") print $1 "\t" status;
      }
    ' \
    || true
else
  echo "codex command not found"
fi

echo
echo "projects:"
if [ -f "$CONFIG" ]; then
  project_count="$(grep -E '^\[projects\."' "$CONFIG" | wc -l | tr -d ' ')"
  missing_count="$(sed -n 's/^\[projects\."\([^"]*\)"\].*/\1/p' "$CONFIG" \
    | while IFS= read -r path; do [ -d "$path" ] || echo missing; done \
    | wc -l | tr -d ' ')"
  echo "project_stanzas=$project_count missing_dirs=$missing_count"
else
  echo "missing config: $CONFIG"
fi

echo
echo "listed_mcp_tools:"
sqlite3 -readonly "$DB" \
  "select feedback_log_body from logs where ts >= strftime('%s','now')-($MINUTES*60)$THREAD_SQL and feedback_log_body like '%listed MCP server tools%';" \
  | perl -ne 'print "$1\t$2\n" if /server_name=([^ ]+) tool_count=([0-9]+)/' \
  | sort | uniq -c | sort -nr || true

echo
echo "snapshot_cache_flags:"
sqlite3 -readonly "$DB" \
  "select feedback_log_body from logs where ts >= strftime('%s','now')-($MINUTES*60)$THREAD_SQL and feedback_log_body like '%has_cached_tool_info_snapshot%';" \
  | perl -ne 'print "$1\t$2\n" if /server_name=([^ ]+) has_cached_tool_info_snapshot=([^ ]+)/' \
  | sort | uniq -c | sort -nr || true

echo
echo "recent_turn_tokens:"
sqlite3 -readonly "$DB" \
  "select datetime(ts,'unixepoch'), feedback_log_body from logs where ts >= strftime('%s','now')-($MINUTES*60)$THREAD_SQL and target='codex_core::session::turn' and feedback_log_body like '%post sampling token usage%' order by ts desc limit 8;" \
  | perl -ne 'print "$1\ttotal=$2\test=$3\n" if /^([^|]+)\|.*total_usage_tokens=([0-9]+).*estimated_token_count=Some\(([0-9]+)\)/' || true

echo
echo "codex_apps_cache_breakdown:"
latest_cache=""
if [ -d "$CACHE_DIR" ]; then
  latest_cache="$(find "$CACHE_DIR" -type f -name '*.json' -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1 || true)"
fi

if [ -n "$latest_cache" ] && command -v jq >/dev/null 2>&1; then
  echo "cache=$(basename "$latest_cache")"
  jq -r '.tools // [] | group_by(.connector_id)[] | [.[0].connector_name, .[0].connector_id, length] | @tsv' "$latest_cache" \
    | sort -k3,3nr || true
else
  echo "no cache breakdown available"
fi
