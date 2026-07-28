# Plan: Public Chat Share Links

## Goal

Add a `Share` button to the right side of the saved-chat top bar. One click
creates or refreshes an unlisted public snapshot, copies its URL to the
clipboard, and shows:

> Public link copied to your clipboard
>
> Anyone with this link can see this conversation.

The public URL uses the current site origin:

```text
https://paperswithcode.co/share/<share-id>
```

Staging therefore produces a staging URL instead of accidentally publishing a
production link.

## Resolved product and privacy decisions

- Sharing is available only for an authenticated user's persisted, non-empty,
  idle chat. Do not show it on `/chat` before the first turn has received a
  session ID, and disable it while that chat is loading or generating.
- The public identifier is a new cryptographically random UUID. Never expose
  the private chat session ID as the share capability.
- A share is an unlisted snapshot, not a live view. Later messages, edits, and
  title changes remain private until the owner clicks `Share` again.
- Re-sharing refreshes the existing snapshot and reuses its URL. This avoids
  creating a pile of links while still making publication an explicit action.
- A shared transcript contains user messages, final assistant answer blocks,
  and the citation snapshots needed to render those answers. It does **not**
  expose reasoning blocks, tool names, tool arguments, tool output, model
  routes, SDK transcript data, internal errors, or the owner's Hugging Face
  identity.
- Public pages are read-only: no composer, model picker, edit controls, chat
  history sidebar, follow-up chips, or private session API calls.
- A share can be revoked. Add `Unshare` to the active chat's action menu once a
  public link exists. Revocation immediately makes the URL return 404.
- Deleting the source chat also deletes its share and invalidates the public
  link.
- Public links are deliberately unlisted: do not add them to sitemaps, set the
  shared page's robots metadata to `noindex,nofollow`, and serve the public API
  response with `Cache-Control: no-store` so revocation is not hidden behind a
  browser or CDN cache.
- Do not show the success toast until clipboard writing succeeds. If the
  Clipboard API is unavailable or denied, show the URL in a small copyable
  fallback dialog and report that it could not be copied automatically.

## Existing pieces to reuse

- `ChatSessionService._owned()` and `get_session()` already enforce immutable
  OAuth-subject ownership and define the visible projection by excluding
  `superseded` and `preparing` messages.
- `ChatMessageResponse`, `ChatSessionDetail`, and
  `frontend/src/lib/chatSessions.ts` already define most of the durable
  browser projection.
- `UserMessage`, `AssistantMessage`, `ChatMarkdown`, and citation snapshots
  already render persisted chats. Extract only enough transcript layout/state
  to reuse these renderers; do not duplicate the Markdown and citation logic.
- `ChatView` already has the right-aligned space in `.chat-topbar`, loading and
  busy state, session menus, and the current session ID.
- The app already mounts the Radix toast system through `<Toaster />`. Use
  `useToast()` and add an intentional top-center chat-share presentation rather
  than building a second notification framework.
- `App.tsx` already lazy-loads route views and places static routes before the
  top-level organization catch-all.

## User flow

### Create or refresh a share

1. The owner opens a saved chat.
2. The top bar shows a compact share icon plus `Share` at the far right.
3. Clicking it disables the button and sends
   `POST /api/v1/chat/sessions/{session_id}/share`.
4. The backend locks the owned session, rejects an active generation, selects
   its current visible messages, creates or refreshes the snapshot, and returns
   `{ share_id, public_path, updated_at }`.
5. The browser constructs
   `new URL(public_path, window.location.origin).toString()` and calls
   `navigator.clipboard.writeText(url)`.
6. On success, show the short-lived top-center toast. Keep the button labeled
   `Share`; repeat clicks refresh and copy the same link.
7. On API failure, restore the button and show the existing session-level error
   or a destructive toast. Do not overwrite or revoke the last valid snapshot.
8. On clipboard failure, keep the successfully created share, open a fallback
   dialog containing the URL, and let the user select/copy it manually.

The POST is idempotent in link identity but intentionally refreshes snapshot
contents and `updated_at`.

### Open a shared link

1. `/share/:shareId` lazy-loads `SharedChatView`.
2. The view requests `GET /api/v1/chat/shares/{share_id}` without credentials
   or an authentication redirect.
3. It renders the snapshotted title and transcript in the normal centered chat
   width, with a small “Shared conversation” label and a link to start a new
   Papers With Code chat.
4. Missing, malformed, revoked, or deleted links render the normal not-found
   state without revealing whether the source session or owner exists.

### Revoke

1. Once the active session reports a share ID, its context menu includes
   `Unshare`.
2. Confirm with: “Remove this public link? Anyone with the link will lose
   access.”
3. `DELETE /api/v1/chat/sessions/{session_id}/share` verifies ownership, deletes
   the share snapshot, and returns 204.
4. Clear the session's local share state and show “Public link removed.”

## Persistence design

Add an idempotent staging migration,
`backend/database/migrations/add_chat_shares.sql`, and register it in the
migration README.

### `chat_shares`

