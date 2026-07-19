# Activity Review Reference

Use this reference to interpret `scripts/codex_activity_review.py` output and its evidence scope.

## Contents

- [Inputs](#inputs)
- [Windows](#windows)
- [Coverage and comparison](#coverage-and-comparison)
- [Measurements](#measurements)
- [Rollout enrichment](#rollout-enrichment)
- [Attribution language](#attribution-language)
- [Privacy](#privacy)

## Inputs

The report discovers the newest versioned `state_*.sqlite` and `logs_*.sqlite` databases under `CODEX_HOME` and opens them read-only.

It uses retained state for thread class, project-area count, current model metadata, rollout locations, and dynamic-tool inventory. It uses compact log rows for model and reasoning observations, within-window cumulative token changes, tool calls and runtimes, compaction attempts, response retries, skill-catalog pressure, MCP tool-list rows, and snapshot flags.

Current `codex` CLI output supplies a report-time plugin, MCP, and Apps feature snapshot. Historical state remains unknown.

## Windows

`--days N` creates two adjacent N-day windows ending at report generation time. The caller selects a lookback from 1 to 90 days. The current period is compared with the preceding period. A third preceding window supplies token baselines and reduces the chance that the first current-period observation absorbs older thread history.

The window is a rolling span of N 24-hour periods. It can touch parts of up to N+1 UTC calendar dates, and the report labels active dates accordingly.

Threads may span both periods. Counts describe observed activity within each period. Thread creation time sits outside this measure.

## Coverage And Comparison

The report records the earliest and latest retained log timestamps and keeps database paths private. A log window is:

- **full** when retained logs reach the window's start and at least one retained row overlaps the window
- **partial** when the earliest retained row falls inside the window
- **unavailable** when no retained row overlaps the window

`full` describes the retained start boundary. Timestamps alone may leave a quiet period and interrupted logging indistinguishable, so the latest observed timestamp remains visible in JSON.

Log-derived turns, tool calls, runtime, and compaction attempts become comparable when both adjacent windows are full. Token changes also require a full preceding baseline window. Current observations remain visible at every coverage level. Unsupported comparison changes and percentages are `null` in JSON and unavailable in Markdown.

Thread counts come from the retained state index and remain a separate state-derived comparison. Historical completeness of that index is unknown.

## Measurements

- **Local cumulative token change:** Positive changes between successive retained per-thread cumulative observations. Negative changes are counted as reset or compaction signals. Billing attribution remains unknown.
- **Model and reasoning turns:** Unique retained turn identifiers with observed model and reasoning fields.
- **Model switches:** Changes between successive observed turns in the same thread.
- **Observed turn span:** Time between the first and last selected telemetry row for a turn. It can include tools, approvals, and idle gaps.
- **Tool runtime:** Retained dispatch and handler duration for completed tool calls. Summed runtime can overlap across parallel threads. Elapsed wall-clock time remains a separate measure.
- **Runtime tool layers:** Wrapper and nested dispatch layers can be retained under separate names, such as `exec` and `exec_command`. A workflow can contribute to both rows. The count of distinct user actions remains unknown.
- **Dynamic-tool surface:** Current retained tool inventory for active threads. Per-turn attachment and invocation remain unknown.
- **Skill context pressure:** Runtime messages showing that descriptions were shortened or whole skills were omitted to fit the skills-list budget. These are separate signals; zero omissions can coexist with shortened descriptions.
- **Shadow selection:** Experimental selection telemetry. Confirmed skill invocation requires separate evidence.
- **Plugin review:** Every installed plugin appears with its current enabled state. A heuristic normalized-name match connects plugin IDs to observed tool names, rollout-derived `SKILL.md` reads, and dynamic namespaces. Matched tool calls receive medium confidence. Skill or inventory name matches receive low confidence. Exact context and token weight remain unavailable.
- **Compaction:** Explicit rollout `context_compacted` events supply the default count. `--no-rollouts` falls back to remote-compaction attempt telemetry.

Automatic-review turns remain visible in their own category alongside working-model reasoning summaries.

## Rollout Enrichment

The review reads compact SQLite telemetry and enriches it from rollout records inside `CODEX_HOME` by default at every candidate size. The scan reads each file backward and stops at the prior comparison boundary, so the selected period controls the inspected record range.

`--no-rollouts` explicitly skips enrichment. In that mode, rollout-derived fields carry `null` or `not measured`, and compaction counts fall back to log-attempt telemetry.

The scan reads files backward, stops at the prior comparison boundary, and extracts these fields:

- task duration and time to first token
- explicit compaction events
- serialized tool-output record sizes associated with tool names
- verification-like command counts
- skill directory names from observed `SKILL.md` paths

Serialized output size supports relative comparison. Decoded content size, context tokens, and billing usage remain outside this measure.

Task timing, skill reads, verification counts, serialized output sizes, and related plugin fields carry `null` or `not measured` only when enrichment is skipped or unavailable. A completed scan with no matching observations reports measured zeros or empty lists.

## Attribution Language

Every attribution finding separates:

- **Observed:** A value directly retained in the selected telemetry.
- **Interpretation:** The narrow relationship supported by that value.
- **Unknown:** What the evidence cannot establish.

Use `high` confidence for direct counts with stable fields. Use `medium` for indirect fields, version-dependent fields, and relative signals. Causal attribution requires separate evidence.

The `--top` option controls the number of displayed ranked rows. Findings and plugin totals use full retained aggregates before display truncation.

## Privacy

Markdown and JSON output keep these values private:

- prompts and responses
- thread titles, previews, and identifiers
- commands and tool results
- full project and rollout paths
- configuration values and secrets

Project-area counts use in-memory hashes, and their source paths stay private. Rollout enrichment searches command inputs for narrow verification and `SKILL.md` path patterns, then discards the source text.

Rollout enrichment follows only rollout paths that resolve inside `CODEX_HOME`.
