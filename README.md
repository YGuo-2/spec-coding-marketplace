# Spec Coding Marketplace

This repository contains a Codex plugin marketplace for the `spec-coding` plugin.

## Import In Codex

Use the Codex "Add plugin marketplace" dialog:

- Source: `YGuo-2/spec-coding-marketplace`
- Git ref: `main`
- Sparse path: leave empty

Codex expects the marketplace manifest at `.agents/plugins/marketplace.json`.
The plugin source is at `plugins/spec-coding`.

## Plugin

`spec-coding` turns a heavy single skill into an intake-first router, three focused workflows, and final acceptance:

- `spec-intake`: clarify requirements, scope, risks, and key constraints before routing
- `spec-coding`: route to the right spec workflow
- `spec-requirements-first`: product-driven feature specs
- `spec-design-first`: architecture-driven specs
- `spec-bugfix`: evidence-driven bugfix specs
- `spec-acceptance`: task-based final acceptance with review and adversarial review agents

The plugin includes the intake and acceptance skills, shared templates, examples, and `scripts/validate_spec.py`.
