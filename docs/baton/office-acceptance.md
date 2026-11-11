# The office slice: how to run its served proof

This page is for whoever runs the acceptance proof for the office control
plane (currently z620). It is a list of commands and what to look for — not a
claim that any of it has been run.

There is one product. Babo owns the office (projects, one lead, a crew, what the
owner wants each agent to be) **and** the metal (pod lifecycle, network,
credentials, rescue) through its own manager core. The page and `babo office`
call `babo/office/api.py`; the core implements it in `babo/office/core.py`.
Nothing here talks to a second program over HTTP. If the Manager can't be reached,
the page says so and shows agents as `unknown` — that is the designed
behaviour, not a failure to hide.

## What you need before starting

- One Babo pod (the product under test) with its rendered Router. No Rails
  process, no HTTP manager seam — the NeoClaw model may appear only as an
  offline oracle in comparison runs, never deployed beside the product.
- One agent that exists in the Manager, with a handle — call it `<handle>`
  below.
- One project in Babo's town: `babo projects new "Office proof"` (or the Town
  page's Projects board).
- `NEOCLAW_MANAGER_URL` set for the Babo process, or
  `baton.office.manager_url` in its config. Leave it unset and Babo uses the
  mesh default `http://10.0.0.3:9200`; it never falls back to a local socket.

## 1. The runtime is read, not guessed

```
# the same facts as the page sees them, from the terminal
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

## 3b. Operator sessions (the inner half of the same boundary)

The Router admits only the host WG address, and the listener additionally trusts
exactly one peer address for session issuance. Check both, because a proof that
only checks the wall cannot tell a working gate from a missing one.

```
# inside the pod: the boot line must name the trusted source (addresses only)
journalctl -u babo-gateway -b | grep "WebUI session sources"
#   -> WebUI session sources: 10.0.0.2/32

# from the host WG address: a session is issued, and the pages work
curl -s http://<wg-addr>:8843/webui/bootstrap | jq '{token: (.token|length), api_token: (.api_token|length)}'
#   -> both non-zero. Then drive the one lifecycle action from the page.

# a token in a URL must not authenticate an API call
curl -s -o /dev/null -w '%{http_code}\n' "http://<wg-addr>:8843/api/office?token=$API_TOKEN"
#   -> 401

# revoke: every browser session dies, including the one that asked
#   inside the pod:  babo ui revoke-sessions
#   then the same browser's next call -> 401

# restart (or rescue): the old token is dead and the work is not
#   restart the gateway, reuse the old token -> 401
```

Pass conditions: the boot line names the address; a second source gets nothing
from the Router *and* nothing from the app; the revoked token fails on the very
next call; a restarted gateway rejects every pre-restart token. A startup that
refuses a bad `trusted_sources` value is also a pass — the failure should name
the value, not start and hope.

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
