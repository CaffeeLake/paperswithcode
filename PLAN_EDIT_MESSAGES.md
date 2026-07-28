# Plan: Edit and Resend Chat Messages

## Goal

Let a user edit any previously sent user message and resend it.

- Editing the first user message starts a new Papers With Code chat session and,
  consequently, a fresh Claude Agent SDK session. The original chat remains
  unchanged.
- Editing any later user message rewinds the current chat to immediately before
  that message, preserves the complete Claude Agent SDK transcript before that
  point, and sends the edited text as the next user message.
- The preserved context must come from the opaque SDK transcript, not from the
  browser projection in `chat_messages.display_blocks`. That is what retains the
  exact ordering and payloads of user messages, assistant messages, thinking
  blocks/signatures, tool calls, and tool results required by models trained
  with interleaved thinking.

This is a destructive rewrite of the current chat only for a non-initial edit:
the edited message, its old assistant response, and every later turn disappear
from the active history. Their projection rows can remain marked
`superseded` for auditability and safe failure recovery.

**Resolved product decision:** non-initial edits rewrite the current chat in
place. They do not create a user-visible branch or a second sidebar entry.
Visible conversation branching may be added as a separate feature later; the
internal SDK fork used to preserve the prefix is an implementation detail, not
a user-facing branch.

**Resolved product decision:** v1 permits editing only while the chat is idle.
Editing during an active assistant generation is deferred to a later feature.
The user must stop the response or let it finish before entering edit mode.

**Resolved product decision:** resending an edit requires no confirmation
dialog, even when later turns will be superseded. While the inline editor is
focused, Enter resends immediately. Any suffix warning is informational and
must not introduce an additional click or confirmation step.

**Resolved product decision:** the inline editor uses chat-style keyboard
controls: Enter resends, Shift+Enter inserts a newline, and Escape cancels.

**Resolved product decision:** the edited text does not need to differ from the
original. Resending unchanged text is a supported regenerate/retry action. Only
empty or whitespace-only text is rejected, and an unchanged resend follows the
same new-chat or in-place-rewrite semantics as a changed resend.

**Resolved product decision:** v1 has no user-visible undo, version history, or
restore-old-response action. Superseded projection rows exist only for internal
consistency/recovery, and the obsolete raw SDK transcript is deleted after the
new fork is safely active. A future branching/history feature must define its
own retention contract.

**Resolved product decision:** completed, failed, and interrupted user turns all
receive the same inline Edit-and-Resend control when the chat is idle. Inline
editing is the primary consistent UI; the existing bottom-composer retry path
remains supported for compatibility.

**Resolved product decision:** inline resending the first user message always
creates a new chat, even if the source turn failed or was interrupted and even
if its text is unchanged. The existing bottom-composer retry is the sole
compatibility path that may retry a failed initial turn in its original chat.

**Resolved product decision:** later-message edits preserve the chat title
exactly. They do not rerun title generation, whether the title was generated,
fallback-derived, or manually supplied. A first-message edit creates a new chat
and therefore generates a new title there.

**Resolved product decision:** edited resends use the model currently selected
in the chat picker, not the model that originally answered the target turn.
This applies to both the new chat created from a first-message edit and an
in-place later-message edit.

**Resolved product decision:** successful fork activation is the history commit
point. Failures before activation leave the old prompt and suffix intact.
Failures or interruptions after activation keep the edited prompt as canonical
and the old suffix superseded; the user retries the edited prompt rather than
having the old history silently restored.

**Resolved product decision:** the inline editor shows a lightweight
informational notice. A later edit with a suffix says that the response and
following messages will be replaced; a first-message edit says that it will
start a new chat. The notice never gates Enter or adds a confirmation step.

**Resolved product decision:** follow the Codex app's hover treatment for the
Edit affordance. On desktop, reveal a compact action row beneath the user
bubble on hover or keyboard focus, with a circular pencil icon button and an
“Edit” tooltip/accessible label. On touch layouts, keep the action reachable
without hover. The supplied screenshot is a visual interaction reference; this
feature does not separately add timestamps or Copy unless those controls are
introduced elsewhere.

