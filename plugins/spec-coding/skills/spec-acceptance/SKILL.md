---
name: spec-acceptance
description: Use after Spec Coding implementation tasks are complete to run final acceptance against docs/specs/tasks.md. Trigger when a Requirements-First, Design-First, or Bugfix branch has no unchecked tasks and needs final multi-agent acceptance, adversarial review, completion checks, over-fallback checks, strict spec-adherence checks, and Bugfix rerouting for confirmed issues.
---

# Spec Coding Acceptance

Use this as the final step after a Spec Coding branch finishes every task in `docs/specs/tasks.md`. Its job is to verify the whole workflow outcome; it does not create `docs/specs/acceptance.md`.

## Required Announcement

If the branch skill has not already printed the announcement, print:

```markdown
我读到了Spec-acceptance技能。
```

## Hard Rules

- Enter only when `docs/specs/tasks.md` has no unchecked `- [ ]` tasks.
- Treat skipped `- [~]` tasks as valid only when the task text or completion log records explicit human approval to skip.
- Do not report the whole Spec Coding workflow complete before this acceptance flow passes.
- Do not spawn sub-agents unless the current conversation explicitly authorizes sub-agent orchestration. If authorization is missing, ask for it and stop.
- Do not downgrade this flow to a single local review or pretend local review is equivalent to multi-agent acceptance.
- Do not edit business source code inside this skill. Confirmed issues must route into `../spec-bugfix/SKILL.md`.
- Final success output must summarize the completed plugin workflow, not dump raw agent review transcripts.

## State A: Acceptance Preconditions

Read the approved spec artifacts, `docs/specs/tasks.md`, relevant diffs, and verification results.

Detect the workflow from the spec files:

- Requirements-First: `product.md`, `architecture.md`, and `tasks.md`
- Design-First: `design.md`, `requirements.md`, and `tasks.md`
- Bugfix: `bugfix.md`, `design.md`, and `tasks.md`

If any task is still unchecked, return to the selected branch's Controlled Implementation state. If required verification evidence is missing, treat that as an acceptance issue.

If sub-agent authorization is missing, ask:

```markdown
结尾验收需要按 `tasks.md` 编排子 agent 进行审查和对抗审查。请明确授权我启动子 agent 后，我再继续验收流程。
```

## State B: Build Review Units

Parse `tasks.md` in order and build review units.

- A task must stand alone if it is high risk, spans multiple major modules, has complex verification, changes public contracts, or appears in the risk table.
- High-risk signals include auth, authorization, payment, billing, database, migration, data repair, concurrency, distributed consistency, cache consistency, secrets, encryption, sensitive data, incident, rollback, hotfix, privacy, performance, or security.
- Low-risk tasks may be grouped only with contiguous tasks under the same phase heading.
- A grouped unit may contain at most three tasks.
- If `tasks.md` has no phase headings, group low-risk tasks by original order, at most three tasks per unit.
- Let the final review-unit count be `M`. If every task stands alone, `M=N` and the flow uses `2N` sub-agents. If low-risk tasks are grouped, the flow uses `2M` sub-agents.

## State C: First-Wave Review

Spawn `M` review agents in parallel. Each agent owns exactly one review unit and must not edit files.

Each first-wave prompt must include:

- The workflow type and relevant approved spec files
- The assigned task IDs and task text from `tasks.md`
- Relevant changed files, diffs, tests, logs, and verification results
- A request to review completion, strict spec adherence, overbroad fallback, missing verification, regression risk, and unapproved behavior

Each first-wave agent must return:

```markdown
## Review Unit
- Unit: [task IDs]
- Status: PASS | ACTIONABLE_ISSUES
- Completion: [complete / incomplete with evidence]
- Spec Adherence: [strict / deviation with evidence]
- Over-Fallback: [none / present with evidence]
- Verification: [sufficient / missing with evidence]
- Issues: [numbered actionable findings or n/a]
```

Wait for all first-wave agents before starting the second wave.

## State D: Adversarial Review

Spawn `M` adversarial agents in parallel. Each adversarial agent reviews the matching first-wave report, the same review unit, and the same spec evidence.

Each adversarial agent must:

- Challenge whether the first-wave review missed incomplete work, spec drift, over-fallback, weak tests, hidden regressions, or unsupported assumptions
- Ask bold questions and prefer concrete evidence over agreement
- Return `PASS` only when no actionable challenge remains

Send each adversarial result back to the matching first-wave agent for a revised conclusion. Reuse the first-wave agent when possible; resume it first if needed.

## State E: Loop Until Clear

Repeat the adversarial review and first-wave revision cycle while new actionable issues appear.

Stop when:

- Every first-wave unit is `PASS`
- Every adversarial unit is `PASS`
- No new spec deviation, incomplete task, over-fallback, missing verification, or regression risk remains

If disagreement persists, treat any evidence-backed actionable concern as an issue and enter the Bugfix path.

## State F: Final Branch

If no issues remain, output the final workflow completion result:

```markdown
## Spec Coding 完成结果

- 流程：[Requirements-First / Design-First / Bugfix]
- 规范：[已批准并执行的 spec 文件]
- Tasks：[全部完成 / 人类批准跳过项]
- 验证：[已运行的关键验证]
- 结尾验收：通过
- 最终结论：整个 Spec Coding 流程已完成。
```

If issues remain:

- Summarize only actionable issues with evidence and affected task IDs.
- Read and follow `../spec-bugfix/SKILL.md`, using the acceptance findings as bug evidence.
- After the Bugfix branch completes its tasks, run this `spec-acceptance` flow again.
