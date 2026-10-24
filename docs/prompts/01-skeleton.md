# Session 01 — project skeleton, config, contracts, first structured LLM answer

Read `CLAUDE.md` and `docs/SPEC.md` first (sections 4, 5, 12, 13, 14). This session covers step 1 of SPEC §14.
Ask the user only when blocked (installs, permissions, decisions with consequences). Do not go beyond this session.

## Step 0. Machine inventory (done 24.10.2026, keep for the report)
macOS 26.5, Apple M4, 16 GB RAM, 156 GB free, Python 3.11.9 in `.venv`, Docker 28.5.1 works, `uv` present (not used — decision 13), **Ollama not installed**.

## Step 1. Packaging
- `pyproject.toml`: src-layout, package `patchloop`, `requires-python = ">=3.11"`, `[project.scripts] patchloop = "patchloop.cli:main"`.
- Runtime dependencies for this session only: `pydantic`, `litellm`, `typer`, `rich`, `pyyaml`. Dev: `pytest`, `ruff`. Other libraries from SPEC §13 (langgraph, docker, sqlalchemy…) are added in the step that needs them.
- Install with `.venv/bin/pip install -e ".[dev]"`. Pin nothing yet; record resulting versions in the report.
- `ruff` configuration in `pyproject.toml` (line length 100, import sorting).
- `.env.example` with empty values (e.g. `OLLAMA_BASE_URL`), already ignored `.env` stays out of git.
- Commit after the step is the user's job; stop and list the files to stage.

## Step 2. Skeleton and config
- Package modules from SPEC §13 as empty modules with a docstring, only those used now: `cli.py`, `config.py`, `schemas.py`, `llm/`.
- `config.py`: load `patchloop.yml` over defaults from `configs/default.yaml` (keys: `language`, `max_attempts`, `llm.model`, `llm.base_url`, `llm.timeout_s`). Validate with Pydantic; unknown keys are an error.
- Test: defaults load; override works; unknown key fails.

## Step 3. Contracts
- `schemas.py` with `SCHEMA_VERSION = 1` and the models from SPEC §5: `Failure`, `CheckResult`, `Patch`, `Review`, `Attempt`, `RunResult`. `frozen=True`, `extra="forbid"`.
- Tests: serialization round trip, forbidden extra field, invalid status rejected.

## Step 4. LLM client with structured output
- `llm/client.py`: one function that takes messages and a Pydantic model, calls the model through LiteLLM (Ollama), forces the answer to the model's JSON schema, validates it, retries once with the validation error, then raises a clear error. No silent fallback.
- `llm/cache.py`: cache of answers on disk keyed by sha256(model, messages, schema) under a gitignored `cache/` directory.
- A fake client for tests (same interface, returns prepared answers). Tests must not use the network or a real model.

## Step 5. `patchloop doctor`
- CLI command (Typer + Rich) checking: Python version, Docker reachable, Ollama reachable at `base_url`, configured model present. Each check prints OK/FAIL with a one-line hint (for example the exact `ollama pull …` command). Missing Ollama is a FAIL, not a crash.
- Test the command logic with fakes.

## Step 6. First real answer (only if Ollama is installed)
- If Ollama is missing, give the user ready-to-run lines (`brew install ollama` or the app, then `ollama pull <model>`) and wait. Model choice: start with `qwen3.5:9b` per `PLAN.md`; if it is not available, say so and propose the closest alternative.
- A small manual script or command that asks the model for a `Patch` for a tiny hard-coded buggy function and prints the validated result. Run it once and report the latency.

## End of session
Run `ruff check .` and `pytest -q`; both must pass. Then write `docs/reports/01-skeleton.md` in the format from `CLAUDE.md`. In "Потрібне рішення" give your recommendation (default model, `llm.timeout_s`, whether the cache key needs more fields). Do not continue to the next step of SPEC §14.
