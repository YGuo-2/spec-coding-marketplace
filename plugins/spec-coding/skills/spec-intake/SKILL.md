---
name: spec-intake
description: Use at the start of Spec Coding workflows to clarify user intent before routing to Requirements-First, Design-First, or Bugfix. Trigger when a spec-coding task needs requirement clarification, scope confirmation, risk or constraint discovery, or timely follow-up questions; inspect available project context first and ask only questions that materially affect the spec.
---

# Spec Coding Intake

Use this as the first step in the Spec Coding plugin. Its job is to clarify intent and unblock routing; it does not generate source code or create a standalone `docs/specs/intake.md`.

## Required Announcement

If the entry router has not already printed the announcement, print:

```markdown
我读到了Spec-intake技能。
```

## Hard Rules

- Clarify first, classify second, then generate spec artifacts.
- Inspect discoverable project context before asking questions.
- Ask only questions that materially affect the spec, route, scope, risk, or acceptance criteria.
- Ask at most 1-3 concise questions at a time. If more gaps exist, ask the blockers first.
- Do not ask for facts that can be found in the repo, docs, configs, schemas, tests, or issue text.
- Do not create `docs/specs/intake.md`; carry intake conclusions into the selected branch's spec artifacts.
- If the user says to proceed with assumptions, record unknowns as assumptions or risks in the downstream spec.
- Do not write business source code before the selected branch's approval phrase is received.

## State A: Context Scan

Before asking, inspect likely sources of truth when available:

- Existing specs under `docs/specs/`
- Project rules such as `constitution.md`, `CONVENTIONS.md`, `README.md`, ADRs, architecture docs, and migration notes
- Stack manifests such as `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, Gradle/Maven files, or similar
- Relevant code paths, tests, logs, screenshots, issue text, alerts, or recent changes named by the user

Summarize what is already clear before deciding whether to ask.

## State B: Gap Check

Check for gaps that would change the selected spec branch or its content:

- Route identity: whether this is restoring existing behavior, adding or changing capability, or starting from a fixed technical design
- Success criteria: user-visible goal, acceptance criteria, non-goals, and definition of done
- Scope boundaries: affected modules, APIs, schemas, integrations, compatibility, migration, and rollback expectations
- Design-first inputs: chosen design granularity, fixed constraints, locked decisions, key interfaces, data flow, and alternatives
- Bugfix evidence: current incorrect behavior, expected behavior, reproduction steps, environment, affected inputs, and behavior that must remain unchanged
- Risk constraints: authentication, authorization, payments, data repair, database schema changes, distributed consistency, cache consistency, secrets, encryption, sensitive data, incidents, hotfixes, performance, or privacy

## State C: Ask Or Summarize

If material gaps remain, stop and ask:

```markdown
## 需求澄清问题

1. [只问会影响规范或路由的问题]
2. [可选]
3. [可选]
```

If no material gaps remain, continue with a compact intake summary:

```markdown
## 需求澄清摘要

- 已确认：[目标 / 范围 / 约束 / 证据中的关键结论]
- 假设：[需要进入后续规范的假设；无则写 n/a]
- 风险：[需要后续规范重点处理的风险；无则写 n/a]
- 下一步：返回 `spec-coding` 路由。
```