```text
id                 uuid primary key
chat_session_id    uuid not null unique references chat_sessions(id) on delete cascade
title              varchar(80) not null
created_at         timestamptz not null default now()
updated_at         timestamptz not null default now()
```

`id` is the public capability. A unique `chat_session_id` enforces one stable
share URL per chat. The title is copied into this row so a later private rename
does not mutate the snapshot.

### `chat_share_messages`

```text
share_id           uuid not null references chat_shares(id) on delete cascade
position           integer not null
message_id         uuid not null references chat_messages(id) on delete cascade
primary key (share_id, position)
unique (share_id, message_id)
```

The ordered message-ID manifest freezes the visible revision without copying up
to 25 MB of JSON projection data per share. Existing edit behavior retains
superseded projection rows, so a snapshot remains renderable after the private
chat is edited. A later Share click transactionally replaces this manifest
with the then-current visible message IDs.

Add `ChatShare` and `ChatShareMessage` ORM models and relationships in
`backend/models/database.py`. Keep cascade behavior explicit and use the
staging owner/application grants established by the other chat migrations.
Update `validate_chat_schema()` so staging readiness fails if either new table
is absent.

Do not use a deterministic hash of the session ID, username, or title. Generate
the share UUID with `uuid.uuid4()` and do not log full share URLs at normal log
levels.

## Backend design

### API models

In `backend/models/chat.py`, add strict models for:

- `ChatShareSummary`: `share_id`, `public_path`, `created_at`, `updated_at`;
- `ChatShareDetail`: snapshotted `title`, timestamps, and public messages;
- `PublicChatMessage`: only `id`, `role`, `content`, filtered answer blocks,
  and citation snapshots.

Add `share_id: UUID | None` to the authenticated session summary/detail so the
owner UI can expose `Unshare`. Do not include that field in the public response
under a misleading private-session name.

### Service boundary

Put share logic in a focused `ChatShareService` under `backend/services/`
rather than adding public-capability queries to the stream orchestrator.

`create_or_refresh(owner, session_id)` must:

1. lock the owned `ChatSession`;
2. reject a currently leased/busy session with 409;
3. select the same current rows as `get_session()` in sequence order;
4. reject an empty transcript;
5. create a share UUID if needed, or retain the existing share UUID;
6. update the title snapshot;
7. replace the ordered manifest in one transaction;
8. flush and return the share record.

If manifest replacement fails, roll back and leave the preceding public
snapshot intact.

`get_public(share_id)` must query only through `chat_shares`, load manifest
rows in `position` order, and build an allowlisted public projection:

- user rows expose only their prompt text;
- assistant rows expose only `kind == "answer"` display blocks and their
  bounded citation snapshots;
- omit reasoning/tool blocks even if they are closed in the owner UI;
- omit `followups`, `model`, `error_code`, revisions, status internals, and all
  owner/session fields;
- normalize restored answer blocks to `done: true`.

Do the filtering server-side. A custom caller of the public API must never
receive private blocks merely because the React view hides them.

`revoke(owner, session_id)` locks the owned session, deletes its share, and is
idempotent (204 whether or not a share currently exists).

### Routes

Extend `backend/routers/chat.py` with:

```text
POST   /api/v1/chat/sessions/{session_id}/share   authenticated owner
DELETE /api/v1/chat/sessions/{session_id}/share   authenticated owner
GET    /api/v1/chat/shares/{share_id}             public
```

Keep all chat routes behind the existing `PWC_CHAT_ENABLED` feature mounting.
The public GET must not depend on `require_user`, set `Cache-Control: no-store`,
and return the same generic 404 for a missing/revoked share. The POST response
returns a relative `public_path` (`/share/<id>`), leaving origin selection to
the browser.

When returning authenticated session summaries, fetch share IDs without an
N+1 query. Use a relationship eager load or a small outer join in the session
service; do not query once per sidebar row.

## Frontend design

### API client

Extend `frontend/src/lib/chatSessions.ts` with:

- `share_id: string | null` on authenticated session types;
- `createOrRefreshShare(sessionId)`;
- `revokeShare(sessionId)`;
- a separate public request helper and `getSharedChat(shareId)`.

The public helper should omit `credentials: "include"` to make its anonymous
contract obvious. Reuse `toUiMessages()` only after adapting it to accept the
narrow public type without inventing missing private status fields; otherwise
add a small `publicShareToUiMessages()` converter.

### Owner view

In `frontend/src/views/ChatView.tsx`:

- place the `Share` control after `.chat-topbar-title`;
- show it only when the route has a loaded, persisted, non-empty session;
- disable it while the chat is busy or a share request is in flight;
- use an existing Lucide share icon or add a matching icon to
  `components/chat/icons.tsx`;
- update the active session's `share_id` from POST/DELETE results;
- add the conditional `Unshare` context-menu action;
- use `useToast()` for success/error feedback;
- keep API errors separate from clipboard errors so an automatic-copy failure
  does not imply the public link was not created.

