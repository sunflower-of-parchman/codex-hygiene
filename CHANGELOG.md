# Changelog

## [v0.2.0] - 2026-07-17

### Added

- Privacy-preserving activity reviews for explicit 1-90 day lookbacks, with Markdown or JSON output and comparison to the preceding period.
- Retention-aware source coverage that keeps current observations visible while suppressing comparisons when the required log windows are incomplete.
- Codex activity review findings label confidence across observed models, reasoning levels, tools, skills, plugins, compactions, subagents, automations, and local cumulative token changes.
- Codex activity review enrichment uses a rollout-size guard for task timing, relative serialized tool-output weight, verification-command counts, explicit compactions, and observed `SKILL.md` reads.
- An activity-review interpretation reference and fixture coverage for attribution, retention gaps, rollout guards, compact-mode fallback, and privacy exclusions.

### Compatibility

- Activity review compatibility preserves the original compact `measure_codex_context.sh` workflow as the default when no lookback period or retrospective is requested. Its commands and output are unchanged.
- The activity review uses Python 3 and the standard library. Codex telemetry schemas, retained history, cache layouts, and CLI output remain version-dependent diagnostic inputs.

### Privacy and limitations

- Activity review privacy excludes prompts, responses, thread titles and identifiers, commands, tool results, full paths, configuration values, and secrets.
- Activity review limitations treat token changes as local cumulative telemetry rather than billing totals. Tool and task runtimes can overlap and do not measure model inference time or work quality.
- Activity review enrichment retains a 512 MiB default guard. When candidates exceed it, the report provides an exact `--max-auto-rollout-mib N` guarded rerun and keeps deep-only values labeled as not measured.

[v0.2.0]: https://github.com/sunflower-of-parchman/codex-hygiene/compare/v0.1.0...v0.2.0
