---
name: invariants-check
description: Checklist of the patchloop invariants (sandbox only, original untouched, untrusted working copy, model never controls flow, bounded loops, Tester guards, honest result) with concrete things to look for in code and tests. Use when reviewing a diff, before handing over changes to the sandbox, patching, graph, agents, contracts or config, or when asked whether a change is safe.
---

# Invariant checklist

For each item answer pass, fail or not touched, and point at the code or test that proves it. The sources are `docs/SPEC.md` (sections given per row), `CLAUDE.md` and the numbered entries in `docs/DECISIONS.md`.

| ID | Invariant (source) | Look for | Red flag |
|---|---|---|---|
| P1 | Project and generated code run only in the sandbox, with no network during checks (SPEC §6, §12). | Commands go through `sandbox/runner.py` with `network_mode="none"`; only image preparation (`sandbox/image.py`) has network. | `subprocess` or `exec` of a project command on the host; importing project modules into our process; a check that runs in the image-build phase. |
| P2 | The original project is never modified; all writes go to the workspace copy, which is always removed (SPEC §1, §12). | Writes target the copy from `make_workspace`; cleanup in a `finally` or context manager; `patchloop apply` is the only code path that touches the project. | A path built from `project` passed to a writing function; a workspace left behind on an error path. |
| P3 | The working copy and every model-produced path are untrusted (SPEC §12, decisions 23, 27). | Host code goes through `patching.py` (no symlink followed, path stays inside the copy); `Patch` validation rejects absolute paths, `..` and `.git/`. | `Path.resolve()`, `open()` or `unlink()` on a workspace path outside `patching.py`; a path from the model used before validation. |
| P4 | The model never decides control flow (SPEC §12). | Limits, stopping, rollback, the choice of file path and the verdict on a test are plain code in `graph.py` or the profile. | A branch on free text from the model; a model field such as "done" or "retry" that the graph obeys. |
| P5 | Every loop has a stop condition (SPEC §8). | `max_attempts`, `max_test_attempts`, the Reviewer limit, stagnation (repeated patch hash or failure set), `total_timeout_s`, container `run_timeout_s`. | A `while` or a graph cycle without a counter and a deadline; a retry added without a bound. |
| P6 | A generated test must fail on the original code before the fix, and the Tester never sees the fix (SPEC §9, decision 27). | The test runs on the original copy and is classified `reproduces` / `passes` / `broken`; only `reproduces` reaches the Programmer; the test is read-only for the Programmer and is not in the patch or the diff. | The Tester called after an attempt; a `broken` or `passes` test handed to the Programmer; the generated test included in `diff`. |
| P7 | No silent fallbacks (SPEC §12). | A missing model, image or Docker raises an error with a clear message. | `except` that swaps in another model, image or code path; a default that hides a failed step. |
| P8 | Contracts between agents are Pydantic models in `schemas.py`: `frozen`, `extra="forbid"`, `schema_version` (SPEC §5). | New contract classes inherit the shared base; `SCHEMA_VERSION` is bumped when a field changes. | A dict or dataclass passed between agents in place of a contract; a changed field with the old version. |
| P9 | Limits, timeouts, image names and commands live in config (`config.py`, `patchloop.yml`, the profile), not in code. | New numbers and commands are config fields with validation ranges. | A literal timeout, limit, image tag or shell command inside `graph.py`, an agent or the sandbox. |
| P10 | Tests use no real LLM and no network; Docker and LLM tests are opt-in markers. | Fakes from `tests/support/`; `docker` and `llm` markers on tests that need them. | A unit test that calls Ollama, pulls an image or opens a socket; a test skipped silently instead of marked. |
| P11 | The result is honest (SPEC §8): one of `fixed` / `partially_fixed` / `not_fixed` / `no_bugs_found`, always with a stop reason; the best attempt is kept; `reliability` is `reduced` when nothing reproduced the bug. | The status follows from check results, not from the model's explanation. | `fixed` without a passing re-check; a lost best attempt after a worse one; a missing `stop_reason`. |
| P12 | Secrets stay out (SPEC §12). | The project's `.env` is not copied unless `sandbox.copy_env`; host environment is not forwarded into the container; nothing secret in logs, reports or run records. | `os.environ` passed to a container; a prompt, log line or record that contains file contents from `.env`. |

Checks that apply to every diff:

- Agents call each other, or one agent reads another's private state, instead of going through the shared graph state.
- A new dependency, or an architecture change, without a `docs/DECISIONS.md` entry.
- A change that contradicts the "Zafixované rozhodnutia" table in SPEC §2.
- Behavior change without a test, or a test that cannot fail. For every new test name the bug that would make it fail.
- A prompt tuned to make one example pass (a measured failure is reported, not hidden).
- A number in a report or doc without the command it came from.
- A docs file that no longer matches the code (SPEC, DECISIONS, `.env.example`).
