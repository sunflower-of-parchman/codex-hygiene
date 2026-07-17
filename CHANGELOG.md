# Changelog

## [v0.2.0] - 2026-07-17

### Added

- A private local activity review for explicit 1-90 day windows, returned as Markdown or JSON.
- Activity review findings include source coverage, supported prior-window comparisons, confidence labels, and separate statements for observed evidence, interpretation, and unknowns.
- Activity review rollout detail is optional and covers task timing, relative serialized tool-output weight, verification-command counts, explicit compactions, and observed `SKILL.md` reads.
- An activity-review reference and fixtures for attribution, retention gaps, rollout guards, the lightweight SQLite path, and privacy boundaries.

### Existing behavior

- The activity review keeps the original compact `measure_codex_context.sh` workflow as the default for current-context diagnostics. Its commands and output stay the same.
- The activity review uses Python 3 and the standard library. Codex telemetry schemas, retained history, cache layouts, and CLI output remain version-dependent diagnostic inputs.

### Privacy and evidence

- Activity review reports keep prompts, responses, thread titles and identifiers, commands, tool results, full paths, configuration values, and secrets private.
- Activity review token changes describe local cumulative telemetry. Billing attribution remains unknown. Tool and task timing includes end-to-end activity and may overlap across concurrent work.
- The activity review core uses compact SQLite telemetry. An optional rollout scan adds deeper fields. Its 512 MiB default disk-work threshold keeps the automatic pass lightweight; larger candidate sets receive the core report, `not measured` labels for rollout-derived fields, and an exact guarded rerun command.

[v0.2.0]: https://github.com/sunflower-of-parchman/codex-hygiene/compare/v0.1.0...v0.2.0
