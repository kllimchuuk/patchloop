---
name: report
description: Writes the patchloop stage report in the fixed ZVIT shape (Hotovo / Čísla / Odchýlky od SPEC / Potrebné rozhodnutie / Ďalej), in Slovak. Use at the end of a step or work session, when blocked, for docs/reports/NN-*.md, or when the user asks for a report or a summary of the branch.
---

# Report

Write the report in Slovak, in exactly this shape. It goes to the chat at the end of a session or when blocked, and at the end of a step into `docs/reports/NN-<name>.md` (same number and name as the step's prompt in `docs/prompts/`).

```
ZVIT <dátum> — <etapa>
Hotovo: …
Čísla: … (len zmerané)
Odchýlky od SPEC: … | žiadne
Potrebné rozhodnutie: … | žiadne
Ďalej: …
```

Rules:

- **Measured only.** A test count, a duration or a model result appears only if it was obtained by running something in this session; give the command next to it (`uv run pytest -q`, `uv run pytest -m docker tests/docker`). A run with a real model states the model, how many runs, and that it is not a statistic. If it was not run, write "nemerané".
- **Say what failed.** Failing tests, skipped checks and unverified assumptions go into the report, not out of it.
- **Deviations.** Each deviation from SPEC with its reason and the DECISIONS number, or "žiadne".
- **Decisions.** Each open question with a recommendation. Something in SPEC that did not work in practice goes here; it is never worked around silently.
- **Review.** If the `branch-reviewer` subagent ran, give its verdict and what was fixed after it.
- **Agent notes.** When the first attempt was wrong and a test, the review or the owner caught it, record it in one line: what was wrong, how it was caught, what changed.
- In the file, the block may be followed by short sections "Čo sa urobilo" and "Známe obmedzenia". Keep it short: a report is read, not browsed.
