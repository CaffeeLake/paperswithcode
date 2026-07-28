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
- **User-confirmed decision:** an idle failed or interrupted chat remains
  shareable. Its snapshot preserves the same bounded partial reasoning, tool
  output, answer text, and user-facing failure/interruption state visible to
  the owner.
- **User-confirmed decision:** Share is disabled throughout active generation.
  The owner must wait for completion or stop the response; once the stop has
  settled, the resulting idle interrupted transcript can be shared. The
  backend also rejects concurrent/stale share attempts with 409.
- **User-confirmed decision:** clicking `Share` immediately publishes or
  refreshes the snapshot and copies its URL. There is no preview or
  confirmation dialog before publication.
- **User-confirmed decision:** the top-right control is always labeled
  `Share`, before and after first publication. Every click refreshes the
  existing snapshot and copies its URL; there is no `Copy link`,
  `Update & copy link`, or snapshot-staleness state.
- The public identifier is a new cryptographically random UUID. Never expose
  the private chat session ID as the share capability.
- **User-confirmed decision:** retain the standard UUID text format in
  `/share/<uuid>` rather than introducing a short slug or alternate encoding.
- **User-confirmed decision:** a share is an unlisted snapshot, not a live
  view. Later messages and edits remain private until the owner explicitly
  publishes another snapshot; the private title is never published.
- **User-confirmed decision:** re-sharing atomically replaces the snapshot
  behind the existing public URL. It does not mint another URL or retain
  separately revocable historical snapshots.
- **User-confirmed decision:** a shared transcript includes the entire
  browser-visible conversation: user messages, reasoning blocks, tool calls
  and results, final answers, and citations. The sandbox limits these traces to
  its public research surface (`Bash`, `Read`, `Grep`, and `WebFetch`, with
  policy and filesystem/network restrictions).
- **User-confirmed boundary:** “entire transcript” means that complete bounded
  browser projection only. Sharing never exposes raw SDK events, system
  prompts, capability data, model routes, sandbox/provider metadata, or the
  owner's Hugging Face identity.
- **User-confirmed decision:** the public page has no owner attribution. It
  does not show or return a Hugging Face username, avatar, or profile link.
- **User-confirmed decision:** the public page does not display, return, or
  snapshot the private chat title. Its page label and document title use the
  generic text `Shared conversation`.
- **User-confirmed decision:** the shared transcript itself is immutable—no
  edit controls, chat history sidebar, follow-up actions, or private source
  session calls—but the page includes a separate fresh-chat composer.
- The fresh composer never continues, forks, or imports context from the shared
  transcript. Submitting hands only the new prompt to the existing `/chat`
  launch flow, which starts a new private chat for a signed-in viewer or
  preserves the draft through the normal sign-in flow.
- **User-confirmed decision:** the public fresh-chat composer has no model
  picker. It queues the prompt without an explicit model so the normal private
  chat flow selects its default and exposes model controls after navigation or
  sign-in.
- **User-confirmed decision:** the shared page uses the existing Papers With
  Code site header and a centered transcript. It has no owner or viewer
  chat-history sidebar.
- **User-confirmed decision:** do not add message timestamps or date
  separators. The snapshot publishes the same transcript metadata visible in
  the owner chat.
- **User-confirmed decision:** viewers do not need to sign in. Possession of the
  unguessable share URL is sufficient, and the public route never redirects to
  OAuth.
- **User-confirmed decision:** V1 has no revoke button or revoke API. A public
  link remains valid until the owner deletes the source chat; that deletion
  cascades through the snapshot and invalidates the URL.
- **User-confirmed decision:** shared conversations are completely unlisted.
  Do not include them in sitemaps, internal search, feeds, galleries, or
  discovery endpoints. Set the shared page's robots metadata to
  `noindex,nofollow`, and serve the public API response with
  `Cache-Control: no-store` so source-chat deletion is not hidden behind a
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
   `Share`; repeat clicks refresh and copy the same link, even when the private
   chat has not changed.
7. On API failure, restore the button and show the existing session-level error
   or a destructive toast. Do not overwrite the last valid snapshot.
8. On clipboard failure, keep the successfully created share, open a fallback
   dialog containing the URL, and let the user select/copy it manually.

The POST is idempotent in link identity but intentionally refreshes snapshot
contents and `updated_at`.

### Open a shared link

1. `/share/:shareId` lazy-loads `SharedChatView`.
2. The view requests `GET /api/v1/chat/shares/{share_id}` without credentials
   or an authentication redirect.