**Resolved product decision:** clicking Edit transforms the targeted user
bubble into an inline editor in place. It never moves the message into the
bottom composer, and any existing bottom-composer draft remains untouched.

**Resolved product decision:** when the inline editor opens, focus it
immediately and place the caret at the end of the existing prompt without
selecting the text.

**Resolved product decision:** the inline textarea auto-grows with its content
up to approximately 40% of the chat viewport height, then scrolls internally.
It retains at least the original bubble width and may grow to the normal maximum
user-message width.

**Resolved product decision:** the inline editor has exactly two visible action
buttons labeled `Cancel` and `Send`. Enter invokes Send; the Send button is
disabled only for invalid/empty text or once submission is underway.

**Resolved product decision:** pressing Send immediately removes the target's
old response and every later visible message, then shows the edited prompt and
streaming assistant placeholder. The UI does not wait for transcript-fork
confirmation; it retains a private snapshot solely to restore on a
pre-activation failure.

**Resolved product decision:** every inline edit shows one context-specific
informational note:

- first user message: “Sending will start a new chat.”
- latest user message: “Sending will replace the response.”
- older user message: “Sending will replace the response and all messages after
  it.”

**Resolved product decision:** after an older-message Send truncates the visible
suffix, keep the edited user bubble near the top of the conversation viewport
with the streaming assistant response directly beneath it. Do not blindly jump
to the bottom in a way that hides the edited prompt.

**Resolved product decision:** if a pre-activation fork fails, close the inline
editor, restore/reload the original history, and show the session-level error
“Couldn’t resend this message. Your original conversation was restored.” The
original message remains eligible for another Edit attempt.

## Existing pieces to reuse

The current implementation already has most of the difficult transcript
plumbing:

- `ChatMessageRecord.sdk_resume_boundary_id` records the last SDK transcript
  message immediately before each user prompt.
- `PostgresSDKSessionStore` stores the SDK transcript entries as ordered, opaque
  JSON objects.
- `claude_agent_sdk.fork_session_via_store(...)` copies a transcript through an
  inclusive message UUID, remaps the SDK/session UUIDs, and preserves the
  transcript contents.
- `ChatStreamOrchestrator._prepare_replacement()` already forks a transcript to
  retry the latest failed prompt.
- `replace_message_id` and `prior_revision` already provide an optimistic
  concurrency contract for that failed-prompt retry.

The implementation should generalize this path rather than build a second
history serializer. In particular, do not construct Claude input from
`ChatMessageResponse`, answer text, citations, or display blocks; those are
lossy UI projections.

## Product behavior

### Editing the initial prompt

1. Show an Edit action on the first user bubble for complete, failed, and
   interrupted turns.
2. Transform that bubble in place into a multiline editor containing its
   current text.
3. On resend, make a normal first-turn request with:
   - `session_id: null`
   - a new `client_message_id`
   - the edited message
   - the currently selected model as `initial_model`
4. Optimistically show only the edited user prompt and its streaming response.
5. When `stream_start` returns the new session ID, navigate to that new chat.
6. Leave the original application session, SDK transcript, title, and messages
   untouched and visible in chat history.

This needs no backend edit operation. It deliberately uses the existing
new-session path, which also generates a new title. This rule applies
regardless of source-turn status or whether the submitted text changed.

### Editing a subsequent prompt

1. Show an Edit action on every non-initial user bubble—whether its turn is
   complete, failed, or interrupted—when the session is not busy.
2. On resend, submit the current session ID plus the target message ID and
   revision using the existing `replace_message_id`/`prior_revision` wire
   fields.
3. Optimistically truncate the visible UI at the target message and append the
   edited user message plus a streaming assistant placeholder immediately when
   Send is invoked.
4. On the server, fork the current SDK session through the target row's
   `sdk_resume_boundary_id`.
5. Atomically switch the application session to the fork, supersede the target
   and all active projection rows after it, then run the edited prompt by
   resuming the forked SDK session.
