# Archeus V1 — API, Realtime and Remote Access

Status: **DECIDED** for the local API and SSE (ADR-0009); **PROPOSED** for remote access and
mobile (ADR-0010). Push beyond ntfy is **DEFERRED**.

## 1. Principles

1. **Commands and queries are separate.** Commands mutate (POST), are idempotent by key, and
   return the new version and resulting event seq. Queries read (GET) and are cacheable by
   version.
2. **The event stream carries identities, not state.** SSE sends `{seq, type, subject}`; the
   client re-queries what it shows (wake-and-requery, as Vicoa's LISTEN/NOTIFY path does). No
   client ever reconstructs state from event payloads, so a missed or reordered event cannot
   produce a wrong screen — only a late one.
3. **One route table.** `archeus/api/routes.py` is a flat list of
   `(method, path, handler, required_scope, idempotent, request_schema, response_schema)`
   (P3.5b: the two schema columns type the generated client and let the route boundary check a
   body's shape; there is no rate-limit column until a route needs one). Documentation
   (`docs/architecture/api-reference.md`, generated in P3.5) and the SPA's typed client
   (`clients/app/src/api/generated.ts`) are generated from it; a test fails when either is stale
   (same pattern as today's `tools/gen_api_docs.py`).
4. **Version in the path** (`/v1/…`). Breaking changes add `/v2` routes; the SPA shipped in the
   same wheel always matches.
5. **Errors are typed:** `400 invalid_request` (names the field), `401`, `403 scope_required`,
   `404`, `409 version_conflict` (returns current version), `410 cursor_expired`, `422
   invalid_transition` (names machine/from/to and the trigger), `422 guard_failed` (the edge
   exists but its guard refused: names machine/from/to/trigger, the guard and its reason —
   state-machines §0), `423 policy_denied` (`{task, action_class, decision, reason}`; the
   PolicyDecision id is added as a new field once P9 persists decisions, and is absent — not
   null — until then), `429`, `503 core_starting`. Never a bare 500 for a client mistake
   (lesson from today's endpoint floor). P3.5b adds `401 token_in_url`, `401
   invalid_launch_code`, `403 host_not_allowed`, `403 cross_site`, `405 method_not_allowed`,
   `413 payload_too_large`, `429 too_many_streams`, `503 busy` (with `Retry-After`) and `503
   core_stopping`; the full table is p3.5b-design-gate.md §5.5 and the generated
   [api-reference.md](api-reference.md) lists every route.

## 2. Resource surface (conceptual)

| Area | Queries (GET) | Commands (POST) |
|---|---|---|
| Presence | `/v1/digest` (P4), `/v1/now` (digest + active + attention summary, P16 — it embeds the digest query), `/v1/activity?since=` | `/v1/digest/ack` (P4; the monotone per-user cursor) |
| Conversation | `/v1/conversations/{id}/messages?before=` — P7: `?after=`, and `primary` names the primary conversation | `/v1/conversations/{id}/messages` (user turn → intent pipeline; returns message id; reply arrives via events) — P7, with `in_reply_to` |
| Intent | `/v1/intents/{id}` (P7) | `/v1/intents/{id}/clarify` (P7: `{choice: proceed\|drop}` for a challenge, or `{text}` answering a clarification) |
| Missions | `/v1/missions?state=&project=`, `/v1/missions/{id}`, `/{id}/plan`, `/{id}/tasks`, `/{id}/timeline`, `/{id}/why` | `create`, `pause`, `resume`, `cancel`, `reprioritize`, `request-changes`, `accept`, `feedback` |
| Plans | `/v1/plans/{id}` | `/v1/plans/{id}/edit` (creates new version) |
| Tasks / Executions | `/v1/tasks/{id}`, `/v1/executions/{id}`, `/v1/executions/{id}/stream?from=` (tail of normalised events), `/v1/executions/{id}/checkpoints` | `stop`, `retry`, `handoff` |
| Approvals / Attention | `/v1/attention` (approvals, blockers, acceptance items, knowledge & drift proposals), `/v1/approvals/{id}` | `/v1/approvals/{id}/decide` `{decision, note, step_up?, idempotency_key}` |
| World | `/v1/status` (P4, deterministic), `/v1/projects`, `/v1/projects/{id}`, `/v1/world/graph?focus=&depth=`, `/v1/repositories/{id}/inspections`, `/v1/meetings`, `/v1/decisions`, `/v1/ideas` (P7, `?state`), `/v1/people` | `projects/create|archive` (`POST /v1/projects`, admin, P4), `projects/{id}/constraints` (P4), `repositories/{id}/inspect`, `meetings/import`, `ideas/capture|promote|park` |
| Knowledge | `/v1/knowledge?type=&scope=&q=`, `/v1/knowledge/{id}` (with supersession chain) — P6: `?project&state&type` | `confirm`, `retract`, `supersede`, `pin`, `forget` (dry-run default) — P6: all but `pin`, plus `reject` and `/v1/feedback` |
| Context | `/v1/context/{package_id}` (P5; also embedded in `/v1/missions/{id}` as `context_package`) | `/v1/context/preview` (P5, observe, writes nothing: assemble without recording) |
| Resources | `/v1/harnesses`, `/v1/accounts`, `/v1/accounts/{id}/usage`, `/v1/models`, `/v1/route-decisions/{id}` (P6, with `?source&purpose` listing), `/v1/provider-terms` (P6) | `accounts/register|disable|reauth`, `resource-policies/{account}` (priority/allocation/budgets), `/v1/route/preview`, `/v1/provider-terms/{harness}` (P6, admin: the ADR-0021 answer) |
| Policy | `/v1/policies?scope=`, `/v1/policy-decisions/{id}`, `/v1/policies/simulate` | `policies/set`, `profiles/apply` |
| Automations | `/v1/automations`, `/v1/automations/{id}/runs` | `create`, `enable`, `disable`, `archive`, `run-now` |
| Devices / Nodes | `/v1/devices`, `/v1/nodes` | `launch/code` (local token only), `launch/redeem` (loopback only), `pair/start` (local only), `pair/redeem`, `devices/{id}/revoke`, `estop`, `rearm` |
| Events | `/v1/events?after=&limit=` (paged catch-up), `/v1/events/stream` (SSE) | — |
| Hooks (execution scope only) | — | `/v1/hook/evaluate`, `/v1/hook/report`, `/v1/hook/checkpoint`, `/v1/hook/request-approval` |
| System | `/v1/health`, `/v1/version` | `/v1/estop` (all executions), `/v1/rearm` |

Every command body carries `idempotency_key` (client-generated ULID) and, where it edits a row,
`expected_version`. Keys are stored 24 h in `idempotency_keys`; a repeat returns the original
response.

## 3. Events

### 3.1 Envelope

```json
{
  "seq": 18233,
  "id": "01JC8Z…",
  "type": "mission.state_changed",
  "at": "2026-09-23T14:02:11.412Z",
  "actor": {"kind": "execution", "id": "prn_…"},
  "cause_chain": ["01JC8Y…", "01JC8X…"],
  "subject": {"kind": "mission", "id": "msn_…"},
  "scope": {"workspace": "ws_…", "project": "prj_…"},
  "visibility": "user",
  "payload": {"from": "EXECUTING", "to": "BLOCKED", "reason": "allocation reached on all eligible accounts"}
}
```

`actor` is the **principal that caused the event** (domain-model §9.5 `actor_principal_id`):
`actor.id` is always a `prn_…` principal id and `actor.kind` that principal's kind. An
execution acts through its own principal; the `exe_…` id is provenance and appears as the
`subject`, in `cause_chain` or in the payload, never as the actor. Stored as `actor_kind` +
`actor_id` in `events`; `Event` refuses any other id.

### 3.2 Event type registry

One file, `archeus/core/domain/events.py`, a flat table `(type, subject_kind, visibility,
notify_default, description)`. The spec's events map as:

| Spec event | Archeus type |
|---|---|
| PROJECT_CHANGED | `project.changed` (repo HEAD moved / files changed, debounced) |
| FILE_ADDED | `repository.file_added` (from watcher/inspection diff; path + glob-matchable) |
| MODEL_CREATED | `repository.model_added` (inspection classifier: new model/schema file) and `catalog.model_released` (new provider model) — two different things the spec conflated |
| MEETING_ADDED | `meeting.imported` |
| DECISION_CREATED | `decision.created` |
| MISSION_CREATED / MISSION_BLOCKED | `mission.created`, `mission.state_changed` (to BLOCKED) |
| TASK_COMPLETED / TASK_FAILED | `task.state_changed` |
| REVIEW_REQUIRED | `review.requested` |
| FEEDBACK_RECEIVED | `feedback.received` |
| ACCOUNT_LIMIT_REACHED | `account.health_changed` (to LIMITED) |
| RESOURCE_UNAVAILABLE | `account.health_changed` / `harness.state_changed` / `node.state_changed` |
| AGENT_FINISHED | `execution.ended` |
| DEVICE_CONNECTED / DISCONNECTED | `device.stream_opened` / `device.stream_closed` (visibility system) |

Design rule (PDF §19): events describe durable facts; consumers decide what they mean.

P7 registers `idea.created`, `idea.state_changed` and `mission.updated` (a continuation added
requirements or constraints) and nothing else: an intent, a clarification and a challenge are
rows recorded by the reply's `message.created`, whose cards say which (p7-design-gate D6).

### 3.3 What is event-driven

Everything a screen shows that can change without the user acting: mission/task/execution state
and progress, attention items, account health and usage snapshots (coalesced ≤ 1/10 s per
account), automation runs, knowledge proposals, digest counts, conversation replies (the brain's
reply is a message row; the stream says `message.created`). Execution output streams are
**not** pushed through the global stream; the inspector subscribes to
`/v1/executions/{id}/stream` only while open.

### 3.4 Retention

Events kept 180 days (configurable); events referenced by an open mission are kept until the
mission closes + 30 days. Retention runs as a nightly outbox consumer.

The cursor contract (`seq` in `Last-Event-ID` or `?after=`), implemented by
`archeus/infra/eventlog/outbox.py` in P2 and mapped to HTTP in P3.5:

| Cursor | Answer |
|---|---|
| not a non-negative integer | `400 invalid_request` |
| behind retention (older than the oldest retained event) | `410 cursor_expired` → snapshot resync (re-query its screens) |
| ahead of the highest `seq` ever assigned (a restored backup, a reset home) | `410 cursor_expired` → snapshot resync |
| otherwise | committed events with `seq > cursor`, oldest first, pages of ≤ 1000, all from one read snapshot |

## 4. SSE transport (stdlib)

- `GET /v1/events/stream` with `Authorization: Bearer <device token>` — the SPA uses
  `fetch()` with a streaming body reader (not `EventSource`, which cannot set headers), so the
  token never appears in a URL.
- Frames: `id: <seq>\nevent: <type>\ndata: {"subject":…,"scope":…}\n\n`; heartbeat comment
  `: hb\n\n` every 15 s (detects half-open sockets on Windows); client reconnects with
  `Last-Event-ID` → Core replays from `events` where `seq > id` (P3.5b: `observe` sees every
  event; per-device filtering arrives with paired devices). A cursor is validated before the
  stream starts (400 malformed, 410 pruned/ahead); **no cursor means live from the head**, what a
  client does after a resync. A stream that falls behind retention mid-way receives `event:
  cursor_expired` and is closed — it never skips silently; Core shutting down sends `event:
  shutdown`.
- **Separate pools.** `api/server.py` keeps request threads (bounded, e.g. 32) and SSE streams
  (bounded, e.g. 8, max 2 per device) apart, so long-lived streams never starve commands — the
  current `gui.py` has a single 32-slot semaphore that SSE would exhaust.
- **One stream per browser.** The SPA elects a leader tab (Web Locks API) that owns the SSE
  connection and fans events out to other tabs via `BroadcastChannel`; this avoids the HTTP/1.1
  six-connections-per-origin limit.
- **Reader discipline.** Stream threads never hold a DB transaction while waiting; they block on
  an in-process condition variable that the writer notifies after each commit, then read new
  events with a short `query_only` connection (no WAL checkpoint starvation).
- **Revocation** closes the device's live streams immediately.

## 5. Authentication, pairing and remote access

### 5.1 Local

- Core binds `127.0.0.1:7337`, and the one accepted origin is `http://127.0.0.1:7337`
  (`localhost` is deliberately not a second name for it: a second origin would mean a second
  stored token and a second stream leader). The port is fixed because the browser origin
  includes it. `<ARCHEUS_HOME>/run/core.json` (`{pid, create_time, port, started_at, version,
  schema}`, not secret) is trusted only while `run/core.lock` is held and its pid is alive with
  its recorded creation time. The CLI and TUI read a **local device token** from
  `<ARCHEUS_HOME>/run/local-token`, created at first start: `0600` on POSIX, where Core refuses
  to start with looser modes; on Windows the default home inherits the user-profile ACL, and a
  home outside the profile gets a warning — it is not isolated the way POSIX `0600` is (DPAPI is
  the upgrade path).
- **Browser/SPA bootstrap (launch code).** A page cannot read that file, and the strict CSP
  forbids injecting a token into inline script. So whoever opens the SPA locally (the desktop
  shell, `archeus core --open`, the legacy GUI's "Open V1" link) first asks Core — authenticated
  with the local token — for a **launch code** (random, single use, 60 s TTL) and opens
  `http://127.0.0.1:<port>/#launch=<code>`. The fragment never reaches the server or its logs.
  The SPA reads it, calls `POST /v1/devices/launch/redeem {code}` (accepted only from loopback
  with a loopback Host header) and receives a device token for a `desktop`/`web` device — with
  the `observe` scope only, because the P3.5b SPA is read-only — stores
  it in IndexedDB, and immediately removes the fragment with `history.replaceState`. A reused or
  expired code gets `401`; the SPA then shows "Open Archeus from the desktop app or run
  `archeus core --open`". Remote devices never use this path; they pair (§5.3). Loopback is **not** trusted by itself (lesson: DNS rebinding):
  Host header allowlist + token, always.
- Fetch-metadata allowlist (`Sec-Fetch-Site` ∈ same-origin/none) for browser requests, as today's
  `gui._fetch_metadata_ok`. Strict CSP: `default-src 'self'; script-src 'self'; connect-src 'self';
  img-src 'self' data:; frame-ancestors 'none'` — the SPA has no inline handlers (unlike today's
  `onclick=` markup, which forced `'unsafe-inline'`).

### 5.2 Remote (PROPOSED, ADR-0010)

Mobile and other machines reach Core through a **user-operated HTTPS tunnel**. Recommended and
documented: **Tailscale Serve** (tailnet-only HTTPS with a real certificate, no public exposure).
Alternatives documented but not automated: Cloudflare Tunnel with Access, a reverse proxy the
user runs.

- HTTPS is required, not optional: a PWA needs a secure context for service workers and install.
- The Host/Origin allowlist gains the paired hostname (e.g. `archeus-pc.tailnet.ts.net`) when the
  user enables remote access; nothing else is accepted.
- The tunnel forwards to loopback, so Core **cannot use source address as identity** — every
  remote request must carry a device token.

### 5.3 Pairing

1. On a local, authenticated desktop session: Control → Devices → "Pair a phone" →
   `POST /v1/devices/pair/start` (local-only route) returns a one-time code (8 chars, 2-minute
   TTL, single use) and a QR code encoding `https://<remote-host>/pair#<code>`.
2. Phone opens the URL, enters a device name and a 6-digit PIN (used later for step-up), calls
   `POST /v1/devices/pair/redeem` → receives a device token (256-bit, shown once, stored in the
   PWA's IndexedDB). Core stores only `sha256(token)`.
3. Default mobile scopes: `observe`, `control`, `approve`. `admin` (policy/resource changes) is
   off by default and can be granted from the desktop.
4. Redeem is rate-limited (5 attempts/min per IP-hash, 20/day per code window).

Tokens are typed (`dev_…` device, `node_…` node, `hook_…` execution hook token) and verified
with `hmac.compare_digest` on bytes. Token prefixes are a namespace of their own, disjoint from
entity-id prefixes: `exe_…` is always an Execution **id**, never a credential (both tables live
in `archeus/core/domain/ids.py`, and a test fails if they overlap).
Execution hook tokens (`hook_…`, delivered as `ARCHEUS_HOOK_TOKEN`) are minted per execution with
scopes report/checkpoint/request_approval and die
with the execution.

### 5.4 Notifications

| Channel | V1 | Notes |
|---|---|---|
| In-app | yes | Attention tray + badge; SSE-driven |
| Desktop | yes | existing `claude_sessions/notify.py` (WinRT toast / osascript / notify-send) |
| ntfy | yes (optional) | stdlib HTTPS POST to a user-chosen ntfy server/topic; message contains no secrets and no content beyond a title + deep link (`https://<remote-host>/a/<approval-id>`). Works on iOS and Android without app-store publication |
| Web Push | DEFERRED | requires ECDSA P-256 (VAPID) signing that the stdlib cannot do; would need an optional extra |

Notification defaults: approvals, blocked missions, mission completed (if it ran > 5 min),
account limits that stop work, drift found. Everything else stays in the feed.

## 6. How clients receive …

| Need | Mechanism |
|---|---|
| Execution updates | `execution.*` events on the global stream (state, coalesced progress); detailed tail from `/executions/{id}/stream` while the inspector is open |
| Mission updates | `mission.*`, `task.*` events → re-query `/v1/missions/{id}` |
| Approval requests | `approval.requested` event → Attention re-query; ntfy/desktop notification per preference |
| Blockers | `mission.state_changed` to BLOCKED + an attention item |
| Notifications | the notifier consumer (desktop/ntfy); clients show in-app from the same events |
| State changes elsewhere | any `*.changed` event whose subject is on screen triggers a re-query |

## 7. Offline and degraded behaviour

- Client offline: the SPA shows the last snapshot with an "offline since …" banner; commands are
  **not** queued offline (an approval sent hours late could be wrong); control verbs are disabled
  with an explanation.
- Core restarting: `503 core_starting` with `Retry-After`; the SPA keeps its cursor and resumes.
- Remote unreachable: the phone shows "Archeus on <PC> is unreachable — work on the PC continues;
  the e-stop on the PC still works."
