---
name: spec-acceptance
description: Use after Spce workflow implementation tasks are complete to run final acceptance against docs/specs/tasks.md. Trigger when a Requirements-First, Design-First, or Bugfix branch has no unchecked tasks and needs final multi-agent acceptance, adversarial review, completion checks, over-fallback checks, strict spec-adherence checks, and Bugfix rerouting for confirmed issues.
---

# Spce workflow Acceptance

Use this as the final step after a Spce workflow branch finishes every task in `docs/specs/tasks.md`. Its job is to verify the whole workflow outcome. It does not create `docs/specs/acceptance.md`; resumable acceptance state lives in `docs/specs/acceptance_state.json`, and acceptance repair work lives in `docs/specs/acceptance-fixes.md`.

## Required Announcement

If the branch skill has not already printed the announcement, print:

```markdown
我读到了Spec-acceptance技能。
```

## Hard Rules

- Enter only when `docs/specs/tasks.md` has no unchecked `- [ ]` tasks.
- Treat skipped `- [~]` tasks as valid only when the task text or completion log records explicit human approval to skip.
- Do not report the whole Spce workflow complete before this acceptance flow passes.
- Do not spawn sub-agents unless the current conversation explicitly authorizes sub-agent orchestration. If authorization is missing, ask for it and stop.
- Do not downgrade this flow to a single local review or pretend local review is equivalent to multi-agent acceptance.
- Local `pre-acceptance` is allowed before sub-agent review, but it is only a readiness check. It must never be reported as final acceptance.
- If the current environment cannot orchestrate sub-agents, state that final acceptance is blocked by missing orchestration capability and do not report the workflow complete.
- Do not edit business source code inside this skill. Confirmed issues must be recorded through the acceptance progress tools first, then fixed from `docs/specs/acceptance-fixes.md`.
- Never append acceptance repair tasks to the original `docs/specs/tasks.md`. The original task IDs are frozen at acceptance start; if they change, final acceptance is blocked.
- Before spawning any sub-agent, run `acceptance-status` (MCP `spec_acceptance_status` or CLI) when `acceptance_state.json` exists. Resume pending agents instead of rebuilding all units from memory.
- Every issue must have severity `P0` through `P4`, affected unit/task IDs, and evidence. Unsupported opinions or style preferences are not actionable issues.
- Rounds 1-3 may auto-fix all evidence-backed actionable issues. From round 4 onward, only `P0`, `P1`, and `P2` issues are auto-fixed; `P3` and `P4` issues are deferred unless the human explicitly upgrades them. Stop at round 6 and request human decision if any `P0`-`P2` issue remains.
- Final success output must summarize the completed plugin workflow, not dump raw agent review transcripts.

## State A: Acceptance Preconditions

Read the approved spec artifacts, `docs/specs/tasks.md`, relevant diffs, and verification results.

Detect the workflow from the spec files:

- Requirements-First: `product.md`, `architecture.md`, and `tasks.md`
- Design-First: `design.md`, `requirements.md`, and `tasks.md`
- Bugfix: `bugfix.md`, `design.md`, and `tasks.md`

If any task is still unchecked, return to the selected branch's Controlled Implementation state. If required verification evidence is missing, treat that as an acceptance issue.

Before asking for sub-agent authorization, run or request the equivalent of:

```bash
python <plugin-root>/scripts/validate_spec.py docs/specs/ --pre-acceptance
```

If `docs/specs/acceptance_state.json` already exists, resume with:

```bash
python <plugin-root>/scripts/spec_progress.py acceptance-status docs/specs/
```

Use the returned pending/running agent IDs and affected units as the source of truth. Do not infer missing agents from chat history.

If pre-acceptance fails, summarize the local issues and route them back to the selected branch or Bugfix path. If pre-acceptance passes but sub-agent orchestration is unavailable, the required wording is:

```markdown
预检通过，但严格验收未完成：当前环境不支持按 `tasks.md` 编排子 agent 审查和对抗审查。根据 Spce workflow 规则，不能把 pre-acceptance 伪装为 final acceptance，也不能宣告整个工作流完成。
```

If sub-agent authorization is missing, ask:

```markdown
结尾验收需要按 `tasks.md` 编排子 agent 进行审查和对抗审查。请明确授权我启动子 agent 后，我再继续验收流程。
```

