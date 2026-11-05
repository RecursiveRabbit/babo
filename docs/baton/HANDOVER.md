# Working on Babo: a handover for collaborators and their coding agents

This is the page to read before changing Babo, whether you are a person or a coding agent working for one. It says what Babo is for, the rules every change is held to, how changes land, where things stand, and the plan for the work now starting: bringing neoclaw's containers and network security into Babo.

Read [DESIGN.md](./DESIGN.md) next (its *Principles* are the test every change has to pass), then [README.md](./README.md) for what the owner sees, and [AGENTS.md](../../AGENTS.md) for the code conventions inherited from the project Babo was forked from.

## Who's who

- **The owner** ([@bgrimes-me](https://github.com/bgrimes-me)) decides what Babo is and approves what goes in. The owner doesn't use git: changes reach the owner's machine only through merged pull requests and the install steps (see *How changes land*).
- **Collaborators** open pull requests. [@RecursiveRabbit](https://github.com/RecursiveRabbit) is leading the containers and security work below, from neoclaw.
- **Coding agents** (Kimi, Claude Code, opencode) do much of the work, for one of the people above. An agent follows this page, DESIGN.md and AGENTS.md; where they disagree with what a person asks, it says so before going ahead.

## What Babo is, in one paragraph

A small town of AI agents on the owner's own machine. The agents are **residents**: persistent, each with a home folder, an office (a job), a memory it writes itself, and a name it may choose. There are no throwaway agents: work goes to a resident, by letter or by **errand**, and the resident gets better at it over time. The **Mayor** is the one the owner talks to. Babo is the harness around them: it decides *when* things happen (memory, upkeep, rounds, freezing idle sessions), the model decides *what* to say and do, and the owner decides anything that touches the machine.

## The rules every change is held to

These are DESIGN.md's principles, said as checks. A pull request that breaks one isn't merged, however good it is otherwise.

1. **The owner is in charge.** Nothing new runs on the machine, widens access or brings a resident to town without the owner's approval (or a standing choice the owner made, which is visible and recorded).
2. **Memory belongs to the resident.** The harness says when; the resident writes what, with its own tools (`checkpoint`, `correct_checkpoint`, `revise_self`). Nothing summarizes, prunes or rewrites a resident's memory behind its back. Transcripts may be kept and trimmed as records; they are never turned into memory without the resident.
3. **No ephemeral agents.** No temporary helpers, crews or subagents, in tools, profiles or engine. A session belongs to a persistent resident, whatever runs it.
4. **Parity.** What the web interface can do, the terminal can do (`babo …`), and the Mayor's chats and residents' sessions offer the same actions. A feature lands in both, or says why it can't.
5. **Provider-agnostic.** Any model the owner configures can run any resident: local (llama.cpp, Ollama, LM Studio) or hosted. Nothing in the code is written for one model or one vendor's agent runtime. Provider quirks live in the provider layer (`babo/providers/`), keyed by provider, never by the owner's model.
6. **Least access.** A resident starts in its own folder with its office's permissions. Anything wider is granted per resident or per session by the owner.
7. **Keys never reach agents.** Model and service credentials stay in Babo; agents reach models through Babo's gateway and town tools through `babo mcp`. A resident with a shell can't read a key.
8. **A generic repository.** No owner's machine, model, names, keys or residents in the code or docs. Residents name themselves; examples use made-up names. Nothing secret is committed, ever (keys are generated on the machine at install or at spawn).
9. **Stability first.** Every change upgrades a running install cleanly: the install steps are re-run, `babo tidy` removes what a version left behind, founding documents the owner hasn't edited are refreshed. Nothing asks the owner to edit config by hand, and a new capability that changes how things run arrives switched off until the owner turns it on.

## How changes land

- **One step, one pull request**, from a branch off `main`. The DESIGN.md plan numbers the steps; say which one a PR is (or propose a new row). Discuss anything large in an issue or a draft PR first.
- **CI must be green** on the PR's latest commit: Python (3.11 and 3.14), Baton tests, WebUI checks and browser tests, the terminal UI, Docker. Never skip, disable or loosen a test to get there. Merges are squash merges.
- **Run the fast checks before pushing**: `ruff check` (never `ruff format`: it rewrites unrelated lines), `basedpyright` on the files you touched, the tests for what you changed (`pytest tests/baton`, `cd webui && npx vitest run`, `npx tsc --noEmit`).
- **Tests** cover reachable behaviour through the code's own entry points; Baton's tests use a founded throwaway town (`tests/baton/conftest.py`) and a mock model server (`tests/baton/mock_llama.py`). External processes (opencode, podman, wg) sit behind an injectable backend with a stub for tests, as neoclaw does.
- **Docs move with the code**: the owner's guide (`docs/baton/README.md`), the install runbook (`docs/baton/RUNBOOK.md`) when installing changes, and the plan in DESIGN.md (move the row to *Done*, in a sentence or two).
- **Commits and PRs** say what changed and why, in plain words. No model names or identifiers in commits, PRs or code comments.
- **How the owner gets it**: after a merge, the owner's install agent runs the install steps from `docs/baton/RUNBOOK.md` (`install/run.sh 02-install-babo`, `04-found-town`, `05-units`, and `host-services` on the host). Anything a change needs on the machine must be one of those steps, idempotent and safe to re-run.
- `docs/releasing.md` describes the upstream project's PyPI releases; Babo doesn't publish packages and ships from `main` through the install steps.

## Words

User-facing text is plain and short (`.agent/copywriting.md`). Babo's vocabulary: **resident**, **office**, **the Mayor**, **the commons**, **the town square**, **letters**, **errands**, **rounds**, **upkeep**, **own time**, **the baton** and **checkpoints**, **move in** and **move away**, **freeze** and **resume**, **Review**. Not used any more: crew, subagent, spawn (for agents), the notice board, Dream.

## Where things are

| Path | What it is |
|---|---|
| `babo/baton/` | The town: founding, registry, offices and profiles, memory (checkpoints, baton, session review), upkeep, rounds, errands, the gateway and its queue, opencode residents, `babo mcp`, the trial and eval. Start here. |
| `babo/agent/` | The agent loop the Mayor runs in (inherited runtime, tools, sessions). |
| `babo/providers/` | Model providers and their quirks (thinking, turn order, tool calls). |
| `babo/webui/`, `webui/` | The web interface: Python routes and the React app. |
| `install/` | The install and upgrade steps the owner's install agent runs. |
| `docs/baton/` | The owner's guide, the runbook, the design and plan, and this page. |

## Where things stand

The plan and its order are in DESIGN.md (*Next, in this order*). In short: the owner is tuning the harness to a small local model with `babo trial` (step 34); the visual overhaul continues (29b); Dream and the old subagent engine are being removed (29d, 29e). Moonshot/Kimi as a provider is done (29c): thinking is sent back, consecutive assistant turns are merged, thinking models get room to think.

## The neoclaw merge (step 35)

**The aim:** Babo's architecture and setup (the town, residents, memory, the gateway, profiles, Review, the web interface and terminal, the install steps) with neoclaw's containers and network security underneath: each resident's session in its own container, reaching only what its profile allows, through WireGuard, with keys made per spawn.

The reference is [neoclaw-rails](https://github.com/RecursiveRabbit/neoclaw-rails) (its `docs/NEOCLAW-RAILS-SPEC.md`, `NETWORK-V2.md`, `WG-ROUTER.md`, `MCP-SERVICES.md`). Its philosophy already matches Babo's: agents are frozen, never killed; a fresh instance picks up the baton; the identity persists and the container is disposable; security is "a safe space, not a prison", with clean boundaries rather than suspicion.

### What each side brings

| neoclaw-rails | Babo today | In the merge |
|---|---|---|
| **Manager**: spawns and freezes agent pods (Podman), capacity (soft and hard caps), reconciles orphaned pods after a restart, generates keys | Babo's session lifecycle: `babo session new / freeze / resume`, upkeep freezing idle sessions, `babo/baton/opencode.py` starting each resident's opencode | Babo keeps the lifecycle and its API (web, terminal, errands, upkeep). The container becomes *where* a session runs: a container backend behind the existing session calls, with the Manager's spawn, freeze, capacity and reconcile logic. |
| **Agent container**: stock image, Relay, Claude Code | Residents run in opencode, against Babo's gateway, on whatever model the owner chose | The container runs the resident's **opencode** (provider-agnostic), not a vendor's agent runtime. Its model calls go to Babo's gateway over the tunnel; its town tools to `babo mcp`. No model keys in the container. |
| **Relay**: delivers messages, reports health and context, handles freeze and sunset | Babo's opencode plugin and the session API (send, stop, checkpoint now, freeze), the event log | The plugin and Babo's own session calls do this today over HTTP; in a container they go over the tunnel. A Relay-style health report (alive, context used) is welcome where Babo lacks it. |
| **WireGuard as authorization**: per-service peering, no peer means no route; a WG router for internet, per agent and revocable | Profiles decide what a resident may do; opencode permission rules enforce it; network access is all or nothing | **The profile stays the one source of truth**, and the network is derived from it: what a resident may reach (gateway, `babo mcp`, the owner's MCP servers, the internet) becomes its peerings. A profile change re-derives them. |
| **Ephemeral keys per spawn** (WG, SSH, git) | Model and service keys stay in Babo's config, never with agents | Keep both: per-spawn tunnel keys generated on the machine at spawn, never written to the repo or the town; service keys still never leave Babo. |
| **nftables firewall**, host `ip_forward=0`, bridge isolation, no agent-to-agent routes | Nothing at the network level | An install step on the host (like `host-services`), opt-in, explained to the owner, with `babo doctor` checks that the rules are in place. |
| **Identity per channel instance** (an identity plus a channel, Matrix accounts per instance) | One persistent resident with many sessions; sessions have tags; Matrix is one of Babo's chat channels | A container runs a **session of a resident**, never a new identity. Channels stay Babo's channels; per-channel instances map to sessions (or tags) of the same resident. |
| **Git is memory**: each agent's own repo, push or it didn't happen; the transcript pruned and pushed by the Relay | The town is one git repository; the resident writes checkpoints and its baton with its tools; transcripts are kept as records | Babo's memory cycle stays exactly as it is (principle 2). The resident's folder is mounted into the container; nothing in it is lost when a container dies, so "push or lose it" isn't needed. |
| **Cron** in the Hub | Rounds and upkeep | Rounds and upkeep. |
| **Admin UI** (Rails) | The web interface (Town page, Settings) and `babo` commands | Container state, capacity and network access show in the web interface and the terminal, with parity. |

### Rules for this work

- **Opt-in first.** Containers arrive behind a setting (for example `baton.containers`), off by default. Without it, Babo runs exactly as today. It becomes the default only when the owner says so.
- **Rootless at run time.** Babo itself never holds the owner's password and never runs as root. Anything that needs root (creating WireGuard interfaces, firewall rules) is a host install step the owner runs once, like `host-services`; at run time Babo uses rootless Podman and what that step prepared.
- **Babo may run inside a distrobox** (the runbook's default). Podman on the host is reached through `distrobox-host-exec`, as the install steps already do; design for both that and a plain host.
- **Python, in this repository.** Babo's tests, CI and installer are Python; the merged code is too. A self-contained image (a router, say) may be anything, as long as it builds from this repository with no committed keys.
- **No secrets in git, anywhere.** neoclaw-rails has private keys committed under `infra/wireguard/keys/`; none of them, and nothing like them, comes into Babo. Keys are generated on the machine: at install for long-lived ones, at spawn for the rest. (Those committed keys should also be rotated in neoclaw-rails.)
- **Least access, derived.** Nothing grants network or tool access except the resident's profile (and the owner's per-session changes). A container reaches the gateway and `babo mcp` and nothing else unless the profile says so.
- **Same outcome either way.** With containers on, `babo trial` and the Baton tests give the same results; sessions freeze and resume; checkpoints, baton and session review work unchanged; Review and errands work unchanged.

### Suggested order (each its own pull request)

1. **35a, a container backend:** a resident's opencode session runs in a rootless Podman container (stock image, the resident's folder mounted, nothing else), reaching Babo's gateway and `babo mcp` on the host. Behind the setting, with an injectable Podman backend and a stub for tests. Freeze, resume and *Stop* work.
2. **35b, lifecycle and capacity:** the Manager's ideas: capacity caps, freezing the idlest when full, reconciling containers after a restart, health and context reports.
3. **35c, the network:** WireGuard between containers and Babo, peerings derived from the profile, internet as its own revocable peering, the host install step, firewall rules, doctor checks.
4. **35d, per-spawn keys** for the tunnel (and SSH or git if needed), generated at spawn, removed at freeze.
5. **35e, tools over the tunnel:** the owner's MCP servers served to containers by service, filtered by profile (neoclaw's adapter and MCP gateway).
6. **35f, the owner's view:** container state, capacity and network access in the web interface and the terminal; docs; then, when the owner says so, containers on by default.

### Questions to settle early (Bryn and the owner)

- Matrix: is it one of Babo's channels (it exists as one), or more central, as in neoclaw?
- Which of neoclaw's services (the MUD, tickets, image generation, home devices) come along, and as what: MCP servers in Settings, with per-profile access?
- Per-channel instances: sessions of one resident with tags, or something more?
- Where the container image is built (at install, from this repository) and how it's updated on upgrade.

When something here turns out wrong once the code is in front of you, change this page in the same pull request and say why.