6. Reload the canonical session after the stream settles. If validation or
   transcript preparation fails before activation, restore/reload the old
   visible history. After activation, a generation failure leaves the edited
   prompt visible with its failed/interrupted state.

The active history after success is exactly: every message before the target,
the revised target prompt, and its new assistant response. The old target,
response, and suffix are retained only as superseded persistence records and
must not appear in the chat UI or create another chat.

Always show a short inline notice. Use “Sending will start a new chat.” for the
first message, “Sending will replace the response.” for the latest user
message, and “Sending will replace the response and all messages after it.” for
an older message. This notice is not a confirmation gate: pressing Enter
immediately resends.

## Backend design

### 1. Expand replacement admission

Update `ChatSessionService.begin_turn()` so
`replace_message_id` can identify any current, non-superseded user message, not
only the latest `interrupted` or `error` message.

Validation must happen while the owned session is locked:

- the target belongs to the authenticated user's session;
- the supplied revision still matches;
- the target is a user message and is not superseded;
- the session is not busy and has no degraded transcript; the backend must
  reject an edit while busy even if a stale or custom client bypasses the
  disabled frontend control;
- a general in-place edit is not allowed for sequence 1 (the client must use
  the new-session behavior);
- `sdk_session_id`, `sdk_project_key`, and
  `sdk_resume_boundary_id` exist for a later-message edit;
- normal model, rate, concurrency, message, and storage limits still apply.

Retain the current failed/interrupted retry behavior and public request fields
for compatibility. Rename internal “replacement” helpers to “edit” or “rewind”
only where that makes the broader semantics clearer.

Use a fresh `turn_id` for a general edit, while setting
`supersedes_message_id` to the target and `revision` to
`target.revision + 1`. A fresh turn ID avoids colliding with the partial unique
index for the still-active target while transcript preparation is in progress.
The existing latest-failed retry may keep its current logical-turn behavior if
desired, but using the same safe preparation path for both cases is preferable.

### 2. Make transcript switching failure-safe

Do not mark the old suffix `superseded` before the SDK fork exists. The current
failed-turn path can afford that assumption because it only replaces an
unresolved tail; arbitrary edits must not erase a healthy conversation if
forking fails or the process exits.

Use this preparation/activation sequence:

1. Admit an edit row at a new monotonic sequence with a durable `preparing`
   status, target link, boundary UUID, and turn lease. Exclude `preparing` rows
   from `get_session()` projections.
2. Call `fork_session_via_store()` with the session's current SDK ID,
   SDK project directory, and the target's `sdk_resume_boundary_id`.
3. In one database transaction, lock the application session again and verify
   that the turn lease, source SDK session ID, target revision, and active
   suffix are unchanged.
4. Mark the target and every later active projection row `superseded`, explicitly
   excluding the newly prepared edit row even though its monotonic sequence is
   later.
5. Change the prepared edit row to `generating`, rebind
   `ChatSession.sdk_session_id` to the fork, recompute the active
   `message_count`, and commit.
6. Resume the fork and send the edited prompt through the normal turn runner.
7. Delete the old SDK transcript only after the new binding commits. A failure
   to delete is a cleanup leak, not a reason to corrupt the active chat.

If forking or activation fails, mark/delete the prepared row, clear its lease,
delete any unbound fork, and keep the old suffix and SDK binding active. Extend
expired-lease recovery so a stranded `preparing` row becomes superseded rather
than turning the old chat into an unresolved failed turn. A small cleanup path
should remove unbound fork sessions left by a crash between steps 2 and 5.

After activation, use the normal `fail_turn()` behavior. Do not attempt to
rebind the old SDK session or unsupersede the old suffix when the model,
sandbox, transport, persistence projection, timeout, or client cancellation
fails during generation.

`last_sequence` remains monotonic. `projection_bytes` should continue to count
all retained projection rows, including superseded rows, because they still
consume storage. `transcript_bytes` must reflect only the SDK transcript bound
to the active session; calculate it from the fork during the rebind.

