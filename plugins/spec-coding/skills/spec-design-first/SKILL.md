---
name: spec-design-first
description: Use for Spec Coding Feature / Design-First work when the user explicitly starts from technical design, architecture constraints, ADRs, high-level design, low-level design, or a fixed implementation approach. Generates design.md, requirements.md, and tasks.md before implementation.
---

# Spec Coding Design-First

Use this branch when the technical design is the starting point and requirements must be derived from that design.

If the entry router has not already printed the announcement, print:

```markdown
我读到了Spec-coding技能。
我会按照“Feature / Design-First”分支来完成。
```

## Hard Rules

- Do not write business source code until the human explicitly replies `批准 design-first 规范，启动执行`.
- Generate or update spec artifacts in `docs/specs/`; they are the source of truth.
- `design.md` is the primary truth source for this branch.
- `requirements.md` must be derived from `design.md`; do not add unsupported product scope.
- If the request is a pure product goal with no technical design intent, reroute to `../spec-requirements-first/SKILL.md`. If the user explicitly asks for Design-First but provides incomplete design input, stay in State A and clarify the design starting point.

## Intake Precondition

Before choosing design granularity or entering State A, if the current conversation does not already include a `spec-intake` summary or a clear no-material-questions decision, read and follow `../spec-intake/SKILL.md`. If intake asks questions, stop and wait for the human answer before generating specs.

## Design Granularity

Choose one before generating artifacts:

- `High Level Design`: system boundaries, component topology, service split, deployment, dependencies, and key interfaces
- `Low Level Design`: module/class responsibilities, function signatures, state transitions, algorithms, detailed data structures, and local implementation flow

If both are needed, start with High Level Design and expand to Low Level Design only where the implementation needs it.

## State A: Design Clarification

Inspect project context before asking questions: existing specs, architecture docs, ADRs, manifests, interface drafts, migration notes, and related code paths.

Clarify only design-critical gaps:

- design objective and fixed constraints
- selected granularity
- affected system boundary, components, APIs, data flow, and state changes
- performance, security, compliance, compatibility, and migration constraints
- decisions already locked vs. decisions still open
- alternatives considered and rejection reasons when available

If clarification is needed, output a concise numbered question list. Unknowns may be recorded as assumptions or risks if the user accepts that.

## State B: Spec Artifact Generation

Use the plugin templates from `../../assets/templates/`:

- `design_first_design_template.md`
- `requirements_template.md`
- `design_first_tasks_template.md`

Generate:

- `docs/specs/design.md`: design granularity, system or module boundaries, relationships, key interfaces, data flow, constraints, rejected alternatives, and risks
- `docs/specs/requirements.md`: requirements and acceptance criteria derived from `design.md`, with clear markers for assumptions
- `docs/specs/tasks.md`: ordered atomic tasks that follow design dependencies, using `- [ ]`, with verification criteria, estimate, and dependencies

If the selected granularity is `Low Level Design`, `design.md` must also include module/class responsibilities, function signatures and contracts, algorithm flow, state transitions, and detailed data structures.

Before review, replace all template placeholders with concrete content. If a template section does not apply, state that explicitly with the reason instead of leaving placeholder text.

If `requirements.md` exposes a gap in `design.md`, update `design.md` first, then derive requirements and tasks again.

The approval phrase for implementation is:

```text
批准 design-first 规范，启动执行
```

Suggested validation:

```bash
python <plugin-root>/scripts/validate_spec.py docs/specs/ --workflow design-first
```

This is a structural integrity check only. Passing validation does not approve implementation; implementation still requires the exact approval phrase.

## State C: Controlled Implementation

Only enter this state after explicit approval.

When the approval phrase is received, update any generated status or approval-record fields in the spec artifacts before implementation.

Implementation rules:

- Read `docs/specs/design.md`, `docs/specs/requirements.md`, and `docs/specs/tasks.md`.
- Select only the first unchecked task in `tasks.md`.
- Implement only behavior inside the approved design boundary.
- Add or update tests that prove both design constraints and derived requirements.
- If implementation conflicts with `design.md` or any approved spec artifact must change, stop code work, return to State B, update the specs, rerun validation, and wait for `批准 design-first 规范，启动执行` again before continuing.
- Run verification and perform at most three self-healing loops.
- After passing verification, mark that task as `- [x]`.
- Provide a commit message suggestion in this form:

```text
feat(scope): short description

Implements task: [task description]
Spec: docs/specs/tasks.md
```

If unchecked tasks remain, ask whether to continue only after the current task is complete.

If no unchecked tasks remain in `docs/specs/tasks.md`, read and follow `../spec-acceptance/SKILL.md` before reporting the whole workflow complete.
