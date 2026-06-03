---
name: spec-coding
description: 当用户要求先写 spec、先做设计、design-first、tech design first、复杂功能开发、多文件或跨模块重构、脚手架搭建、回归排查、复杂 Bug 修复或高风险改动时使用。作为 Spec Coding 插件入口，只负责分流到 Requirements-First、Design-First 或 Bugfix，并在规范批准前禁止业务代码。
---

# Spec Coding Router

This is the lightweight entrypoint for the Spec Coding plugin. Keep this file small: classify the request, announce the route, then hand off to the branch skill.

## Required Announcement

Once this skill is read and selected, print:

```markdown
我读到了Spec-coding技能。
```

Then print the route decision:

```markdown
## Spec 路由决定

- 路径：Feature / Requirements-First | Feature / Design-First | Bugfix | 待澄清
- Design-First 粒度：n/a | High Level Design | Low Level Design
- 原因：[一句话说明判断依据]
- 下一步：[分流澄清 | 需求澄清 | Design-First 澄清 | Bug 分析澄清 | 规范生成]
```

Immediately after the route block, print one branch line:

```markdown
我会按照“Feature / Requirements-First”分支来完成。
```

or:

```markdown
我会按照“Feature / Design-First”分支来完成。
```

or:

```markdown
我会按照“Bugfix”分支来完成。
```

If the route is still unclear:

```markdown
我会先完成分流澄清，再进入对应分支。
```

## Hard Rules

- No business source code before a human explicitly approves the spec artifacts.
- Classify first, clarify second, then generate spec artifacts.
- Do not invent missing boundaries, compatibility rules, security constraints, or failure modes. Ask or record them as assumptions.
- Planning artifacts must be written to `docs/specs/`; chat-only plans are not the source of truth.
- Do not mix Feature and Bugfix. If a fix adds new user-visible capability or changes product scope, reroute to Feature.
- Do not mix Requirements-First and Design-First. Use Design-First only when fixed technical design, architecture, ADRs, or technical constraints are the primary starting point; ordinary stack, compatibility, or schema constraints can be recorded in Requirements-First specs.

## Routing Rules

Check in this order and stop at the first match:

1. `Bugfix`: the user wants to fix, investigate, reproduce, roll back, or recover existing expected behavior.
2. `Feature / Design-First`: the user asks for design-first, tech design first, high-level design, low-level design, architecture, ADR, or gives a technical plan or primary technical constraints that must drive requirements.
3. `Feature / Requirements-First`: the user asks for a new feature, capability, workflow, scaffold, complex refactor, or product outcome without a fixed technical design starting point.
4. `待澄清`: ask one question only: `这次主要是 A. 恢复既有预期行为 / 修复缺陷，B. 从业务需求新增或调整能力，还是 C. 从技术设计 / 架构约束推进？`

## Branch Handoff

- Requirements-First: read and follow `../spec-requirements-first/SKILL.md`.
- Design-First: read and follow `../spec-design-first/SKILL.md`.
- Bugfix: read and follow `../spec-bugfix/SKILL.md`.

After handoff, keep only the selected branch in scope until the user changes direction.

## High-Risk Warning

If the task involves authentication, authorization, payments, billing, database schema changes, data repair, distributed consistency, cache consistency, secrets, encryption, sensitive data, incident mitigation, rollback, or hotfix work, include:

```markdown
> [!WARNING]
> 高风险变更警告：当前任务涉及核心系统或高影响范围区域，必须进行人类深度审查，切勿草率合并。
```
