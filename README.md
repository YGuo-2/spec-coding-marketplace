# Useful-marketplace

This repository provides the Codex plugin marketplace entry for `spce-workflow`.

## Import in Codex

Use the Codex "Add plugin marketplace" dialog:

- Source: `YGuo-2/Useful-marketplace`
- Git ref: `main`
- Sparse path: leave empty

Codex expects the marketplace manifest at `.agents/plugins/marketplace.json`.
The plugin source is at `plugins/spce-workflow`.

## What It Does

`spce-workflow` is a spec-first workflow for changes where correctness, scope control, resumability, and reviewability matter more than speed.

It includes seven skills:

- `spec-intake`: inspect context first, then ask only material clarification questions.
- `spce-workflow`: route the request to the right workflow branch.
- `spec-requirements-analysis`: run Kiro-style Analyze Requirements before artifact generation.
- `spec-requirements-first`: create product-led feature specs.
- `spec-design-first`: create design-led specs from fixed architecture or technical constraints.
- `spec-bugfix`: create evidence-led bugfix specs before code changes.
- `spec-acceptance`: run final multi-agent acceptance after all approved tasks are complete.

Use it for complex features, cross-module refactors, design-first work, regressions, production fixes, or high-risk changes. For tiny local edits, the workflow can be heavier than the task; low-risk work can opt into Quick Plan only with explicit human authorization.

## Workflow

![Spce workflow plugin workflow](spce-workflow-flowchart.png)

All generated artifacts live in `docs/specs/`; chat-only plans are not the source of truth.

1. Resume first if `docs/specs/progress.md` exists.
2. Intake clarifies goal, scope, risk, and acceptance criteria.
3. Router selects one branch:
   - Requirements-First: product goal or new capability without fixed technical design.
   - Design-First: architecture, ADR, HLD/LLD, or fixed technical approach drives the work.
   - Bugfix: restore existing expected behavior with evidence and regression protection.
4. Requirements-First and Design-First run Analyze Requirements before finalizing specs.
5. The selected branch writes Markdown artifacts plus:
   - `docs/specs/tasks.md`: human-readable task source of truth.
   - `docs/specs/progress.md`: resume entrypoint after interruption, shutdown, or lost thread.
   - `docs/specs/spec.yml`: Kiro-compatible machine index for workflow, artifacts, approval, risk, requirement IDs, task graph, and current task.
6. Implementation proceeds through Spec Progress CLI/MCP task updates, one safe task wave at a time.
7. When no unchecked tasks remain, local pre-acceptance runs before strict final multi-agent acceptance.

The preferred implementation approval phrase for every branch is:

```text
批准规范，启动执行
```

Legacy phrases remain valid for compatibility:

```text
批准 design-first 规范，启动执行
批准 bugfix 规范，启动执行
```

Passing validation is not approval. The human approval phrase is still required before writing business source code.

## Kiro Compatibility

The plugin keeps its existing Markdown strengths while adding a machine-readable index:

- Requirements-First keeps `product.md + architecture.md + tasks.md`.
- Design-First keeps `design.md + requirements.md + tasks.md`.
- Bugfix keeps `bugfix.md + design.md + tasks.md`.
- `spec.yml` maps those artifacts into Kiro-style workflow metadata: `workflow`, `mode`, `approval`, `risk_level`, `artifacts`, `requirements`, `task_ids`, `task_graph`, and `current_task`.

`product.md` and `requirements.md` include an `Analyze Requirements / 需求分析结论` section for ambiguity, conflicts, missing boundaries, failure paths, permissions, concurrency, data consistency, and risk checks.

## Progress And Resume

Task state is enforced through `tasks.md`, `progress.md`, and `spec.yml`.

Use the CLI directly:

```bash
python plugins/spce-workflow/scripts/spec_progress.py init docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py status docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py resume docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py start docs/specs/ T-001
python plugins/spce-workflow/scripts/spec_progress.py complete docs/specs/ T-001 --evidence "pytest tests/test_feature.py passed"
python plugins/spce-workflow/scripts/spec_progress.py block docs/specs/ T-001 --reason "needs API decision"
python plugins/spce-workflow/scripts/spec_progress.py skip docs/specs/ T-001 --approval "human approved skip"
python plugins/spce-workflow/scripts/spec_progress.py waves docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py sync-check docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py pre-acceptance docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py acceptance-init docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py acceptance-status docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py acceptance-plan-fixes docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py acceptance-next-round docs/specs/
python plugins/spce-workflow/scripts/spec_progress.py acceptance-finish docs/specs/
```

