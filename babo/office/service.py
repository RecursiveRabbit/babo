"""The Manager's side of the hop: handlers, validation, and the peer check.

D-12 makes the UI the only caller: as ruled, the UI pod is 10.0.0.11 and the
Manager (this service) is 10.0.0.12. Neither number is a default here — the peer
list is a required argument, so the render owns the values and this module only
compares what it is given. That is enforced twice on purpose — the
Router admits only the UI pod's address to this port, and these handlers compare
the **socket peer** to that same exact address, header-blind. A wrong network
rule therefore still gets a 403 from the application rather than an open door.

The handlers are pure: they take a peer string and a parsed body, and return
``(status, payload)``. The listener, its binding and its policy belong to the
network lane; keeping the interpretation here means the rules can be tested
without a socket.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

from babo.office.api import (
    AGENT_ACTIONS,
    OPERATOR_ACTIONS,
    OPERATOR_SOURCE,
    TERMINAL,
    OfficeManager,
)


def _named(exc: BaseException, *names: str) -> bool:
    """Match a core exception by class name.

    The core's exception types live in ``babo/office/core.py``, which is another
    branch's file until the slice lands; importing them here would make this
    surface unimportable on its own head. The name match is deliberately narrow —
    anything that is not one of these keeps propagating, because a swallowed
    programming error is worse than a loud 500.
    """
    return type(exc).__name__ in names

# The handle a restart-ui action carries: the UI *pod's* name, because the audit
# row must name something an operator can look up, and the core's dispatch does a
# real container lookup. A synthetic "ui" would be neither an agent handle nor a
# pod name — an illegible row and an impossible lookup (soro's H-5).
UI_POD = "babo-ui"

# A body may carry these and nothing else; unknown keys are refused rather than
# ignored, because an ignored key is a client believing it changed something.
ACTION_FIELDS = frozenset({"handle", "action", "reason", "actor", "actor_source", "action_id"})

# The restart read is bounded on purpose. The route names one thing — the latest
# restart — and `limit` exists only because the store query underneath is
# parameterised. A bound the caller cannot raise keeps this from quietly becoming
# the collection endpoint the narrowing refused (F2, ruled 2026-11-12).
RESTART_READ_MAX = 20


class _ActionRowLike(Protocol):
    """The fields this surface reads off one stored action row.

    Declared here rather than imported from the store, and deliberately **without
    `boot_id`**: the Manager's boot is not the UI pod's boot, so a field that invites
    that correlation must not be part of the shape this surface is able to project
    (contract §3). A missing field is honest; a field that appears to work is not.
    """

    id: str
    handle: str
    verb: str
    state: str
    said: str
    actor: str
    actor_source: str
    reason: str
    created_at: str


@runtime_checkable
class _ActionStore(Protocol):
    """The one store read this surface makes: a parameterised, bounded query.

    Not on ``OfficeManager`` because it is a store query and not a manager verb: the
    interface stays the surface's contract, and this module keeps the read it needs
    without widening the door for anyone else. A core with no such store is reported
    as unreadable (503), never as an empty answer.
    """

    def actions(self, *, handle: str | None = ..., verbs: Iterable[str] | None = ...,
                limit: int = ...) -> Sequence[_ActionRowLike]:
        ...


def peer_allowed(peer: str, allowed: tuple[str, ...]) -> bool:
    """Exact address match, no prefixes and no header trust — the trusted_sources rule."""
    return any(entry == peer for entry in allowed)


# The render's two door variables, in the render's own names. This module keeps no
# address of its own: the pod's entrypoint resolves these, and a door whose address
# is chosen here would answer to a source nobody rendered.
RENDER_UI_SOURCES = "BABO_TRUSTED_SOURCES"          # the UI pod: the WebUI listener's only source
RENDER_OPERATOR_SOURCES = "BABO_OPERATOR_SOURCES"   # the host's WG address: the operator door only


class RenderIncompleteError(ValueError):
    """The render did not declare a door, and this door has no honest default.

    Raised at construction, not at the first refusal. A Manager that starts with
    the operator door silently closed answers every host call with `403 not an
    admitted door` — the same sentence a wrong principal gets. Two facts that read
    identically in the only place a caller can see them are one fact, and that is
    the one thing this door cannot afford.
    """


def _exact_source(entry: str, *, key: str) -> str:
    """One declared source, as the exact string ``peer_allowed`` compares.

    The pod's entrypoint already refuses anything but an exact IPv4 /32
    (``trusted_ok``); this is the door's second reader of the same rule, and it is
    deliberately narrow. A shorter prefix would not fail *open* here — the compare
    is exact — it would fail *silently*: admitting nobody while the configuration
    says a source was named. So a prefix, a hostname, a second spelling of one
    address (``010.0.0.2``) and an address no caller can arrive from are refused
    by name, rather than becoming a peer that matches nothing.
    """
    address = entry[:-3] if entry.endswith("/32") else entry
    if "/" in address:
        raise RenderIncompleteError(f"{key}: {entry!r} is a prefix, not an exact source")
    octets = address.split(".")
    if len(octets) != 4 or not all(
            o.isascii() and o.isdigit() and str(int(o)) == o and int(o) <= 255 for o in octets):
        raise RenderIncompleteError(f"{key}: {entry!r} is not an IPv4 address")
    first = int(octets[0])
    if first in (0, 127) or first >= 224:
        raise RenderIncompleteError(f"{key}: {entry!r} is not a source a caller arrives from")
    return address


def _sources(declared: str | None, *, key: str) -> tuple[str, ...]:
    """A rendered source list → the peer tuple. One or more, exact, no empty slots."""
    if declared is None or not declared.strip():
        raise RenderIncompleteError(f"{key} is not declared; the render owns this door's addresses")
    entries = [piece.strip() for piece in declared.split(",")]
    if not all(entries):
        raise RenderIncompleteError(f"{key}: {declared!r} has an empty entry; that is not an address")
    return tuple(_exact_source(entry, key=key) for entry in entries)


def doors_from_render(render: Mapping[str, str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The two peer lists, read from the render and from nowhere else.

    Both are required. `An unset door is a closed door` is the right rule for a
    trust list whose absence the pod reports at start; it is the wrong rule here,
    because this door's absence has no report — every host call would be a 403, and
    a 403 is also what a stranger gets.
    """
    return (_sources(render.get(RENDER_UI_SOURCES), key=RENDER_UI_SOURCES),
            _sources(render.get(RENDER_OPERATOR_SOURCES), key=RENDER_OPERATOR_SOURCES))


