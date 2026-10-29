# Session 03 — Python profile, error parsing, Programmer ↔ check loop, limits, result states

Read `CLAUDE.md` and `docs/SPEC.md` first (sections 3, 4, 5, 6, 8, 12, 13, 14), then `docs/reports/02-sandbox.md`. This session covers step 3 of SPEC §14.
Ask the user only when blocked (installs, permissions, decisions with consequences). Do not go beyond this session.
Out of scope: Tester and test-must-fail guard (step 4), CLI, `apply` and `patchloop diff` (step 5), Reviewer and its loop (step 6), database (step 7), RAG and tree-sitter (step 8). The graph is driven from tests and a small function, not from the CLI.

## Step 0. Decisions first (ask the user, then record in `docs/DECISIONS.md`)
- **Installing the project itself.** Phase 1 copies only manifests, so `pip install .` cannot work. Recommended: install only dependencies in phase 1 and put the workspace on the path in phase 2 (`PYTHONPATH=/work:/work/src`), so a patched file is picked up without rebuilding the image. Alternatives: copy the full source in phase 1 (image changes with every project edit), or editable install. Pick one and write it down.
- **Base image.** SPEC says `python:3.12` (~1 GB); tests use `python:3.12-slim`. Decide the default. Slim lacks compilers for native wheels; since phase 1 has network, that only matters for packages without wheels.
- **Where retries and state live.** Confirm the default: graph state holds attempts, best attempt and counters in the Pydantic models from SPEC §5.

## Step 1. Contracts
- `schemas.py`: `Failure`, `CheckResult`, `Patch`, `Attempt`, `RunResult` exactly as in SPEC §5 (`frozen`, `extra="forbid"`, `schema_version`). `Review` may be added now as a stub because `Attempt` references it; no Reviewer logic.
- `Patch` validation: relative paths only, no `..`, no absolute paths, no `.git/`, non-empty `files`. A model-produced path is untrusted input.
- Tests: valid and invalid models, unknown field fails, path rejection.

## Step 2. Config
- `config.py`: `LoopConfig` with `max_attempts` (default 3, allowed 1–5), `total_timeout_s`, `tail_lines` (for `raw_tail`). Defaults in the models (decision 21), unknown keys are an error.
- `patchloop.yml` keys from SPEC §6 (`image`, `install`, `build`, `test`, `lint`, `env`) load into a profile override model. Per-run `env` goes into the container; check that secrets from the host are not forwarded.
- Tests: defaults, override, unknown key, range violation.

## Step 3. Python profile
- `profiles/base.py`: `LanguageProfile` protocol (`detect`, `image`, commands for `install`/`build`/`test`/`lint`, `parse_errors`). `profiles/python.py`: the Python implementation.
- `detect()`: `manage.py` → Django, `fastapi` in dependencies → FastAPI, otherwise plain `pytest`. Django/FastAPI only change defaults (env, test command); no separate code paths.
- Manifest discovery: `requirements*.txt`, `pyproject.toml`, `uv.lock`/`poetry.lock` if present. Feed the list to `ensure_image`.
- Defaults: build `python -m compileall -q .`, lint `ruff check --output-format=concise .`, tests `pytest -x -q`. Commands live in the profile/config, not in the loop code.
- Tests: detection on small fixture projects under `tests/fixtures/`, override precedence (`patchloop.yml` over profile).

## Step 4. Parsing errors
- `profiles/python.py: parse_errors(stage, result) -> list[Failure]`: pure functions over text, no Docker.
  - compileall: `SyntaxError` blocks (file, line, message).
  - ruff concise: `path:line:col: CODE message`.
  - pytest: failed test ids with the file and line of the failing frame, exception type and message; `failing_tests` is the count of failed plus errored tests from the summary line.
  - Fallback: if nothing is parsed from a failed stage, one `Failure` with `raw_tail` (last `tail_lines` lines). Never an empty failure list for a failed check.
