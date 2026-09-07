Start each session by running the /plan-recap skill to understand the project goal and status.

Always read `ARCHITECTURE.md` at the repo root first if it exists — it should be the current, whole-system map (components, request flow, deploy flow, what's live vs. deferred) pointing to the ADR/spec for any decision's full reasoning, not restating it. Also read README files across the project (including in subdirectories and modules), and review the `docs/` directory if one exists (`status_docs/` for planning and session notes, `prds/` for product requirements, `specs/` for technical specs, `decisions/` for ADRs) — make sure you review documentation and understand the codebase before you proceed. If no `ARCHITECTURE.md` exists once there's a real system to describe (more than a single component), create one before closing the session, same as the README rule below. Keep it current when a change alters what it describes (new component, changed flow, a requirement moving from deferred to built).

For any new feature or project planning, run /grill-me to stress-test the plan before building. Do not run this when operating autonomously.

When sanity-checking a state model or UI direction before committing to a real implementation, use /prototype to build throwaway code that answers the question.

For any production coding work:
- Always follow test driven development as outlined in /tdd and /testing.
- Look for opportunities to validate your own work and get feedback directly. Design and run an end-to-end smoke test or practical validation. For projects involving web UI use the /agent-browser skill to review UIs directly.
- Prefer the simplest change that moves things forward. Avoid large refactors or multiple concerns in one go.
- After each logical change:
	1. Check what's staged: `git status`
	2. Commit with a short, descriptive message: `git commit -m "your message"`. Keep it to a one-line summary (~72 chars); add a short body only if genuinely needed, a few lines max — not a rationale essay.
	3. Commit often. Each commit should represent one coherent, working change — not a batch of unrelated edits.
- For Python projects, always use a virtual environment: `python -m venv venv` if one doesn't exist, then `source venv/bin/activate` before running any `pip install`.
- Follow /documentation-and-adrs when making significant architectural decisions or choosing between competing approaches. If a README.md does not exist at the project root, create one before closing the session.

Do not write to Claude's internal memory folders (e.g. `~/.claude/projects/.../memory/`). Persist session context and learnings by updating the relevant `.md` files, as explained in /documentation-and-adrs and /summarise-session.

Close each session by running the /summarise-session skill to write up what we did.

This CLAUDE.md provides the framework. Skills contain the detailed guidance. Load skills based on what you're doing:

| Skill | Purpose | Load when |
|-------|---------|-----------|
| plan-recap | Read planning docs and produce a session briefing | Start of every session |
| grill-me | Stress-test a plan by interviewing the user | New features or project planning (not autonomous runs) |
| prototype | Build throwaway code to sanity-check a state model or UI direction | Before committing to a design when the logic or UI feel is uncertain |
| tdd | RED-GREEN-REFACTOR workflow, recovery strategies | Starting any code work |
| testing | Test patterns, factories, antipatterns | Starting any code work |
| agent-browser | Browser automation for reviewing web UIs | Validating web/UI changes |
| documentation-and-adrs | Record architectural decisions and ensure README exists | Significant technical decisions; end of any session where no README exists |
| summarise-session | Write a structured session summary to a WORK_SUMMARY file | End of every session |
| simplify | Review recently changed code for clarity/consistency and refine without changing behaviour | After a burst of fast-moving changes, before committing/closing a slice |
| security-reviewer | Review code for injection, auth, secrets, and data-handling issues | Before deploying, or when touching security-sensitive surfaces (auth, input validation, public endpoints) |