Add focused styles in `frontend/src/styles.css` for the top-bar button, loading
state, mobile icon-only treatment if the title becomes cramped, the top-center
share toast, and the clipboard fallback dialog. Preserve keyboard focus rings
and use an `aria-label` when the text label is visually hidden.

### Public view

Add and lazy-load `frontend/src/views/SharedChatView.tsx`, then register
`/share/:shareId` in `App.tsx` before `/:orgSlug`.

The shared view should:

- have explicit loading, not-found, and retryable network-error states;
- set a useful document title and a temporary `robots=noindex,nofollow` meta
  tag, restoring prior document metadata on unmount;
- render the snapshot without invoking `useChat`, opening SSE, listing private
  sessions, or requiring OAuth;
- initialize collapsible state locally for the remaining answer renderer (the
  public payload will contain no tool/reasoning blocks);
- reuse normal user/assistant typography and citation links;
- offer a restrained “Start a new chat” link to `/chat`, subject to the existing
  chat feature flag.

Extract a small presentational transcript component only if it materially
reduces duplication between `ChatView` and `SharedChatView`. Do not move
streaming, editing, auto-scroll, or composer state into a generic abstraction.

## Concurrency and failure behavior

- Lock the source session while taking the message manifest so Share cannot
  race a title update, edit activation, or turn admission.
- The frontend disables Share while busy, but the server remains authoritative
  and returns 409 to stale/custom clients.
- Generate the new snapshot inside one database transaction. Readers see
  either the old complete manifest or the new complete manifest, never a
  partially refreshed transcript.
- A failed refresh keeps the previous public link and contents intact.
- Revocation and source-chat deletion rely on database cascades and must not
  leave orphan manifest rows.
- Never claim clipboard success on rejection. Clipboard failure is recoverable
  without issuing a second POST or rotating the link.
- Treat the public endpoint as capability access: do not vary behavior based on
  whether an anonymous request also carries a valid login cookie.

## Validation

### Backend tests

Add focused tests alongside `backend/tests/test_chat_endpoint.py` or in
`backend/tests/test_chat_shares.py`:

- only the immutable OAuth-subject owner can create, refresh, or revoke a share;
- POST rejects missing, empty, and busy chats;
- the first POST generates a UUID and a repeated POST retains it;
- the snapshot title and manifest remain unchanged after private rename/new
  messages until POST is called again;
- refresh atomically replaces the manifest in sequence order;
- edited/superseded rows referenced by an older snapshot remain readable;
- public GET works without authentication;
- public GET excludes reasoning, tool args/output, model fields, followups, and
  owner identity while preserving answer text and citations;
- missing and revoked IDs return the same 404;
- DELETE is idempotent, and deleting a chat cascades through both share tables;
- public GET sends `Cache-Control: no-store`;
- API models reject unexpected fields.

Extend runtime/deployment schema tests for both new tables and migration grants.

### Frontend tests

Add Vitest/Testing Library coverage for:

- Share is absent for a new/empty chat and present for a loaded saved chat;
- it is disabled during streaming and during its own request;
- POST success writes the current-origin URL and shows the exact two-line toast;
- a clipboard rejection opens the manual-copy fallback without creating a
  second link;
- API failure does not show a copied-success message;
- Unshare confirms, calls DELETE, and removes local shared state;
- `/share/:shareId` loads anonymously and renders title, prompts, answers, and
  citations;
- shared view has no composer, edit action, sidebar, reasoning, or tool output;
- missing shares render a non-enumerating not-found state;
- the route wins over the organization catch-all.

Run targeted checks:

```bash
uv run --env-file backend/keys.env pytest backend/tests/test_chat_shares.py
cd frontend && npm run lint
cd frontend && npm test -- --run <share-test-files>
```

Do not run `npm run build` as a routine validation step.

## Implementation sequence

1. Add the two tables, ORM relationships, migration documentation, and staging
   readiness validation.
2. Add strict share API models and `ChatShareService`.
3. Add authenticated create/revoke routes and the anonymous public GET with
   server-side projection filtering.
4. Extend authenticated session responses with `share_id` and update the
   frontend API types.
5. Implement the owner top-bar Share flow, clipboard fallback, toast, and
   Unshare action.
6. Add the anonymous shared-chat route and read-only transcript view.
7. Add backend and frontend tests, then run the focused validation commands.
8. Commit the intended source changes to `main`, push `origin main`, and deploy
   that exact commit to staging following the repository publishing policy.
   Apply the additive staging migration before the new release is made active,
   then smoke-test the owner flow, an anonymous/incognito shared URL,
   revocation, `/health`, `/`, `/share/<test-id>`, and the public share API.

## Out of scope for V1

- searchable or browsable galleries of shared chats;
- multiple simultaneous public links for one chat;
- live-updating shares;
- expiry dates, passwords, access analytics, comments, or collaborative edits;
- exposing chain-of-thought, tool traces, or raw SDK transcripts;
- server-rendered social preview cards for shared conversations;
- copying or forking a public chat into another user's private history.