Superseded projection rows must not be treated as durable user-facing version
history. They may be purged later under a bounded retention policy once they
are no longer needed for operational recovery.

### 3. Preserve the exact interleaved transcript

The fork cutoff must be the target user row's
`sdk_resume_boundary_id`, not the target's UI sequence and not the preceding
assistant projection ID. Passing that UUID to
`fork_session_via_store(..., up_to_message_id=...)` produces:

```text
system/session metadata
user turn 1
assistant thinking
assistant tool_use
user tool_result
assistant thinking/answer
...
assistant response immediately before edited prompt
```

The original target prompt and everything after it are intentionally absent.
The normal SDK `resume=<forked session id>` call then appends the edited prompt.
Tool use/result blocks and thinking signatures must remain opaque throughout;
application code should inspect UUID/type fields only for cutoff and storage.

Both `local_mcp` and `modal_cli` runners already resume an SDK session ID. Keep
their directory/project-key choice aligned with the existing replacement code:
the configured agent working directory locally and `/workspace` for Modal.

### 4. Projection and session reads

Update `get_session()` to return only the active lineage:

- exclude `superseded` rows as today;
- exclude `preparing` edit rows;
- order the remaining prefix and replacement by their monotonic sequence.

Because the new edited row is appended at the end, ordering still produces the
desired prefix followed by the edit after the old suffix is superseded. Recount
`message_count` from active user/assistant rows when activating an edit instead
of trying to adjust it with fragile arithmetic.

During preparation, a concurrent session read intentionally returns the old
active lineage and `is_busy: true`; the hidden prepared row becomes visible
only after activation changes it to `generating`.

Do not expose raw SDK transcript entries through the API.

### 5. Titles and model selection

- An initial-message edit creates a new session and should generate a new title
  from the edited prompt.
- A later-message edit keeps the existing title exactly and must not start
  title generation. This includes both generated and manually renamed titles.
- Both first- and later-message resends use the currently selected picker
  model. The later turn reads `ChatSession.selected_model` at admission,
  matching a normal follow-up; it does not copy the target row's old `model`.
  The preserved prefix remains unchanged if the selected model differs.

## Frontend design

### 1. Message controls

Extend `UserMessage` in `frontend/src/components/chat/ChatMessage.tsx` to
receive the message ID, whether it is initial, whether editing is allowed, and
edit/cancel/resend callbacks.

Add a Codex-style hover action row beneath every persisted user bubble,
including failed and interrupted turns. On desktop it appears when the bubble
is hovered or contains keyboard focus. The Edit action is a circular pencil
icon with an `Edit message` accessible label and an “Edit” tooltip; do not put a
persistent text button inside the bubble. On touch/mobile layouts, expose the
action persistently or through an equally direct tap target because hover is
unavailable. The inline editor should:

- replace the selected bubble in place rather than populate the bottom
  composer;
- receive focus immediately with the caret at the end and no automatic
  select-all;
- use an auto-growing textarea, at least as wide as the original bubble and up
  to the normal user-message maximum width;
- cap its height at approximately 40% of the chat viewport and use internal
  scrolling beyond that cap;
- preserve newlines;
- reject empty/whitespace-only input and respect the 8,000-character limit;
- allow submission when the normalized text is unchanged so the user can
  regenerate or retry;
- submit immediately on Enter, without opening a modal or requiring another
  button click;
- insert a newline on Shift+Enter;
- show exactly two visible buttons, `Cancel` and `Send`;
- make Escape and `Cancel` restore the original bubble;
- make Enter and `Send` perform the same resend action;
- remain accessible by keyboard and expose clear button labels.

Disable all edit controls while a response is streaming. Only one bubble may
be edited at a time. Do not make an Edit click implicitly stop generation in
v1; edit-during-generation, whether by automatic cancellation or live rewind,
is explicitly deferred.

### 2. Chat hook API

Refactor `useChat` so normal sends and edits share one streaming implementation,
but expose an explicit edit method such as:

```ts
editAndResend(messageId: string, text: string): boolean
```

The hook should locate the target in `messagesRef` and choose:

- first user message: request `session_id: null`, no replacement fields, and
  reset the optimistic message list to the edited prompt;
- later user message: keep the current session ID, include
  `replace_message_id` and `prior_revision`, and optimistically truncate at the
  target.

Do not infer an arbitrary edit from “latest user message has a non-complete
status.” Preserve that automatic failed/interrupted retry behavior as a
separate case or route it explicitly through the same edit helper.
Specifically, an inline edit of the initial turn must not accidentally take the
legacy in-place failed-turn replacement path.

Keep a snapshot of the pre-edit UI messages through the request. The existing
`stream_start` event proves turn admission but is emitted before SDK fork
activation, so it must not be treated as the edit commit point. On any
same-session edit error or ambiguous disconnect, reload
`GET /chat/sessions/{id}`: it will return the old lineage if activation did not
commit or the edited failed/interrupted lineage if it did. Use the in-memory
snapshot only as an immediate fallback while that canonical reload completes.
Generate a new `client_message_id` for every resend.

When the canonical reload shows that activation did not commit, close edit mode
and surface the session-level message “Couldn’t resend this message. Your
original conversation was restored.” Do not leave a failed assistant placeholder
in the restored history.

### 3. View routing and refresh

Wire the edit state and callbacks in `ChatView`.

- For an initial edit, allow the existing `stream_start` handler to navigate to
  the newly returned session ID; ensure `onSettled` refreshes that new route,
  not the stale source-session ID captured before navigation.
- For a later edit, remain on the current route.
- Clear the bottom-composer draft only for sends initiated from that composer;
  inline edits should not silently discard an unrelated draft.
- After completion, refresh the sidebar and reload the canonical session so
  server IDs, revisions, statuses, and superseded suffixes are reflected.
- After an older-message Send, anchor scrolling to the edited user bubble and
  leave room beneath it for the streaming response. The existing unconditional
  scroll-to-bottom effect in `ChatView` must be adjusted so it does not scroll
  the edited prompt out of view.

Add focused styles beside the existing `.chat-msg-user` and `.chat-bubble`
rules in `frontend/src/styles.css`, including the hover/focus-within reveal,
circular icon treatment, visible focus states, and mobile/touch layout. Use the
provided Codex screenshot as the interaction reference without treating its
timestamp and Copy controls as part of this feature's scope.

## API and persistence work

The external request shape can remain unchanged:

```json
{
  "message": "edited text",
  "session_id": "<current session>",
  "client_message_id": "<new idempotency key>",
  "replace_message_id": "<target user message>",
  "prior_revision": 1
}
```

The Pydantic pairing validation for `replace_message_id` and `prior_revision`
already fits the new behavior.

The unconstrained `chat_messages.status` already supports `preparing`, but
crash-safe fork cleanup requires typed durable fork identity. Add nullable
`prepared_fork_sdk_session_id` and `prepared_fork_sdk_project_key` columns with
a constraint requiring both or neither. Persist the exact fork namespace after
forking, clear it on activation or cleanup, and migrate legacy preparing rows
that encoded `fork:<uuid>` in `error_code`. Readiness validation must require
both columns before activating the release. No transcript schema change is
required: the existing boundary ID and opaque SDK store remain sufficient.

## Tests

### Backend

Add targeted service/API tests covering:

1. Editing the second prompt forks at its stored boundary and sends the edited
   prompt with the fork ID as `resume`.
2. Editing a middle prompt preserves all prefix SDK entries—including fixture
   thinking, `tool_use`, and `tool_result` content—in the same order, while
   excluding the old target and suffix. Assert only the UUID/session fields
   transformed by the SDK fork helper change.
3. Successful activation supersedes the target user row, its assistant row,
   and every later old row, but not the prefix or newly prepared edit row.
4. The session read returns prefix + edited turn and hides `preparing` and
   superseded rows.
5. A fork failure, activation race, or process-recovery path leaves the original
   active history and SDK binding intact.