@dataclass
class ManagerService:
    core: OfficeManager
    ui_peers: tuple[str, ...]
    # The host-WG door's admitted addresses — the only callers `restart-ui`
    # answers. Both sets are required arguments and neither has a default: the
    # render owns the addresses, and a door built here with `()` is closed on
    # purpose. `from_render` is the other direction — it refuses a door the render
    # never declared rather than quietly handing back one of these.
    operator_peers: tuple[str, ...]

    @classmethod
    def from_render(cls, core: OfficeManager, *, render: Mapping[str, str]) -> ManagerService:
        """Build the service from the render's declared doors — the only constructor.

        Not a convenience over the dataclass: these two fields *are* the admission
        lists, and until this existed no process built them, so `restart-ui`'s
        host-WG admission was a code capability with no rendered entry. The UI
        listener's trust and the operator door's admission are two facts with two
        names; the render is where both are declared, and this is where they
        arrive as peers.

        The caller is the Manager process. That process does not exist yet, and the
        listener that would front it is unassigned and unruled: this chooses no
        address, binds nothing and claims no row.
        """
        ui_peers, operator_peers = doors_from_render(render)
        return cls(core=core, ui_peers=ui_peers, operator_peers=operator_peers)

    # -- reads -----------------------------------------------------------
    def health(self) -> tuple[int, dict[str, Any]]:
        available, detail = self.core.health()
        if available:
            return 200, {"available": True, "detail": detail, "core": getattr(self.core, "name", "core")}
        return 503, {"available": False, "detail": detail}

    def agents(self, peer: str) -> tuple[int, dict[str, Any]]:
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        return 200, {"agents": [a.overview() for a in self.core.agents()]}

    # -- actions ---------------------------------------------------------
    def act(self, peer: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        unknown = set(body) - ACTION_FIELDS
        if unknown:
            return 400, {"detail": f"unknown field(s): {', '.join(sorted(unknown))}"}
        handle = str(body.get("handle") or "").strip()
        action = str(body.get("action") or "").strip()
        reason = str(body.get("reason") or "").strip()
        actor = str(body.get("actor") or "").strip()
        actor_source = str(body.get("actor_source") or "").strip()
        replay = body.get("action_id")
        if not handle:
            return 400, {"detail": "missing handle"}
        if action in OPERATOR_ACTIONS:
            # The agent path does not carry the pod verb. This is a refusal by
            # name, not an unknown word: the verb exists, the door does not.
            return 403, {"detail": (f"{action} is the host operator's verb, admitted at the host-WG "
                                    "door; it is not carried on the agent path")}
        if action not in AGENT_ACTIONS:
            return 400, {"detail": f"unknown action {action!r}; it is one of {', '.join(AGENT_ACTIONS)}"}
        if not reason:
            return 400, {"detail": "missing reason"}
        if not actor or not actor_source:
            # R5: no actor, no effect. Refuse here rather than let the core do it,
            # because this surface is the one that must not accept an anonymous call.
            return 400, {"detail": "missing actor or actor_source; an action must name who is asking"}
        try:
            action_id = self.core.act(handle, action, reason, actor=actor, actor_source=actor_source,
                                      action_id=str(replay) if isinstance(replay, str) and replay else None)
        except Exception as exc:
            if not _named(exc, "CoreRefusalError", "RefusalError"):
                raise
            # A refusal is an answer, not a server fault: nothing was queued, so
            # this is 409 carrying the core's own sentence.
            return 409, {"detail": str(exc)}
        return 202, {"action_id": action_id}

    def restart_ui(self, peer: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """The cross-pod half of revocation: replace the UI pod.

        It is an action, not a side door: same actor/reason requirement, same
        idempotency key, same closed terminal states. The ledger records that it
        invalidates sessions by construction rather than by an API call reaching
        into another pod's memory.

        Two admissions, one principal (ruled 2026-11-11). The API-source check
        guards who may reach the port; the authority check guards whose act it is,
        and it is an allow-list of exactly one: the caller's provenance must be
        `OPERATOR_SOURCE`, and the agent is not the caller's to name — this handler
        fixes it at `UI_POD`. Everything else — a Lead, a crew agent, a service
        identity, a session, an unauthenticated local process, or a name offered
        without that provenance — is refused here **before effect**, with the class
        it caught named.

        The limit is the ruling's own: this Manager cannot re-derive the operator,
        so it checks the class token the caller carried. This verb's authority
        rests on the door that authenticated the operator, and the refusal catches a
        wrong class, not a forged one.

        The answer is 202 and it is **best-effort** (Bomu, H-6): replacing the pod
        kills the process that asked, so a client that died mid-request cannot be
        shown a verdict, and no client ever sees this action reach `succeeded` from
        inside that process. The action row is the witness, not the response.
        """
        if not (peer_allowed(peer, self.ui_peers) or peer_allowed(peer, self.operator_peers)):
            return 403, {"detail": f"{peer} is not an admitted door for {OPERATOR_ACTIONS[0]}"}
        unknown = set(body) - {"reason", "actor", "actor_source", "action_id"}
        if unknown:
            return 400, {"detail": f"unknown field(s): {', '.join(sorted(unknown))}"}
        reason = str(body.get("reason") or "").strip()
        actor = str(body.get("actor") or "").strip()
        actor_source = str(body.get("actor_source") or "").strip()
        replay = body.get("action_id")
        if not reason or not actor or not actor_source:
            return 400, {"detail": "missing reason, actor or actor_source"}
        if actor_source != OPERATOR_SOURCE:
            # A name without provenance is a string that satisfied a check, not an
            # identity (F-7): the door's word is the class, and the name rides with
            # it. The refusal names the class it caught.
            return 403, {"detail": (f"the actor's provenance is not the host operator (caught {actor_source!r}); "
                                    f"{OPERATOR_ACTIONS[0]} admits {OPERATOR_SOURCE!r} only")}
        try:
            action_id = self.core.act(UI_POD, "restart-ui", reason, actor=actor, actor_source=actor_source,
                                      action_id=str(replay) if isinstance(replay, str) and replay else None)
        except Exception as exc:
            if not _named(exc, "CoreRefusalError", "RefusalError"):
                raise
            return 409, {"detail": str(exc)}
        return 202, {
            "action_id": action_id,
            "status": "accepted",
            "best_effort": True,
            "note": ("accepted, best-effort: this action replaces the pod, so the caller that would "
                     "have polled will not see a terminal state — no client sees `succeeded`. "
                     "Read the action row for the verdict."),
        }

    def action(self, peer: str, action_id: str) -> tuple[int, dict[str, Any]]:
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        try:
            record = self.core.action(action_id)
        except Exception as exc:
            if not _named(exc, "UnknownActionError", "KeyError"):
                raise
            # An unknown id is 404, never an invented `failed`.
            return 404, {"detail": str(exc)}
        if record.state not in ("pending", "running", *TERMINAL):
            # A core bug must not reach the UI as a fifth word.
            return 503, {"detail": f"the core reported an unknown action state {record.state!r}"}
        return 200, {"state": record.state, "detail": record.said, "id": record.id,
                     "handle": record.handle, "action": record.action,
                     "actor": record.actor, "actor_source": record.actor_source,
                     "reason": record.reason, "created_at": record.created_at}

    # -- the restart door's read half ------------------------------------
    def restart_latest(self, peer: str, limit: int = 1) -> tuple[int, dict[str, Any]]:
        """The latest `restart-ui` row, for the pod that has to live with it.

        The write half (`restart_ui`) replaces the pod and kills the process that
        asked, so no caller ever sees its verdict from inside. This read is how the
        replacement finds out what happened to it: after it comes up, it asks the
        Manager for the newest row on its own door.

        The narrowing is the point (F2, ruled 2026-11-12). The route names one
        thing and this method asks for one thing: no caller-supplied handle and no
        caller-supplied verb reaches the query, so there is nothing here that a
        later party can widen into `?handle=…&verb=…` without editing the door.
        `limit` is the store's parameter, bounded by this module.

        Four answers, and none of them is a well-formed empty list:

        - ``403`` the caller is not the UI pod. The write admits two doors; this
          read admits one, because the operator's host does not need to read the
          pod's own history.
        - ``503`` the store cannot answer — and it says which of two different
          things went wrong. A core that exposes no action store at all gets one
          sentence; a store that is present and raises gets another, carrying its own
          words. The office looks broken rather than clean either way: "no restart"
          is a claim, and a read that did not happen cannot make it.
        - ``404`` the store is readable and holds no such row. Said out loud, so a
          consumer that is really a yes/no has to answer "there is no restart".
        - ``200`` ``{"actions": [...], "count": n}``, newest first, each row in the
          same wire names the single-row read uses — `detail`, not `said` — and
          never `boot_id`.
        """
        if not peer_allowed(peer, self.ui_peers):
            return 403, {"detail": f"{peer} is not the UI pod"}
        if limit < 1 or limit > RESTART_READ_MAX:
            # A limit of zero would return exactly the empty answer §4 forbids, and
            # an unbounded limit is the collection endpoint by another name.
            return 400, {"detail": (f"limit is between 1 and {RESTART_READ_MAX}; this route names "
                                     f"the latest {OPERATOR_ACTIONS[0]}, not a listing")}
        store = getattr(self.core, "store", None)
        if not isinstance(store, _ActionStore):
            # Absence, said as absence, and only that. `@runtime_checkable` checks
            # that the attribute is *there*; it is not a signature check, and wrong
            # shapes walk through it. So this is the cheap pre-check and the call
            # below is the real one — which is why the two failures get two
            # sentences rather than one sentence pretending to be a shape check.
            return 503, {"detail": ("the core exposes no action store; the office cannot say whether "
                                     "a restart happened")}
        try:
            # Parameterised here, inside, and nowhere else: the pod is the row's
            # handle and the door is the row's verb, both fixed by this module.
            rows = list(store.actions(handle=UI_POD, verbs=OPERATOR_ACTIONS, limit=limit))
        except Exception as exc:
            # A store that is present and cannot answer is a different fact from a
            # core that never had one, and the two must not share a sentence.
            return 503, {"detail": f"the core's store could not be read: {exc}"}
        if not rows:
            return 404, {"detail": f"no {OPERATOR_ACTIONS[0]} row is recorded here; there is no restart to read"}
        for row in rows:
            if row.state not in ("pending", "running", *TERMINAL):
                # Same guard as the single-row read: a fifth word is a core bug and
                # must not reach a page as a status nobody can render.
                return 503, {"detail": f"the core reported an unknown action state {row.state!r}"}
        return 200, {"actions": [self._row(row) for row in rows], "count": len(rows)}

    @staticmethod
    def _row(row: _ActionRowLike) -> dict[str, Any]:
        """One stored row in the wire names ``action()`` already uses.

        `detail` is the wire name for the row's `said` column and `action` for its
        `verb`; those two spellings were ruled (contract §2) because the single-row
        read is already on the wire. Two endpoints teaching two clients two names
        is the failure, so this projects field for field the same shape — if anyone
        ever moves it, they move both reads together.

        `created_at` is here because the endpoint's purpose needs it: a pod that came
        up inside a restart cannot otherwise tell *the restart that made me* from *a
        restart aimed at me*. It also makes "newest first" falsifiable by the caller
        instead of a claim the door makes about itself.

        The stamp is rendered in the house's zone (`core.house_time`) exactly as the
        single-row read renders it: the store keeps one offset because it compares
        these strings, and a caller is owed the zone the house lives in. Imported
        here, not at module scope, so this surface stays importable without the core.
        """
        from babo.office.core import house_time

        return {"state": row.state, "detail": row.said, "id": row.id,
                "handle": row.handle, "action": row.verb,
                "actor": row.actor, "actor_source": row.actor_source,
                "reason": row.reason, "created_at": house_time(row.created_at)}
