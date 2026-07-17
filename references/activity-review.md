# Activity Review Reference

Use this reference to interpret `scripts/codex_activity_review.py` output and its evidence boundaries.

## Contents

- [Inputs](#inputs)
- [Windows](#windows)
- [Coverage and comparison](#coverage-and-comparison)
- [Measurements](#measurements)
- [Deep rollout enrichment](#deep-rollout-enrichment)
- [Attribution language](#attribution-language)
- [Privacy](#privacy)

## Inputs

The report discovers the newest versioned `state_*.sqlite` and `logs_*.sqlite` databases under `CODEX_HOME` and opens them read-only.

It uses retained state for thread class, project-area count, current model metadata, rollout locations, and dynamic-tool inventory. It uses compact log rows for model and reasoning observations, within-window cumulative token changes, tool calls and runtimes, compaction attempts, response retries, skill-catalog pressure, MCP tool-list rows, and snapshot flags.

Current `codex` CLI output supplies a report-time plugin, MCP, and Apps feature snapshot. That snapshot is not historical evidence.

## Windows

`--days N` creates two adjacent N-day windows ending at report generation time. The caller must select a lookback from 1 to 90 days. The current period is compared with the preceding period. A third preceding window supplies token baselines so the first current-period observation is less likely to absorb older thread history.

The window is rolling rather than aligned to UTC midnight. An N-day window can therefore touch parts of up to N+1 UTC calendar dates; the report labels active dates accordingly.

Threads may span both periods. Counts describe observed activity within each period rather than newly created threads.

## Coverage And Comparison

The report records the earliest and latest retained log timestamps without printing database paths. A log window is:

- **full** when retained logs reach the window's start and at least one retained row overlaps the window
- **partial** when the earliest retained row falls inside the window
- **unavailable** when no retained row overlaps the window

`full` describes the retained start boundary. A quiet period and interrupted logging cannot always be distinguished from timestamps alone, so the latest observed timestamp remains visible in JSON.

Compare log-derived turns, tool calls, runtime, and compaction attempts only when both adjacent windows are full. Compare token changes only when the additional preceding baseline window is also full. When those conditions are not met, current observations remain visible while comparison changes and percentages are `null` in JSON and unavailable in Markdown.

Thread counts come from the retained state index and remain a separate state-derived comparison. Historical completeness of that index is unknown.

## Measurements

- **Local cumulative token change:** Positive changes between successive retained per-thread cumulative observations. Negative changes are counted as reset or compaction signals. These are not billing totals.
- **Model and reasoning turns:** Unique retained turn identifiers with observed model and reasoning fields.
- **Model switches:** Changes between successive observed turns in the same thread.
- **Observed turn span:** Time between the first and last selected telemetry row for a turn. It can include tools, approvals, and idle gaps.
- **Tool runtime:** Retained dispatch and handler duration for completed tool calls. Summed runtime can overlap across parallel threads and is not elapsed wall-clock time.
- **Runtime tool layers:** Wrapper and nested dispatch layers can be retained under separate names, such as `exec` and `exec_command`. A workflow can contribute to both rows, so their counts are not automatically distinct user actions.
- **Dynamic-tool surface:** Current retained tool inventory for active threads. Inventory does not prove per-turn attachment or invocation.
- **Skill context pressure:** Runtime messages showing that descriptions were shortened or whole skills were omitted to fit the skills-list budget. These are separate signals; zero omissions can coexist with shortened descriptions.
- **Shadow selection:** Experimental selection telemetry. It is not confirmed skill invocation.
- **Plugin attribution:** A heuristic normalized-name match across currently enabled plugin IDs, observed tool names, deep `SKILL.md` reads, and dynamic namespaces. It is medium confidence when tool calls match and low confidence when only skill or inventory names match.
- **Compaction:** Prefer explicit rollout `context_compacted` events when deep enrichment runs; otherwise report remote-compaction attempt telemetry.

Automatic-review turns remain visible but are separated from working-model reasoning summaries.

## Deep Rollout Enrichment

The automatic mode totals candidate rollout sizes first. It scans when the total is at or below 512 MiB and otherwise reports the skipped size guard. Change the guard with `--max-auto-rollout-mib` or force the scan with `--deep`.

When automatic enrichment is skipped, the warning reports the minimum whole-MiB `--max-auto-rollout-mib N` value required for the measured candidates. Rerunning with that value is the guarded middle path: it approves the known size while still stopping if the candidate set grows. `--deep` ignores the guard entirely.

The scan reads files backward and stops at the prior comparison boundary. It extracts only:

- task duration and time to first token
- explicit compaction events
- serialized tool-output record sizes associated with tool names
- verification-like command counts
- skill directory names from observed `SKILL.md` paths

Serialized output size is useful for relative comparison. It is not decoded content size, context tokens, or billing usage.

When rollout enrichment does not run, task timing, skill reads, verification counts, serialized output sizes, and related plugin fields are `null` or `not measured`. A completed scan with no matching observations reports measured zeros or empty lists.

## Attribution Language

Every attribution finding separates:

- **Observed:** A value directly retained in the selected telemetry.
- **Interpretation:** The narrow relationship supported by that value.
- **Unknown:** What the evidence cannot establish.

Use `high` confidence for direct counts with stable fields. Use `medium` when the field is indirect, version-dependent, or only a relative signal. Do not turn correlation into causal attribution.

The `--top` option limits displayed ranked rows only. Findings and plugin totals use full retained aggregates before display truncation.

## Privacy

Markdown and JSON output omit:

- prompts and responses
- thread titles, previews, and identifiers
- commands and tool results
- full project and rollout paths
- configuration values and secrets

Project-area counts use in-memory hashes and do not print their source paths. Deep inspection searches command inputs for narrow verification and `SKILL.md` path patterns, then discards the source text.

Deep enrichment follows only rollout paths that resolve inside `CODEX_HOME`.