3. It renders the transcript in the normal centered chat width under the
   generic label `Shared conversation`, followed by a fresh-chat composer.
4. Missing, malformed, or source-deleted links render the normal not-found
   state without revealing whether the source session or owner exists.

## Persistence design

Add an idempotent staging migration,
`backend/database/migrations/add_chat_shares.sql`, and register it in the
migration README.

### `chat_shares`

```text
id                 uuid primary key
chat_session_id    uuid not null unique references chat_sessions(id) on delete cascade
snapshot_version   smallint not null default 1
messages           jsonb not null
created_at         timestamptz not null default now()
updated_at         timestamptz not null default now()
```

`id` is the public capability. A unique `chat_session_id` enforces one stable
share URL per chat. The private title is deliberately absent from the public
snapshot schema. `messages` stores an ordered, self-contained array of the
allowlisted `PublicChatMessage` projection described below; it never stores
foreign keys to `chat_messages` or raw private persistence records.
`snapshot_version` identifies that persisted projection contract so a future
format change can be migrated explicitly rather than guessed at read time.

Copying the bounded public projection is intentional. The share is the owner of
the data it publishes, so private edits and any later purge of superseded
`chat_messages` cannot mutate or truncate an existing public snapshot. V1 keeps
only one snapshot per chat, and PostgreSQL TOAST handles a large JSONB value
without requiring a second table or a message-retention pinning system. A later
Share click atomically replaces `messages` with the then-current projection.
The only source relationship retained is the `chat_session_id` foreign key,
which implements the separate product decision that deleting the private chat
invalidates its public URL.

Add a `ChatShare` ORM model and its session relationship in
`backend/models/database.py`. Keep the session-delete cascade explicit and use
the staging owner/application grants established by the other chat migrations.
Add a check constraint requiring `jsonb_typeof(messages) = 'array'`; validate
the full contents through the strict API model at the service boundary. Update
`validate_chat_schema()` so staging readiness fails if the new table or its
required columns are absent.

The consistency pass found that `ChatSessionService.complete_turn()` accepts a
`finish_reason`, and the live UI can display it, but
`ChatMessageRecord` currently discards it. Add a nullable, bounded
`finish_reason` column to `chat_messages` in the same migration, persist the
validated value on completed assistant rows, expose it in authenticated
history, and restore it in `toUiMessages()`. The public projection maps it to
the same user-facing early-stop note. Without this addition, a share created
immediately after a turn could differ from the same chat after reload.

Do not use a deterministic hash of the session ID or username. Generate
the share UUID with `uuid.uuid4()` and do not log full share URLs at normal log
levels.

## Backend design

### API models

In `backend/models/chat.py`, add strict models for:

- `ChatShareSummary`: `share_id`, `public_path`, `created_at`, `updated_at`;
- `ChatShareDetail`: timestamps and public messages, with no private title;
- `PublicChatMessage`: a snapshot-local `id`, `role`, `content`, the complete
  validated browser-display block projection, citation snapshots, and a narrow
  user-facing completion/interruption/failure state. Generate snapshot-local
  IDs while projecting; do not publish source `chat_messages.id` values.

### Service boundary

Put share logic in a focused `ChatShareService` under `backend/services/`
rather than adding public-capability queries to the stream orchestrator.

`create_or_refresh(owner, session_id)` must:

1. lock the owned `ChatSession`;
2. reject a currently leased/busy session with 409;
3. select the same current rows as `get_session()` in sequence order;
4. reject an empty transcript;
5. build and strictly validate the complete allowlisted public projection in
   memory, while the source-session lock still fixes the visible revision;
6. create a share UUID if needed, or retain the existing share UUID;
7. insert the share or replace its `messages`, `snapshot_version`, and
   `updated_at` in one transaction;
8. flush and return the share record.

Do not commit the share write until projection of every message succeeds. If
projection validation or snapshot replacement fails, roll back and leave the
preceding public snapshot intact.

`get_public(share_id)` must query only `chat_shares`, validate
`snapshot_version` and `messages` as the strict persisted public contract, and
return that stored projection without joining to `chat_messages` or rebuilding
it from current private state. `create_or_refresh()` constructs each stored
message as follows:

- completed user rows expose their prompt text;
- failed/interrupted user rows expand exactly as `toUiMessages()` does: one
  public user prompt plus a derived public assistant message containing that
  row's bounded partial `display_blocks` and generic user-facing failure or
  interruption notice;
