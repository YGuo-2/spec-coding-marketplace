---
name: spec-bugfix
description: Use for Spec Coding Bugfix work when the user asks to fix, investigate, reproduce, roll back, or handle a regression, failing behavior, production issue, incorrect result, or data inconsistency. Generates bugfix.md, design.md, and tasks.md before implementation.
---

# Spec Coding Bugfix

Use this branch to restore existing expected behavior with evidence, root-cause analysis, and minimal safe implementation.

If the entry router has not already printed the announcement, print:

```markdown
我读到了Spec-coding技能。
我会按照“Bugfix”分支来完成。
```

## Hard Rules

- Do not write business source code until the human explicitly replies `批准 bugfix 规范，启动执行`.
- Generate or update spec artifacts in `docs/specs/`; they are the source of truth.
- Do not hide root cause behind symptom-only patches.
- Do not delete failing tests, weaken assertions, or disable warnings just to pass validation.
- Keep the fix minimal and avoid unrelated refactors.
- If the bug requires new user-visible capability or product scope change, stop and reroute to Feature.

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

Use the plugin templates from `../../assets/templates/`:

- `bugfix_template.md`
- `bugfix_design_template.md`
- `bugfix_tasks_template.md`

Generate:

- `docs/specs/bugfix.md`: defect summary, impact, environment, reproduction evidence, automated-reproduction status, substitute evidence when needed, current behavior, expected behavior, unchanged behavior, scope boundaries, and non-goals
- `docs/specs/design.md`: root-cause analysis, code-path trace, minimal fix strategy, alternatives, affected surface, explicitly untouched areas, test strategy, and non-automated verification risks when applicable
- `docs/specs/tasks.md`: ordered atomic tasks using `- [ ]`, starting with reproduction or strongest available evidence, then minimal fix, regression protection, and verification

Before review, replace all template placeholders with concrete content. If a template section does not apply, state that explicitly with the reason instead of leaving placeholder text.

If automated reproduction cannot be created, record why in `bugfix.md`, describe substitute evidence strength and limits, and use the strongest available verification substitute.

The approval phrase for implementation is:

```text
批准 bugfix 规范，启动执行
```

Suggested validation:

```bash
python <plugin-root>/scripts/validate_spec.py docs/specs/ --workflow bugfix
```

This is a structural integrity check only. It does not prove root-cause quality, minimal-fix scope, unchanged-behavior coverage, substitute reproduction strength, rollback safety, or monitoring sufficiency; review those semantics before implementation.

## State C: Controlled Implementation

Only enter this state after explicit approval.

When the approval phrase is received, update any generated status or approval-record fields in the spec artifacts before implementation.

Implementation rules:

- Read `docs/specs/bugfix.md`, `docs/specs/design.md`, and `docs/specs/tasks.md`.
- Select only the first unchecked task in `tasks.md`.
- Implement only that task and keep the change tied to the recorded root cause.
- Prefer proof order: reproduce the bug, prove the fix, prove unchanged behavior.
- Run verification and perform at most three self-healing loops.
- After passing the selected task's verification criteria, mark that task as `- [x]`. For a reproduction task, passing means the failure proof behaves as expected on unfixed code or the substitute evidence is recorded and strong enough to constrain the fix.
- Provide a commit message suggestion in this form:

```text
fix(scope): short description

Implements task: [task description]
Spec: docs/specs/tasks.md
```

If unchecked tasks remain, ask whether to continue only after the current task is complete.

If no unchecked tasks remain in `docs/specs/tasks.md`, read and follow `../spec-acceptance/SKILL.md` before reporting the whole workflow complete.
