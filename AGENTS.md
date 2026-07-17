# AGENTS.md

## Project

- This repository contains a public Codex skill for auditing Codex Desktop context and tool surfaces.
- Keep diagnostics compact, read-only by default, and explicit about uncertainty.
- Treat Codex telemetry schemas, cache layouts, and CLI output as version-dependent.

## Working agreements

- Read the relevant skill, script, test, and reference files before changing behavior.
- Keep shell code portable across the supported macOS and Unix-like environments.
- Never print secrets, full configuration, full logs, or complete private path inventories.
- Keep `README.md`, `SKILL.md`, tests, and references consistent when behavior changes.
- Do not change user configuration, delete local data, push commits, publish releases, or modify repository settings without explicit approval.

## Verification

- Run `bash -n scripts/measure_codex_context.sh tests/measure_codex_context_test.sh` after shell changes.
- Run `bash tests/measure_codex_context_test.sh` after behavior changes.
- Run `python3 -m py_compile scripts/codex_activity_review.py` and `python3 -m unittest -v tests/codex_activity_review_test.py` after activity-review changes.
- Confirm generated reports contain no prompts, responses, titles, IDs, commands, tool results, full paths, or secrets.
- Report changed files, verification results, and remaining uncertainty clearly.