- assistant rows expose the complete validated `display_blocks` projection,
  including reasoning, tool calls/results, answer blocks, and their bounded
  citation snapshots;
- failed or interrupted turns expose a stable public display state and generic
  user-facing message equivalent to the owner UI, not the internal
  `error_code`;
- omit `followups`, `model`, raw status/error fields, revisions, and all
  owner/session fields;
- normalize restored blocks to an idle historical state: reasoning is
  inactive, completed blocks retain their result, and any tool left `running`
  by an interrupted turn becomes a failed historical block.

Construct this projection server-side from the already bounded and validated UI
fields before persisting it. Revalidate the stored value on read so corrupt or
unsupported snapshot data fails closed rather than leaking unmodeled fields. A
custom caller of the public API must never receive raw SDK entries, provider
metadata, capability material, or other persistence fields merely because the
React view ignores them.

### Routes

Extend `backend/routers/chat.py` with:

```text
POST   /api/v1/chat/sessions/{session_id}/share   authenticated owner
GET    /api/v1/chat/shares/{share_id}             public
```

Keep all chat routes behind the existing `PWC_CHAT_ENABLED` feature mounting.
The public GET must not depend on `require_user`, set `Cache-Control: no-store`,
and return the same generic 404 for a missing or source-deleted share. The POST
response returns a relative `public_path` (`/share/<id>`), leaving origin
selection to the browser.

Accept the public path parameter as a string and parse the UUID inside the
service/adapter so malformed and unknown capabilities both produce the same
generic 404 instead of FastAPI's distinguishable 422 validation response.

### Public edge routing

The production nginx config already serves hashed frontend assets publicly,
but the staging host currently places the SPA, assets, and all `/api/` routes
behind its admin gate. Anonymous shared links therefore require explicit,
reviewed locations in both checked-in nginx templates:

- match only `/share/<uuid>`, serve the current SPA shell with
  `Cache-Control: no-store` and `X-Robots-Tag: noindex, nofollow`;
- proxy only `GET`/`HEAD /api/v1/chat/shares/<uuid>` without browser auth and
  retain the API's `no-store` header;
- on staging, allow hashed `/assets/` files without the admin gate so the public
  share shell can load; this exposes immutable frontend code, not private
  staging data or API access;
- on staging, allow `GET /api/v1/auth/me` through to FastAPI without the nginx
  admin gate so the global `AuthProvider` receives its normal 200/401 response
  instead of following an OAuth redirect;
- keep the owner POST endpoint, `/chat`, every other staging SPA route, and all
  other staging APIs behind their existing authentication boundaries.

Keep the client-side `noindex,nofollow` metadata as defense in depth. The HTTP
`X-Robots-Tag` is the authoritative crawler control because the SPA shell is
otherwise served before React runs. Applying these checked-in nginx changes is
a separate explicit `pwc-nginx` operation; an application deploy alone does
not install them.

## Frontend design

### API client

Extend `frontend/src/lib/chatSessions.ts` with:

- `createOrRefreshShare(sessionId)`;
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
- set the generic document title `Shared conversation` and a temporary
  `robots=noindex,nofollow` meta tag, restoring prior document metadata on
  unmount;
- render the snapshot without invoking `useChat`, opening SSE, listing private
  sessions, or requiring OAuth;
- initialize reasoning and tool blocks as collapsed historical blocks and keep
  their normal owner-view expand/collapse interaction;
- reuse normal user/assistant typography and citation links;
- render the existing `Composer` in fresh-chat mode without `models`,
  `selectedModel`, or `onModelChange`; on submit call
  `queueChatLaunch(prompt)` and navigate to `/chat` so the normal new-chat/auth
  behavior owns the default model, model loading, and SSE;
- do not include any shared message IDs, transcript text, or source session
  identifier in that launch.

Extract a small presentational transcript component only if it materially
reduces duplication between `ChatView` and `SharedChatView`. Do not move
streaming, editing, auto-scroll, or composer state into a generic abstraction.

## Concurrency and failure behavior

- Lock the source session while selecting and projecting its visible messages
  so Share cannot race an edit activation or turn admission.
- The frontend disables Share while busy, but the server remains authoritative
  and returns 409 to stale/custom clients.
- Generate and validate the complete projection before writing it, then replace
  the single `chat_shares.messages` value inside the same database transaction.
  PostgreSQL row-level MVCC means readers see either the old complete JSONB
  snapshot or the new complete JSONB snapshot, never a partial refresh.
