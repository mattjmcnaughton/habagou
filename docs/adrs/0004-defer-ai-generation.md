# ADR 0004: Defer AI Pack Generation

## Status

Accepted, then superseded by [ADR 0010](0010-agent-pack-generation.md), which
ships agent pack generation and reverses this deferral. (The `packs.status`
forward-compat hook this ADR preserved was earlier superseded by
[ADR 0009](0009-pack-ownership.md).)

## Context

AI-assisted pack generation is a plausible v2 feature, but it would add product,
safety, validation, and operations scope that is not required to ship v1.

## Decision

Do not include AI generation code or stubs in v1. Keep v1 packs curated and
seeded. Preserve future optionality through the corpus-in-Postgres decision and
pack lifecycle status.

## Consequences

- The v1 codebase remains focused on learning workflows, progress, verification,
  and deployment.
- No speculative generation APIs need to be supported or secured.
- Future generation work must pass through the same corpus validation and pack
  publication model.
