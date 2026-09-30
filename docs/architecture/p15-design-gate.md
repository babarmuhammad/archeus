# P15 design gate: presence, pairing, remote access and client runtime

Status: **FROZEN (P15), before any P15 code.** Written 2026-09-28 on the P14 baseline (`197554b`,
CI run 36407448948 green). The as-built record and its deviations are §22. Items are marked as in
the earlier gates:

- **[spec]** already specified by the V1 architecture (plan, domain model, state machines, ADRs);
- **[clar]** a clarification of an existing contract the documents leave open, or that the code
  has already settled differently;
- **[new]** a new contract decision.

Every [new] item and every change to a frozen P1–P14 contract is a numbered decision (§21).

Sources read, in precedence order: the plan (§22, §26, §27, §28, §31.1 **P14, P15, P16**, §33 Q2/Q3),
ADR-0009 (SSE, ids-only, re-query), ADR-0010 (PWA over a user-operated tunnel, PROPOSED), ADR-0004
(mission is continuity; sessions are infrastructure), ADR-0023, domain-model **§3**, state-machines
**§12** (device), api-and-realtime **§1–§7**, the P3.5b gate (§3 D2/D5/D7, §4, §6, A4, A9, A16,
A40), the P9 gate (**§8.7 D16** step-up, §17 item 5 "step-up locality"), the P12 gate (session
identity), the P14 gate (events are facts, tables are the authority); testing-strategy §2 rows
**S11, S14, G6**; ui-architecture §5.1 (P16 graph — read, not changed). The code:
`api/{auth,server,routes,schemas,sse}.py`, `core/domain/{entities,states,values,ids,events}.py`,
`core/application/{commands,queries,authorization,world,sessions}.py`, `infra/eventlog/outbox.py`,
`core/runtime.py`, `cli/main.py`, `clients/app/src/api/{stream,transport}.ts`, and the judge
(`client.py`, `http.py`, `support.py`, `test_s11_remote_control.py`, `test_s14_digest.py`,
`test_g06_security.py`). Where a document and the code disagree, the code says what exists.

---

## 1. Purpose

P15 makes the same Archeus usable from the local machine, a second browser, and a phone reached
through a tunnel — at the same time, across disconnects and Core restarts — without any of those
clients becoming a source of truth or a second path around P9–P14.

The rule it enforces: **P15 controls access to the service and delivers notice of change. It never
decides whether an action is permitted (P9), routes (P10), executes or controls an execution
(P11), owns a session (P12), verifies (P13) or reacts to events (P14).** Every command a remote
client sends is an existing route running an existing application command, unchanged.

## 2. Architecture boundary

```
   client (CLI · SPA tab · paired PWA)          P15 = the left edge of this picture
        │  Authorization: Bearer dev_…
        ▼
   HTTP pipeline (Host/Origin → token → route scope)          ← P3.5b, extended by P15
        │                                   │
        │ commands (idempotent, versioned)  │ GET + X-Archeus-Seq      SSE ids-only frames
        ▼                                   ▼                              ▲
   application layer (P7–P14 commands and guards; P9 decides)   outbox (P2/P14 events)
        │
        ▼
   SQLite tables  ←── the authority; events are facts written in the same transaction
```

| Concern | Owner | P15's part |
|---|---|---|
| Is this a live credential? Does it hold the route's coarse scope? | P3.5b auth layer | extended to paired clients and remote hosts |
| May this principal fire this trigger on this subject? | **P9** | none (reads nothing, decides nothing) |
| Step-up for deploy/destructive | **P9** guard `step_up_valid` | supplies the proof check for a *paired* client (§6.6) — the guard stays P9's |
| Pause / resume / stop / e-stop | P7 mission lifecycle, **P11** | exposes the existing routes to paired clients; adds the optional `expected_version` P7's commands already take (§14) |
| Resume / hand off a session | **P12** | none; a connection is never a session (§10) |
| Verification state and decisions | **P13** | none |
| Events | **P14** (durable, same-transaction) | delivers identities of committed events to connected clients; never a second bus |
| Model × harness selection | **P10** (with P7/P8/P13 inputs) | none; no P15 field names a model, harness or account (§15) |
| Client registrations, pairing, presence, remote host allowlist, resync anchor | — | **P15** |

## 3. Identity model [spec + clar + new]

Twelve distinct things. None is inferred from another; none is identified by IP address or
user-agent.

| Entity | What it is | Where it lives | Identified by |
|---|---|---|---|
| **User** | the person who owns this Archeus home. V1 is single-owner (plan §2): at most one row | `users` | `usr_…` |
| **Principal** | the acting identity a credential authenticates as, and the `actor` of every event it causes. Kinds: `user_device`, `brain`, `execution`, `automation`, `node`, `system` | `principals` | `prn_…` |
| **Client** | one credentialed installation of a client program: the CLI/TUI's local token, one browser profile's SPA (launch code), one paired PWA/browser. Exactly one `user_device` principal per client | `devices` (entity `Device`, see D1) | `dvc_…` |
| **Device** (hardware) | the physical machine or phone a client runs on | **not an entity** (D2). A client carries the user's `host_label` and the client-declared `platform` — display and grouping only, never trusted | — |
| **Credential** | a bearer token for one principal; only its sha256 is stored | `tokens` | `dev_…` prefix (token prefixes never reuse id prefixes) |
| **Connection** | one live event-stream registration of one client. Ephemeral: it dies with its socket or with Core | Core memory; durable trace in `device.stream_opened` / `device.stream_closed` events | `connection_id` (ULID, in the event payload) |
| **Session** | a P12 working session with a harness (a Claude Code conversation, a Codex run) | `sessions` (P12) | `ses_…` |
| **Mission / Task / Execution** | P7 / P8 / P11 work units | their tables | `msn_` / `tsk_` / `exe_` |
| **Harness / Model / Account / Resource** | P10's routing inputs | P10 | P10 ids |

