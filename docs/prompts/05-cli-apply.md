# Session 05 — live CLI, diff, run record on disk, `patchloop apply`

Read `CLAUDE.md` and `docs/SPEC.md` first (sections 3, 5, 8, 10, 12, 13, 14), then `docs/reports/04-tester.md` and decision 29 in `docs/DECISIONS.md`. This session covers step 5 of SPEC §14.
Ask the user only when blocked (installs, permissions, decisions with consequences). Do not go beyond this session.
Out of scope: Reviewer and its loop (step 6), database, `patchloop runs`, `patchloop report` and the HTML report (step 7), RAG and tree-sitter (step 8). No new dependency (Typer, Rich, PyYAML are already in). Do not tune prompts. Do not add the demo bugs to the repository.

Branch: `feat/cli-apply` (created from fresh `main`).

## Step 0. Decisions (all recommended options confirmed 2026-11-14, recorded as decision 30 in `docs/DECISIONS.md`)
- **Live progress.** Recommended: `Engine.run(..., on_step=callback)`, fed by `graph.stream(stream_mode="updates")`; the callback gets the node name and its state update and prints one line per node (`check original: build ok, lint ok, tests 2 failing`, `tester: test accepted`, `attempt 2: patch written to 3 files`, ...). The engine stays free of Rich. Alternative: wrap each node in `build()`.
- **`run_id`.** Recommended: `YYYYMMDD-HHMMSS-<4 hex>` (sorts by time, fits a git branch name). Alternative: a plain uuid4.
- **`apply` on `partially_fixed`.** Recommended: allowed with a printed warning ("partial fix, N checks still fail"); refused only when the diff is empty (`not_fixed`, `no_bugs_found`). Alternative: only `fixed`.
- **`apply` conflicts.** Recommended: no stored HEAD hash; `git apply --check` runs first, so a diff that no longer fits leaves nothing behind (no branch created). Alternative: store the commit and refuse on a different HEAD.
- **Exit codes of `fix`.** Recommended: 0 `fixed` or `no_bugs_found`, 1 `partially_fixed` or `not_fixed`, 2 usage or environment error (a clear message, no silent fallback).

## Step 1. Contract and config
- `schemas.py`: `GeneratedTest(path, content, output)` (`frozen`, `extra="forbid"`); `RunResult.generated_test: GeneratedTest | None = None`; `SCHEMA_VERSION` 1 → 2. `output` is the failure text of the accepted test run on the original code, clipped.
- `graph.py`: the `tester` node keeps the output of the accepted test run in state, `finish` puts it in `RunResult`. The test stays out of the diff and out of the patch.
- `config.py`: `runs_dir: Path` (default `~/.patchloop/runs`, `~` expanded), unknown keys still an error.
- Tests: contract round trip, unknown field fails, version bumped, `generated_test` set only when a test reproduced the bug and absent in `no_bugs_found` and in a run without a test; config default and override.

## Step 2. Run record
- New module `runs.py`: `new_run_id(now)`, `save_record(runs_dir, run_id, record)`, `load_record(runs_dir, run_id)`. Record = `RunResult` + resolved project path + issue + `schema_version`. Files are written with a temp file and an atomic rename; `run_id` is validated against the format (no path separators, so `apply ../x` cannot leave `runs_dir`).
- `load_record` of an unknown id, broken JSON or an older schema version is a clear error, not a traceback.
- Tests: save then load round trip, bad id rejected, missing run, corrupt file, old `schema_version`, two ids in the same second differ.

## Step 3. `patchloop fix`
- `patchloop fix PROJECT [--issue TEXT | --issue-file PATH] [--config PATH]`. `--issue` together with `--issue-file` is a usage error; an unreadable or empty issue file is an error.
- Before the run: the environment check from `patchloop check` (Docker, Ollama, model). A failed check ends the command with its message and hint and starts nothing.
- Builds `LiteLLMClient` and the Docker client in `cli.py` (the engine receives them as before, so tests inject fakes); prints live progress through `on_step` with Rich; at the end prints status, stop reason, reliability, the diff (syntax-highlighted), the explanation, the generated test (path, content, its failure output) marked as "not part of the fix", and the `run_id` plus the hint `patchloop apply <run_id>`. A `partially_fixed` result is labelled "partial" and lists what still fails (SPEC §8).
- Saves the record, also for `no_bugs_found` and `not_fixed`. The original project is not touched in any code path.
- Tests (fake LLM, fake Docker via `tests/support/`, `CliRunner`): `fixed` run prints diff, explanation and run id and writes a record; `partially_fixed` shows the partial label; `no_bugs_found` and `not_fixed` write a record and print no apply hint; both issue options at once, missing project path, empty issue file; failed environment check starts no run; exit codes per step 0; the project directory is byte-identical before and after (hash of the tree).

## Step 4. `patchloop apply`
- `patchloop apply RUN_ID [--config PATH]`: loads the record, then in the project path from the record:
  1. refuses when the diff is empty;
  2. refuses when the path is not a git work tree or the tree is not clean (untracked files count as dirty);
  3. refuses when the branch `patchloop/<run_id>` already exists;
  4. `git apply --check` of the stored diff, then `git switch -c patchloop/<run_id>` and `git apply`;
  5. no commit, no push, no `git add`; prints the branch, the changed files and `git diff` as the next step.
- Only the fix is applied; the generated test is never written to the project. The diff comes from the record, never from re-running anything.
- Git is called through `subprocess` with an argument list (no shell), `cwd` set to the project, and a short timeout. A diff path that is absolute or contains `..` is refused before `git apply` (the record is a file on disk and is treated as input).
- Tests with a real `git` in a temporary repository (no Docker, no model): clean repo gets the branch and the changed working tree with nothing staged or committed, HEAD unchanged; dirty tracked file, untracked file, not a git repo, existing branch, empty diff, diff that no longer fits (`--check` fails and no branch is left behind), new file in the diff, file without a trailing newline, a record whose diff has a `..` path, the generated test is absent from the project afterwards.

## Step 5. Checks and hand over
- `uv run ruff check .`, `uv run pytest -q`; with Docker running also `uv run pytest -m docker -q`.
- One manual run with the real model on one of the demo bugs outside the repository: `fix`, then `apply` on a copy of that project in a git repo. Report the real numbers only (time, status, attempts), as one run, not a statistic.
- Update the docs that become true: SPEC §10 (record path, `runs_dir`), decision 30, `CLAUDE.md` only if a command changes. Run `branch-reviewer` on the branch, then the report `docs/reports/05-cli-apply.md` with the `report` skill.