- A failed refresh keeps the previous public link and contents intact.
- Private-message deletion or superseded-row purging cannot affect stored share
  contents because there is no share-to-message foreign key. Source-chat
  deletion still cascades to its single `chat_shares` row and invalidates the
  link.
- Never claim clipboard success on rejection. Clipboard failure is recoverable
  without issuing a second POST or rotating the link.
- Treat the public endpoint as capability access: do not vary behavior based on
  whether an anonymous request also carries a valid login cookie.

## Validation

### Backend tests

Add focused tests alongside `backend/tests/test_chat_endpoint.py` or in
`backend/tests/test_chat_shares.py`:

- only the immutable OAuth-subject owner can create or refresh a share;
- POST rejects missing, empty, and busy chats;
- idle failed and interrupted chats can be snapshotted without dropping their
  bounded partial transcript or public display state;
- the first POST generates a UUID and a repeated POST retains it;
- a private rename never appears in the public API or page, and new messages
  leave the stored projection unchanged until POST is called again;
- refresh atomically replaces the complete ordered JSONB projection;
- editing and then purging superseded private rows leaves the previous public
  snapshot byte-for-byte unchanged and readable;
- public GET works without authentication;
- public GET preserves the complete validated browser transcript, including
  reasoning and tool blocks, while excluding raw SDK entries, model routes,
  capabilities, followups, owner identity, and other private persistence data;
- persisted public messages use snapshot-local IDs and expose no source
  `chat_messages.id` values;
- authenticated history and public snapshots preserve the validated
  `finish_reason`/user-facing early-stop note across reloads;
- missing and source-deleted IDs return the same 404;
- deleting a chat cascades to its share, while deleting individual private
  messages does not alter the share;
- public GET sends `Cache-Control: no-store`;
- API models reject unexpected fields.

Extend runtime/deployment schema tests for the new table, required columns,
JSON-array constraint, and migration grants.
Add nginx validation tests proving that only the shared-page GET, its public GET
API, hashed assets, and `/api/v1/auth/me` bypass staging admin auth, and that
the owner POST and all unrelated staging routes remain gated. Assert the
share-page HTTP response carries `X-Robots-Tag: noindex, nofollow`.

### Frontend tests

Add Vitest/Testing Library coverage for:

- Share is absent for a new/empty chat and present for a loaded saved chat;
- it is disabled during streaming and during its own request;
- POST success writes the current-origin URL and shows the exact two-line toast;
- a clipboard rejection opens the manual-copy fallback without creating a
  second link;
- API failure does not show a copied-success message;
- `/share/:shareId` loads anonymously and renders `Shared conversation`,
  prompts, answers, and citations without the private title;
- shared view has no edit action or sidebar, does render collapsible reasoning
  and tool output, and its composer launches a separate empty-context chat;
- submitting the public composer passes only its new prompt into the existing
  `/chat` launch/auth flow and never mutates or imports the shared transcript;
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

1. Add the self-contained `chat_shares` table, ORM relationship, migration
   documentation, and staging readiness validation; persist the currently
   dropped `finish_reason`.
2. Add strict share API models and `ChatShareService`.
3. Add the authenticated create/refresh route and the anonymous public GET
   with server-side projection filtering.
4. Add the narrow public nginx routing and authoritative no-index headers while
   retaining the staging owner-route/API gates.
5. Update the frontend API types and request helpers.
6. Implement the owner top-bar Share flow, clipboard fallback, and toast.
7. Add the anonymous shared-chat route, immutable transcript, and fresh-chat
   composer.
8. Add backend, frontend, and nginx tests, then run the focused validation
   commands.
9. Commit the intended source changes to `main`, push `origin main`, and deploy
   that exact commit to staging following the repository publishing policy.
   Apply the additive staging migration before the new release is made active,
   apply the separately reviewed staging nginx template with `pwc-nginx`, then
   smoke-test the owner flow, an anonymous/incognito shared URL, source-chat
   deletion invalidation, no-index headers, `/health`, `/`,
   `/share/<test-id>`, and the public share API.

## Out of scope for V1

- searchable or browsable galleries of shared chats;
- multiple simultaneous public links for one chat;
- revoking or rotating a public link without deleting the source chat;
- live-updating shares;
- expiry dates, passwords, access analytics, comments, or collaborative edits;
- exposing raw SDK transcripts, provider metadata, or sandbox capabilities
  beyond the bounded browser-visible reasoning and tool projection;
- server-rendered social preview cards for shared conversations;
- copying or forking the shared transcript into another user's private history;
  the public composer starts with empty context.
