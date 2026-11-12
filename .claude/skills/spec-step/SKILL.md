---
name: spec-step
description: Work loop for one step of SPEC §14 in patchloop. Use when starting or continuing a step, when the user says "next step" or names one, or when planning a session. Covers reading the spec, decisions first, the session prompt, test first, implementation rules, checks, independent review, local commits and the report.
argument-hint: "[step number from SPEC §14]"
---

# Implementing a step

Follow these phases in order. The step list is in `docs/SPEC.md` §14; the rules behind the loop are in `CLAUDE.md`. Phases 1-3 produce a plan and stop for the owner; code starts in phase 4.

1. **Read.** Open the step in SPEC §14 and every section it relies on, the last report in `docs/reports/`, and the DECISIONS entries about the area. Check memory for decisions the owner confirmed but that are not in `docs/DECISIONS.md` yet.
2. **Decisions first.** List what the step needs decided before code (a new dependency, a contract change, a choice SPEC leaves open), each with a recommendation and the alternatives. Ask the owner. Record the answers in `docs/DECISIONS.md` (next number, Slovak) before writing code. If SPEC is silent or wrong, stop and report "Potrebné rozhodnutie"; do not guess.
3. **Session prompt.** Write `docs/prompts/NN-<name>.md` in English: scope, what is out of scope, numbered sub-steps, and for each sub-step the tests that prove it (the acceptance criteria). Show it to the owner and wait for approval. Check `git branch --show-current`: work happens on a branch for the step, never on `main`, and the owner says which branch; do not create one unasked.
4. **Test first.** For each sub-step write the failing test in `tests/unit/` (fakes from `tests/support/`, no real LLM, no network), run it and see it fail for the right reason. Tests that need Docker or a model go to `tests/docker/` or `tests/e2e/` with the `docker` / `llm` markers.
5. **Implement.** Smallest code that passes, within the rules of `CLAUDE.md` ("Code"). Create only the files the prompt names. Do not go beyond the step: a later step of §14 is out of scope even when it looks close.
6. **Check.** `uv run ruff check .` and `uv run pytest -q`; with Docker running also `uv run pytest -m docker -q`. A run with a real model is reported as measured; the prompt is not tuned to make one example pass.
7. **Document.** A design choice made on the way goes to `docs/DECISIONS.md`; SPEC is edited only for factual changes, in the same change that makes them true, and never its "Zafixované rozhodnutia" table.
8. **Review.** Run the `branch-reviewer` subagent on the branch, naming the step and the prompt file. Fix each confirmed finding with a test that failed first. Leave findings that are taste or belong to a later step, and say so. Run the reviewer again after the fixes and list the earlier findings for it.
9. **Commit locally.** With `ruff` and `pytest` green, commit in a few larger groups: one per finished chunk of 2-3 sub-steps, module and its tests together, review fixes as separate `fix:` commits. Stage by explicit path. Conventional Commits message in English, no attribution lines. Never push, never amend or reset history.
10. **Report and hand over.** Write `docs/reports/NN-<name>.md` with the `report` skill, commit it, and show `git log --stat main..HEAD`. The owner pushes and opens the pull request.

If a phase fails twice for the same reason, stop and say what you tried instead of looping.
