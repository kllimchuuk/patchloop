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
- Small steps. Follow the order in SPEC §14.
- If something in SPEC does not work in practice, do not work around it silently: stop and raise it as "Потрібне рішення" in the report.
- Any new dependency, library or architecture change goes through a decision first, then `docs/DECISIONS.md`.
- Session tasks live in `docs/prompts/NN-*.md` (English); reports in `docs/reports/NN-*.md`. Read the current prompt before starting a session and do only its steps.
- Before the repository is shown publicly, service files (`CLAUDE.md`, `docs/prompts/`) can be removed in a separate commit; they stay in git history.
- At the end of a work session or when blocked, give a short report in this format (numbers only if measured):

```
ЗВІТ <дата> — <етап>
Зроблено: …
Цифри: … (лише виміряне)
Відхилення від SPEC: … | немає
Потрібне рішення: … | немає
Далі: …
```

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

## Git
- The user writes their own commit messages. Stage files if asked, but do not commit.
- When asked to suggest a message, use Conventional Commits in English (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).
- Do not push and do not open PRs without being asked. Work on a feature branch, not directly on `main`.

## Secrets and artifacts
- Secrets only in `.env` (gitignored); keep `.env.example` with empty values. Never print secret values in logs, reports or commits.
- `.venv`, caches, run results and model weights stay out of git.

## Do not
- Do not run user or generated code outside the sandbox.
- Do not modify the user's original project in any code path except an explicit `patchloop apply`.
- Do not invent numbers in reports; write only what was measured.
