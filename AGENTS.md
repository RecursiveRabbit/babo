# Working on babo

**Read [`docs/baton/HANDOVER.md`](docs/baton/HANDOVER.md) first**, then the principles in [`docs/baton/DESIGN.md`](docs/baton/DESIGN.md). Babo is a town of persistent AI residents on the owner's machine; every change is held to those principles (the owner decides, memory belongs to the resident, no ephemeral agents, parity between web and terminal, provider-agnostic, least access, keys never reach agents, a generic repository, stability first). Where a request conflicts with them, say so before writing code. The rest of this file is the code guidance inherited from the project Babo was forked from; it still applies.

The Python gateway owns agent execution, sessions, tools, memory, and security policy. WebUI and TUI share that runtime; keep execution and policy out of the clients.

## Task-specific guidance

| When working on | Read |
| --- | --- |
| Core boundaries, extensions, or internal types | [`.agent/design.md`](.agent/design.md) |
| Refactoring, fallbacks, or test selection | [`.agent/simplify.md`](.agent/simplify.md) |
| User-facing copy, feature naming, or localization | [`.agent/copywriting.md`](.agent/copywriting.md) |
| Path permissions, HTTP/MCP, or shell isolation | [`.agent/security.md`](.agent/security.md) |
| Dependency setup, WebUI transport, config, Windows, prompts, or persistence | [`.agent/gotchas.md`](.agent/gotchas.md) |
| Reusing verification evidence | [`.agent/workflow.md`](.agent/workflow.md) |
| WebUI/host compatibility | [`.agent/review-guide.md`](.agent/review-guide.md) |
| Contribution or publication | [`CONTRIBUTING.md`](CONTRIBUTING.md), [`docs/releasing.md`](docs/releasing.md) |

## Development constraints

- Analyze the required behavior, state ownership, and root cause before extending existing code. Refactor when the structure causes the problem; a smaller diff does not justify another fallback.
- Do not add defensive tests for hypothetical internal states or unsupported combinations. Each new test needs a reachable path and a meaningful contract to protect.
- Do not add tests merely to prove that nonexistent behavior, removed code, or obsolete symbols are absent. Negative assertions must exercise a concrete, reachable risk and protect an observable behavioral contract; prefer testing supported actions and their results.
- Do not run `ruff format`; mechanical formatting obscures git blame and creates unrelated diffs. This constraint takes precedence over the optional touched-file formatting in `CONTRIBUTING.md`.
- Do not manually wrap prose in Markdown files. Keep each paragraph on one source line; use line breaks only for Markdown structure.