If sub-agent orchestration is unavailable in the current environment, stop with:

```markdown
结尾验收被阻塞：当前环境不支持按 `tasks.md` 编排子 agent 审查和对抗审查。根据 Spce workflow 规则，不能降级为单 agent 自审，也不能宣告整个工作流完成。
```

## State B: Initialize Or Resume Acceptance

If no acceptance state exists, initialize it:

```bash
python <plugin-root>/scripts/spec_progress.py acceptance-init docs/specs/
```

The tool parses `tasks.md`, freezes the original task IDs, builds review units, and plans two agents per unit: first-wave review plus adversarial review. It writes `docs/specs/acceptance_state.json`.

Review-unit rules are implemented by `spec_progress.py`:

- high-risk tasks stand alone
- low-risk tasks may group only with contiguous tasks under the same phase
- grouped units contain at most three tasks
- later rounds include only affected units

## State C: First-Wave Review

Spawn only the first-wave agents shown as planned by `acceptance-status`. Before each launch, call `acceptance-start-agent`/`spec_acceptance_start_agent`. Each agent owns exactly one review unit and must not edit files.

Each first-wave prompt must include:

- The workflow type and relevant approved spec files
- The assigned task IDs and task text from `tasks.md`
- Relevant changed files, diffs, tests, logs, and verification results
- A request to review completion, strict spec adherence, overbroad fallback, missing verification, regression risk, and unapproved behavior
- The instruction to classify each finding as `P0`, `P1`, `P2`, `P3`, or `P4` with evidence; non-evidence-backed concerns must be reported as notes, not issues

Each first-wave agent must return:

```markdown
## Review Unit
- Unit: [task IDs]
- Status: PASS | ACTIONABLE_ISSUES
- Completion: [complete / incomplete with evidence]
- Spec Adherence: [strict / deviation with evidence]
- Over-Fallback: [none / present with evidence]
- Verification: [sufficient / missing with evidence]
- Issues: [numbered actionable findings with severity/evidence or n/a]
```

After each result, call `acceptance-complete-agent`. For every evidence-backed issue, call `acceptance-record-issue`. Wait for all first-wave agents before starting the second wave.

## State D: Adversarial Review

Spawn only the planned adversarial agents for the current round. Each adversarial agent reviews the matching first-wave report, the same review unit, and the same spec evidence.

Each adversarial agent must:

- Challenge whether the first-wave review missed incomplete work, spec drift, over-fallback, weak tests, hidden regressions, or unsupported assumptions
- Prefer concrete evidence over agreement
- Assign severity `P0`-`P4` to any new issue
- Return `PASS` only when no actionable challenge remains

After each result, call `acceptance-complete-agent` and record any issues through `acceptance-record-issue`.

## State E: Loop Until Clear

After a review round completes, call:

```bash
python <plugin-root>/scripts/spec_progress.py acceptance-plan-fixes docs/specs/
```

This creates or refreshes `docs/specs/acceptance-fixes.md`. It must not modify `docs/specs/tasks.md`.

Fix policy:

- rounds 1-3: plan fixes for all evidence-backed actionable issues
- rounds 4-6: plan fixes only for `P0`, `P1`, and `P2`; defer `P3` and `P4`
- after round 6: if any `P0`-`P2` remains, stop and request human decision

After fixes complete, call `acceptance-next-round`; it plans agents only for affected units. Do not rerun all original units unless the tool reports all units as affected.

Stop when `acceptance-status` reports no pending agents, no pending fixes, and no unresolved issues. Then call `acceptance-finish`.

## State F: Final Branch

If `acceptance-finish` succeeds, output the final workflow completion result:

```markdown
## Spce workflow 完成结果

- 流程：[Requirements-First / Design-First / Bugfix]
- 规范：[已批准并执行的 spec 文件]
- Tasks：[全部完成 / 人类批准跳过项]
- 验证：[已运行的关键验证]
- 结尾验收：通过
- 最终结论：整个 Spce workflow 流程已完成。
```

If issues remain:

- Summarize only actionable issues with evidence and affected task IDs.
- Use `docs/specs/acceptance-fixes.md` as the fix queue.
- Do not append these fixes to `docs/specs/tasks.md`.
- After fixes complete, resume this acceptance flow with `acceptance-status`.
