#!/usr/bin/env bash
set -euo pipefail

MINUTES_RAW="${1:-30}"
THREAD_ID="${2:-}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
CONFIG="$CODEX_HOME_DIR/config.toml"
DB="$CODEX_HOME_DIR/logs_2.sqlite"
CACHE_DIR="$CODEX_HOME_DIR/cache/codex_apps_tools"

if ! [[ "$MINUTES_RAW" =~ ^[0-9]+$ ]]; then
  echo "usage: measure_codex_context.sh [minutes: 1-1440] [thread_id]" >&2
  exit 2
fi

MINUTES=$((10#$MINUTES_RAW))
if (( MINUTES < 1 || MINUTES > 1440 )); then
  echo "minutes must be between 1 and 1440" >&2
  exit 2
fi

if [ -n "$THREAD_ID" ] && ! [[ "$THREAD_ID" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "thread_id may contain only letters, digits, and hyphens" >&2
  exit 2
fi

for required in sqlite3 perl awk sort; do
  if ! command -v "$required" >/dev/null 2>&1; then
    echo "missing required command: $required" >&2
    exit 3
  fi
done

if [ ! -f "$DB" ]; then
  echo "missing log db: $DB" >&2
  exit 3
fi

if ! sqlite3 -readonly "$DB" "select 1 from logs limit 1;" >/dev/null 2>&1; then
  echo "unsupported or unreadable log schema: $DB" >&2
  exit 3
fi

THREAD_SQL=""
if [ -n "$THREAD_ID" ]; then
  THREAD_SQL=" and thread_id='$THREAD_ID'"
fi

file_mtime_epoch() {
  local file="$1"

  if [ "$(uname -s)" = "Darwin" ]; then
    stat -f '%m' "$file"
  else
    stat -c '%Y' "$file"
  fi
}

format_epoch_utc() {
  local epoch="$1"

  if date -u -r "$epoch" '+%Y-%m-%dT%H:%M:%SZ' >/dev/null 2>&1; then
    date -u -r "$epoch" '+%Y-%m-%dT%H:%M:%SZ'
  else
    date -u -d "@$epoch" '+%Y-%m-%dT%H:%M:%SZ'
  fi
}

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
echo "plugin_state:"
if command -v codex >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
  plugin_json="$(codex plugin list --json 2>/dev/null || true)"
  if jq -e '.installed | arrays' >/dev/null 2>&1 <<<"$plugin_json"; then
    jq -r '
      "installed=" + ((.installed | length) | tostring)
      + " enabled=" + ([.installed[] | select(.enabled == true)] | length | tostring)
      + " disabled=" + ([.installed[] | select(.enabled == false)] | length | tostring),
      "enabled_ids=" + ([.installed[] | select(.enabled == true) | (.pluginId // .name // "unknown")] | sort | join(",")),
      "disabled_ids=" + ([.installed[] | select(.enabled == false) | (.pluginId // .name // "unknown")] | sort | join(","))
    ' <<<"$plugin_json"
  else
    echo "plugin state unavailable"
  fi
else
  echo "plugin state requires codex and jq"
fi
echo "note=plugin enablement records current availability; model attachment remains unknown"

echo
echo "mcp_state:"
if command -v codex >/dev/null 2>&1; then
  codex mcp list 2>/dev/null \
    | awk '
      $1 != "Name" && NF > 1 {
        status="";
        for (i=1; i<=NF; i++) {
          if ($i=="enabled" || $i=="disabled") status=$i;
        }
        if (status!="") {
          count[status]++;
          names[status]=(names[status] == "") ? $1 : names[status] "," $1;
        }
      }
      END {
        print "enabled=" (count["enabled"] + 0) " names=" names["enabled"];
        print "disabled=" (count["disabled"] + 0) " names=" names["disabled"];
      }
    ' \
    || true
else
  echo "codex command not found"
fi

echo
echo "projects:"
if [ -f "$CONFIG" ]; then
  project_count=0
  missing_count=0
  while IFS= read -r path; do
    [ -n "$path" ] || continue
    project_count=$((project_count + 1))
    if [ ! -d "$path" ]; then
      missing_count=$((missing_count + 1))
    fi
  done < <(sed -n 's/^\[projects\."\([^"]*\)"\].*/\1/p' "$CONFIG")
  echo "project_stanzas=$project_count missing_dirs=$missing_count"
else
  echo "missing config: $CONFIG"
fi

echo
echo "listed_mcp_tools:"
listed_output="$(
  sqlite3 -readonly -separator $'\t' "$DB" \
    "select coalesce(thread_id,''), feedback_log_body from logs where ts >= strftime('%s','now')-($MINUTES*60)$THREAD_SQL and feedback_log_body like '%listed MCP server tools%';" \
    | perl -ne '
        chomp;
        my ($thread, $body) = split(/\t/, $_, 2);
        if (defined $body && $body =~ /server_name=([^ ]+) tool_count=([0-9]+)/) {
          print "$1\t$2\t", ($thread || "unknown"), "\n";
        }
      ' \
    | awk -F '\t' '
        {
          key=$1 FS $2;
          rows[key]++;
          thread_key=key SUBSEP $3;
          if (!seen_thread[thread_key]++) threads[key]++;
        }
        END {
          for (key in rows) {
            split(key, fields, FS);
            print rows[key] FS threads[key] FS fields[1] FS fields[2];
          }
        }
      ' \
    | sort -t $'\t' -k1,1nr -k3,3
)"
if [ -n "$listed_output" ]; then
  awk -F '\t' '{print "rows=" $1 " threads=" $2 " server=" $3 " tools=" $4}' <<<"$listed_output"
else
  echo "none"
fi

echo
echo "snapshot_cache_flags:"
snapshot_output="$(
  sqlite3 -readonly -separator $'\t' "$DB" \
    "select coalesce(thread_id,''), feedback_log_body from logs where ts >= strftime('%s','now')-($MINUTES*60)$THREAD_SQL and feedback_log_body like '%has_cached_tool_info_snapshot%';" \
    | perl -ne '
        chomp;
        my ($thread, $body) = split(/\t/, $_, 2);
        if (defined $body && $body =~ /server_name=([^ ]+) has_cached_tool_info_snapshot=([^ ]+)/) {
          print "$1\t$2\t", ($thread || "unknown"), "\n";
        }
      ' \
    | awk -F '\t' '
        {
          key=$1 FS $2;
          rows[key]++;
          thread_key=key SUBSEP $3;
          if (!seen_thread[thread_key]++) threads[key]++;
        }
        END {
          for (key in rows) {
            split(key, fields, FS);
            print rows[key] FS threads[key] FS fields[1] FS fields[2];
          }
        }
      ' \
    | sort -t $'\t' -k1,1nr -k3,3
)"
if [ -n "$snapshot_output" ]; then
  awk -F '\t' '{print "rows=" $1 " threads=" $2 " server=" $3 " cached=" $4}' <<<"$snapshot_output"
else
  echo "none"
fi

echo
echo "recent_thread_token_deltas:"
token_output="$(
  sqlite3 -readonly -separator $'\t' "$DB" \
    "select ts, datetime(ts,'unixepoch') || 'Z', coalesce(thread_id,''), feedback_log_body from logs where ts >= strftime('%s','now')-($MINUTES*60)$THREAD_SQL and target='codex_core::session::turn' and feedback_log_body like '%post sampling token usage%' order by thread_id, ts, ts_nanos;" \
    | perl -ne '
        chomp;
        my ($epoch, $utc, $thread, $body) = split(/\t/, $_, 4);
        next unless defined $body && $body =~ /total_usage_tokens=([0-9]+)/;
        print join("\t", $epoch, $utc, ($thread || "unknown"), $1), "\n";
      ' \
    | awk -F '\t' '
        {
          event_key=$3 SUBSEP $1 SUBSEP $4;
          if (seen_event[event_key]++) next;

          thread=$3;
          if (!(thread in seen_thread)) {
            seen_thread[thread]=1;
            first_epoch[thread]=$1;
            first_utc[thread]=$2;
            first_total[thread]=$4;
          }
          last_epoch[thread]=$1;
          last_utc[thread]=$2;
          last_total[thread]=$4;
          rows[thread]++;
        }
        END {
          for (thread in seen_thread) {
            elapsed=last_epoch[thread]-first_epoch[thread];
            delta=last_total[thread]-first_total[thread];
            rate=(elapsed > 0) ? sprintf("%.1f", delta*60/elapsed) : "n/a";
            tail=(length(thread) > 8) ? substr(thread, length(thread)-7) : thread;
            print last_utc[thread] FS tail FS rows[thread] FS first_utc[thread] FS elapsed FS first_total[thread] FS last_total[thread] FS delta FS rate;
          }
        }
      ' \
    | sort -t $'\t' -k1,1r
)"
if [ -n "$token_output" ]; then
  token_thread_count="$(awk 'END {print NR}' <<<"$token_output")"
  token_threads_shown="$token_thread_count"
  if (( token_threads_shown > 5 )); then
    token_threads_shown=5
  fi
  echo "threads=$token_thread_count showing=$token_threads_shown"
  sed -n '1,5p' <<<"$token_output" | awk -F '\t' '{
    print "last_utc=" $1 " thread_tail=" $2 " rows=" $3 " first_utc=" $4 " elapsed_s=" $5 \
      " cumulative_first=" $6 " cumulative_last=" $7 " delta=" $8 " delta_per_min=" $9
  }'
  echo "note=deltas describe local cumulative telemetry; billing attribution remains unknown; negative values may indicate reset or compaction"
else
  echo "none"
fi

echo
echo "cached_app_inventory_not_enabled_state:"
latest_cache=""
latest_mtime=0
if [ -d "$CACHE_DIR" ]; then
  while IFS= read -r -d '' candidate; do
    candidate_mtime="$(file_mtime_epoch "$candidate" 2>/dev/null || true)"
    if [[ "$candidate_mtime" =~ ^[0-9]+$ ]] && (( candidate_mtime > latest_mtime )); then
      latest_cache="$candidate"
      latest_mtime="$candidate_mtime"
    fi
  done < <(find "$CACHE_DIR" -type f -name '*.json' -print0 2>/dev/null)
fi

if [ -n "$latest_cache" ] && command -v jq >/dev/null 2>&1; then
  now_epoch="$(date +%s)"
  cache_age_seconds=$((now_epoch - latest_mtime))
  if (( cache_age_seconds < 0 )); then
    cache_age_seconds=0
  fi
  cache_age_minutes=$((cache_age_seconds / 60))
  if (( cache_age_seconds > MINUTES * 60 )); then
    cache_older_than_window=true
  else
    cache_older_than_window=false
  fi

  echo "cache_mtime_utc=$(format_epoch_utc "$latest_mtime") age_minutes=$cache_age_minutes older_than_window=$cache_older_than_window"
  jq -r '
    .tools // []
    | group_by(.connector_id)[]
    | [((.[0].connector_name // "unknown") | tostring | gsub("[\\t\\r\\n]"; " ")), length]
    | @tsv
  ' "$latest_cache" | sort -t $'\t' -k2,2nr || true
  echo "note=cache inventory may be stale; current app enablement remains unknown"
else
  echo "no cache inventory available"
fi