6. A provider failure or interruption after activation leaves the edited prompt
   canonical and the old suffix superseded.
7. A stale revision, foreign message ID, superseded target, busy session,
   degraded transcript, or missing boundary receives a typed 409/422 response
   without changing history.
8. The existing latest failed/interrupted prompt retry remains supported.
9. Message counts, byte quotas, idempotent client-message replay, title
   behavior, and old-transcript cleanup remain correct.
10. Both local and Modal runners receive the forked resume ID.
11. The resent turn uses the currently selected model rather than the target
    row's historical model.

Use the real `fork_session_via_store` against a small fake/in-memory
`SessionStore` fixture for the transcript-integrity test. This guards against a
future “simplification” that reconstructs history from display blocks.

### Frontend

Add React tests covering:

1. Every eligible user message has a keyboard-accessible Edit action.
   Desktop tests should cover hover/focus reveal; touch-layout tests should
   verify that the action does not depend on hover.
2. Cancel leaves the message and composer draft unchanged.
   Opening the editor focuses it at the end without selecting the prompt.
3. Editing the first message sends a request with `session_id: null` and
   navigates to the returned new session for complete, failed, interrupted, and
   unchanged source prompts.
4. Editing a later message sends the target ID/revision, truncates the
   optimistic suffix, and remains on the same route.
5. Empty edits are rejected and controls are disabled while busy.
6. Enter resends directly and never opens a confirmation dialog, including
   when a suffix will be superseded.
7. Shift+Enter inserts a newline and Escape cancels without resending.
   The visible `Cancel` and `Send` buttons perform those same actions.
8. Unchanged non-empty text can be resent and follows normal edit semantics.
9. The editor shows the appropriate new-chat or suffix-replacement notice
   without changing the Enter behavior.
10. A pre-admission error restores the optimistic snapshot; a server-side edit
    failure or ambiguous disconnect reloads canonical history, without assuming
    that `stream_start` means the SDK fork activated.
11. Existing interrupted-turn “edit and retry” behavior still works.
12. Sending an older edit keeps the edited prompt in view with the response
    streaming beneath it.
13. A pre-activation failure closes edit mode, restores the original lineage,
    removes the optimistic placeholder, and displays the agreed recovery error.

## Validation and rollout

1. Run focused backend chat endpoint/session/SDK-store tests.
2. Run the focused frontend message/hook tests and `npm run lint`.
3. Manually exercise, on a non-production port:
   - first-prompt edit creates a separate sidebar entry;
   - second-prompt edit preserves the complete first turn;
   - middle edit removes all later visible turns;
   - a conversation containing at least one tool call resumes successfully;
   - refresh during preparation and after completion shows a coherent lineage.
4. Add structured logs for edit target, source/fork SDK IDs (IDs only, never
   transcript content), cutoff UUID, activation outcome, and cleanup outcome.
5. After implementation and focused validation, follow the repository publishing
   policy: commit the intended source changes to `main`, push `origin main`, and
   deploy that exact commit to staging. Production remains out of scope unless
   explicitly requested.

## Acceptance criteria

- Editing the first prompt creates a new chat and does not mutate the original.
- Editing any later prompt replaces that turn and all later turns in the active
  chat.
- A later-message edit stays on the same chat route and creates no visible
  branch or sidebar entry.
- Enter resends an edited prompt directly; there is no confirmation modal.
- There is no undo or version-history UI, and successful rewinds do not retain
  the obsolete SDK transcript as an implicit hidden branch.
- Claude receives the exact SDK transcript through the preceding assistant
  response, including interleaved thinking, tool calls, and tool results,
  followed by the edited user prompt.
- No application code reconstructs model history from the UI projection.
- Fork/preparation failures cannot erase or hide the previously healthy chat.
- Edit controls are unavailable while generating, and the backend rejects a
  concurrent edit without cancelling or altering the active turn.
- Editing works for both local and Modal execution backends, survives refresh,
  is concurrency-safe, and preserves the existing failed-turn retry contract.