`complete` requires verification evidence. `skip` requires explicit human approval evidence. Task updates also synchronize the top-level `tasks.md` status, current task, progress count, and completion log. If a task is active and the worktree has business-code changes after an interruption, `resume` reports `interrupted`; the next agent must inspect the diff and evidence before continuing.

## MCP Tools

The plugin includes `.mcp.json` and a stdio server at `mcp/spec_progress_server.py`. The MCP tools wrap the same state machine as the CLI:

- `spec_status`
- `spec_resume`
- `spec_start_task`
- `spec_complete_task`
- `spec_block_task`
- `spec_skip_task`
- `spec_acceptance_init`
- `spec_acceptance_status`
- `spec_acceptance_start_agent`
- `spec_acceptance_complete_agent`
- `spec_acceptance_record_issue`
- `spec_acceptance_plan_fixes`
- `spec_acceptance_fix_start`
- `spec_acceptance_fix_complete`
- `spec_acceptance_next_round`
- `spec_acceptance_finish`

Agents should use MCP task tools when available. The CLI is the fallback and remains the canonical implementation.

## Hook Guard

A pre-commit hook template lives at:

```text
plugins/spce-workflow/assets/hooks/pre-commit-spec-progress
```

Install it into a target repository by copying it to `.git/hooks/pre-commit` and making it executable. It blocks commits that stage business-code changes while an active spec workflow exists but no legal `docs/specs/tasks.md`, `docs/specs/progress.md`, or `docs/specs/spec.yml` update is staged.

## Validation

Run the structural validator against the generated specs:

```bash
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --workflow requirements-first
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --workflow design-first
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --workflow bugfix
```

`--workflow auto` is the default when the directory contains exactly one recognizable artifact set.

The validator checks required files, unresolved template placeholders, formal GWT lines, branch-specific task IDs, LLD depth rules, basic structural sections, Analyze Requirements, task graph fields, and progress/index consistency when `spec.yml` or `progress.md` exists. It does not prove semantic quality, root-cause correctness, minimal scope, test strength, or safe rollout.

Color output defaults to `auto` and can be controlled with:

```bash
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --color never
```

Progress and acceptance checks:

```bash
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --progress
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --resume
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --sync-check
python plugins/spce-workflow/scripts/validate_spec.py docs/specs/ --pre-acceptance
```

## Final Acceptance

Final acceptance is intentionally strict. Local `pre-acceptance` may verify readiness when sub-agents are unavailable, but it is not final acceptance. Strict final acceptance requires explicit authorization to orchestrate sub-agents for first-wave review and adversarial review. If the current environment cannot run sub-agents, the workflow is blocked at acceptance; it must not be downgraded to a single-agent self-review or reported as complete.

Acceptance is resumable through `docs/specs/acceptance_state.json`. The state file freezes the original `tasks.md` task IDs, records review units, tracks which sub-agents are planned/running/completed, and records issue/fix/deferred status. After context compaction or interruption, agents must run `acceptance-status` and resume only the missing agents instead of rebuilding all review units.

Confirmed acceptance issues are repaired through `docs/specs/acceptance-fixes.md`, not by appending tasks to the original `docs/specs/tasks.md`. Rounds 1-3 may fix all evidence-backed actionable issues. From round 4 onward, only P0-P2 issues are auto-fixed; P3/P4 issues are deferred unless a human upgrades them. Round 6 is the hard stop for unresolved P0-P2 issues.

## High-Risk Work

Authentication, authorization, payments, billing, database schema changes, data repair, distributed consistency, cache consistency, secrets, encryption, sensitive data, incidents, rollback, and hotfix work require a visible warning and human deep review before merge.

## Development Checks

Useful local checks for this repository:

```bash
python -m py_compile plugins/spce-workflow/scripts/validate_spec.py
python -m py_compile plugins/spce-workflow/scripts/spec_progress.py
python -m py_compile plugins/spce-workflow/mcp/spec_progress_server.py
python plugins/spce-workflow/scripts/validate_spec.py --help
python plugins/spce-workflow/scripts/test_validate_spec.py
python -m json.tool plugins/spce-workflow/.codex-plugin/plugin.json
python -m json.tool plugins/spce-workflow/.mcp.json
git diff --check
```

For a spec directory that has entered final acceptance, also run:

```bash
python plugins/spce-workflow/scripts/spec_progress.py acceptance-status docs/specs/
```
