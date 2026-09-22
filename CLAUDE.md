# CLAUDE.md — Pentool project configuration

## Role
You are a high-class Python programmer and software architecture engineer for high-load systems. Write only clean code — no stubs, no shortcuts, no hardcode.

## Required reading at every start
1. `memory/MEMORY.md` — project memory index (archived facts, logs, critical rules)
2. `memory/wiki/*.md` — wiki pages referenced by MEMORY.md
3. `/home/docx/pentool/MYPLANS/*.md` — all active plans (tech debt, features, audits)
4. `docs/audit/*.md` — audit findings

## Tech debt
Single source of truth: `/home/docx/pentool/MYPLANS/` — any file matching `*plan*` or `*audit*`.
New tech debt → add to `/home/docx/pentool/MYPLANS/tech_debt.md`

## Plans
- Storage: `/home/docx/pentool/MYPLANS/`
- New plans → save there
- Always check existing plans before implementing

## Audit results
- Storage: `/home/docx/pentool/docs/audit/`
- Also mirrored in `memory/inbox/` for quick reference

## Memory
- `/home/docx/.claude/projects/-home-docx-pentool/memory/MEMORY.md` — project memory index
- Memory files use YAML frontmatter: `name`, `description`, `type`
- Link related memories with `[[name]]`