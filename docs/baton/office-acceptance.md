# The office slice: how to run its served proof

This page is for whoever runs the acceptance proof for the office control
plane (currently z620). It is a list of commands and what to look for — not a
claim that any of it has been run.

The slice has two halves and they meet at one interface: Babo owns the office
(projects, one lead, a crew, and what the owner wants each agent to be), and
the NeoClaw Manager owns the metal (pods, network, credentials, Router). Babo
never touches podman; it asks the Manager. If the Manager can't be reached,
the page says so and shows agents as `unknown` — that is the designed
behaviour, not a failure to hide.

## What you need before starting

- Babo running where the Manager can reach it and it can reach the Manager's
  `http://<manager>:9200` (WireGuard), per the packaging step.
- One agent that exists in the Manager, with a handle — call it `<handle>`
  below.
- One project in Babo's town: `babo projects new "Office proof"` (or the Town
  page's Projects board).
- `NEOCLAW_MANAGER_URL` set for the Babo process, or
  `baton.office.manager_url` in its config. Leave it unset and Babo uses the
  mesh default `http://10.0.0.3:9200`; it never falls back to a local socket.

## 1. The Manager is read, not guessed

```
# from the host, as the Manager answers it
curl -s "$NEOCLAW_MANAGER_URL/api/v1/office/state" | jq '.agents[] | {handle, state}'

# the same facts as Babo sees them
babo office
```

Pass: every agent listed by the Manager appears in `babo office` with the same
`state`, and each is shown under its project with `(lead)` or `(crew)` from
the project's `CREW.md`. Capture both outputs side by side.

Then stop the Manager (or point Babo at a dead address) and run `babo office`
again: pass is a plain "The Manager can't be read: …" line and every agent
`unknown` — never a cached `running`.

## 2. One real lifecycle action from the UI

1. Set the project's lead and crew (either surface; they are the same code):
   ```
   babo office crew "office-proof" --lead <handle> --crew <other-handle>
   babo office record <handle> --resident <resident> --project "office-proof"
   ```
2. Open the web interface, go to **Office**, find `<handle>`.
   - If it is `frozen`, **Wake** it. If it is `running`, **Freeze** it.
3. Watch the row: the state goes `pending`, then the Manager's own verdict is
   shown with its detail text; the row's state changes only after the Manager
   says `succeeded`.
4. Cross-check against the Manager's own record:
   ```
   curl -s "$NEOCLAW_MANAGER_URL/api/v1/office/actions/<action_id>" | jq .
   ```
   (the action id is in the page's answer / `babo office` run, and in the
   Manager's audit rows). Pass: the page's verdict and the Manager's `state`
   and `detail` are the same words.

**What freeze actually is (corrected by Soro after the first draft of this
page):** the agent is asked to stand down and push its work; the pod is then
released and its credentials are revoked. Wake spawns a **fresh pod** that
resumes the rescued workspace with new keys. The work is preserved; the
process does not continue. If the page ever says "paused", it is wrong — a true
pause would be a different primitive (podman pause/unpause) and a different
risk surface. `destroy` is separate and is not on the page.

## 3. The network wall (soro's half, cited here)

```
# from the host's WireGuard address: the UI answers
curl -s -o /dev/null -w '%{http_code}\n' http://<babo-wg>:18790/office

# from anywhere else: refused at the Router, before Babo sees a packet
curl -s -m 3 -o /dev/null -w '%{http_code}\n' http://<babo-public-or-lan>:18790/office
```

Pass: 200 from the WG source, refused/timeout from the other. The Office page
also prints the address it is bound to; that line is corroboration only — the
Router's source rule is the wall, and no token or password is an alternative
path. Be precise about what that proves: the rule identifies the **host**, not
the person. "Authenticated by WireGuard" means "you are on the host"; the page
cannot tell two people on that host apart, and nobody should read more into it.

## 4. What to capture for the record

- The two `babo office` outputs from step 1 (Manager up and Manager
  unreachable).
- The action id, the page's verdict text, and the Manager's action row.
- The two `curl` codes from step 3, and the address line from the page.
- The exact commit under test (`git -C <babo checkout> rev-parse HEAD`) and the
  Manager image/commit it talked to.

Anything that doesn't pass goes into the commission's request thread as a
finding with the command that showed it — not a narrative. If the Manager
refuses (`refused`) or times out, that is a real, reportable result: the page
is supposed to show it.
