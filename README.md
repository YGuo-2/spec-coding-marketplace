# Spec Coding Marketplace

This repository contains a Codex plugin marketplace for the `spec-coding` plugin.

## Import In Codex

Use the Codex "Add plugin marketplace" dialog:

- Source: `YGuo-2/spec-coding-marketplace`
- Git ref: `main`
- Sparse path: `plugins/codex`

The marketplace file is at `plugins/codex/marketplace.json`, and the plugin source is at `plugins/codex/plugins/spec-coding`.

## Plugin

`spec-coding` turns a heavy single skill into a lightweight router plus three focused workflows:

- `spec-coding`: route to the right spec workflow
- `spec-requirements-first`: product-driven feature specs
- `spec-design-first`: architecture-driven specs
- `spec-bugfix`: evidence-driven bugfix specs

The plugin includes shared templates, examples, and `scripts/validate_spec.py`.
