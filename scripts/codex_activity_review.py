#!/usr/bin/env python3
"""Generate a privacy-preserving activity review from local Codex telemetry."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


SCHEMA_VERSION = "0.2.0"
UTC = dt.timezone.utc
SAFE_LABEL = re.compile(r"[^A-Za-z0-9._:@+-]+")
TURN_ID_RE = re.compile(r"(?:turn\.id=|turn_id=)([A-Za-z0-9-]+)")
MODEL_RE = re.compile(r"\bmodel=([A-Za-z0-9._:@+-]+)")
EFFORT_RE = re.compile(r"codex\.turn\.reasoning_effort=([A-Za-z0-9._:@+-]+)")
TOKEN_TOTAL_RE = re.compile(r"total_usage_tokens=([0-9]+)")
TOOL_NAME_RE = re.compile(r"tool_name=([A-Za-z0-9._:@+-]+)")
CALL_ID_RE = re.compile(r"call_id=([A-Za-z0-9_-]+)")
TOTAL_DURATION_RE = re.compile(r"total_duration_ms=([0-9]+(?:\.[0-9]+)?)")
MCP_LIST_RE = re.compile(r"server_name=([^ ]+) tool_count=([0-9]+)")
SNAPSHOT_RE = re.compile(r"server_name=([^ ]+) has_cached_tool_info_snapshot=([^ ]+)")
SKILL_BUDGET_RE = re.compile(
    r"budget_limit=([0-9]+).*?total_skills=([0-9]+).*?included_skills=([0-9]+)"
    r".*?omitted_skills=([0-9]+).*?truncated_description_chars_per_skill=([0-9]+)"
    r".*?truncated_skill_descriptions=([0-9]+)"
)
SHADOW_SKILL_RE = re.compile(
    r"catalog_entries=([0-9]+).*?selected_entries=([0-9]+).*?query_terms=([0-9]+)"
)
SKILL_PATH_RE = re.compile(
    r"(?:^|[/\\])([A-Za-z0-9][A-Za-z0-9._-]{0,63})[/\\]SKILL\.md(?:\b|$)",
    re.IGNORECASE,
)
VERIFICATION_RE = re.compile(
    r"(?:^|[;&|\s])(?:"
    r"pytest(?:\s|$)|python(?:3)?\s+-m\s+(?:pytest|unittest)(?:\s|$)|"
    r"cargo\s+test(?:\s|$)|go\s+test(?:\s|$)|swift\s+test(?:\s|$)|"
    r"xcodebuild[^\n]*(?:\s|-)test(?:\s|$)|"
    r"(?:npm|pnpm|yarn)\s+(?:run\s+)?(?:test|lint|typecheck)(?:\s|$)|"
    r"bash\s+tests?[/\\]|make\s+(?:test|check)(?:\s|$)"
    r")",
    re.IGNORECASE,
)
TIMESTAMP_BYTES_RE = re.compile(br'"timestamp"\s*:\s*"([^"]+)"')
CALL_ID_BYTES_RE = re.compile(br'"call_id"\s*:\s*"([^"]+)"')

LOG_TARGETS = (
    "codex_core::session::turn",
    "codex_core::tools::parallel",
    "codex_core::compact_remote_v2::attempt",
    "codex_core::responses_retry",
    "codex_core_skills::loader",
    "codex_core_skills::render",
    "codex_core_skills::service",
    "codex_skills_extension::shadow_selection_experiment",
    "mcp",
)

COMPARISON_LABELS = (
    ("turns", "observed turns"),
    ("token_delta", "local cumulative token change"),
    ("tool_calls", "tool calls"),
    ("tool_runtime_ms", "tool runtime"),
    ("compactions", "compactions"),
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a local Codex activity review without printing prompts or paths."
    )
    parser.add_argument(
        "--days", type=int, required=True, help="Lookback window in days (1-90)."
    )
    parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown", help="Output format."
    )
    parser.add_argument(
        "--codex-home",
        default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
        help="Codex data directory (default: CODEX_HOME or ~/.codex).",
    )
    parser.add_argument(
        "--now",
        help="Deterministic UTC endpoint for tests, for example 2026-07-17T12:00:00Z.",
    )
    rollout_group = parser.add_mutually_exclusive_group()
    rollout_group.add_argument(
        "--deep",
        action="store_true",
        help="Force a bounded reverse scan of recent rollout records for task timing, output weight, and skill-read evidence.",
    )
    rollout_group.add_argument(
        "--no-rollouts",
        action="store_true",
        help="Skip rollout enrichment and use compact SQLite telemetry only.",
    )
    parser.add_argument(
        "--max-auto-rollout-mib",
        type=int,
        default=512,
        help="Automatic rollout scan size guard in MiB (default: 512).",
    )
    parser.add_argument("--top", type=int, default=8, help="Maximum rows in ranked sections.")
    args = parser.parse_args(argv)
    if args.days < 1 or args.days > 90:
        parser.error("--days must be between 1 and 90")
    if args.max_auto_rollout_mib < 1:
        parser.error("--max-auto-rollout-mib must be positive")
    if args.top < 1 or args.top > 50:
        parser.error("--top must be between 1 and 50")
    return args


def parse_utc(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(tz=UTC).replace(microsecond=0)
    normalized = value.strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)


def iso(value: dt.datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_label(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    cleaned = SAFE_LABEL.sub("-", text).strip("-.")[:80]
    return cleaned or fallback


def match_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def human_int(value: int | float) -> str:
    return f"{int(round(value)):,}"


def human_duration(milliseconds: int | float) -> str:
    seconds = max(0, int(round(float(milliseconds) / 1000)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def human_bytes(value: int | float) -> str:
    amount = float(max(0, value))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if amount < 1024 or unit == "GiB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} GiB"


def percent(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) * 100.0 / float(denominator), 1)


def plural(count: int | float, singular: str, plural_form: str | None = None) -> str:
    return singular if int(count) == 1 else (plural_form or f"{singular}s")


def join_words(values: list[str]) -> str:
    if not values:
        return "none"
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} and {values[1]}"
    return f"{', '.join(values[:-1])}, and {values[-1]}"


def median(values: Iterable[int | float]) -> float:
    items = list(values)
    return float(statistics.median(items)) if items else 0.0


def discover_versioned_db(codex_home: Path, prefix: str) -> Path | None:
    candidates: list[tuple[int, float, Path]] = []
    for path in codex_home.glob(f"{prefix}_*.sqlite"):
        match = re.search(r"_([0-9]+)\.sqlite$", path.name)
        version = int(match.group(1)) if match else -1
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((version, mtime, path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path))}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in connection.execute(f"pragma table_info('{table}')")}
    except sqlite3.DatabaseError:
        return set()


def empty_window(label: str, start: dt.datetime, end: dt.datetime) -> dict[str, Any]:
    return {
        "label": label,
        "start": start,
        "end": end,
        "thread_ids": set(),
        "project_hashes": set(),
        "active_days": collections.Counter(),
        "turns": {},
        "turn_spans": {},
        "token_delta": 0,
        "token_resets": 0,
        "tokens_by_model": collections.Counter(),
        "tool_calls": {},
        "tool_call_ids": set(),
        "compactions": 0,
        "response_retries": 0,
        "skill_budget_events": [],
        "shadow_skill_events": [],
        "listed_mcp_tools": collections.Counter(),
        "snapshot_flags": collections.Counter(),
        "task_durations_ms": [],
        "task_time_to_first_token_ms": [],
        "task_runtime_by_model": collections.Counter(),
        "skill_reads": collections.Counter(),
        "verification_commands": 0,
        "rollout_output_bytes": collections.Counter(),
        "rollout_compactions": 0,
    }


def choose_window(timestamp: int, current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any] | None:
    if int(current["start"].timestamp()) <= timestamp < int(current["end"].timestamp()):
        return current
    if int(previous["start"].timestamp()) <= timestamp < int(previous["end"].timestamp()):
        return previous
    return None


def window_coverage(
    available_start: int | None,
    available_end: int | None,
    window: dict[str, Any],
) -> dict[str, Any]:
    start = int(window["start"].timestamp())
    end = int(window["end"].timestamp())
    duration = max(1, end - start)
    if available_start is None or available_end is None:
        return {"status": "unavailable", "coverage_percent": 0.0}

    overlap_start = max(start, available_start)
    overlap_end = min(end, available_end)
    if available_end < start or available_start >= end or overlap_end <= overlap_start:
        return {"status": "unavailable", "coverage_percent": 0.0}

    full = available_start <= start
    overlap_seconds = max(0, overlap_end - overlap_start)
    coverage_percent = 100.0 if full else round(overlap_seconds * 100.0 / duration, 1)
    return {
        "status": "full" if full else "partial",
        "coverage_percent": coverage_percent,
        "observed_start": iso(dt.datetime.fromtimestamp(overlap_start, UTC)),
        "observed_end": iso(dt.datetime.fromtimestamp(overlap_end, UTC)),
    }


def load_state(
    state_db: Path,
    previous_start: dt.datetime,
    current: dict[str, Any],
    previous: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, set[tuple[str, str]]], list[str]]:
    warnings: list[str] = []
    metadata: dict[str, dict[str, Any]] = {}
    dynamic_tools: dict[str, set[tuple[str, str]]] = collections.defaultdict(set)
    connection = connect_readonly(state_db)
    try:
        columns = table_columns(connection, "threads")
        required = {"id", "rollout_path", "updated_at"}
        if not required.issubset(columns):
            missing = ",".join(sorted(required - columns))
            raise RuntimeError(f"unsupported threads schema; missing columns: {missing}")
        optional = {
            "cwd",
            "model",
            "reasoning_effort",
            "thread_source",
            "created_at",
        }
        selected = ["id", "rollout_path", "updated_at"] + sorted(optional & columns)
        query = (
            f"select {','.join(selected)} from threads "
            "where updated_at >= ? order by updated_at"
        )
        for row in connection.execute(query, (int(previous_start.timestamp()),)):
            item = dict(row)
            thread_id = str(item.get("id") or "")
            if not thread_id:
                continue
            source = safe_label(item.get("thread_source"), "unknown")
            if source not in {"user", "subagent", "automation"}:
                source = "unknown"
            cwd = str(item.get("cwd") or "")
            project_hash = hashlib.sha256(cwd.encode("utf-8", "ignore")).hexdigest()[:12] if cwd else ""
            metadata[thread_id] = {
                "rollout_path": str(item.get("rollout_path") or ""),
                "updated_at": int(item.get("updated_at") or 0),
                "created_at": int(item.get("created_at") or 0),
                "model": safe_label(item.get("model")),
                "effort": safe_label(item.get("reasoning_effort")),
                "source": source,
                "project_hash": project_hash,
            }
            window = choose_window(int(item.get("updated_at") or 0), current, previous)
            if window:
                window["thread_ids"].add(thread_id)
                if project_hash:
                    window["project_hashes"].add(project_hash)

        dynamic_columns = table_columns(connection, "thread_dynamic_tools")
        if {"thread_id", "name"}.issubset(dynamic_columns):
            namespace_expr = "coalesce(namespace,'unknown')" if "namespace" in dynamic_columns else "'unknown'"
            dynamic_query = (
                f"select thread_id,{namespace_expr} as namespace,name "
                "from thread_dynamic_tools where thread_id in "
                "(select id from threads where updated_at >= ?)"
            )
            for row in connection.execute(dynamic_query, (int(previous_start.timestamp()),)):
                thread_id = str(row["thread_id"] or "")
                dynamic_tools[thread_id].add(
                    (safe_label(row["namespace"]), safe_label(row["name"]))
                )
        else:
            warnings.append("dynamic tool exposure unavailable in this state schema")
    finally:
        connection.close()
    return metadata, dynamic_tools, warnings


def update_turn(
    window: dict[str, Any],
    thread_id: str,
    turn_id: str,
    timestamp: int,
    model: str,
    effort: str,
) -> None:
    key = f"{thread_id}:{turn_id}"
    existing = window["turns"].get(key)
    if existing is None:
        window["turns"][key] = {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "timestamp": timestamp,
            "model": model,
            "effort": effort,
        }
    else:
        if existing["model"] == "unknown" and model != "unknown":
            existing["model"] = model
        if existing["effort"] == "unknown" and effort != "unknown":
            existing["effort"] = effort
        existing["timestamp"] = min(existing["timestamp"], timestamp)
    span = window["turn_spans"].setdefault(key, [timestamp, timestamp])
    span[0] = min(span[0], timestamp)
    span[1] = max(span[1], timestamp)


def tool_bucket(window: dict[str, Any], name: str) -> dict[str, Any]:
    return window["tool_calls"].setdefault(
        safe_label(name),
        {
            "calls": 0,
            "failures": 0,
            "duration_ms": 0.0,
            "durations_ms": [],
            "automatic_calls": 0,
            "automatic_duration_ms": 0.0,
        },
    )


def scan_logs(
    logs_db: Path,
    baseline_start: dt.datetime,
    current: dict[str, Any],
    previous: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    warnings: list[str] = []
    connection = connect_readonly(logs_db)
    last_token_by_thread: dict[str, int] = {}
    try:
        columns = table_columns(connection, "logs")
        required = {"ts", "target", "feedback_log_body", "thread_id"}
        if not required.issubset(columns):
            missing = ",".join(sorted(required - columns))
            raise RuntimeError(f"unsupported logs schema; missing columns: {missing}")
        bounds = connection.execute("select min(ts),max(ts) from logs").fetchone()
        available_start = int(bounds[0]) if bounds and bounds[0] is not None else None
        available_end = int(bounds[1]) if bounds and bounds[1] is not None else None
        coverage = {
            "available_start": iso(dt.datetime.fromtimestamp(available_start, UTC))
            if available_start is not None
            else None,
            "available_end": iso(dt.datetime.fromtimestamp(available_end, UTC))
            if available_end is not None
            else None,
            "current": window_coverage(available_start, available_end, current),
            "previous": window_coverage(available_start, available_end, previous),
            "token_baseline": window_coverage(
                available_start,
                available_end,
                {"start": baseline_start, "end": previous["start"]},
            ),
        }
        placeholders = ",".join("?" for _ in LOG_TARGETS)
        query = f"""
            select ts,coalesce(thread_id,'') as thread_id,target,feedback_log_body
            from logs
            where ts >= ? and feedback_log_body is not null and (
              target in ({placeholders})
              or feedback_log_body like '%listed MCP server tools%'
              or feedback_log_body like '%has_cached_tool_info_snapshot%'
            )
            order by ts,ts_nanos
        """
        parameters: list[Any] = [int(baseline_start.timestamp()), *LOG_TARGETS]
        for row in connection.execute(query, parameters):
            timestamp = int(row["ts"])
            thread_id = str(row["thread_id"] or "unknown")
            target = str(row["target"] or "")
            body = str(row["feedback_log_body"] or "")
            window = choose_window(timestamp, current, previous)

            model_match = MODEL_RE.search(body)
            effort_match = EFFORT_RE.search(body)
            model = safe_label(model_match.group(1) if model_match else "unknown")
            effort = safe_label(effort_match.group(1) if effort_match else "unknown")
            turn_match = TURN_ID_RE.search(body)
            turn_id = turn_match.group(1) if turn_match else ""

            if window:
                window["thread_ids"].add(thread_id)
                window["active_days"][dt.datetime.fromtimestamp(timestamp, UTC).date().isoformat()] += 1
                if turn_id:
                    update_turn(window, thread_id, turn_id, timestamp, model, effort)

            if "post sampling token usage" in body:
                total_match = TOKEN_TOTAL_RE.search(body)
                if total_match:
                    total = int(total_match.group(1))
                    prior = last_token_by_thread.get(thread_id)
                    last_token_by_thread[thread_id] = total
                    if window and prior is not None:
                        delta = total - prior
                        if delta >= 0:
                            window["token_delta"] += delta
                            window["tokens_by_model"][model] += delta
                        else:
                            window["token_resets"] += 1

            if target == "codex_core::tools::parallel" and "tool call" in body:
                name_match = TOOL_NAME_RE.search(body)
                call_match = CALL_ID_RE.search(body)
                if window and name_match:
                    call_id = call_match.group(1) if call_match else f"{thread_id}:{timestamp}:{name_match.group(1)}"
                    if call_id not in window["tool_call_ids"]:
                        window["tool_call_ids"].add(call_id)
                        bucket = tool_bucket(window, name_match.group(1))
                        bucket["calls"] += 1
                        automatic = model.startswith("codex-auto-review")
                        if automatic:
                            bucket["automatic_calls"] += 1
                        if "failed" in body.lower() or "error" in body.lower():
                            bucket["failures"] += 1
                        duration_match = TOTAL_DURATION_RE.search(body)
                        if duration_match:
                            duration = float(duration_match.group(1))
                            bucket["duration_ms"] += duration
                            bucket["durations_ms"].append(duration)
                            if automatic:
                                bucket["automatic_duration_ms"] += duration

            if window and target == "codex_core::compact_remote_v2::attempt":
                window["compactions"] += 1
            if window and target == "codex_core::responses_retry":
                window["response_retries"] += 1

            if window and "truncated skill metadata" in body:
                budget_match = SKILL_BUDGET_RE.search(body)
                if budget_match:
                    values = [int(value) for value in budget_match.groups()]
                    window["skill_budget_events"].append(
                        {
                            "budget_limit": values[0],
                            "total_skills": values[1],
                            "included_skills": values[2],
                            "omitted_skills": values[3],
                            "description_limit": values[4],
                            "truncated_descriptions": values[5],
                        }
                    )

            if window and "ran shadow skill selection" in body:
                shadow_match = SHADOW_SKILL_RE.search(body)
                if shadow_match:
                    values = [int(value) for value in shadow_match.groups()]
                    window["shadow_skill_events"].append(
                        {"catalog_entries": values[0], "selected_entries": values[1], "query_terms": values[2]}
                    )

            listed_match = MCP_LIST_RE.search(body)
            if window and listed_match:
                key = f"{safe_label(listed_match.group(1))}:{listed_match.group(2)}"
                window["listed_mcp_tools"][key] += 1
            snapshot_match = SNAPSHOT_RE.search(body)
            if window and snapshot_match:
                key = f"{safe_label(snapshot_match.group(1))}:{safe_label(snapshot_match.group(2))}"
                window["snapshot_flags"][key] += 1
    finally:
        connection.close()
    return warnings, coverage


def reverse_lines(path: Path, chunk_size: int = 1024 * 1024) -> Iterable[bytes]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        remainder = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            block = handle.read(read_size)
            parts = (block + remainder).split(b"\n")
            remainder = parts[0]
            for line in reversed(parts[1:]):
                if line:
                    yield line
        if remainder:
            yield remainder


def extract_timestamp_key(line: bytes) -> bytes | None:
    match = TIMESTAMP_BYTES_RE.search(line[:512])
    if not match:
        return None
    return match.group(1)[:19]


def text_inputs(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("input", "arguments"):
        raw = payload.get(key)
        if isinstance(raw, str):
            values.append(raw)
            try:
                decoded = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            stack: list[Any] = [decoded]
            while stack:
                item = stack.pop()
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    stack.extend(item.values())
                elif isinstance(item, list):
                    stack.extend(item)
    return values


def scan_rollouts(
    candidates: list[Path],
    current: dict[str, Any],
    previous: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    cutoff_key = previous["start"].strftime("%Y-%m-%dT%H:%M:%S").encode()
    current_key = current["start"].strftime("%Y-%m-%dT%H:%M:%S").encode()
    end_key = current["end"].strftime("%Y-%m-%dT%H:%M:%S").encode()
    files_scanned = 0
    bytes_considered = 0
    malformed = 0

    for path in candidates:
        try:
            bytes_considered += path.stat().st_size
        except OSError:
            continue
        pending_outputs: dict[tuple[str, str], int] = {}
        turn_data: dict[tuple[str, str], dict[str, Any]] = {}
        try:
            for line in reverse_lines(path):
                timestamp_key = extract_timestamp_key(line)
                if timestamp_key is None:
                    continue
                if timestamp_key < cutoff_key:
                    break
                if timestamp_key >= end_key:
                    continue
                window = current if timestamp_key >= current_key else previous
                window_name = str(window["label"])
                head = line[:4096]

                if b'custom_tool_call_output' in head or b'function_call_output' in head:
                    call_match = CALL_ID_BYTES_RE.search(head)
                    if call_match:
                        call_id = call_match.group(1).decode("utf-8", "ignore")
                        pending_outputs[(window_name, call_id)] = len(line)
                    continue

                relevant = any(
                    marker in head
                    for marker in (
                        b'custom_tool_call',
                        b'function_call',
                        b'task_complete',
                        b'turn_context',
                        b'context_compacted',
                    )
                )
                if not relevant:
                    continue
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    malformed += 1
                    continue
                record_type = record.get("type")
                payload = record.get("payload") or {}
                payload_type = payload.get("type")

                if record_type == "event_msg" and payload_type == "context_compacted":
                    window["rollout_compactions"] += 1
                    continue

                if record_type == "event_msg" and payload_type == "task_complete":
                    turn_id = safe_label(payload.get("turn_id"))
                    duration = payload.get("duration_ms")
                    first_token = payload.get("time_to_first_token_ms")
                    key = (window_name, turn_id)
                    details = turn_data.setdefault(key, {})
                    if isinstance(duration, (int, float)) and duration >= 0:
                        details["duration_ms"] = float(duration)
                    if isinstance(first_token, (int, float)) and first_token >= 0:
                        details["time_to_first_token_ms"] = float(first_token)
                    continue

                if record_type == "turn_context":
                    turn_id = safe_label(payload.get("turn_id"))
                    key = (window_name, turn_id)
                    details = turn_data.setdefault(key, {})
                    details["model"] = safe_label(payload.get("model"))
                    details["effort"] = safe_label(payload.get("effort"))
                    continue

                if record_type == "response_item" and payload_type in {"custom_tool_call", "function_call"}:
                    call_id = safe_label(payload.get("call_id"))
                    name = safe_label(payload.get("name"))
                    output_size = pending_outputs.pop((window_name, call_id), 0)
                    if output_size:
                        window["rollout_output_bytes"][name] += output_size
                    inputs = text_inputs(payload)
                    matched_skills: set[str] = set()
                    verification_seen = False
                    for text in inputs:
                        for skill_match in SKILL_PATH_RE.finditer(text):
                            matched_skills.add(safe_label(skill_match.group(1)))
                        if not verification_seen and VERIFICATION_RE.search(text):
                            verification_seen = True
                    for skill_name in matched_skills:
                        window["skill_reads"][skill_name] += 1
                    if verification_seen:
                        window["verification_commands"] += 1
        except OSError:
            warnings.append("one rollout file became unreadable during the scan")
            continue
        files_scanned += 1
        for (window_name, _turn_id), details in turn_data.items():
            window = current if window_name == current["label"] else previous
            duration = details.get("duration_ms")
            first_token = details.get("time_to_first_token_ms")
            model = safe_label(details.get("model"))
            if isinstance(duration, (int, float)):
                window["task_durations_ms"].append(duration)
                window["task_runtime_by_model"][model] += duration
            if isinstance(first_token, (int, float)):
                window["task_time_to_first_token_ms"].append(first_token)

    if malformed:
        warnings.append(f"ignored {malformed} malformed relevant rollout records")
    return {
        "status": "scanned",
        "files": files_scanned,
        "candidate_bytes": bytes_considered,
    }, warnings


def capture_cli_snapshot(codex_home: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "captured_at_report_time": True,
        "apps_feature": "unavailable",
        "plugins": {"installed": 0, "enabled": 0, "disabled": 0, "enabled_ids": []},
        "mcp": {"enabled": [], "disabled": []},
        "projects": {"stanzas": 0, "missing_directories": 0},
    }
    codex = shutil.which("codex")
    if codex:
        try:
            result = subprocess.run(
                [codex, "features", "list"], capture_output=True, text=True, timeout=8, check=False
            )
            for line in result.stdout.splitlines():
                fields = line.split()
                if fields and fields[0] == "apps":
                    snapshot["apps_feature"] = safe_label(fields[-1])
                    break
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            result = subprocess.run(
                [codex, "plugin", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            payload = json.loads(result.stdout or "{}")
            installed = payload.get("installed") if isinstance(payload, dict) else None
            if isinstance(installed, list):
                enabled_ids = sorted(
                    safe_label(item.get("pluginId") or item.get("name"))
                    for item in installed
                    if isinstance(item, dict) and item.get("enabled") is True
                )
                disabled_count = sum(
                    1 for item in installed if isinstance(item, dict) and item.get("enabled") is False
                )
                snapshot["plugins"] = {
                    "installed": len(installed),
                    "enabled": len(enabled_ids),
                    "disabled": disabled_count,
                    "enabled_ids": enabled_ids,
                    "enabled_plugins": [
                        {
                            "id": safe_label(item.get("pluginId") or item.get("name")),
                            "name": safe_label(
                                item.get("name")
                                or str(item.get("pluginId") or "").split("@", 1)[0]
                            ),
                        }
                        for item in installed
                        if isinstance(item, dict) and item.get("enabled") is True
                    ],
                }
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        try:
            result = subprocess.run(
                [codex, "mcp", "list"], capture_output=True, text=True, timeout=8, check=False
            )
            enabled: list[str] = []
            disabled: list[str] = []
            for line in result.stdout.splitlines():
                fields = line.split()
                if not fields or fields[0] == "Name":
                    continue
                if "enabled" in fields:
                    enabled.append(safe_label(fields[0]))
                elif "disabled" in fields:
                    disabled.append(safe_label(fields[0]))
            snapshot["mcp"] = {"enabled": sorted(set(enabled)), "disabled": sorted(set(disabled))}
        except (OSError, subprocess.TimeoutExpired):
            pass

    config = codex_home / "config.toml"
    if config.is_file():
        project_re = re.compile(r'^\[projects\."([^"]+)"\]')
        project_count = 0
        missing_count = 0
        try:
            with config.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = project_re.match(line.strip())
                    if not match:
                        continue
                    project_count += 1
                    if not Path(match.group(1)).is_dir():
                        missing_count += 1
            snapshot["projects"] = {
                "stanzas": project_count,
                "missing_directories": missing_count,
            }
        except OSError:
            pass
    return snapshot


def attach_state_context(
    window: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
    dynamic_tools: dict[str, set[tuple[str, str]]],
) -> None:
    for thread_id in window["thread_ids"]:
        item = metadata.get(thread_id)
        if item and item.get("project_hash"):
            window["project_hashes"].add(item["project_hash"])

    namespace_counts: collections.Counter[str] = collections.Counter()
    distinct_tools: set[tuple[str, str]] = set()
    exposed_counts: list[int] = []
    for thread_id in window["thread_ids"]:
        tools = dynamic_tools.get(thread_id)
        if tools is None:
            continue
        exposed_counts.append(len(tools))
        distinct_tools.update(tools)
        namespace_counts.update(namespace for namespace, _name in tools)
    window["dynamic_tool_summary"] = {
        "threads_with_inventory": len(exposed_counts),
        "distinct_tools": len(distinct_tools),
        "average_tools_per_thread": round(sum(exposed_counts) / len(exposed_counts), 1)
        if exposed_counts
        else 0.0,
        "namespaces": namespace_counts,
    }


def ranked_counter(
    counter: collections.Counter[str], limit: int | None = None
) -> list[dict[str, Any]]:
    return [{"name": name, "value": value} for name, value in counter.most_common(limit)]


def finalize_window(
    window: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
    top: int,
    deep_available: bool,
) -> dict[str, Any]:
    source_counts: collections.Counter[str] = collections.Counter()
    thread_models: dict[str, set[str]] = collections.defaultdict(set)
    for turn in window["turns"].values():
        thread_models[turn["thread_id"]].add(safe_label(turn.get("model")))
    for thread_id in window["thread_ids"]:
        source = metadata.get(thread_id, {}).get("source", "unknown")
        if source == "unknown" and thread_models.get(thread_id) == {"codex-auto-review"}:
            source = "auto-review"
        source_counts[source] += 1

    model_turns: collections.Counter[str] = collections.Counter()
    effort_turns: collections.Counter[str] = collections.Counter()
    working_effort_turns: collections.Counter[str] = collections.Counter()
    model_first: dict[str, int] = {}
    model_last: dict[str, int] = {}
    model_sources: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    turns_by_thread: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for turn in window["turns"].values():
        model = safe_label(turn.get("model"))
        effort = safe_label(turn.get("effort"))
        timestamp = int(turn["timestamp"])
        model_turns[model] += 1
        effort_turns[effort] += 1
        if not model.startswith("codex-auto-review"):
            working_effort_turns[effort] += 1
        model_first[model] = min(model_first.get(model, timestamp), timestamp)
        model_last[model] = max(model_last.get(model, timestamp), timestamp)
        source = metadata.get(turn["thread_id"], {}).get("source", "unknown")
        if source == "unknown" and model.startswith("codex-auto-review"):
            source = "auto-review"
        model_sources[model][source] += 1
        turns_by_thread[turn["thread_id"]].append(turn)

    model_switches = 0
    for turns in turns_by_thread.values():
        previous_model = ""
        for turn in sorted(turns, key=lambda item: item["timestamp"]):
            model = safe_label(turn.get("model"))
            if previous_model and model != previous_model:
                model_switches += 1
            previous_model = model

    span_values = [
        max(0, (end - start) * 1000) for start, end in window["turn_spans"].values()
    ]
    models = []
    all_models = set(model_turns) | set(window["tokens_by_model"]) | set(window["task_runtime_by_model"])
    for model in sorted(all_models, key=lambda name: (-model_turns[name], name)):
        models.append(
            {
                "model": model,
                "category": "automatic-review" if model.startswith("codex-auto-review") else "working-model",
                "turns": model_turns[model],
                "token_delta": int(window["tokens_by_model"][model]),
                "task_runtime_ms": int(window["task_runtime_by_model"][model])
                if deep_available
                else None,
                "user_thread_turns": int(model_sources[model].get("user", 0)),
                "thread_sources": dict(sorted(model_sources[model].items())),
                "first_observed": iso(dt.datetime.fromtimestamp(model_first[model], UTC))
                if model in model_first
                else None,
                "last_observed": iso(dt.datetime.fromtimestamp(model_last[model], UTC))
                if model in model_last
                else None,
            }
        )

    tools = []
    for name, values in window["tool_calls"].items():
        output_bytes = (
            int(window["rollout_output_bytes"].get(name, 0)) if deep_available else None
        )
        tools.append(
            {
                "tool": name,
                "calls": int(values["calls"]),
                "failures": int(values["failures"]),
                "runtime_ms": int(round(values["duration_ms"])),
                "median_runtime_ms": int(round(median(values["durations_ms"]))),
                "automatic_calls": int(values["automatic_calls"]),
                "automatic_runtime_ms": int(round(values["automatic_duration_ms"])),
                "serialized_output_bytes": output_bytes,
            }
        )
    for name, output_bytes in window["rollout_output_bytes"].items():
        if deep_available and name not in window["tool_calls"]:
            tools.append(
                {
                    "tool": name,
                    "calls": 0,
                    "failures": 0,
                    "runtime_ms": 0,
                    "median_runtime_ms": 0,
                    "automatic_calls": 0,
                    "automatic_runtime_ms": 0,
                    "serialized_output_bytes": int(output_bytes),
                }
            )
    tools.sort(key=lambda item: (-item["runtime_ms"], -item["calls"], item["tool"]))

    budget_events = window["skill_budget_events"]
    shadow_events = window["shadow_skill_events"]
    dynamic_summary = window.get("dynamic_tool_summary", {})
    namespaces = dynamic_summary.get("namespaces", collections.Counter())
    all_skill_reads = ranked_counter(window["skill_reads"]) if deep_available else None
    all_namespaces = ranked_counter(namespaces)
    result = {
        "label": window["label"],
        "start": iso(window["start"]),
        "end": iso(window["end"]),
        "threads": len(window["thread_ids"]),
        "thread_sources": dict(sorted(source_counts.items())),
        "project_areas": len(window["project_hashes"]),
        "active_days": len(window["active_days"]),
        "turns": len(window["turns"]),
        "model_switches": model_switches,
        "token_delta": int(window["token_delta"]),
        "token_resets": int(window["token_resets"]),
        "observed_turn_span_ms": int(sum(span_values)),
        "median_turn_span_ms": int(round(median(span_values))),
        "models": models[:top],
        "_all_models": models,
        "reasoning_efforts": [
            {"effort": name, "turns": count} for name, count in effort_turns.most_common(top)
        ],
        "working_reasoning_efforts": [
            {"effort": name, "turns": count}
            for name, count in working_effort_turns.most_common(top)
        ],
        "automatic_review_turns": int(model_turns.get("codex-auto-review", 0)),
        "tools": tools[:top],
        "_all_tools": tools,
        "tool_calls": sum(int(item["calls"]) for item in tools),
        "tool_runtime_ms": sum(int(item["runtime_ms"]) for item in tools),
        "tool_failures": sum(int(item["failures"]) for item in tools),
        "serialized_tool_output_bytes": sum(
            int(item["serialized_output_bytes"] or 0) for item in tools
        )
        if deep_available
        else None,
        "compactions": int(
            window["rollout_compactions"] if deep_available else window["compactions"]
        ),
        "compaction_source": "rollout" if deep_available else "log-attempt",
        "response_retries": int(window["response_retries"]),
        "tasks_completed": len(window["task_durations_ms"]) if deep_available else None,
        "task_runtime_ms": int(sum(window["task_durations_ms"]))
        if deep_available
        else None,
        "median_task_runtime_ms": int(round(median(window["task_durations_ms"])))
        if deep_available
        else None,
        "median_time_to_first_token_ms": int(
            round(median(window["task_time_to_first_token_ms"]))
        )
        if deep_available
        else None,
        "verification_commands": int(window["verification_commands"])
        if deep_available
        else None,
        "skill_reads": all_skill_reads[:top] if all_skill_reads is not None else None,
        "_all_skill_reads": all_skill_reads,
        "skill_context": {
            "metadata_truncation_events": len(budget_events),
            "max_catalog_skills": max((event["total_skills"] for event in budget_events), default=0),
            "max_omitted_skills": max((event["omitted_skills"] for event in budget_events), default=0),
            "max_truncated_descriptions": max(
                (event["truncated_descriptions"] for event in budget_events), default=0
            ),
            "shadow_selection_events": len(shadow_events),
            "max_shadow_catalog": max((event["catalog_entries"] for event in shadow_events), default=0),
            "max_shadow_selected": max((event["selected_entries"] for event in shadow_events), default=0),
        },
        "dynamic_tool_surface": {
            "threads_with_inventory": int(dynamic_summary.get("threads_with_inventory", 0)),
            "distinct_tools": int(dynamic_summary.get("distinct_tools", 0)),
            "average_tools_per_thread": float(dynamic_summary.get("average_tools_per_thread", 0.0)),
            "top_namespaces": all_namespaces[:top],
        },
        "_all_namespaces": all_namespaces,
        "listed_mcp_tools": ranked_counter(window["listed_mcp_tools"], top),
        "snapshot_flags": ranked_counter(window["snapshot_flags"], top),
    }
    return result


def public_window(window: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in window.items() if not key.startswith("_")}


def delta(
    current: int | float,
    previous: int | float,
    source: str,
    comparable: bool = True,
    reason: str | None = None,
) -> dict[str, Any]:
    if not comparable:
        return {
            "source": source,
            "comparable": False,
            "reason": reason or "source coverage is incomplete",
            "current": current,
            "previous": previous,
            "change": None,
            "change_percent": None,
        }
    change = current - previous
    change_percent = round(change * 100.0 / previous, 1) if previous else None
    return {
        "source": source,
        "comparable": True,
        "reason": None,
        "current": current,
        "previous": previous,
        "change": change,
        "change_percent": change_percent,
    }


def build_plugin_attribution(current: dict[str, Any], cli: dict[str, Any], top: int) -> list[dict[str, Any]]:
    plugins = cli.get("plugins", {}).get("enabled_plugins", [])
    skill_read_rows = current.get("_all_skill_reads")
    skill_reads = (
        {item["name"]: int(item["value"]) for item in skill_read_rows}
        if skill_read_rows is not None
        else None
    )
    namespaces = current.get("_all_namespaces", [])
    rows: list[dict[str, Any]] = []
    for plugin in plugins:
        plugin_id = safe_label(plugin.get("id"))
        plugin_name = safe_label(plugin.get("name"), plugin_id.split("@", 1)[0])
        keys = {match_key(plugin_name), match_key(plugin_id.split("@", 1)[0])}
        keys = {key for key in keys if len(key) >= 3}
        calls = 0
        runtime_ms = 0
        outputs = 0 if current.get("serialized_tool_output_bytes") is not None else None
        matched_tools: list[str] = []
        for tool in current.get("_all_tools", []):
            tool_key = match_key(tool["tool"])
            if any(key in tool_key for key in keys):
                calls += int(tool["calls"])
                runtime_ms += int(tool["runtime_ms"])
                if outputs is not None:
                    outputs += int(tool["serialized_output_bytes"] or 0)
                matched_tools.append(tool["tool"])
        reads = 0 if skill_reads is not None else None
        matched_skills: list[str] | None = [] if skill_reads is not None else None
        if skill_reads is not None and matched_skills is not None:
            for skill_name, count in skill_reads.items():
                skill_key = match_key(skill_name)
                if any(key in skill_key for key in keys):
                    reads += count
                    matched_skills.append(skill_name)
        inventoried_tools = 0
        for item in namespaces:
            namespace_key = match_key(item["name"])
            if any(key in namespace_key for key in keys):
                inventoried_tools += int(item["value"])
        if calls or (reads or 0) or inventoried_tools:
            rows.append(
                {
                    "plugin": plugin_id,
                    "matched_tool_calls": calls,
                    "matched_tool_runtime_ms": runtime_ms,
                    "matched_serialized_output_bytes": outputs,
                    "matched_skill_reads": reads,
                    "matched_inventoried_tools": inventoried_tools,
                    "matched_tools": sorted(set(matched_tools))[:top],
                    "matched_skills": sorted(set(matched_skills))[:top]
                    if matched_skills is not None
                    else None,
                    "confidence": "medium" if calls else "low",
                }
            )
    rows.sort(
        key=lambda item: (
            -item["matched_tool_runtime_ms"],
            -item["matched_tool_calls"],
            -(item["matched_skill_reads"] or 0),
            item["plugin"],
        )
    )
    return rows[:top]


def build_findings(
    current: dict[str, Any],
    cli: dict[str, Any],
    deep_status: dict[str, Any],
    plugin_attribution: list[dict[str, Any]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    source = current["thread_sources"]
    subagents = int(source.get("subagent", 0))
    if current["threads"]:
        findings.append(
            {
                "confidence": "high",
                "observed": f"Subagent threads represented {percent(subagents, current['threads']):.1f}% of {current['threads']} active threads.",
                "interpretation": "Delegated agent work was a material part of the selected period's activity." if subagents else "No subagent thread activity was observed in the retained state records.",
                "unknown": "Thread count does not measure whether the delegated work improved quality or completion time.",
            }
        )

    token_models = [
        item for item in current.get("_all_models", []) if item["token_delta"] > 0
    ]
    if token_models and current["token_delta"] > 0:
        top_model = max(token_models, key=lambda item: item["token_delta"])
        findings.append(
            {
                "confidence": "high",
                "observed": f"{top_model['model']} was associated with {human_int(top_model['token_delta'])} positive cumulative tokens in retained log coverage, {percent(top_model['token_delta'], current['token_delta']):.1f}% of the measured change.",
                "interpretation": "This was the largest observed model-associated token-change contributor in the retained telemetry.",
                "unknown": "The delta excludes unobserved first baselines, is not a billing total, and does not measure the value or difficulty of the work.",
            }
        )

    if current.get("_all_tools"):
        top_tool = max(current["_all_tools"], key=lambda item: item["runtime_ms"])
        automatic_note = ""
        if top_tool.get("automatic_calls"):
            automatic_note = f" {top_tool['automatic_calls']} of those calls were associated with automatic-review turns."
        findings.append(
            {
                "confidence": "high",
                "observed": f"{top_tool['tool']} had the largest observed tool runtime in retained log coverage: {human_duration(top_tool['runtime_ms'])} across {top_tool['calls']} {plural(top_tool['calls'], 'call')}.{automatic_note}",
                "interpretation": "It was the strongest measured tool-runtime contributor in this window.",
                "unknown": "Tool runtime does not isolate prompt-schema tokens, result tokens, or the value of the returned evidence.",
            }
        )

    skill_context = current["skill_context"]
    if skill_context["metadata_truncation_events"]:
        omitted_detail = (
            f"as many as {skill_context['max_omitted_skills']} skills were omitted"
            if skill_context["max_omitted_skills"]
            else "no skills were omitted"
        )
        findings.append(
            {
                "confidence": "high",
                "observed": f"Skill-list budget pressure appeared in {skill_context['metadata_truncation_events']} observed context-build events; as many as {skill_context['max_truncated_descriptions']} skill descriptions were shortened, and {omitted_detail}.",
                "interpretation": "The runtime shortened descriptions or omitted entries to fit its initial skills-list budget during part of the selected period.",
                "unknown": "This does not show that omitted skills, included skills, or full SKILL.md files were invoked.",
            }
        )

    surface = current["dynamic_tool_surface"]
    if surface["threads_with_inventory"]:
        findings.append(
            {
                "confidence": "medium",
                "observed": f"Dynamic-tool inventories covered {surface['threads_with_inventory']} {plural(surface['threads_with_inventory'], 'thread')} with an average of {surface['average_tools_per_thread']:.1f} tools and {surface['distinct_tools']} distinct tool names.",
                "interpretation": "This is the best retained measure of model-visible dynamic tool breadth for those threads.",
                "unknown": "Inventory rows do not prove that each tool schema was sent on every turn or that any listed tool was called.",
            }
        )

    if current["compactions"]:
        if current["compaction_source"] == "rollout":
            verb = "was" if current["compactions"] == 1 else "were"
            compaction_observed = (
                f"{current['compactions']} explicit {plural(current['compactions'], 'context-compaction event')} {verb} observed "
                "in retained rollout telemetry."
            )
            compaction_interpretation = (
                "At least one thread reached a context-management boundary during the selected period."
            )
            compaction_unknown = (
                "Compaction alone does not identify whether growth came from conversation history, "
                "tool schemas, tool output, or source evidence."
            )
        else:
            verb = "was" if current["compactions"] == 1 else "were"
            compaction_observed = (
                f"{current['compactions']} {plural(current['compactions'], 'remote-compaction attempt')} {verb} observed in retained log telemetry."
            )
            compaction_interpretation = (
                "At least one thread attempted context management during retained log coverage."
            )
            compaction_unknown = (
                "Attempt telemetry does not prove that compaction completed or identify what caused growth."
            )
        findings.append(
            {
                "confidence": "high" if current["compaction_source"] == "rollout" else "medium",
                "observed": compaction_observed,
                "interpretation": compaction_interpretation,
                "unknown": compaction_unknown,
            }
        )

    if deep_status.get("status") == "scanned" and current["serialized_tool_output_bytes"]:
        findings.append(
            {
                "confidence": "medium",
                "observed": f"The deep scan associated {human_bytes(current['serialized_tool_output_bytes'])} of serialized rollout records with tool outputs.",
                "interpretation": "This provides a relative output-weight signal across observed tools.",
                "unknown": "Serialized bytes are not model tokens and may include encoding or protocol overhead.",
            }
        )

    plugins = cli.get("plugins", {})
    if plugins.get("installed"):
        findings.append(
            {
                "confidence": "high",
                "observed": f"The report-time plugin snapshot contained {plugins.get('enabled', 0)} enabled and {plugins.get('disabled', 0)} disabled plugins.",
                "interpretation": "This records current availability for comparison with observed tool and skill surfaces.",
                "unknown": "Current enablement does not prove enablement or model attachment throughout the selected period.",
            }
        )
    if plugin_attribution:
        top_plugin = plugin_attribution[0]
        skill_read_text = (
            f"{top_plugin['matched_skill_reads']} observed SKILL.md reads"
            if top_plugin["matched_skill_reads"] is not None
            else "SKILL.md reads not measured"
        )
        findings.append(
            {
                "confidence": top_plugin["confidence"],
                "observed": f"Name matching associated {top_plugin['plugin']} with {top_plugin['matched_tool_calls']} {plural(top_plugin['matched_tool_calls'], 'tool call')}, {human_duration(top_plugin['matched_tool_runtime_ms'])} of tool runtime, and {skill_read_text}.",
                "interpretation": "This is the strongest plugin-associated activity signal available from current names and retained events.",
                "unknown": "The runtime does not retain a stable historical plugin-to-tool-to-skill attribution table, so name matches can miss or misclassify relationships.",
            }
        )
    return findings


def make_report(
    now: dt.datetime,
    days: int,
    current: dict[str, Any],
    previous: dict[str, Any],
    cli: dict[str, Any],
    deep_status: dict[str, Any],
    log_coverage: dict[str, Any],
    top: int,
    warnings: list[str],
) -> dict[str, Any]:
    logs_comparable = all(
        log_coverage.get(label, {}).get("status") == "full"
        for label in ("current", "previous")
    )
    tokens_comparable = logs_comparable and (
        log_coverage.get("token_baseline", {}).get("status") == "full"
    )
    deep_available = deep_status.get("status") == "scanned"
    log_reason = "log telemetry does not fully cover both adjacent windows"
    token_reason = "log telemetry does not fully cover both windows and the token-baseline window"
    comparisons = {
        "threads": delta(current["threads"], previous["threads"], "state"),
        "turns": delta(
            current["turns"], previous["turns"], "logs", logs_comparable, log_reason
        ),
        "token_delta": delta(
            current["token_delta"],
            previous["token_delta"],
            "logs",
            tokens_comparable,
            token_reason,
        ),
        "tool_calls": delta(
            current["tool_calls"],
            previous["tool_calls"],
            "logs",
            logs_comparable,
            log_reason,
        ),
        "tool_runtime_ms": delta(
            current["tool_runtime_ms"],
            previous["tool_runtime_ms"],
            "logs",
            logs_comparable,
            log_reason,
        ),
        "compactions": delta(
            current["compactions"],
            previous["compactions"],
            "rollouts" if deep_available else "logs",
            deep_available or logs_comparable,
            None if deep_available else log_reason,
        ),
    }
    plugin_attribution = build_plugin_attribution(current, cli, top)
    report_warnings = list(warnings)
    if not logs_comparable:
        report_warnings.append(
            "log retention does not fully cover both adjacent windows; log-derived comparisons are unavailable"
        )
    elif not tokens_comparable:
        report_warnings.append(
            "the token-baseline window is not fully retained; token-change comparison is unavailable"
        )
    coverage = {
        "state": {
            "status": "retained_index",
            "historical_completeness": "unknown",
        },
        "logs": log_coverage,
        "rollouts": {
            "status": "retained_scan" if deep_available else "not_scanned",
            "historical_completeness": "unknown",
        },
    }
    findings = build_findings(current, cli, deep_status, plugin_attribution)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso(now),
        "days": days,
        "privacy": {
            "local_only": True,
            "read_only_inputs": True,
            "omitted": [
                "prompts",
                "responses",
                "thread titles",
                "thread ids",
                "commands",
                "tool results",
                "full paths",
                "secrets",
            ],
        },
        "current": public_window(current),
        "previous": public_window(previous),
        "comparison": comparisons,
        "coverage": coverage,
        "report_time_snapshot": cli,
        "plugin_attribution": plugin_attribution,
        "rollout_detail": deep_status,
        "findings": findings,
        "warnings": sorted(set(report_warnings)),
    }


def comparison_text(entry: dict[str, Any]) -> str:
    if not entry.get("comparable", True):
        return "prior comparison unavailable"
    change = entry["change"]
    prefix = "+" if change > 0 else ""
    percent_value = entry.get("change_percent")
    if percent_value is None:
        return f"{prefix}{human_int(change)}; no prior baseline"
    return f"{prefix}{human_int(change)} ({prefix}{percent_value:.1f}%)"


def optional_duration(value: int | float | None) -> str:
    if value is None:
        return "not measured"
    if not value:
        return "n/a"
    return human_duration(value)


def optional_bytes(value: int | float | None) -> str:
    return "not measured" if value is None else human_bytes(value)


def optional_count(value: int | float | None) -> str:
    return "not measured" if value is None else human_int(value)


def coverage_text(entry: dict[str, Any]) -> str:
    status = str(entry.get("status", "unavailable"))
    coverage_percent = entry.get("coverage_percent")
    if isinstance(coverage_percent, (int, float)):
        return f"**{status}** ({coverage_percent:.1f}%)"
    return f"**{status}**"


def render_markdown(report: dict[str, Any], top: int) -> str:
    current = report["current"]
    comparison = report["comparison"]
    suppressed_comparisons = [
        label
        for key, label in COMPARISON_LABELS
        if not comparison.get(key, {}).get("comparable", True)
    ]
    compaction_label = (
        "Compactions" if current["compaction_source"] == "rollout" else "Compaction attempts"
    )
    lines = [
        "# Codex Activity Review",
        "",
        f"Generated: `{report['generated_at']}`  ",
        f"Window: `{current['start']}` through `{current['end']}`",
        "",
        f"> This is a rolling {report['days']}-day ({report['days'] * 24}-hour) window, so observed activity can fall across parts of up to {report['days'] + 1} UTC calendar dates.",
        "",
        "> Local, read-only telemetry review. Prompts, responses, titles, thread IDs, commands, tool results, full paths, and secrets are excluded.",
        "",
        "## Period at a glance",
        "",
        f"- **Threads active:** {human_int(current['threads'])} ({comparison_text(comparison['threads'])} from the prior window)",
        f"- **Observed turns:** {human_int(current['turns'])} ({comparison_text(comparison['turns'])})",
        f"- **Local cumulative token change:** {human_int(current['token_delta'])} ({comparison_text(comparison['token_delta'])})",
        f"- **Tool calls:** {human_int(current['tool_calls'])} with {human_duration(current['tool_runtime_ms'])} observed runtime",
        f"- **Project areas:** {human_int(current['project_areas'])} across {human_int(current['active_days'])} UTC calendar dates with observed activity",
        f"- **{compaction_label}:** {human_int(current['compactions'])}; **response retries:** {human_int(current['response_retries'])}",
    ]
    if current["tasks_completed"]:
        lines.append(
            f"- **Deep task timing:** {human_int(current['tasks_completed'])} completed {plural(current['tasks_completed'], 'task')}; median {human_duration(current['median_task_runtime_ms'])}; median first token {human_duration(current['median_time_to_first_token_ms'])}"
        )

    lines.extend(["", "### Thread sources", "", "| Source | Threads | Share |", "|---|---:|---:|"])
    for source, count in sorted(current["thread_sources"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {source} | {human_int(count)} | {percent(count, current['threads']):.1f}% |")

    lines.extend(
        [
            "",
            "## Model and reasoning activity",
            "",
            "Model timing below is observed end-to-end turn or task activity. It includes tool work, can overlap across concurrent tasks, and is not pure model inference time.",
            "",
            "| Model | Category | Turns | User-thread turns | Token change | Deep task runtime | First observed | Last observed |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for model in current["models"][:top]:
        lines.append(
            f"| {model['model']} | {model['category']} | {human_int(model['turns'])} | {human_int(model['user_thread_turns'])} | {human_int(model['token_delta'])} | {optional_duration(model['task_runtime_ms'])} | {model['first_observed'] or 'n/a'} | {model['last_observed'] or 'n/a'} |"
        )
    if not current["models"]:
        lines.append("| unavailable | unknown | 0 | 0 | 0 | n/a | n/a | n/a |")

    lines.extend(["", "### Working-model reasoning levels", "", "| Level | Turns |", "|---|---:|"])
    for item in current["working_reasoning_efforts"][:top]:
        lines.append(f"| {item['effort']} | {human_int(item['turns'])} |")
    if not current["working_reasoning_efforts"]:
        lines.append("| unavailable | 0 |")
    lines.append(
        f"\nAutomatic-review turns are separated from this table: **{human_int(current['automatic_review_turns'])}** observed. Model switches between turns: **{human_int(current['model_switches'])}**."
    )

    lines.extend(
        [
            "",
            "## Tool activity",
            "",
            "| Tool | Calls | Auto-review calls | Runtime | Median call | Failures | Serialized output |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for tool in current["tools"][:top]:
        lines.append(
            f"| {tool['tool']} | {human_int(tool['calls'])} | {human_int(tool['automatic_calls'])} | {human_duration(tool['runtime_ms'])} | {human_duration(tool['median_runtime_ms'])} | {human_int(tool['failures'])} | {optional_bytes(tool['serialized_output_bytes'])} |"
        )
    if not current["tools"]:
        lines.append("| unavailable | 0 | 0 | 0s | 0s | 0 | not measured |")
    tool_names = {item["tool"] for item in current["tools"]}
    if {"exec", "exec_command"}.issubset(tool_names):
        lines.extend(
            [
                "",
                "`exec` and `exec_command` are separate retained runtime labels in this build. One workflow can pass through both an outer orchestration layer and a nested command dispatch, so the rows are not automatically distinct user actions.",
            ]
        )

    surface = current["dynamic_tool_surface"]
    lines.extend(
        [
            "",
            "### Available surface",
            "",
            f"Dynamic-tool inventory was retained for **{human_int(surface['threads_with_inventory'])}** {plural(surface['threads_with_inventory'], 'thread')}: **{human_int(surface['distinct_tools'])}** distinct tools, averaging **{surface['average_tools_per_thread']:.1f}** per inventoried thread.",
        ]
    )
    if surface["top_namespaces"]:
        lines.append("")
        lines.append("| Namespace | Inventoried tools |")
        lines.append("|---|---:|")
        for item in surface["top_namespaces"][:top]:
            lines.append(f"| {item['name']} | {human_int(item['value'])} |")

    skill_context = current["skill_context"]
    lines.extend(
        [
            "",
            "## Skills and plugins",
            "",
            f"- Skill-list budget-pressure events: **{human_int(skill_context['metadata_truncation_events'])}**",
            f"- Largest observed skill catalog: **{human_int(skill_context['max_catalog_skills'])}**; most descriptions shortened in one event: **{human_int(skill_context['max_truncated_descriptions'])}**; most skills omitted in one event: **{human_int(skill_context['max_omitted_skills'])}**",
            "- Description shortening and whole-skill omission are separate signals; zero omitted skills can coexist with shortened descriptions.",
            f"- Shadow-selection observations: **{human_int(skill_context['shadow_selection_events'])}**. These are experimental selection signals, not confirmed skill invocations.",
        ]
    )
    if current["skill_reads"] is None:
        lines.extend(["", "Observed `SKILL.md` reads: **not measured**."])
    elif current["skill_reads"]:
        lines.extend(["", "Observed `SKILL.md` reads from the deep rollout scan:", "", "| Skill | Reads |", "|---|---:|"])
        for item in current["skill_reads"][:top]:
            lines.append(f"| {item['name']} | {human_int(item['value'])} |")
    else:
        lines.extend(["", "Observed `SKILL.md` reads from the deep rollout scan: **0**."])
    plugins = report["report_time_snapshot"]["plugins"]
    lines.append(
        f"\nReport-time plugin snapshot: **{human_int(plugins.get('enabled', 0))} enabled**, **{human_int(plugins.get('disabled', 0))} disabled**. Enablement does not prove model attachment or use during the selected period."
    )
    if report["plugin_attribution"]:
        lines.extend(
            [
                "",
                "Heuristic plugin attribution uses normalized name matches across observed tools, skill reads, and dynamic namespaces:",
                "",
                "| Plugin | Confidence | Tool calls | Tool runtime | Skill reads | Inventoried tools |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for item in report["plugin_attribution"][:top]:
            lines.append(
                f"| {item['plugin']} | {item['confidence']} | {human_int(item['matched_tool_calls'])} | {human_duration(item['matched_tool_runtime_ms'])} | {optional_count(item['matched_skill_reads'])} | {human_int(item['matched_inventoried_tools'])} |"
            )

    lines.extend(["", "## Attribution findings", ""])
    for index, finding in enumerate(report["findings"], start=1):
        lines.extend(
            [
                f"### {index}. {finding['confidence'].title()} confidence",
                "",
                f"- **Observed:** {finding['observed']}",
                f"- **Interpretation:** {finding['interpretation']}",
                f"- **Unknown:** {finding['unknown']}",
                "",
            ]
        )

    log_coverage = report["coverage"]["logs"]
    lines.extend(
        [
            "## Questions raised by the review",
            "",
            "- Which high-reasoning turns involved judgment that benefited from the additional depth?",
            "- Which repeated tool calls produced evidence that materially changed the work?",
            "- Which long or compacted threads should remain continuous, and which work naturally fits a fresh focused task?",
            "",
            "## Coverage and uncertainty",
            "",
            f"- Rollout detail: **{report['rollout_detail'].get('status', 'unknown')}**.",
            f"- Log coverage: current {coverage_text(log_coverage['current'])}; previous {coverage_text(log_coverage['previous'])}; token baseline {coverage_text(log_coverage['token_baseline'])}.",
            f"- Suppressed prior-period comparisons: **{join_words(suppressed_comparisons)}**.",
            "- State-derived thread counts come from the retained thread index; historical completeness is unknown.",
            "- Deep-only values are shown as not measured when rollout enrichment does not run.",
            "- Token changes are local cumulative telemetry deltas, not billing totals.",
            "- Tool and deep task runtimes can overlap across concurrent threads and do not measure schema or result tokens.",
            "- Plugin and MCP snapshots describe report-time configuration unless a timestamped event was observed.",
        ]
    )
    for warning in report["warnings"]:
        lines.append(f"- Warning: {warning}.")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    now = parse_utc(args.now)
    current_start = now - dt.timedelta(days=args.days)
    previous_start = current_start - dt.timedelta(days=args.days)
    baseline_start = previous_start - dt.timedelta(days=args.days)
    current = empty_window("current", current_start, now)
    previous = empty_window("previous", previous_start, current_start)
    codex_home = Path(args.codex_home).expanduser().resolve()
    warnings: list[str] = []

    state_db = discover_versioned_db(codex_home, "state")
    logs_db = discover_versioned_db(codex_home, "logs")
    if state_db is None:
        print("missing state database under CODEX_HOME", file=sys.stderr)
        return 3
    if logs_db is None:
        print("missing logs database under CODEX_HOME", file=sys.stderr)
        return 3

    try:
        metadata, dynamic_tools, state_warnings = load_state(
            state_db, previous_start, current, previous
        )
        warnings.extend(state_warnings)
        log_warnings, log_coverage = scan_logs(
            logs_db, baseline_start, current, previous
        )
        warnings.extend(log_warnings)
    except (sqlite3.DatabaseError, RuntimeError, OSError) as error:
        print(f"unable to read supported Codex telemetry: {error}", file=sys.stderr)
        return 3

    attach_state_context(current, metadata, dynamic_tools)
    attach_state_context(previous, metadata, dynamic_tools)

    candidate_paths: list[Path] = []
    candidate_bytes = 0
    for item in metadata.values():
        raw_path = item.get("rollout_path")
        if not raw_path:
            continue
        path = Path(str(raw_path))
        try:
            resolved_path = path.resolve()
            resolved_path.relative_to(codex_home)
        except (OSError, ValueError):
            warnings.append("ignored a rollout path outside CODEX_HOME")
            continue
        if not resolved_path.is_file():
            continue
        candidate_paths.append(resolved_path)
        try:
            candidate_bytes += resolved_path.stat().st_size
        except OSError:
            pass
    unique_candidates = sorted(set(candidate_paths))
    guard_bytes = args.max_auto_rollout_mib * 1024 * 1024
    if args.no_rollouts:
        deep_status = {
            "status": "skipped_by_request",
            "files": 0,
            "candidate_bytes": candidate_bytes,
        }
    elif args.deep or candidate_bytes <= guard_bytes:
        deep_status, deep_warnings = scan_rollouts(unique_candidates, current, previous)
        warnings.extend(deep_warnings)
    else:
        required_guard_mib = max(1, math.ceil(candidate_bytes / (1024 * 1024)))
        deep_status = {
            "status": "skipped_size_guard",
            "files": len(unique_candidates),
            "candidate_bytes": candidate_bytes,
            "guard_bytes": guard_bytes,
        }
        warnings.append(
            f"deep rollout enrichment skipped by the {human_bytes(guard_bytes)} automatic size guard because candidates total {human_bytes(candidate_bytes)}; rerun with --max-auto-rollout-mib {required_guard_mib} to approve this measured size while retaining a guard, or use --deep to ignore the guard"
        )

    deep_available = deep_status.get("status") == "scanned"
    current_final = finalize_window(current, metadata, args.top, deep_available)
    previous_final = finalize_window(previous, metadata, args.top, deep_available)
    cli = capture_cli_snapshot(codex_home)
    report = make_report(
        now,
        args.days,
        current_final,
        previous_final,
        cli,
        deep_status,
        log_coverage,
        args.top,
        warnings,
    )
    if args.format == "json":
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(report, args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
