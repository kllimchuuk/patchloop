# patchloop

Semester project (TUKE, two semesters): a multi-agent system (Programmer, Tester, Reviewer) that fixes bugs in Python projects, running on a local LLM via Ollama.

`docs/SPEC.md` is the source of truth for design. Do not change its "Zafixované rozhodnutia" table without explicit permission. `docs/DECISIONS.md` is the dated decision log; `PLAN.md` is the original plan, kept locally (gitignored, not in the repository); SPEC supersedes it, so do not keep the two in sync. All are in Slovak.

## In 30 seconds
Input: project path + optional bug description → copy into a no-network Docker sandbox → check (build, lint, tests) → Programmer writes a fix as whole files → apply to the copy → re-check → Reviewer → result (diff, explanation, run record in DB). Agents share a LangGraph state and never call each other. The original project is never modified; `patchloop apply` creates a git branch with the fix (no commit, no push).

## Scope
- Semester project, not a thesis: no research part, no ablation studies or benchmarks. A working, demonstrable system is what matters.
- `PLAN.md` is the global two-semester plan. Do not shrink it to fit the 5-week first handover.
- Architecture is language-agnostic (profiles + `patchloop.yml`); implementation and evaluation are Python only (Django, FastAPI).

## How we work
- Chat with the user in Ukrainian. Docs (`docs/`, `PLAN.md`) are in Slovak. Code, identifiers, comments and commit messages are in English.
- Small steps. Follow the order in SPEC §14. One step is one loop of the `spec-step` skill: read the spec, settle decisions, write the session prompt and get it approved, then failing test, code, checks, review, report.
- Session tasks live in `docs/prompts/NN-*.md` (English) and carry the scope, what is out of scope, and the tests that prove each sub-step; reports live in `docs/reports/NN-*.md` (Slovak, like the other docs). Read the current prompt before starting a session and do only its steps.
- Test first: write the failing test for a sub-step, see it fail for the right reason, then write the code.
- Review before the pull request: run the `branch-reviewer` subagent (read-only, fresh context, checks the `invariants-check` list) on the branch, and again after the fixes. Fix confirmed findings, each with a test that failed first; skip taste.
- Create only the files that the current session prompt or SPEC asks for. Do not add extras (README, scripts, examples, extra config) on your own initiative; propose them first.
- If something in SPEC does not work in practice, do not work around it silently: stop and raise it as "Potrebné rozhodnutie" in the report.
- Any new dependency, library or architecture change goes through a decision first, then `docs/DECISIONS.md`.
- Update the docs in the same change that makes them true.
- At the end of a work session or when blocked, give a short report in the ZVIT shape (`report` skill): Hotovo / Čísla (measured only) / Odchýlky od SPEC / Potrebné rozhodnutie / Ďalej.
- Before the repository is shown publicly, service files (`CLAUDE.md`, `.claude/`, `docs/prompts/`) can be removed in a separate commit; they stay in git history.

## Commands
- Lint: `uv run ruff check .`
- Unit tests (no Docker, no model): `uv run pytest -q`
- Docker tests (Docker running, base image pulled): `uv run pytest -m docker -q`
- Smoke test with a real model (Docker and Ollama running): `uv run pytest -m "docker and llm" -q`

## Enforced by the harness
`.claude/settings.json` holds the rules that have no exceptions; the lines in this file are guidance.
- `git push`, `git commit --amend` and `git reset --hard` are denied; merge, rebase and `uv add` ask first.
- A Stop hook (`.claude/hooks/checks_before_stop.py`) runs `ruff check` and the unit tests when code changed and returns a red result once, so a turn never ends quietly with failing checks.
- The `branch-reviewer` subagent has no edit tools, and a hook (`.claude/hooks/reviewer_readonly.py`) lets its Bash run only read-only git, `ruff check` and `pytest`.

## Stack and dependencies
Python 3.12 (`.venv`, dependencies managed with `uv`: `pyproject.toml` + `uv.lock`), LangGraph, Pydantic, LiteLLM, Ollama, docker-py, SQLAlchemy 2 + Alembic + PostgreSQL (pgvector), Typer + Rich, tree-sitter. Dev: pytest, ruff. List is in SPEC §13; anything else needs a decision first.

## Code
- src-layout under `src/patchloop/`; structure in SPEC §13.
- Type hints everywhere. Contracts between agents are Pydantic models in `schemas.py` with `schema_version` (`frozen`, `extra="forbid"`).
- Limits, timeouts, image names and commands live in config (`patchloop.yml`, `configs/`), not in code.
- The model never decides control flow (limits, stopping, rollback): plain code in the graph does.
- Every loop has a stop condition (iteration limit, stagnation check, timeout). See SPEC §8.
- A generated test must fail on the original code before the fix, and the Tester never sees the fix.
- No silent fallbacks: a missing model, image or Docker is an error with a clear message.
- Tests (pytest) must not use a real LLM or the network; use a fake LLM client. Run `uv run ruff check .` and `uv run pytest -q` before saying work is done.
- The same rules as a checklist with red flags (P1-P12): `invariants-check` skill.

## Git
- Commit locally; never run `git push`: the user pushes, opens the pull request and merges.
- A few larger commits: one per finished chunk (2-3 sub-steps, a module together with its tests), only when `ruff` and `pytest` are green (docs-only commits excepted). After a series of commits show `git log --stat`.
- Messages are Conventional Commits in English (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`), a one-line subject describing behavior, no `Co-Authored-By` or other attribution lines.
- Stage files by explicit path, never `git add .`; never stage `.env`.
- No `--amend`, `reset` or `rebase` on existing history unless the user asks. Work on a feature branch, not directly on `main`; do not create a branch unasked.

## Secrets and artifacts
- Secrets only in `.env` (gitignored); keep `.env.example` with empty values. The agent may read `.env` when the work needs it, but never prints secret values in the chat, logs, reports or commits.
- `.venv`, caches, run results and model weights stay out of git.

## Do not
- Do not run user or generated code outside the sandbox.
- Do not modify the user's original project in any code path except an explicit `patchloop apply`.
- Do not invent numbers in reports; write only what was measured.
