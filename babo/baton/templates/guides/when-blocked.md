---
title: When something is refused
when: when a tool call is refused or a command isn't allowed
errors: ["(?i)permission denied", "(?i)permission\\.rejected", "(?i)blocked", "(?i)not allowed", "(?i)is not available", "Commit paused by the Baton harness", "(?i)outside (the configured workspace|allowed directory|working dir)"]
---
Something you tried was refused. That is the town's rules working, not a fault.

- **Don't try the same thing again**, or a way round it. The answer won't change.
- **Read what it said.** "Commit paused" means: write a checkpoint, then commit again.
- **Work within what you may do**, or say plainly what you'd need and why. The Mayor can ask {{ owner }} for a session with more access; a resident can write to the Mayor or to `owner`.
- Your own folder is yours to change; other residents' folders and the town's own files are not.
- **The town's files are read with `read_note`**, not the shell: `read_note("rounds/")` lists the rounds, `read_note("rounds/night.md")` reads one (offices/ and commons/ the same way).
