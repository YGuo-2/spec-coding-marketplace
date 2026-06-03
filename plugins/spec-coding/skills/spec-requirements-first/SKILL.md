---
name: spec-requirements-first
description: Use for Spec Coding Feature / Requirements-First work when the user starts from product goals, user value, new capabilities, complex feature work, scaffolding, or cross-module refactors without a fixed technical design. Generates product.md, architecture.md, and tasks.md before implementation.
---

# Spec Coding Requirements-First

Use this branch for feature work driven by requirements rather than a fixed technical design.

If the entry router has not already printed the announcement, print:

```markdown
我读到了Spec-coding技能。
我会按照“Feature / Requirements-First”分支来完成。
```

## Hard Rules

- Do not write business source code until the human explicitly replies `批准规范，启动执行`.
- Generate or update spec artifacts in `docs/specs/`; they are the source of truth.
- Keep this branch for new capabilities, user workflows, scaffolding, complex refactors, and product-driven work.
- If the user switches to architecture-first or ADR-first work, reroute to `../spec-design-first/SKILL.md`.
- If the work is actually restoring existing expected behavior, reroute to `../spec-bugfix/SKILL.md`.

## State A: Requirements Clarification

Before writing specs, inspect available project context such as `constitution.md`, `CONVENTIONS.md`, existing `docs/specs/`, and stack manifests like `package.json`, `pyproject.toml`, `Cargo.toml`, or similar files.

Clarify only gaps that materially affect the spec:

- user goals, user stories, and success criteria
- functional and non-functional requirements
- boundaries, non-goals, compatibility, and migration constraints
- permissions, safety, security, and privacy expectations
- performance, concurrency, consistency, and operational constraints
- affected modules, APIs, schemas, or integrations

If clarification is needed, output a concise numbered question list. If the user says to proceed with assumptions, record unknowns as assumptions in the spec.

## State B: Spec Artifact Generation

Use the plugin templates from `../../assets/templates/`:

- `product_template.md`
- `architecture_template.md`
- `tasks_template.md`

Generate:

- `docs/specs/product.md`: user stories, acceptance criteria using GIVEN / WHEN / THEN, constraints, assumptions, and non-goals
- `docs/specs/architecture.md`: implementation blueprint, component boundaries, data model, API/interface shape, dependencies, error handling, security, and performance boundaries
- `docs/specs/tasks.md`: ordered atomic tasks using `- [ ]`, with verification criteria, estimate, and dependencies

After generation, ask the human to review the artifacts. The approval phrase for implementation is:

```text
批准规范，启动执行
```

Suggested validation:

```bash
python scripts/validate_spec.py docs/specs/ --workflow requirements-first
```

## State C: Controlled Implementation

Only enter this state after explicit approval.

Implementation rules:

- Read `docs/specs/product.md`, `docs/specs/architecture.md`, and `docs/specs/tasks.md`.
- Select only the first unchecked task in `tasks.md`.
- Implement only that task.
- Add or update tests that prove the approved acceptance criteria.
- Run verification and perform at most three self-healing loops.
- After passing verification, mark that task as `- [x]`.
- Provide a commit message suggestion in this form:

```text
feat(scope): short description

Implements task: [task description]
Spec: docs/specs/tasks.md
```

Ask whether to continue only after the current task is complete.
