---
name: spec-bugfix
description: Use for Spce workflow Bugfix work when the user asks to fix, investigate, reproduce, roll back, or handle a regression, failing behavior, production issue, incorrect result, or data inconsistency. Generates bugfix.md, design.md, and tasks.md before implementation.
---

# Spce workflow Bugfix

Use this branch to restore existing expected behavior with evidence, root-cause analysis, and minimal safe implementation.

If the entry router has not already printed the announcement, print:

```markdown
我读到了Spce workflow技能。
我会按照“Bugfix”分支来完成。
```

## Hard Rules

- Do not write business source code until the human explicitly replies the preferred approval phrase `批准规范，启动执行`.
- For compatibility, also accept the legacy Bugfix approval phrase `批准 bugfix 规范，启动执行`.
- Generate or update spec artifacts in `docs/specs/`; they are the source of truth.
- New specs must also generate `docs/specs/spec.yml` and `docs/specs/progress.md` from the templates in `../../assets/templates/`.
- Do not hide root cause behind symptom-only patches.
- Do not delete failing tests, weaken assertions, or disable warnings just to pass validation.
- Keep the fix minimal and avoid unrelated refactors.
- If the bug requires new user-visible capability or product scope change, stop and reroute to Feature.
- If the bug evidence comes from final acceptance and `docs/specs/acceptance_state.json` exists, do not append repair tasks to the original `docs/specs/tasks.md`. Use `docs/specs/acceptance-fixes.md` and the acceptance progress tools instead, then return to `../spec-acceptance/SKILL.md`.

## High-Risk Warning

If the task involves authentication, authorization, payments, billing, database schema changes, data repair, distributed consistency, cache consistency, secrets, encryption, sensitive data, incident mitigation, rollback, or hotfix work, include this warning even when the router was skipped:

```markdown
> [!WARNING]
> 高风险变更警告：当前任务涉及核心系统或高影响范围区域，必须进行人类深度审查，切勿草率合并。
```

## Intake Precondition

Before State A, if the current conversation does not already include a `spec-intake` summary or a clear no-material-questions decision, read and follow `../spec-intake/SKILL.md`. If intake asks questions, stop and wait for the human answer before generating specs.

## State A: Bug Analysis Clarification

Inspect available evidence before asking questions: failing tests, logs, screenshots, issue text, alerts, recent changes, existing specs, manifests, and relevant code paths.

Clarify only bug-critical gaps:

- current incorrect behavior and evidence
- expected behavior
- behaviors that must remain unchanged
- reproduction steps, frequency, and affected inputs
- environment, version, and deployment context
- suspected root cause or recent related changes

If clarification is needed, output a concise numbered question list focused on reproduction, evidence, scope, and regression constraints. Unknowns may be recorded as assumptions or risks if the user accepts that.

## State B: Bugfix Spec Artifact Generation

If this is an acceptance repair:

- Treat `docs/specs/acceptance_state.json` as the source of truth for round, issue severity, affected units, and pending fixes.
- Treat `docs/specs/acceptance-fixes.md` as the repair task list.
- Do not regenerate `docs/specs/tasks.md`, do not append `B-xxx` tasks to it, and do not change the frozen original task IDs.
- Use `python <plugin-root>/scripts/spec_progress.py acceptance-fix-start docs/specs/ F-xxx` before editing code and `acceptance-fix-complete` with evidence after verification.
- When all planned fixes are done, resume `../spec-acceptance/SKILL.md` via `acceptance-status` / `acceptance-next-round`.

For ordinary bugfixes, continue with the normal artifact flow below.

Use the plugin templates from `../../assets/templates/`:

- `bugfix_template.md`
- `bugfix_design_template.md`
- `bugfix_tasks_template.md`
- `progress_template.md`
- `spec_index_template.yml`

Generate:

- `docs/specs/bugfix.md`: defect summary, impact, environment, reproduction evidence, automated-reproduction status, substitute evidence when needed, current behavior, expected behavior, unchanged behavior, scope boundaries, and non-goals
- `docs/specs/design.md`: root-cause analysis, code-path trace, minimal fix strategy, alternatives, affected surface, explicitly untouched areas, test strategy, and non-automated verification risks when applicable
- `docs/specs/tasks.md`: ordered atomic tasks using `- [ ]`, starting with reproduction or strongest available evidence, then minimal fix, regression protection, and verification. Each task must include status, files, verify, evidence, depends_on, risk, covers, and parallelizable.
- `docs/specs/progress.md`: resume entrypoint with workflow status, current task, approval state, branch, commit, blockers, and recovery notes
- `docs/specs/spec.yml`: Kiro-compatible machine index with workflow, mode, approval, risk level, artifact paths, requirement IDs, task graph, current task, and checkpoint

Bugfix defaults to `strict`. Do not use Quick Plan for P0/P1, production incidents, data repair, auth, payment, schema, consistency, secrets, encryption, or sensitive-data work.

Before review, replace all template placeholders with concrete content. If a template section does not apply, state that explicitly with the reason instead of leaving placeholder text.

If automated reproduction cannot be created, record why in `bugfix.md`, describe substitute evidence strength and limits, and use the strongest available verification substitute.

The preferred approval phrase for implementation is:

```text
批准规范，启动执行
```

The legacy Bugfix phrase remains valid for compatibility:

```text
批准 bugfix 规范，启动执行
```

Suggested validation:

```bash
python <plugin-root>/scripts/validate_spec.py docs/specs/ --workflow bugfix
python <plugin-root>/scripts/spec_progress.py init docs/specs/
python <plugin-root>/scripts/validate_spec.py docs/specs/ --resume
```

This is a structural integrity check only. It does not prove root-cause quality, minimal-fix scope, unchanged-behavior coverage, substitute reproduction strength, rollback safety, or monitoring sufficiency; review those semantics before implementation. Passing validation does not approve implementation; implementation still requires an accepted approval phrase.

## State C: Controlled Implementation

Only enter this state after explicit approval.

When the approval phrase is received, update any generated status or approval-record fields in the spec artifacts before implementation.

Implementation rules:

- Read `docs/specs/bugfix.md`, `docs/specs/design.md`, and `docs/specs/tasks.md`.
- Select only the first unchecked task in `tasks.md`.
- Before editing business code for that task, call `spec_start_task` through MCP or run `python <plugin-root>/scripts/spec_progress.py start docs/specs/ B-xxx`.
- Implement only that task and keep the change tied to the recorded root cause.
- Prefer proof order: reproduce the bug, prove the fix, prove unchanged behavior.
- If implementation reveals that the recorded root cause is wrong, the fix scope must change, or `bugfix.md`, `design.md`, or `tasks.md` must change, stop code work, return to State B, update the specs, run sync-check, set approval to `reapproval-required`, and wait for an accepted approval phrase again before continuing.
- Run verification and perform at most three self-healing loops.
- After passing the selected task's verification criteria, call `spec_complete_task` through MCP or run `python <plugin-root>/scripts/spec_progress.py complete docs/specs/ B-xxx --evidence "<verification evidence>"`. For a reproduction task, passing means the failure proof behaves as expected on unfixed code or the substitute evidence is recorded and strong enough to constrain the fix.
- If blocked, call `spec_block_task` or `python <plugin-root>/scripts/spec_progress.py block docs/specs/ B-xxx --reason "<reason>"`.
- If skipped, call `spec_skip_task` or `python <plugin-root>/scripts/spec_progress.py skip docs/specs/ B-xxx --approval "<human approval evidence>"`.
- Provide a commit message suggestion in this form:

```text
fix(scope): short description

Implements task: [task description]
Spec: docs/specs/tasks.md
```

If unchecked tasks remain, ask whether to continue only after the current task is complete.

If no unchecked tasks remain in `docs/specs/tasks.md`, read and follow `../spec-acceptance/SKILL.md` before reporting the whole workflow complete.