- Paths are normalized to project-relative; anything outside the workspace is dropped.
- Tests: real captured outputs stored as fixtures (syntax error, ruff errors, assertion failure, import error, collection error, timeout with no output).

## Step 5. Check runner
- `checks.py` (or `sandbox/checks.py`): `run_checks(client, config, profile, image, workdir) -> list[CheckResult]` runs build → lint → tests via `run_in_sandbox`. A failed build short-circuits the later stages (SPEC §3 step 3). Timeout and OOM become a `Failure(kind="runtime")`, not a crash.
- Tests with the fake Docker client; one opt-in `docker` test on a tiny fixture project.

## Step 6. Applying a patch
- `apply_patch(workdir, patch)`: writes whole files into the workspace copy, creating parent directories, never following symlinks and never writing outside `workdir` (SPEC §12 rule for untrusted copies). `patch_hash` = sha256 over sorted path + content.
- Diff for the report is computed by plain code (`difflib`) against the original files, not by the model.
- Tests: normal write, new file, traversal attempt, symlink in the path, hash stability.

## Step 7. Programmer agent
- `agents/programmer.py`: input is the failures (with the code fragment around `file:line`, plus the files named in failures read whole), attempt history (patch explanation plus the failures it left), and nothing else. Output is `Patch` through the existing structured-response client. English prompts (decision 14).
- Prompt text lives in one place, not scattered through the code. No control flow decided by the model.
- Retry once if the structured output is invalid; a second failure ends the attempt as an error attempt, not a crash.
- Tests with a fake LLM client: prompt contains failures and history, invalid JSON handled, no real model.

## Step 8. Graph and stop conditions
- `graph.py`: LangGraph nodes `prepare`, `check_original`, `fix`, `apply`, `check`, `decide`, `finish`. State holds the attempts, best attempt, counters and deadline (SPEC §5).
- Without an issue description, the check of the original is the whole input: if it passes, result is `no_bugs_found`. With an issue description but no Tester yet, the Programmer works from the description and `reliability="reduced"`.
- `decide` is plain code on a conditional edge (SPEC §8): `passed` → finish with `success`; `max_attempts` reached → `iteration_limit`; same `patch_hash` as the previous attempt or the same failure set again → `stagnation`; total deadline → `timeout`.
- Progress and rollback: if `failing_tests` (plus lint and build failures) dropped, allow another attempt; if it grew, restore the workspace to the best attempt before the next one. Keep the best attempt, not the last.
- Final `RunResult`: status `fixed`/`partially_fixed`/`not_fixed`/`no_bugs_found`, `best_attempt`, `diff`, `explanation`, `stop_reason`, `reliability`. The Reviewer step is skipped; mark in the code where step 6 plugs in.
- The original project is never modified. All writes go to the workspace copy, and the workspace is always removed.
- Tests with a fake LLM and a fake sandbox: success on attempt 1, success on attempt 3, iteration limit, stagnation by identical hash, stagnation by repeated failure, timeout, rollback to the best attempt, `no_bugs_found`, `partially_fixed` with its failing list.

## Step 9. End-to-end smoke
- One opt-in `docker` test (also needs a running Ollama, so mark it `llm` too and keep it out of the default run): a tiny fixture project with a one-line bug, real sandbox, real model. Record success, attempts and time in the report. If the model fails, report it as measured; do not tune the prompt to make one example pass.

## End of session
Run `uv run ruff check .` and `uv run pytest -q` (and `uv run pytest -m docker -q` with Docker running); all must pass. Write `docs/reports/03-python-profile.md` in the format from `CLAUDE.md` with measured numbers only. Add decisions to `docs/DECISIONS.md` (24+) for step 0 and for any design choice made on the way; update SPEC only for factual changes, never the "Zafixované rozhodnutia" table. In "Potrebné rozhodnutie" list anything in SPEC that did not work in practice. Do not continue to step 4 of SPEC §14. Do not commit.