Relations: a User owns every client (single owner); a client has exactly one principal and one or
more credentials over its life (V1 issues one); a client has 0..n connections at a time (at most 2,
P3.5b's stream pool) and many over time; a connection belongs to exactly one client. **Nothing
relates a connection or a client to a session, mission, task or execution** — a client *views* and
*commands* those through routes; it never owns them.

What each word must never mean in P15 code, docs and API: *client* ≠ connection (a phone that
reconnects is the same client, a new connection); *client* ≠ session (a P12 session is a harness
conversation; a client may watch many); *device* ≠ client (one laptop can hold the CLI and two
browser profiles — three clients); *presence* ≠ activity (§5).

## 4. Client model [clar + new]

| Field | Meaning | Set by | Notes |
|---|---|---|---|
| `id` | the client id (`dvc_…`) | Core at registration | stable for the client's life; never reused |
| `principal_id` | the client's acting identity | Core | 1:1 |
| `name` | a label ("Pixel", "browser (web)") | pairing start, or the redeeming client | display only |
| `platform` | `desktop` `web` `ios` `android` `tui` | the client, declared | display only, **not** a security input (D5) |
| `client_type` **new** | `cli` (local token), `spa` (the SPA, in a tab or installed as a PWA) | Core, from how the client registered | a `native` type is added only if a native app ever exists |
| `origin` **new** | `local` (local token, launch code: proved presence on this machine) or `paired` (redeemed a pairing code, may be anywhere) | Core, from the registration path | the security-relevant bit (D5) |
| `host_label` **new** | "which physical device", as the user said at pairing | the user | groups clients for display and bulk revoke by a person; unverified |
| `state` | `ACTIVE` / `REVOKED` (machine `device`, state-machines §12) | commands | unchanged |
| `pin_hash` **new** | pbkdf2-sha256 of the step-up PIN, for a paired client that set one | Core | **never serialized** by any query or response |
| scopes | on the principal and the credential | Core at registration | `observe` `control` `approve` `admin` |
| credential `expires_at` | paired credentials expire **180 days** after pairing (D8); local/launch credentials as before (none) | Core | listed, so a client can warn before it lapses |

**Registration paths** (all one command, `commands.register_device`, one transaction: principal +
client + credential + events):

| Path | `client_type` | `origin` | scopes | Who vouches |
|---|---|---|---|---|
| local token (first Core start) | `cli` | `local` | all four | Core's system principal |
| launch code (P3.5b) | `spa` | `local` | `observe` | the minting local client |
| pairing (P15) | `spa` | `paired` | fixed at pairing start (default `observe control approve`) | the client that started the pairing |

**Capabilities** are *derived*, never declared by the client: `{scopes, step_up}` where `step_up`
is `local` (satisfied by being local, P9 D16), `pin` (a paired client with a PIN) or `none` (a
paired client without one — it can never satisfy a step-up; P9 refuses fail-closed). P16 reads
them to decide what to offer; Core enforces them regardless.

**Revocation** (P3.5b's route, unchanged): client ACTIVE → REVOKED, every credential of its principal
revoked, its live connections closed before the response returns. **Lost device**: revoke each of
its clients (a device list grouped by `host_label` is P16's surface; the route is per client).
**Re-pairing** is a new pairing: a new client, never a resurrected one. **Last-seen** is presence
(§5), not a stored field.

## 5. Presence model [new]

Presence is **what Core observes about a client's connectivity, now**, and nothing else.

| State | Definition | Claims | Does not claim |
|---|---|---|---|
| `connected` | the client has ≥ 1 open event stream on this Core process | frames are reaching it (heartbeat every 15 s) | that anyone is looking at the screen |
| `recent` | no open stream, but an authenticated request within the last 60 s | it reached Core a moment ago | that it will again |
| `absent` | neither, since this Core process started | nothing | that the client is off, lost, or gone |
| `revoked` | the client is REVOKED | it can no longer authenticate | — |

Definitions of the words the brief asks for: **online** = `connected` or `recent`; **offline** =
`absent` *as observed by Core* (the client may be fine and simply not connected); **connected** =
the state above; **available** and **active** (a person available or at work) are **not modelled**:
Archeus has no signal that supports them, so no field, event or response claims them (D6).

Mechanics:
- **Heartbeat**: the SSE comment `: hb` every 15 s (P3.5b). A write to a half-open socket fails and
  closes the connection; presence follows.
- **Multiple connections**: counted per client; `connected` while any is open.
- **Multiple clients**: independent; presence is per client, never per user or per device.
- **Server restart**: presence is in-memory, so every client is `absent` until it reconnects —
  correct, because every connection died with the old process. `last_seen_at` is "since this Core
  started", and `null` before then.
- **Durable trace**: when a client goes from 0 → 1 open connections Core writes
  `device.stream_opened` (payload `connection_id`), and on 1 → 0 `device.stream_closed` (payload
  `connection_id`, `reason`: `client_gone` `revoked` `core_stopping` `cursor_expired`). Both are
  `system`-visibility types already registered (P3.5b deferred them to P15). Only transitions are
  written, so a client holding two streams writes two events, not four.
- **Presence is never an input.** No application command, guard, worker or query in `archeus/core`
  reads it (a boundary test pins that no `core` module imports the presence tracker). A client
  going `absent` cancels, pauses, fails, expires or verifies nothing (§10, P07/P08/P30).

## 6. Pairing model [spec + new]

### 6.1 Flow

1. **Initiation — the user's confirmation.** On the machine running Core, an `admin` client that is
   *local* (loopback peer **and** loopback `Host`, §8.3) calls `POST /v1/devices/pair/start
   {name?, host_label?, scopes?}` — from `archeus pair` today, from the desktop SPA in P16. The
   scopes, name and host label are fixed here; the redeemer cannot widen them (D9).
2. **Bootstrap credential.** Core answers `{code, expires_in: 120, scopes, url}`. The code is 128
   random bits (`secrets.token_urlsafe(16)`), kept only in Core memory as `sha256(code)` → (expiry,
   starter principal, scopes, name, host label). `url` is `https://<remote-host>/#pair=<code>` when a
   remote host is configured (§8), else `null`. The code rides in the **fragment**, which a browser
   never sends to the server or to a proxy log. A QR code of `url` (P16's to draw) is therefore a
   120-second, single-use, scope-bound bootstrap — not a credential.
3. **Redemption.** The new client calls `POST /v1/devices/pair/redeem {code, name?, platform, pin?}`
   (public route: no bearer; Host allowlist and fetch metadata still apply). Core pops the code
   under a lock — the pop *is* the use, so of two concurrent redemptions exactly one wins — then
   mints the device token on the HTTP thread and runs one `register_device` command that receives
   only the token's hash (P3.5b A4: no idempotency key, so the response holding the token is stored
   nowhere). Answer: `{device_id, token, scopes, expires_at}`.
4. **Notice.** The registration writes `principal.created` and `device.state_changed`
   (`code_redeemed`), so every connected client — the desktop that started the pairing — hears of
   the new client at once and can revoke it.

### 6.2 Properties

| Property | How |
|---|---|
| short-lived | 120 s from start |
| one-time | popped on first redemption, success or failure of the command after it |
| identity binding | the new principal is `user_device` with the start's scopes; `created_by` is the starter |
| no permanent secret in the QR/URL | the code is a bootstrap; the token is minted at redemption and returned once in a response body, never in a URL (P3.5b `token_in_url` stays) |
| no enumeration | every failure is the same `401 invalid_pairing_code` (unknown, expired, reused, malformed) |
| brute force | 128-bit codes; and a **failure breaker**: more than 10 failed redemptions within 60 s burns every live pairing code and answers `429 pairing_locked` until the window passes (D10) |
| revocation | P3.5b's revoke; a revoked client's token is refused on its next request and its streams close |
| lost device | revoke its clients; the PIN protects step-up approvals meanwhile (§6.6) |

### 6.3 Why no second confirmation after redemption (D11)

A "confirm this phone on the desktop" step would defend a code photographed during its 120 s. It
costs a PAIRING state the credential check must half-accept, a status route the unconfirmed client
polls, and an expiry sweeper. The start is already the user's confirmation, on the local machine,
with the scopes chosen there; the redemption is announced on every connected client; revocation is
immediate. The residual risk (a code seen and redeemed within 120 s by someone who can also reach
the tunnel) is accepted and listed in §16; P20's threat review may add the second step.

### 6.4 Authentication vs pairing vs authorization

Pairing **establishes trust once** (a client exists, with scopes). Authentication **proves, per
request**, that the caller holds a live credential for that client (`auth.live`: hash match on
bytes, not revoked, not expired, client ACTIVE). Authorization is **P9's**, per action, inside the
application layer. P15 adds no rule, reads no policy and never branches on an actor's kind in the
HTTP layer (the P3.5b structure test stays green).

### 6.5 Scopes of a paired client

Default `observe control approve`; `admin` only when the starter asks for it explicitly (plan §22).
A scope list must be a non-empty subset of the four coarse scopes, and `observe` is always included
(a client that cannot read cannot show what it approves).

### 6.6 Step-up PIN (P9 D16's "proof P15 defines") [spec + new]

- At redemption a client may set a 6–12 digit PIN. Core stores `pbkdf2_hmac('sha256', pin, salt,
  200_000)` with a 16-byte random salt, in the client row; the PIN is never logged, returned or put
  in an event.
- P9's guard input `step_up_valid` keeps its definition — *"the deciding client is local, or
  presented a valid proof"* — and P15 supplies both halves: **local** is now `origin != 'paired'`
  (and, for rows written before P15, `platform` not `ios`/`android`, P9's rule); a **valid proof**
  is the PIN matching the paired client's `pin_hash`. A paired client without a PIN can never give
  one (fail-closed).
- **Why locality moves from platform to origin** (repository-specific finding R1): P9 derived
  "paired" from `platform ∈ {ios, android}`. A paired *browser on another laptop* declares
  `platform: web` and would have counted as local — satisfying step-up with no proof, from anywhere
  the tunnel reaches. `platform` is client-declared; `origin` is decided by Core from the
  registration path.
- **Lockout**: 5 consecutive wrong PIN proofs from one client revoke that client (reason
  `step_up_failures`). The counter is per Core process (a restart needs local access); any correct
  proof resets it.

## 7. Connection model [new]

A connection is one `GET /v1/events/stream` held open. It is registered in the stream pool (8
slots, at most 2 per client — P3.5b) under a fresh `connection_id`; it ends when the socket fails,
the client is revoked (closed before the revoke answers), its cursor falls behind retention
(`cursor_expired` frame, then close), or Core stops (`shutdown` frame). A connection carries no
authority of its own: every request, including the stream itself, authenticates its bearer token;
the stream re-checks its token each time it wakes.

Commands are **not** bound to a connection: HTTP/1.1 requests use whatever socket the client has,
and a phone may send a command over mobile data while its stream is on Wi-Fi. A client-originated
mutation is attributed to **principal → client** (and hence host label, origin, platform), which is
exact; it is not attributed to a connection id, which would be a guess (D12, §17).

## 8. Remote-access boundary [spec + clar + new]

### 8.1 Environments

| Environment | V1 | Threat model |
|---|---|---|
| same machine (loopback) | **default**; Core binds `127.0.0.1` only | local processes of any user can reach the port: token + Host + fetch-metadata (P3.5b) |
| local network (Core bound to a LAN address) | **not supported**: Core never binds anything but loopback | — |
| authenticated tunnel (Tailscale Serve recommended, Cloudflare Tunnel + Access, a user's reverse proxy) | **supported, opt-in** (`--remote-host`) | anyone who can reach the tunnel URL: every route but the SPA files and `pair/redeem` needs a token; HTTPS is the tunnel's |
| internet-facing deployment | **not supported** | — |

### 8.2 Remote hosts

`archeus core --remote-host <host>` (repeatable) adds `<host>` to the Host allowlist, and
`https://<host>` to the accepted Origins for requests carrying that Host. The host is a DNS name
(optionally `:port`), validated; `*`, IP-literal wildcards and schemes are refused. Without the
flag nothing but `127.0.0.1:<port>` is accepted — exactly P3.5b. Core never trusts the source
address or `X-Forwarded-*`: a tunnel forwards from loopback, so the peer address says nothing about
where a request came from. The proxy must pass the original `Host` header through; one that
rewrites it to `127.0.0.1` makes every remote request indistinguishable from a local one, and the
runbook says so.

### 8.3 Local-only routes (repository-specific finding R2)

P3.5b's `_loopback` checked the **peer address** only. Behind a tunnel every request has a loopback
peer, so `launch/redeem`, `launch/code` and `pair/start` would have been reachable remotely the day
a remote host was enabled. A local-only route now requires a loopback peer **and** a request `Host`
equal to the loopback origin's host. Mutation M02 removes the Host half.

### 8.4 Controls

| Threat | Control |
|---|---|
| transport | the tunnel's HTTPS; Core refuses a remote `Host` whose `Origin` is not `https://<that host>` |
| origin abuse / DNS rebinding | Host allowlist (exact names), Origin must match the Host's own origin, fetch-metadata allowlist |
| CSRF | none applicable: credentials are bearer headers, never cookies, and every route needs the header |
| WebSocket hijacking | no WebSocket; the SSE stream is a `fetch` with a bearer header (ADR-0009) |
| token in URLs / logs | refused (`401 token_in_url`); codes ride in fragments; the request log has no header, query or body |
| replayed pairing code | single use (popped); 120 s |
| replayed mutation | idempotency key → original answer, one effect (24 h); after that, state guards and `expected_version` (§14) |
| stale credential / revoked client | `auth.live` on every request and on every stream wake |
| stolen device / credential | revoke; 180-day expiry bounds an unnoticed theft; step-up needs the PIN; admin off by default |
| cloned client (token copied) | indistinguishable by design (a bearer token is the identity); visible as unexpected presence/actions; revoke. Device attestation is out of reach for a PWA (D2) |
| a local credential used through the tunnel | refused: a local credential (the CLI's token, a launch-code browser) is honoured on the loopback Host only; a remote client is a paired one (D21) |
| malicious client with a valid token | can do what its scopes allow, through P9 like any client — never more: every command is the route's application command, guarded as for the local CLI |
| cross-user | V1 has one owner; every `user_device` principal acts for that owner. Non-user principals (brain, execution, automation) hold no `observe` scope and cannot read or subscribe (P19) |
| cross-project | a client sees the owner's whole workspace (single owner, D13); a stream may be *narrowed* to projects (§11), which is a subscription, not a permission |
| brute-force / enumeration of pairing | §6.2 failure breaker; uniform 401 |

## 9. Authentication and authorization integration [spec + clar]

Unchanged pipeline (server.py §4), each step failing closed, with two P15 edits: step 1 accepts a
configured remote host (and step 2 then requires its `https` origin); local-only handlers check
Host as well as peer (§8.3). Route scopes stay coarse and are the only authorization at this layer:
`observe` reads and subscribes, `control` runs mission/execution/session/knowledge commands,
`approve` reaches only the three human decisions, `admin` changes configuration and starts
pairings. **P9 remains the authority for every action**: a remote approval runs
`Authorization.decide` with the echoed `action_hash`, its eligibility checks and its step-up guard,
exactly as the CLI's does (P14, P31).

## 10. Session, mission and execution integration [spec + clar]

- A connection opening, closing or dropping writes only the §5 presence events. It creates,
  resumes, links, closes or hands off no P12 session; it moves no mission, task, execution,
  approval or verification.
- A client **views** a session (`GET /v1/sessions/{id}`), **resumes** one (`POST
  /v1/sessions/{id}/resume`, P12 continuity and brief), **creates** one, **hands one off**, or
  **disconnects** — the last does nothing to the session. A reconnect never creates a session: no
  P15 path calls a P12 command (boundary test, mutation M13).
- Session state is reconstructed from P12's rows and brief, never from the event stream.
- A disconnected client implies nothing about missions or executions. Only authoritative rows say a
  mission was cancelled or an execution stopped (P07, P08, P23).
- Reconnecting duplicates nothing: every command carries an idempotency key; approvals are
  single-use and bound to `action_hash`; P14's `UNIQUE (automation, event)` is untouched; P13's
  verifications are recorded only by its worker (P11, P24).

## 11. Realtime and event integration [spec + new]

One transport: **SSE**, ids-only frames, `Last-Event-ID` replay, 410 on an expired cursor
(ADR-0009, P3.5b). No WebSocket, no polling loop, no second bus. The flow is exactly:

```
authoritative row + event, one transaction (P14)  →  outbox seq  →  SSE frame {seq, type, subject, scope}
     →  client re-queries the subject  →  screen shows what the row says
```

**Client-visible event contract.** Every frame:

| Field | Source |
|---|---|
| `id` | the event `seq` (the resume cursor) |
| `event` | the event type from the registry (`archeus/core/domain/events.py`) |
| `data.subject` | `{kind, id}` — the entity to re-query |
| `data.scope` | `{workspace, project}` |

Version: the frame shape is `v1` with the API path; types are versioned by the registry (P14 D2 —
a new meaning is a new type). Timestamp, actor, `cause_chain` and payload are **not** in the frame;
they are in the envelope from `GET /v1/events?after=` (observe) for a client that wants the audit
trail. Frames carry no payload, so no frame can carry a secret, a model's reasoning or content.

**What is exposed.** Every registered type reaches `observe` clients (P3.5b A16: one owner; the
in-process and HTTP bindings see the same events). A client may **narrow** its stream with
`?project=<id>` (repeatable; events of those projects plus events with no project) and `?type=<prefix>`
(repeatable, e.g. `mission.`, `approval.`) — for constrained connectivity (P27) and for P20's "no
cross-project frames on a project-scoped screen". Narrowing never widens: a filter can only remove
frames an unfiltered stream would carry.

**Delivery** is at most once per connection and resumable, **not reliable**: a phone that loses the
connection, sleeps past retention, or reconnects to a restored backup misses frames, and that is
correct behaviour. Every frame is safe to drop because the client can always re-query (§12). The
server's P14 delivery guarantees (at least once, to Core's own consumers) are **not** extended to
clients (D14).

## 12. Offline and disconnected behaviour [spec + new]

The server declares, per command, whether a client may **replay it from an offline queue**. A client
that sends a command it queued while offline marks it `X-Archeus-Queued: 1`; Core refuses every
queued command that is not declared replayable with `409 queued_intent_refused` before anything is
written (the client then re-reads and asks its user again).

| Class | Commands | Queue offline? | Validated | Changed state / expired authorization / changed plan / completed mission / already done |
|---|---|---|---|---|
| read-only cache | every GET (with its `X-Archeus-Seq`) | n/a — display only, marked stale (§13) | — | — |
| safe local UI | drafts, filters, tab, scroll | client-only, never sent | — | — |
| replayable intent | `POST /v1/digest/ack` | **yes** | at delivery | monotone (`max`): an older ack is a no-op, `changed: false` |
| live-only | every other command (missions, pause/resume/stop, e-stop/rearm, approvals, verification decisions, reviews, sessions, messages, knowledge, projects, admin) | **no** → `409 queued_intent_refused` | — | the client re-reads and re-asks |
| never queued, even online after a disconnect of unknown outcome | the same commands, **retried** with their original idempotency key | a retry, not a queue | at delivery | same key → the original answer, one effect; a new decision needs a new key and passes every guard again |

What a *live* command meets when the world moved on (all existing, all typed, none silent):
state changed → `422 invalid_transition` / `guard_failed`; version moved → `409 version_conflict`
with `current`; authorization expired/superseded/plan changed → `409 approval_not_eligible` (P9
§8.5); mission completed → `422 invalid_transition`; already performed → the idempotent original
answer, or `changed: false`.

This is api-and-realtime §7 made enforceable: "commands are not queued offline — an approval sent
hours late could be wrong". The header is a declaration by a well-behaved client; a client that
lies about it gains nothing a live command could not already do, because the live path is guarded
the same way.

## 13. Reconnect and resynchronization [new]

**`GET /v1/sync`** (observe) is the anchor:

```json
{"client": {"id": "dvc_…", "principal_id": "prn_…", "state": "ACTIVE", "origin": "paired",
            "client_type": "spa", "scopes": ["observe", "control", "approve"],
            "capabilities": {"step_up": "pin"}, "expires_at": "…"},
 "core": {"instance": "<random per Core process>", "started_at": "…", "version": "…"},
 "head_seq": 18233, "floor_seq": 1041, "server_time": "…"}
```

Every authenticated JSON response carries **`X-Archeus-Seq`**: the event head read *before* the
handler's own read, so the body reflects at least that seq.

Protocol (the SPA's `stream.ts` already does steps 3–5 for a tab; P15 makes it a contract):

1. **Authenticate**: any request; `401` → the credential is gone (revoked/expired) → re-pair.
2. **Anchor**: `GET /v1/sync` → `head_seq` H, `floor_seq` F, `core.instance` I.
3. **Resume or resync**: if the client holds a cursor C with F ≤ C ≤ H, open the stream with
   `Last-Event-ID: C` (Core replays `seq > C`, then goes live) and re-query the subjects the replayed
   frames name. Otherwise (no cursor, C < F, or C > H — a restored backup) open the stream with
   `Last-Event-ID: H` **first**, then re-query every screen: anything committed after H arrives on
   the stream, and every query answers at `X-Archeus-Seq ≥ H`, so there is no gap.
4. **Current or stale** (P25): a displayed object read at `X-Archeus-Seq` S is current while the
   stream is connected (a heartbeat within 30 s) and no received frame with seq > S names it;
   otherwise it is stale and shows its age. `core.instance` changing tells the client every
   connection and presence it knew about is void.
5. **Mid-stream expiry**: `event: cursor_expired` → step 3's resync branch.

Subscriptions are the stream's query string; a reconnect re-sends it. Session, mission and
execution state after a reconnect come from their own queries (P12's brief, `GET /v1/missions/{id}`,
`GET /v1/executions/{id}`) — the stream only says *what* to re-query.

## 14. Conflicts and optimistic concurrency [spec + clar]

- Every command already carries an idempotency key (24 h): the same key replays the original answer;
  the same key with a different body is `400` (P3.5b).
- `expected_version` stops a command built on an obsolete read: approvals and resource policies take
  it already; **P15 exposes the optional `expected_version` that P7's `Missions.pause` and
  `resume` already accept** on their two routes (D15). A mismatch is `409 version_conflict` with the
  current version — never last-write-wins.
- Approval decisions are additionally bound to the `action_hash` the client displayed (P9 X02).
- Retry: on `409 version_conflict` the client re-reads and asks its user; on `503 busy` it retries
  the same key after `Retry-After`; on a network failure of unknown outcome it retries the same key.

## 15. Model and harness boundary [clar]

A client may display the selected harness, account, model and the route decision's reasons
(`GET /v1/route-decisions/{id}`, `GET /v1/executions/{id}`) — structured provenance, never a
model's private reasoning (P10/P11 already expose only decisions and outputs). **No P15 route,
field or schema accepts a model, harness, account, effort or resource preference**; pairing
schemas reject unknown fields, and no P15 module imports `archeus.core.routing` or
`archeus.harnesses` (boundary test, mutation M17). Selection stays P10's (with P7/P8/P13 inputs).

## 16. Security model summary [new]

Threats and controls are §8.4. Residual risks, stated rather than implied:

1. **A leaked pairing code** within its 120 s by someone who can reach the tunnel pairs a client with
   the start's scopes (not admin unless chosen). Announced on every connected client; revocable.
2. **A stolen unlocked phone** holds a valid credential until revoked or 180 days pass; it can
   observe, control and approve non-step-up items. Step-up items need the PIN.
3. **A cloned credential** is indistinguishable from its client (no attestation, D2).
4. **Single owner** (D13): no per-project or per-user permissions exist to leak across; a second
   person given a client is given the owner's view.
5. **The Windows local token** is protected by the profile ACL, not `0600` (P3.5b; DPAPI is P20).
6. PIN lockout counters reset on Core restart (restart needs local access).

## 17. Observability and audit [new]

For a client-originated mutation, the audit chain is all rows, no logs:

| Question | Answered by |
|---|---|
| which user | the owner (single-owner home) |
| which client / device | the event's `actor` principal → `devices.principal_id` → client id, name, `host_label`, `platform`, `origin`, `client_type` |
| which connection | stream lifecycle only (`device.stream_opened/closed` with `connection_id`); commands are not bound to a connection (§7, D12) |
| which session / mission / task | the command's subject and its event's subject/payload (P7/P12) |
| which authorization | the approval (`approved_by` principal, `action_hash`) and `PolicyDecision` rows (P9) |
| which execution | the mission's executions and route decisions (P10/P11) |

`GET /v1/devices` lists clients with presence (`state`, `connections`, `last_seen_at` since this
Core started). The request log keeps method, route template, status, duration and client id —
never a header, query string, body, token, code or PIN. Presence logs and events never state more
than §5 defines.

## 18. API contracts [new]

| Method | Path | Scope | Idempotency | Notes |
|---|---|---|---|---|
| POST | `/v1/devices/pair/start` | admin + local | exempt (the response holds a code) | `{name?, host_label?, scopes?}` → `{code, expires_in, scopes, url}` |
| POST | `/v1/devices/pair/redeem` | none (code) | exempt (holds a token) | `{code, platform, name?, pin?}` → `{device_id, token, scopes, expires_at}`; 401 `invalid_pairing_code`, 429 `pairing_locked` |
| GET | `/v1/devices` | observe | — | clients with presence and capabilities; no hash, no PIN |
| GET | `/v1/sync` | observe | — | §13 |
| GET | `/v1/events/stream` | observe | — | adds `?project=` and `?type=` narrowing (§11) |
| POST | `/v1/missions/{id}/pause`, `/resume` | control | required | adds optional `expected_version` (§14) |

Headers: every authenticated JSON response carries `X-Archeus-Seq`; a command may carry
`X-Archeus-Queued: 1` (§12). New error codes: `401 invalid_pairing_code`, `409
queued_intent_refused`, `429 pairing_locked`. Revocation, launch codes, every domain route: unchanged.

CLI: `archeus pair [--name N] [--host-label H] [--scopes a,b]` prints the code, its expiry and the URL
(or how to set `--remote-host`); `archeus devices` lists clients with presence; `archeus devices
revoke <id>`; `archeus core --remote-host <host>`.

Not in P15 (P16): a pairing screen, QR rendering, a device-management surface, the PWA manifest and
service worker, mobile layouts, notification preferences.

## 19. Acceptance scenarios

Deterministic, over the real HTTP stack (`TempCore`) unless marked; file
`tests/v1/integration/test_presence.py` unless noted. Judge rows S11, S14 and G6 finish here.

| # | Scenario | Proven by |
|---|---|---|
| P01 | a new client pairs securely: start (admin, local) → redeem → token works with exactly the start's scopes | integration |
| P02 | a pairing code expires (injected clock) | integration |
| P03 | a pairing code cannot be reused, even concurrently (one of two wins) | integration |
| P04 | a revoked client cannot reconnect (401 on stream and requests) | integration + judge G6 |
| P05 | two clients coexist for one user (both ACTIVE, both listed, independent tokens) | integration |
| P06 | desktop and phone receive the same authoritative state (same body, same frames) | integration |
| P07 | a client disconnect does not end a mission | integration |
| P08 | a client disconnect does not end an execution | integration |
| P09 | reconnect reconstructs authoritative state (`/v1/sync` + re-query) | integration |
| P10 | missed frames: resume with `Last-Event-ID` replays; behind retention → 410 → resync | integration |
| P11 | reconnect does not duplicate an action (same key → one effect) | integration |
| P12 | an offline-queued command is refused unless declared replayable; the ack is accepted | integration |
| P13 | a stale client mutation is detected (`expected_version` on pause; approval `action_hash`) | integration |
| P14 | a remote approval still passes through P9 (eligibility, step-up, `action_hash`) | integration + judge S11 |
| P15 | remote execution control still passes through P11 (stop via the P11 route, rows show P11's move) | integration |
| P16 | session resume still uses P12 (same session id, P12's brief; no session from a reconnect) | integration |
| P17 | verification state still comes from P13 (the phone reads P13's rows; no P15 write path) | integration |
| P18 | P14 events update connected clients (a frame per committed event) | integration |
| P19 | a non-user principal cannot read or subscribe; a revoked owner client cannot either | integration |
| P20 | a stream narrowed to a project carries no other project's frames | integration |
| P21 | revoked credentials stop access immediately, including an open stream | integration + judge G6 |
| P22 | two tabs (two connections of one client) receive the same frames; a third is 429 | integration |
| P23 | reconnection during an active execution is safe (execution continues, no duplicate) | integration |
| P24 | reconnection during an approval is safe (still PENDING; one decision with a retried key) | integration |
| P25 | a client can tell current from stale (`X-Archeus-Seq` vs frame seqs) | integration |
| P26 | a client can request authoritative resync (`/v1/sync` anchor) | integration |
| P27 | constrained connectivity: type/project narrowing, paged catch-up | integration |
| P28 | pairing exposes no permanent credential (code ≠ token, fragment URL, nothing stored, no token in any event/log) | integration |
| P29 | the audit trail identifies client/device/connection for a client-originated mutation | integration |
| P30 | presence implies no mission/session/execution state | integration |
| P31 | P15 bypasses no owner (boundary: P15 routes run only registration/revocation commands; no `core` module reads presence) | unit `test_presence_units.py` |
| P32 | model/harness selection stays outside P15 (schemas refuse the fields; no routing/harness import) | unit |
| R1 | a paired `web` client is not local: step-up needs its PIN; 5 wrong PINs revoke it | integration |
| R2 | a tunnel-forwarded request (loopback peer, remote Host) cannot reach a local-only route | integration |
| R3 | a remote Host is accepted only with its own `https` Origin; an unconfigured host is refused | integration |
| R4 | the pairing failure breaker burns live codes and answers 429 | integration |
| R5 | presence events are written only on 0↔1 transitions, with the connection id | integration |
| S11 | a paired phone pauses and resumes a mission; an observe-only client cannot (403) | judge |
| S14 | an ack on one client clears the digest on the others | judge |
| G6 | revoking a client closes its live stream | judge |

## 20. Mutation strategy (`tools/mutate_p15.py`)

Same runner as P11–P14. Each mutation must be killed by the named tests.

| # | Mutation | Killed by |
|---|---|---|
| M01 | authentication bypassed for a paired credential (`live` ignores revocation) | P04, P21 |
| M02 | local-only routes check the peer only (Host half removed) | R2 |
| M03 | an expired pairing code is accepted | P02 |
| M04 | a pairing code is not popped (reusable) | P03 |
| M05 | the redeemer may widen the start's scopes | P01 |
| M06 | the failure breaker never trips | R4 |
| M07 | a revoked client's stream is not closed | P21, G6 |
| M08 | step-up locality by platform only (origin ignored) | R1 |
| M09 | any PIN proof is accepted | R1 |
| M10 | PIN lockout never revokes | R1 |
| M11 | a queued live-only command is accepted | P12 |
| M12 | `expected_version` dropped on pause | P13 |
| M13 | a stream open resumes/creates a P12 session (presence treated as session) | P16, P30 |
| M14 | a stream disconnect pauses the client's missions (disconnect treated as authoritative) | P07 |
| M15 | the project narrowing is ignored | P20 |
| M16 | a remote Host is accepted with an `http` Origin | R3 |
| M17 | pairing accepts a model/harness field | P32 |
| M18 | `X-Archeus-Seq` read after the handler's query (current-state claim too new) | P25 |
| M19 | the sync anchor reports a stale head | P26, P09 |
| M20 | presence events written on every connection instead of 0↔1 | R5 |
| M21 | a client may decide an approval without the echoed `action_hash` reaching P9 (route drops it) | P14 |
| M22 | reconnect replay: the idempotency key is not forwarded on pause | P11 |
| M23 | a local credential is honoured through the tunnel (D21) | R3 |

## 21. Decisions

- **D1** The `Device` entity *is* the client registration. No rename: the table, the `dvc_` prefix,
  the `device.*` events and `/v1/devices` stay; prose and fields say "client".
- **D2** Physical devices are not entities: Archeus cannot verify one (no attestation for a PWA or
  in the stdlib). A client carries the user's `host_label` and a declared `platform`, for display.
- **D3** `client_type` (`cli`, `spa`) and `origin` (`local`, `paired`) are set by Core from the
  registration path; rows written before P15 read as `cli`/`local` (platform `tui`) or `spa`/`local`.
- **D4** Presence is in-memory, per client, per Core process; states `connected`, `recent`,
  `absent`, `revoked`; durable trace only as `device.stream_opened/closed` on 0↔1 transitions.
- **D5** Security decisions use `origin`, never the client-declared `platform` (except P9's
  pre-P15 rule, kept for old rows).
- **D6** "Available" and "active" (a person) are not modelled.
- **D7** Pairing is start (admin, local) → 128-bit code, 120 s, single use, scopes fixed at start →
  redeem (public) → token minted on the HTTP thread, only its hash in the command.
- **D8** Paired credentials expire 180 days after pairing; there is no refresh (re-pair). Local and
  launch credentials are unchanged.
- **D9** The redeemer chooses only `name` (if the start did not), `platform` and `pin`.
- **D10** More than 10 failed redemptions in 60 s burn every live code and lock redemption for the
  rest of the window.
- **D11** No post-redemption confirmation step (§6.3).
- **D12** Commands are attributed to principal → client, not to a connection.
- **D13** Single owner: no per-project or per-user permission in V1; stream narrowing is a
  subscription, not a permission.
- **D14** Client delivery is best-effort and resumable; correctness comes from re-query.
- **D15** `expected_version` is exposed on pause/resume (P7's commands already take it).
- **D16** Remote hosts are explicit (`--remote-host`), exact names; the tunnel is the user's.
- **D17** Local-only routes require loopback peer **and** loopback Host (R2).
- **D18** Offline queuing is server-declared: only the digest ack is replayable.
- **D19** Step-up PIN: 6–12 digits, pbkdf2-sha256 200k, per-client; 5 consecutive failures revoke.
- **D21** A credential whose client is not `paired` is honoured on the loopback Host only
  (added during implementation, §22).
- **D20** Deferred to P16: pairing and device screens, QR rendering, PWA manifest and service worker,
  mobile layouts. Deferred to P20 (or a user decision on ADR-0010 Q3): ntfy notifications. Deferred:
  token refresh, self-revoke ("sign out this phone"), per-project client grants.

## 22. As built

Everything in §1–§21 is built as written, except the deviations below.

**Files.** New: `archeus/api/presence.py`, `tests/v1/integration/test_presence.py`,
`tests/v1/unit/test_presence_units.py`, `tools/mutate_p15.py`. Changed: `archeus/api/auth.py`
(remote hosts in `Origin`, `remote_host`, `PairingCodes` + `PairingLocked`, `StepUpFailures`,
`iso`/`now_iso`; `LaunchCodes` keeps its API over a shared `_mint`/`_pop`), `api/server.py`
(`Api` gains `remote_hosts`, `pairing`, `step_up`, `instance`, `started_at`, `seen`; the pipeline
records presence, adds `X-Archeus-Seq`, refuses queued intent and local credentials on a remote
Host), `api/sse.py` (connection ids, narrowing, the 0↔1 traces, a stream's own traces hidden
from it), `api/routes.py` (four routes, `REPLAYABLE`, Host-and-peer `_loopback`, the step-up
lockout in `decide_approval`, `expected_version` on pause/resume), `api/schemas.py`,
`core/domain/entities.py` (`Device.origin`, `client_type`, `host_label`, `pin_hash`),
`core/application/commands.py` (`register_device` takes them, `hash_pin`, `pin_matches`,
`record_connection`), `core/application/authorization.py` (`is_paired`, `_step_up_valid` —
the change P9 D16 reserved for P15), `core/application/queries.py` (`devices`, the credential's
`device_origin`), `core/runtime.py` + `cli/main.py` + `claude_sessions/cli.py` (`--remote-host`,
`archeus pair`, `archeus devices`), the generated API reference and TypeScript client, the judge
(`http.py`, `support.py`, S11, S14, G6), `tests/v1/integration/test_sse.py`,
`tests/v1/unit/test_api_structure.py`. No migration: every new client field is a body field with
a default, so rows written before P15 read as `local`.

**Tests.** 32 integration tests (P01–P30, R1–R5, the CLI), 35 unit and boundary tests (codes,
breaker, lockout, hosts, narrowing, PIN at rest, P31, P32, the trace moves nothing); judge S11
(both functions), S14 (cross-device) and G6 (revoked stream) no longer xfail — over the HTTP
binding; the in-process binding has no credentials and skips `rig.device`.

**Deviations.**

1. **D21 was added while building** [new]. With a remote host enabled, the CLI's local token (all
   four scopes, a file on this machine) was accepted through the tunnel like a paired client.
   A client that is not `paired` is now honoured on the loopback Host only (`403
   host_not_allowed`, "pair this client to use Archeus remotely"); R3 and M23 pin it.
2. **A stream hides its own client's traces** [clar]. `device.stream_opened` is written after the
   stream registers, so the opening stream would otherwise receive the notice of its own
   connection. Other clients still see it (the desktop hears the phone connect). The P3.5b SSE
   tests that compared frames with *every* event now compare with every event but the client's
   own traces.
3. **S14's cross-device function waits for Core to settle** before the phone acknowledges: the
   engine moves the new mission on by itself, and an event after the ack is — correctly — news on
   the desktop. The per-user cursor is what the function proves, and it does.
4. **`rig.device` skips on the in-process binding** (as `device_token` and `http_get` already do):
   pairing is a transport concept with nothing to call in process.
5. **Mutation list.** M07 needs two edits (the revoke handler's close *and* the stream's own
   re-check), because either alone still closes the stream within one wake — a single-edit M07
   would test nothing. M13/M14 are the plausible "presence is authoritative" regressions (a
   dropped last stream closes the client's sessions / pauses running missions), inserted where the
   close trace is written. M21 is "the route drops the step-up proof on its way to P9". M23 was
   added with D21. M14 first **survived**: P07 closed only the client's raw socket, which the
   HTTP response object kept open, so Core never saw a disconnect and the mutated code never ran.
   P07 now closes the client properly and waits for Core's own `device.stream_closed` before it
   asserts — a disconnect is a disconnect when Core has seen it.
6. **`queries.credential` also returns `device_origin`**, which the pipeline needs for D21 and the
   lockout; the P3.5b `launch/*` routes now check Host as well as peer (R2), which changes nothing
   for a local caller.
7. **A P3.5b test race, widened by P15.** `test_a_stream_that_falls_behind_a_prune_…` armed its
   page hold *after* the stream opened, so a first page already in flight could read past the
   prune. The trace commit before the stream's first page made that window wide enough to fail
   about one run in three; the hold is now armed before the stream opens (10/10 afterwards).
   `Origin.origin_for(None)` is the local origin: a unit test calls `fetch_ok` with no Host,
   which a real request never reaches (the Host check runs first).
8. **ADR-0010 stays PROPOSED.** P15 built the tunnel-agnostic parts (remote hosts, pairing, PIN,
   resync); the tunnel choice (Q2) and ntfy (Q3) remain the user's (D20).

**Known limitations** (stated in §16 or here; none is a gap P9–P14 rely on): presence and the PIN
lockout counter are per Core process; a PIN proof is checked inside P9's transaction (pbkdf2,
~0.05 s of writer time per proof on the development machine); the failure breaker is global, so
someone who can reach the tunnel can keep *pairing* locked (not access); no token refresh (re-pair
after 180 days); no self-revoke ("sign out this phone"); commands are attributed to a client, not a
connection (D12); a single owner, so no per-project client grants (D13); the pairing and device
screens, QR, PWA manifest and service worker and mobile layouts are P16's, ntfy is P20's or Q3's
(D20) — until P16, pairing is `archeus pair` plus any HTTP client.
