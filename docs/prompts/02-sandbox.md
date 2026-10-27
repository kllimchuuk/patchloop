# Session 02 — sandbox: image preparation, no-network run, limits, output capture

Read `CLAUDE.md` and `docs/SPEC.md` first (sections 6, 12, 13, 14). This session covers step 2 of SPEC §14.
Ask the user only when blocked (installs, permissions, decisions with consequences). Do not go beyond this session.
Scope is generic: no language profile (step 3), no LangGraph, no agents.

## Step 1. Dependency and config
- Add `docker` (docker-py) with `uv add docker`. Register the pytest marker `docker` and deselect it by default (`addopts = "-m 'not docker'"`).
- `config.py`: add `SandboxConfig` as the `sandbox` section of `Config`: `base_image` (`python:3.12`), `memory_mb`, `cpus`, `pids_limit`, `run_timeout_s`, `prepare_timeout_s`, `output_limit_bytes`. Defaults stay in the Pydantic models (decision 21); unknown keys are an error.
- Tests: defaults load, override works, unknown key fails.

## Step 2. Workspace
- `sandbox/workspace.py`: `make_workspace(project)` copies the project into a temp dir, skipping `.git`, `.venv`, `__pycache__` and tool caches. The original is never modified.

## Step 3. Image preparation (phase 1, network allowed)
- `sandbox/image.py`: `ensure_image(client, config, manifest_files, install_cmd)` generates a Dockerfile (`FROM base`, `COPY` manifests, `RUN install_cmd`) and builds it as `patchloop-env:<hash>`. Hash = sha256(base image, install command, manifest contents). If the tag exists, skip the build.
- A missing daemon, failed pull or failed build raises `SandboxError` with a clear message. No fallback.

## Step 4. Run (phase 2, no network)
- `sandbox/runner.py`: `run_in_sandbox(client, config, image, workdir, command) -> ExecResult`.
- Container: `network_mode="none"`, memory, CPU and pids limits, `cap_drop=["ALL"]`, `no-new-privileges`, non-root user, workdir bind-mounted at `/work`.
- Timeout: wait, then kill. Always remove the container. Capture stdout and stderr, truncate to `output_limit_bytes` keeping the tail.
- `ExecResult` (frozen dataclass): `exit_code`, `stdout`, `stderr`, `duration_s`, `timed_out`, `oom_killed`, `truncated`. It is internal, not an agent contract, so it stays out of `schemas.py`.

## Step 5. Tests
- Default tests use a fake docker client: no network, no real Docker.
- Opt-in tests marked `docker` (`pytest -m docker`) use a real container and check: no network, timeout kill, memory limit, non-root, original project unchanged, no leftover containers.

## End of session
Run `ruff check .` and `pytest -q` (and `pytest -m docker -q` with Docker running); all must pass. Write `docs/reports/02-sandbox.md` in the format from `CLAUDE.md` with measured numbers only (image build cold and cached, container overhead). Add decision 22 to `docs/DECISIONS.md`. In "Potrebné rozhodnutie" mention how the project itself is installed in step 3 (phase 1 copies only manifests). Do not continue to the next step of SPEC §14.
