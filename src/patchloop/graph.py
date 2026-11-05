"""The repair loop as a LangGraph (SPEC §3, §8, decision 25).

Nodes: prepare, check_original, tester, fix, apply, check, decide, finish. Every decision
(repeat, stop, roll back, accept a generated test) is plain code; the model only proposes.

The state of every attempt is the original code plus ONE merged patch. Before each attempt the
workspace is reset to the original and the best attempt's patch is applied, so the Programmer
sees the best code so far with its remaining errors, and a worse attempt is simply never used
as a base (rollback). The Reviewer plugs in at the marked place (step 6).

A generated test lives in the state (`repro_test`), not in the project: it is written into the
workspace for the Programmer to read, removed for build and lint, and run on its own after the
project's checks. It never reaches the diff.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from patchloop.agents.programmer import HistoryEntry, propose_patch
from patchloop.agents.tester import PreviousTry, TesterMode, free_path, propose_test
from patchloop.checks import run_checks, run_test_file
from patchloop.config import Config
from patchloop.context.files import has_tests
from patchloop.llm.client import LLMClient
from patchloop.patching import apply_patch, make_diff, patch_hash, restore_files
from patchloop.profiles.base import LanguageProfile, ProjectSetup
from patchloop.profiles.registry import detect_profile
from patchloop.sandbox import ensure_image, make_workspace, remove_workspace
from patchloop.schemas import Attempt, CheckResult, Failure, Patch, RunResult

StopReason = Literal["success", "iteration_limit", "stagnation", "timeout", "none"]
Score = tuple[int, int, int]
SHOWN_LEFT = 10  # failures listed in the explanation of a partial fix
PROBLEM_CHARS = 300
REJECTED = {
    "passes": (
        "It passes on the current code, so it does not reproduce the bug. "
        "Make it fail because of the described bug."
    ),
    "broken": (
        "It fails for a reason that is not the bug (an import, syntax or setup error in the "
        "test itself): {detail}. Fix the test."
    ),
}


class RunState(TypedDict, total=False):
    issue: str | None
    reliability: Literal["normal", "reduced"]
    original: list[CheckResult]
    attempts: list[Attempt]
    notes: list[HistoryEntry]  # one per attempt, same order
    best: int | None  # position in `attempts`; None = the original code is still the best
    best_files: dict[str, str]  # merged patch of the best attempt
    new_patch: Patch | None  # what the Programmer returned in the attempt in flight
    merged_files: dict[str, str]
    touched: list[str]  # every path any attempt wrote
    stop_reason: StopReason
    tester_mode: TesterMode
    repro_test: dict[str, str]  # path -> content of the accepted generated test (at most one)
    route: str
    result: RunResult


def all_failures(checks: list[CheckResult]) -> list[Failure]:
    return [failure for check in checks for failure in check.failures]


def passed(checks: list[CheckResult]) -> bool:
    return bool(checks) and all(check.passed for check in checks)


def score(checks: list[CheckResult]) -> Score:
    """Lower is better. A failed build is worse than any failing tests: later stages never ran."""
    build_failed = any(c.stage == "build" and not c.passed for c in checks)
    return (
        int(build_failed),
        sum(len(c.failures) for c in checks),
        sum(c.failing_tests for c in checks),
    )


def _clip(text: str, limit: int = PROBLEM_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + " ..."


def _signature(checks: list[CheckResult]) -> frozenset[tuple[Any, ...]]:
    return frozenset((f.kind, f.file, f.line, f.message) for f in all_failures(checks))


@dataclass
class Engine:
    project: Path
    config: Config
    llm: LLMClient
    docker: Any
    profile: LanguageProfile | None = None
    clock: Callable[[], float] = time.monotonic
    checks_fn: Callable[..., list[CheckResult]] = run_checks
    test_file_fn: Callable[..., CheckResult] = run_test_file
    image_fn: Callable[..., str] = ensure_image
    # set by run()/prepare
    base: Path = field(init=False)
    work: Path = field(init=False)
    setup: ProjectSetup = field(init=False)
    image: str = field(init=False)
    deadline: float = field(init=False)

    # ---- nodes -------------------------------------------------------------------------------

    def prepare(self, state: RunState) -> RunState:
        self.profile = self.profile or detect_profile(self.project)
        self.setup = self.profile.setup(self.project, self.config)
        sandbox = self.config.sandbox.model_copy(update={"base_image": self.setup.image})
        self.image = self.image_fn(self.docker, sandbox, self.setup.manifests, self.setup.install)
        return {}

    def _run_test_file(self, path: str, content: str) -> CheckResult:
        """Run one test file on the current workspace; the file is removed afterwards."""
        assert self.profile is not None
        apply_patch(self.work, Patch(files={path: content}, explanation="generated test"))
        try:
            return self.test_file_fn(
                self.docker, self.config, self.profile, self.setup, self.image, self.work, path
            )
        finally:
            (self.work / path).unlink(missing_ok=True)

    def _run_checks(self, repro: dict[str, str] | None = None) -> list[CheckResult]:
        """The project's checks, then the generated test (only if the build passed)."""
        assert self.profile is not None
        for path in repro or {}:
            (self.work / path).unlink(missing_ok=True)  # the test is not part of build or lint
        results = self.checks_fn(
            self.docker, self.config, self.profile, self.setup, self.image, self.work
        )
        if all(r.passed for r in results if r.stage == "build"):
            results += [self._run_test_file(path, text) for path, text in (repro or {}).items()]
        return results

    def check_original(self, state: RunState) -> RunState:
        results = self._run_checks()
        update: RunState = {"original": results}
        issue = state["issue"]
        if passed(results) and not issue and has_tests(self.work):
            update["result"] = RunResult(status="no_bugs_found", stop_reason="none")
            update["route"] = "finish"
        elif self.clock() >= self.deadline:
            update["stop_reason"] = "timeout"
            update["route"] = "finish"
        elif passed(results):  # nothing fails yet: a generated test may show the bug (SPEC §9)
            update["tester_mode"] = "issue" if issue else "basic"
            update["route"] = "tester"
        else:
            update["route"] = "fix"
        return update

    def tester(self, state: RunState) -> RunState:
        """Get a test that fails on the original code, within `max_test_attempts` tries.

        With a bug description the test must fail (it reproduces the bug); without one the
        project has no tests, and the generated basic tests either pass (nothing found) or fail
        (a candidate bug). Either way the result is less reliable than with the project's tests.
        """
        assert self.profile is not None
        mode = state["tester_mode"]
        path = free_path(self.work, self.profile.generated_test_path)
        previous: PreviousTry | None = None
        for _ in range(self.config.max_test_attempts):
            if self.clock() >= self.deadline:
                break
            outcome = propose_test(
                self.llm,
                self.work,
                self.config.loop,
                mode=mode,
                path=path,
                framework=self.profile.test_framework,
                issue=state["issue"],
                previous=previous,
                language=self.config.language,
            )
            if outcome.plan is None:  # an unusable answer is a spent attempt
                continue
            content = outcome.plan.content
            check = self._run_test_file(path, content)
            verdict = self.profile.classify_test_run(check)
            if verdict == "passes" and mode == "basic":
                break  # the basic tests pass: nothing found
            if verdict == "reproduces":
                reliability = "normal" if mode == "issue" else "reduced"
                return {
                    "repro_test": {path: content},
                    "original": [*state["original"], check],
                    "reliability": reliability,
                    "route": "fix",
                }
            detail = _clip(check.failures[0].message) if check.failures else ""
            previous = PreviousTry(content, REJECTED[verdict].format(detail=detail))
        if self.clock() >= self.deadline:
            return {"stop_reason": "timeout", "route": "finish"}
        if mode == "basic":
            result = RunResult(status="no_bugs_found", stop_reason="none", reliability="reduced")
            return {"result": result, "route": "finish"}
        return {"route": "fix"}  # no test: go on from the description, as less reliable

    def fix(self, state: RunState) -> RunState:
        attempts, notes = state["attempts"], state["notes"]
        best_files = state["best_files"]
        restore_files(self.base, self.work, state["touched"])
        repro = state["repro_test"]
        if repro:  # the Programmer reads the failing test; its edits are refused
            apply_patch(self.work, Patch(files=repro, explanation="generated test"))
        if best_files:
            apply_patch(self.work, Patch(files=best_files, explanation="best attempt so far"))
        best = state["best"]
        failures = all_failures(attempts[best].checks if best is not None else state["original"])
        history = [note for note, attempt in zip(notes, attempts, strict=True) if attempt.checks]
        outcome = propose_patch(
            self.llm,
            self.work,
            failures,
            self.config.loop,
            issue=state["issue"],
            history=history,
            language=self.config.language,
            protected=list(repro),
        )
        if outcome.patch is None:  # a spent attempt: nothing to apply or check
            attempt = Attempt(index=len(attempts), patch_hash="")
            note = HistoryEntry(f"(no usable answer: {outcome.error})", [])
            return {
                "attempts": [*attempts, attempt],
                "notes": [*notes, note],
                "new_patch": None,
                "route": "decide",
            }
        merged = {**best_files, **outcome.patch.files}
        return {"new_patch": outcome.patch, "merged_files": merged, "route": "apply"}

    def apply(self, state: RunState) -> RunState:
        patch = state["new_patch"]
        assert patch is not None
        apply_patch(self.work, patch)
        return {"touched": sorted({*state["touched"], *patch.files})}

    def check(self, state: RunState) -> RunState:
        patch, merged = state["new_patch"], state["merged_files"]
        assert patch is not None
        results = self._run_checks(state["repro_test"])
        attempts, notes = state["attempts"], state["notes"]
        attempt = Attempt(
            index=len(attempts),
            patch_hash=patch_hash(Patch(files=merged, explanation="")),
            checks=results,
        )
        note = HistoryEntry(patch.explanation, all_failures(results))
        best = state["best"]
        threshold = score(attempts[best].checks if best is not None else state["original"])
        update: RunState = {"attempts": [*attempts, attempt], "notes": [*notes, note]}
        if passed(results) or score(results) < threshold:
            update["best"] = len(attempts)
            update["best_files"] = merged
        return update

    def decide(self, state: RunState) -> RunState:
        attempts = state["attempts"]
        last = attempts[-1]
        real = [a for a in attempts if a.checks]
        reason: StopReason | None = None
        if passed(last.checks):
            # Reviewer (step 6) approves here; its remarks would send the run back to fix.
            reason = "success"
        elif len(attempts) >= self.config.max_attempts:
            reason = "iteration_limit"
        elif last.checks and len(real) >= 2 and (
            last.patch_hash in {a.patch_hash for a in real[:-1]}
            or _signature(real[-1].checks) == _signature(real[-2].checks)
        ):
            reason = "stagnation"
        elif self.clock() >= self.deadline:
            reason = "timeout"
        if reason is None:
            return {"route": "fix"}
        return {"stop_reason": reason, "route": "finish"}

    def finish(self, state: RunState) -> RunState:
        if "result" in state:  # no_bugs_found
            return {}
        attempts, best = state["attempts"], state["best"]
        stop_reason = state.get("stop_reason", "none")
        fixed = bool(attempts) and passed(attempts[-1].checks)
        diff, explanation, best_index = "", "", None
        if best is not None:
            restore_files(self.base, self.work, state["touched"])
            apply_patch(self.work, Patch(files=state["best_files"], explanation="best attempt"))
            diff = make_diff(self.base, self.work, state["touched"])
            best_index = attempts[best].index
            explanation = state["notes"][best].explanation
            if not fixed:
                left = all_failures(attempts[best].checks)
                lines = [f"- {f.file or '?'}:{f.line or '?'} {f.message}" for f in left]
                more = len(lines) - SHOWN_LEFT
                lines = lines[:SHOWN_LEFT] + ([f"- ... and {more} more"] if more > 0 else [])
                explanation += "\n\nStill failing:\n" + "\n".join(lines)
        status = "fixed" if fixed else "partially_fixed" if best is not None else "not_fixed"
        result = RunResult(
            status=status,
            best_attempt=best_index,
            diff=diff,
            explanation=explanation,
            stop_reason=stop_reason,
            reliability=state["reliability"],
        )
        return {"result": result}

    # ---- wiring ------------------------------------------------------------------------------

    def build(self) -> Any:
        graph = StateGraph(RunState)
        names = ("prepare", "check_original", "tester", "fix", "apply", "check", "decide", "finish")
        for name in names:
            graph.add_node(name, getattr(self, name))

        def route(state: RunState) -> str:
            return state["route"]

        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "check_original")
        graph.add_conditional_edges("check_original", route, ["tester", "fix", "finish"])
        graph.add_conditional_edges("tester", route, ["fix", "finish"])
        graph.add_conditional_edges("fix", route, ["apply", "decide"])
        graph.add_edge("apply", "check")
        graph.add_edge("check", "decide")
        graph.add_conditional_edges("decide", route, ["fix", "finish"])
        graph.add_edge("finish", END)
        return graph.compile()

    def run(self, issue: str | None = None) -> RunResult:
        """One run. The original project is only read; both copies are removed at the end."""
        copy_env = self.config.sandbox.copy_env
        self.base = make_workspace(self.project, copy_env=copy_env)  # pristine snapshot
        try:
            self.work = make_workspace(self.project, copy_env=copy_env)
        except BaseException:
            remove_workspace(self.base)
            raise
        try:
            self.deadline = self.clock() + self.config.loop.total_timeout_s
            initial: RunState = {
                "issue": issue,
                "reliability": "reduced" if issue else "normal",  # until a test reproduces it
                "attempts": [],
                "notes": [],
                "best": None,
                "best_files": {},
                "touched": [],
                "repro_test": {},
            }
            limit = 12 + 4 * self.config.max_attempts  # four nodes per attempt
            final = self.build().invoke(initial, {"recursion_limit": limit})
            return final["result"]
        finally:
            remove_workspace(self.work)
            remove_workspace(self.base)


def run_fix(
    project: Path,
    config: Config,
    llm: LLMClient,
    docker: Any,
    issue: str | None = None,
    **overrides: Any,
) -> RunResult:
    return Engine(project, config, llm, docker, **overrides).run(issue)
