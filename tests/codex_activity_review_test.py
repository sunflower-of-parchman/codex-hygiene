#!/usr/bin/env python3

import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "codex_activity_review.py"
UTC = dt.timezone.utc


def epoch(value: str) -> int:
    return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


class CodexActivityReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.codex_home = self.root / "codex-home"
        self.bin_dir = self.root / "bin"
        self.codex_home.mkdir()
        self.bin_dir.mkdir()
        self.existing_project = self.root / "private-project"
        self.existing_project.mkdir()
        self.rollout = self.codex_home / "private-rollout.jsonl"
        self._create_state()
        self._create_logs()
        self._create_rollout()
        self._create_config()
        self._create_codex_stub()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_state(self) -> None:
        connection = sqlite3.connect(self.codex_home / "state_5.sqlite")
        connection.executescript(
            """
            create table threads (
              id text primary key,
              rollout_path text not null,
              created_at integer not null,
              updated_at integer not null,
              cwd text,
              model text,
              reasoning_effort text,
              thread_source text,
              title text
            );
            create table thread_dynamic_tools (
              thread_id text not null,
              position integer not null,
              name text not null,
              description text not null,
              input_schema text not null,
              defer_loading integer not null,
              namespace text,
              primary key (thread_id, position)
            );
            """
        )
        connection.executemany(
            "insert into threads values (?,?,?,?,?,?,?,?,?)",
            [
                (
                    "thread-user-secret",
                    str(self.rollout),
                    epoch("2026-07-01T00:00:00Z"),
                    epoch("2026-07-16T10:00:00Z"),
                    str(self.existing_project),
                    "gpt-5.6-sol",
                    "max",
                    "user",
                    "private thread title",
                ),
                (
                    "thread-subagent-secret",
                    "",
                    epoch("2026-07-08T00:00:00Z"),
                    epoch("2026-07-09T10:00:00Z"),
                    str(self.existing_project),
                    "gpt-5.6-terra",
                    "medium",
                    "subagent",
                    "private subagent title",
                ),
            ],
        )
        connection.executemany(
            "insert into thread_dynamic_tools values (?,?,?,?,?,?,?)",
            [
                ("thread-user-secret", 0, "exec", "private description", "{}", 0, "functions"),
                ("thread-user-secret", 1, "search", "private description", "{}", 0, "web"),
            ],
        )
        connection.commit()
        connection.close()

    def _create_logs(self) -> None:
        connection = sqlite3.connect(self.codex_home / "logs_2.sqlite")
        connection.executescript(
            """
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
            """
        )
        rows = [
            (
                epoch("2026-07-09T11:00:00Z"),
                "codex_core::session::turn",
                "turn{thread.id=thread-user-secret turn.id=turn-before model=gpt-5.5 codex.turn.reasoning_effort=high}: post sampling token usage turn_id=turn-before total_usage_tokens=100",
                "thread-user-secret",
            ),
            (
                epoch("2026-07-12T11:00:00Z"),
                "codex_core::session::turn",
                "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: post sampling token usage turn_id=turn-current total_usage_tokens=250",
                "thread-user-secret",
            ),
            (
                epoch("2026-07-12T11:00:01Z"),
                "codex_core::tools::parallel",
                "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: tool call completed tool_name=exec call_id=call-one total_duration_ms=1200",
                "thread-user-secret",
            ),
            (
                epoch("2026-07-12T11:00:02Z"),
                "codex_core_skills::render",
                "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: truncated skill metadata to fit skills context budget budget_limit=8000 total_skills=140 included_skills=140 omitted_skills=0 truncated_description_chars_per_skill=24 truncated_skill_descriptions=100",
                "thread-user-secret",
            ),
            (
                epoch("2026-07-12T11:00:03Z"),
                "codex_skills_extension::shadow_selection_experiment",
                "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: ran shadow skill selection catalog_entries=140 selected_entries=3 query_terms=5",
                "thread-user-secret",
            ),
            (
                epoch("2026-07-12T11:00:04Z"),
                "codex_core::compact_remote_v2::attempt",
                "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: rewrote history outputs before remote compaction v2 turn_id=turn-current",
                "thread-user-secret",
            ),
            (
                epoch("2026-07-12T11:00:05Z"),
                "codex_core::responses_retry",
                "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: retrying response",
                "thread-user-secret",
            ),
            (
                epoch("2026-07-12T11:00:06Z"),
                "mcp",
                "listed MCP server tools server_name=example tool_count=12",
                "thread-user-secret",
            ),
        ]
        connection.executemany(
            "insert into logs (ts,ts_nanos,level,target,feedback_log_body,thread_id,estimated_bytes) values (?,0,'INFO',?,?,?,0)",
            rows,
        )
        connection.commit()
        connection.close()

    def _append_logs(self, rows: list[tuple[int, str, str | None, str]]) -> None:
        connection = sqlite3.connect(self.codex_home / "logs_2.sqlite")
        connection.executemany(
            "insert into logs (ts,ts_nanos,level,target,feedback_log_body,thread_id,estimated_bytes) values (?,0,'INFO',?,?,?,0)",
            rows,
        )
        connection.commit()
        connection.close()

    def _create_rollout(self) -> None:
        secret_command = (
            f"bash tests/private_test.sh && sed -n '1,20p' "
            f"{self.root}/skills/codex-hygiene/SKILL.md"
        )
        records = [
            {
                "timestamp": "2026-07-12T11:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "private user prompt"}],
                },
            },
            {
                "timestamp": "2026-07-12T11:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "private assistant response"}
                    ],
                },
            },
            {
                "timestamp": "2026-07-12T11:00:00Z",
                "type": "turn_context",
                "payload": {"turn_id": "turn-current", "model": "gpt-5.6-sol", "effort": "max"},
            },
            {
                "timestamp": "2026-07-12T11:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "call-one",
                    "name": "exec",
                    "input": json.dumps({"cmd": secret_command}),
                },
            },
            {
                "timestamp": "2026-07-12T11:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call-one",
                    "output": "private tool result /Users/example/secret token=do-not-print",
                },
            },
            {
                "timestamp": "2026-07-12T11:00:03Z",
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-current",
                    "duration_ms": 5000,
                    "time_to_first_token_ms": 700,
                },
            },
            {
                "timestamp": "2026-07-12T11:00:04Z",
                "type": "event_msg",
                "payload": {"type": "context_compacted"},
            },
        ]
        write_jsonl(self.rollout, records)

    def _create_config(self) -> None:
        missing = self.root / "missing-private-project"
        self.codex_home.joinpath("config.toml").write_text(
            f'[projects."{self.existing_project}"]\ntrust_level = "trusted"\n\n'
            f'[projects."{missing}"]\ntrust_level = "trusted"\n',
            encoding="utf-8",
        )

    def _create_codex_stub(self) -> None:
        stub = self.bin_dir / "codex"
        stub.write_text(
            """#!/bin/sh
case "$1 $2" in
  "features list") echo "apps stable false" ;;
  "plugin list") echo '{"installed":[{"pluginId":"exec@local","name":"exec","enabled":true},{"pluginId":"beta@local","enabled":false}]}' ;;
  "mcp list") printf 'Name Status\\nalpha enabled\\nbeta disabled\\n' ;;
  *) exit 1 ;;
esac
""",
            encoding="utf-8",
        )
        stub.chmod(0o755)

    def run_report(self, *extra: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--codex-home",
                str(self.codex_home),
                "--now",
                "2026-07-17T12:00:00Z",
                "--days",
                "7",
                *extra,
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_deep_json_report_is_attributed_and_private(self) -> None:
        result = self.run_report("--deep", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        current = report["current"]

        self.assertEqual(report["schema_version"], "0.2.0")
        self.assertEqual(current["token_delta"], 150)
        self.assertEqual(current["tool_calls"], 1)
        self.assertEqual(current["tool_runtime_ms"], 1200)
        self.assertEqual(current["tasks_completed"], 1)
        self.assertEqual(current["median_task_runtime_ms"], 5000)
        self.assertEqual(current["compactions"], 1)
        self.assertEqual(current["verification_commands"], 1)
        self.assertEqual(current["dynamic_tool_surface"]["distinct_tools"], 2)
        self.assertEqual(current["skill_context"]["max_omitted_skills"], 0)
        self.assertEqual(current["skill_context"]["max_truncated_descriptions"], 100)
        self.assertEqual(current["skill_reads"][0], {"name": "codex-hygiene", "value": 1})
        self.assertGreater(current["serialized_tool_output_bytes"], 0)
        self.assertEqual(current["compaction_source"], "rollout")
        self.assertEqual(report["previous"]["tasks_completed"], 0)
        self.assertEqual(report["previous"]["skill_reads"], [])
        self.assertEqual(report["previous"]["serialized_tool_output_bytes"], 0)
        self.assertEqual(report["previous"]["compactions"], 0)
        self.assertEqual(report["previous"]["compaction_source"], "rollout")
        self.assertEqual(report["rollout_detail"]["status"], "scanned")
        self.assertEqual(report["report_time_snapshot"]["plugins"]["enabled"], 1)
        self.assertEqual(report["report_time_snapshot"]["projects"]["missing_directories"], 1)
        self.assertEqual(report["plugin_attribution"][0]["plugin"], "exec@local")
        self.assertEqual(report["plugin_attribution"][0]["matched_tool_calls"], 1)

        serialized = json.dumps(report)
        for private_value in (
            str(self.root),
            "private-project",
            "thread-user-secret",
            "turn-current",
            "call-one",
            "do-not-print",
            "private user prompt",
            "private assistant response",
            "private thread title",
            "private subagent title",
            "private tool result",
            "private_test.sh",
            "/Users/example/secret",
        ):
            self.assertNotIn(private_value, serialized)

    def test_markdown_labels_evidence_and_uncertainty(self) -> None:
        result = self.run_report("--deep")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# Codex Activity Review", result.stdout)
        self.assertIn("**Observed:**", result.stdout)
        self.assertIn("**Interpretation:**", result.stdout)
        self.assertIn("**Unknown:**", result.stdout)
        self.assertIn("working-model", result.stdout)
        self.assertIn("codex-hygiene", result.stdout)
        self.assertIn("prior comparison unavailable", result.stdout)
        self.assertIn("Log coverage:", result.stdout)
        self.assertIn(
            "Suppressed prior-period comparisons: **observed turns, local cumulative token change, tool calls, and tool runtime**.",
            result.stdout,
        )
        self.assertIn("rolling 7-day (168-hour) window", result.stdout)
        self.assertIn("most descriptions shortened in one event: **100**", result.stdout)
        self.assertIn("most skills omitted in one event: **0**", result.stdout)
        self.assertIn("zero omitted skills can coexist with shortened descriptions", result.stdout)
        self.assertIn("Prompts, responses, titles, thread IDs", result.stdout)
        self.assertIn("stay private", result.stdout)
        self.assertNotIn("Questions raised by the review", result.stdout)
        for private_value in (
            str(self.root),
            "private user prompt",
            "private assistant response",
            "private thread title",
            "private subagent title",
            "thread-user-secret",
            "turn-current",
            "call-one",
            "private_test.sh",
            "private tool result",
            "do-not-print",
            "/Users/example/secret",
        ):
            self.assertNotIn(private_value, result.stdout)

    def test_markdown_explains_nested_exec_runtime_labels(self) -> None:
        self._append_logs(
            [
                (
                    epoch("2026-07-12T11:00:07Z"),
                    "codex_core::tools::parallel",
                    "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: tool call completed tool_name=exec_command call_id=call-two total_duration_ms=500",
                    "thread-user-secret",
                )
            ]
        )
        result = self.run_report("--no-rollouts")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "`exec` and `exec_command` are separate retained runtime labels",
            result.stdout,
        )
        self.assertIn("The count of distinct user actions remains unknown", result.stdout)

    def test_no_rollouts_keeps_core_report_available(self) -> None:
        result = self.run_report("--no-rollouts", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["rollout_detail"]["status"], "skipped_by_request")
        self.assertIsNone(report["current"]["tasks_completed"])
        self.assertIsNone(report["current"]["task_runtime_ms"])
        self.assertIsNone(report["current"]["median_task_runtime_ms"])
        self.assertIsNone(report["current"]["median_time_to_first_token_ms"])
        self.assertIsNone(report["current"]["verification_commands"])
        self.assertIsNone(report["current"]["skill_reads"])
        self.assertIsNone(report["current"]["serialized_tool_output_bytes"])
        self.assertTrue(
            all(item["task_runtime_ms"] is None for item in report["current"]["models"])
        )
        self.assertTrue(
            all(
                item["serialized_output_bytes"] is None
                for item in report["current"]["tools"]
            )
        )
        self.assertIsNone(report["plugin_attribution"][0]["matched_skill_reads"])
        self.assertIsNone(
            report["plugin_attribution"][0]["matched_serialized_output_bytes"]
        )
        finding_text = json.dumps(report["findings"])
        self.assertIn("SKILL.md reads not measured", finding_text)
        self.assertNotIn("0 observed SKILL.md reads", finding_text)
        self.assertEqual(report["current"]["compaction_source"], "log-attempt")
        self.assertEqual(report["current"]["tool_calls"], 1)
        self.assertEqual(report["current"]["token_delta"], 150)
        markdown = self.run_report("--no-rollouts")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn(
            "Suppressed prior-period comparisons: **observed turns, local cumulative token change, tool calls, tool runtime, and compactions**.",
            markdown.stdout,
        )

    def test_partial_log_retention_suppresses_comparisons(self) -> None:
        result = self.run_report("--no-rollouts", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        coverage = report["coverage"]["logs"]
        self.assertEqual(coverage["current"]["status"], "full")
        self.assertEqual(coverage["previous"]["status"], "partial")
        self.assertEqual(coverage["token_baseline"]["status"], "unavailable")
        self.assertTrue(report["comparison"]["threads"]["comparable"])
        for key in ("turns", "token_delta", "tool_calls", "tool_runtime_ms", "compactions"):
            self.assertFalse(report["comparison"][key]["comparable"])
            self.assertIsNone(report["comparison"][key]["change"])
            self.assertIsNone(report["comparison"][key]["change_percent"])
        self.assertTrue(
            any("full retained log coverage" in warning for warning in report["warnings"])
        )

    def test_full_log_retention_allows_comparisons(self) -> None:
        self._append_logs(
            [(epoch("2026-06-26T12:00:00Z"), "coverage", None, "")]
        )
        result = self.run_report("--no-rollouts", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        coverage = report["coverage"]["logs"]
        self.assertEqual(coverage["current"]["status"], "full")
        self.assertEqual(coverage["previous"]["status"], "full")
        self.assertEqual(coverage["token_baseline"]["status"], "full")
        for key in ("turns", "token_delta", "tool_calls", "tool_runtime_ms", "compactions"):
            self.assertTrue(report["comparison"][key]["comparable"])
            self.assertIsNotNone(report["comparison"][key]["change"])

    def test_top_limits_display_without_changing_attribution(self) -> None:
        self._append_logs(
            [
                (
                    epoch("2026-07-13T11:00:00Z"),
                    "codex_core::session::turn",
                    "turn{thread.id=auto-thread turn.id=auto-one model=codex-auto-review codex.turn.reasoning_effort=medium}: post sampling token usage turn_id=auto-one total_usage_tokens=10",
                    "auto-thread",
                ),
                (
                    epoch("2026-07-14T11:00:00Z"),
                    "codex_core::session::turn",
                    "turn{thread.id=auto-thread turn.id=auto-two model=codex-auto-review codex.turn.reasoning_effort=medium}: post sampling token usage turn_id=auto-two total_usage_tokens=20",
                    "auto-thread",
                ),
                (
                    epoch("2026-07-15T11:00:00Z"),
                    "codex_core::tools::parallel",
                    "turn{thread.id=thread-user-secret turn.id=turn-current model=gpt-5.6-sol codex.turn.reasoning_effort=max}: tool call completed tool_name=exec_secondary call_id=call-two total_duration_ms=1",
                    "thread-user-secret",
                ),
            ]
        )
        top_one = json.loads(
            self.run_report("--no-rollouts", "--top", "1", "--format", "json").stdout
        )
        top_all = json.loads(
            self.run_report("--no-rollouts", "--top", "50", "--format", "json").stdout
        )
        self.assertEqual(len(top_one["current"]["models"]), 1)
        self.assertGreater(len(top_all["current"]["models"]), 1)
        self.assertEqual(top_one["findings"], top_all["findings"])
        token_finding = next(
            item for item in top_one["findings"] if "cumulative tokens" in item["observed"]
        )
        self.assertIn("gpt-5.6-sol", token_finding["observed"])
        self.assertEqual(
            top_one["plugin_attribution"][0]["matched_tool_calls"], 2
        )
        self.assertEqual(
            top_one["plugin_attribution"][0]["matched_tool_calls"],
            top_all["plugin_attribution"][0]["matched_tool_calls"],
        )

    def test_lookback_window_must_be_selected(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT), "--codex-home", str(self.codex_home), "--no-rollouts"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--days", result.stderr)

    def test_automatic_rollout_size_guard_is_visible(self) -> None:
        with self.rollout.open("a", encoding="utf-8") as handle:
            handle.write(" " * (2 * 1024 * 1024))
        result = self.run_report("--max-auto-rollout-mib", "1", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["rollout_detail"]["status"], "skipped_size_guard")
        self.assertIsNone(report["current"]["tasks_completed"])
        self.assertIsNone(report["current"]["skill_reads"])
        self.assertIsNone(report["current"]["serialized_tool_output_bytes"])
        self.assertTrue(any("disk-work threshold" in item for item in report["warnings"]))
        self.assertTrue(any("core SQLite review is available" in item for item in report["warnings"]))
        self.assertTrue(
            any("--max-auto-rollout-mib 3" in item for item in report["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
