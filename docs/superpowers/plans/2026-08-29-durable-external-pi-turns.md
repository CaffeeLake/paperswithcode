# Durable External Pi Turns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make externally hosted Pi turns survive browser and transport disconnects, fence every privileged operation to the current durable turn claim, execute Bash exactly once across ambiguous transport failures, and retain executor workspaces per chat session so staging can admit 32 and then 100 simultaneous chats without one full agent sandbox per user.

**Architecture:** Keep the Pi harness outside the sandbox. A database-backed detached-turn coordinator owns each model run independently of an SSE subscriber, journals bounded events, and lets any API process resume by sequence. The external Pi worker retains an in-memory run across WebSocket reconnects, while the gateway validates both worker generation and turn lease generation before every privileged request. Bash is lazy: the first tool call acquires a retained executor-only sandbox, and ambiguous executor responses reattach to the same operation identity instead of executing again.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/PostgreSQL, asyncio, TypeScript/Node.js, React/Vite, Vitest, pytest, Modal executor sandboxes, systemd external Pi workers, Locust.

**Spec:** `docs/superpowers/specs/2026-08-29-durable-external-pi-turns-design.md`

## Global Constraints

- Preserve the existing sandbox-Pi path; the new fencing contract is required only for external Pi capabilities.
- Do not introduce Redis, a request queue, model replay after ambiguous failure, or snapshot-based persistence.
- Preserve one simultaneous active chat turn per user and immediate admission semantics.
- Keep the public chat protocol backward compatible while adding SSE `id:` cursors and `Last-Event-ID` resume.
- Bound journal frames to 256 KiB, journal storage to 8 MiB or 4,096 events per turn, and external-worker replay storage to the same limits.
- Delete transient event chunks only after the canonical terminal assistant message and terminal turn-job state are durable.
- Never retry an ambiguous Bash operation with a new execution ID.
- Keep chat admission disabled during migrations and intermediate staging releases.
- Chat-related commits deploy only to staging until the user explicitly authorizes production.
- Use `uv run --env-file backend/keys.env` followed by the command shown in each task for Python tests and repository commands.
- Do not run `npm run build` as routine validation; use focused Vitest, `npm run typecheck`, and `npm run lint`.

---

### Task 1: Add the bounded durable turn-event journal

**Files:**

- Create: `backend/database/migrations/add_chat_turn_event_chunks.sql`
- Modify: `backend/models/database.py`
- Create: `backend/services/chat_turn_event_repository.py`
- Create: `backend/tests/test_chat_turn_event_repository.py`

**Consumes:** `ChatTurnJob`, `TurnLeaseClaim`, the existing SQLAlchemy session/transaction pattern.

**Produces:** monotonic durable event cursors and bounded replay APIs usable by detached coordinators in every backend process.

- [ ] Write PostgreSQL repository tests proving that two appends under one live claim receive contiguous sequence numbers, stale lease generations are rejected, reads begin strictly after the supplied cursor, limits are enforced before mutation, and terminal cleanup deletes chunks without deleting the turn job.

  ```python
  first = repository.append(db, claim=claim, events=[event("delta", {"text": "a"})], now=now)
  second = repository.append(db, claim=claim, events=[event("delta", {"text": "b"})], now=now)
  assert [frame.sequence for frame in (*first, *second)] == [1, 2]
  assert repository.read_after(db, turn_id=claim.turn_id, after_sequence=1, limit=10) == second
  ```

- [ ] Run the new test and confirm it fails because the table and repository do not exist:

  `uv run --env-file backend/keys.env pytest -q backend/tests/test_chat_turn_event_repository.py`

- [ ] Add `event_sequence` and `event_bytes` non-null integer counters with server default `0` to `chat_turn_jobs`, plus `chat_turn_event_chunks` with `id`, `turn_id`, `first_sequence`, `last_sequence`, `events`, `payload_bytes`, and `created_at`. Add a unique constraint on `(turn_id, first_sequence)` and an index on `(turn_id, last_sequence)`.

  ```sql
  CREATE TABLE chat_turn_event_chunks (
      id BIGSERIAL PRIMARY KEY,
      turn_id UUID NOT NULL REFERENCES chat_turn_jobs(turn_id) ON DELETE CASCADE,
      first_sequence INTEGER NOT NULL,
      last_sequence INTEGER NOT NULL,
      events JSONB NOT NULL,
      payload_bytes INTEGER NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CONSTRAINT uq_chat_turn_event_chunk_start UNIQUE (turn_id, first_sequence),
      CONSTRAINT ck_chat_turn_event_chunk_range CHECK (last_sequence >= first_sequence)
  );
  ```

- [ ] Implement immutable journal contracts and canonical compact JSON sizing. Lock the job row during append, call `ChatTurnJobRepository.require_live_claim`, assign cursors, and update both counters in the same transaction.

  ```python
  @dataclass(frozen=True)
  class JournalFrame:
      sequence: int
      event: str
      payload: dict[str, object]

  class TurnEventJournal:
      MAX_FRAME_BYTES = 256 * 1024
      MAX_TURN_BYTES = 8 * 1024 * 1024
      MAX_TURN_EVENTS = 4_096
  ```

  The exact append signature is `append(db: Session, *, claim: TurnLeaseClaim, events: Sequence[UnsequencedJournalEvent], now: datetime) -> Sequence[JournalFrame]`; `read_after` and `delete_terminal` use the same explicit `Session` transaction boundary.

- [ ] Represent overflow as `JournalLimitExceeded(code="event_journal_exhausted")`; ensure no partial chunk or counter update is committed when one frame or the turn total exceeds a limit.

- [ ] Run the focused test plus the existing job repository tests:

  `uv run --env-file backend/keys.env pytest -q backend/tests/test_chat_turn_event_repository.py backend/tests/test_chat_turn_job_repository.py`

- [ ] Run Ruff on the touched Python files, inspect the migration/model parity, then commit:

  `git commit -m "Add durable chat turn event journal"`

---

### Task 2: Detach turn execution from SSE subscribers

**Files:**

- Create: `backend/services/chat_detached_turn_service.py`
- Modify: `backend/services/chat_live_stream_service.py`
- Create: `backend/tests/test_chat_detached_turn_service.py`
- Modify: `backend/tests/test_chat_live_stream_service.py`

**Consumes:** `ChatStreamOrchestrator`, `TurnEventJournal`, `ChatTurnJobRepository`, and the current in-process live stream registry.

**Produces:** one strongly owned source task per local turn plus cross-process durable replay/tailing by cursor.

- [ ] Write tests for: subscriber cancellation does not cancel the source; two subscribers see identical ordered frames; a coordinator with no local source replays and tails the database journal; only the live turn claim may append; journal overflow produces one terminal failure; an admitted job that is never leased becomes `interrupted` with `dispatch_failed`.

  ```python
  stream = await coordinator.start(turn=turn, source=source())
  first = coordinator.subscribe(turn_id=turn.turn_id, after_sequence=0)
  await anext(first)
  await first.aclose()
  assert not stream.source_task.cancelled()
  assert [frame.sequence async for frame in coordinator.subscribe(
      turn_id=turn.turn_id, after_sequence=0
  )] == [1, 2, 3]
  ```

- [ ] Run the tests and confirm they fail at the missing service:

  `uv run --env-file backend/keys.env pytest -q backend/tests/test_chat_detached_turn_service.py backend/tests/test_chat_live_stream_service.py`

- [ ] Implement `DetachedTurnCoordinator.start` so it holds a strong task reference, consumes the orchestrator exactly once, persists each event before notifying local subscribers, and shields the source task from subscriber cancellation.

  ```python
  async def _pump(self, handle: DetachedTurnHandle) -> None:
      async for event in handle.source:
          frames = await self._transaction(
              lambda db: self._journal.append(
                  db, claim=handle.claim, events=(event,), now=self._clock()
              )
          )
          await handle.publish(frames)
  ```

- [ ] Implement `subscribe(turn_id, after_sequence)` as a journal-first loop. Use an in-process `asyncio.Condition` only to reduce polling latency; re-read the job and journal after every wake so another API process can serve the reconnect.

- [ ] Keep `LiveChatStreamRegistry` as the compatibility facade and delegate durable-dispatch streams to the coordinator. Preserve the old in-memory behavior when `chat_durable_turn_dispatch_enabled` is false.

- [ ] Ensure source exceptions produce a bounded failure event, canonical failure persistence, and terminal job state. Never start a second source after lease expiry or an ambiguous worker loss.

- [ ] Run focused regressions and Ruff:

  `uv run --env-file backend/keys.env pytest -q backend/tests/test_chat_detached_turn_service.py backend/tests/test_chat_live_stream_service.py backend/tests/test_chat_durable_stop_expiry.py`

- [ ] Commit:

  `git commit -m "Detach durable chat turns from SSE subscribers"`

---

### Task 3: Make chat admission and SSE resume idempotent

**Files:**

- Modify: `backend/routers/chat.py`
- Modify: `backend/services/chat_session_service.py`
- Modify: `backend/services/chat_stream_service.py`
- Modify: `backend/tests/test_chat_stream_endpoint.py`
- Modify: `backend/tests/test_chat_durable_admission_bridge.py`
- Modify: `backend/tests/test_chat_local_turn_lease.py`

**Consumes:** detached coordinator subscriptions, durable job identity, `client_message_id`, and the existing POST/GET stream endpoints.

**Produces:** idempotent attach-to-active-turn behavior and SSE frames with resumable IDs.

- [ ] Add endpoint tests proving: every non-comment SSE event contains `id: <sequence>`; GET resume honors `Last-Event-ID`; reconnect emits only later frames; a duplicate POST with the same session and `client_message_id` attaches to the existing turn; it does not persist another user message, mint another capability, or invoke another model source; a different active message remains rejected.

  ```python
  resumed = client.get(
      f"/api/v1/chat/sessions/{session_id}/stream",
      headers={"Last-Event-ID": "7", "Accept": "text/event-stream"},
  )
  assert "id: 7\n" not in resumed.text
  assert "id: 8\n" in resumed.text
  ```

- [ ] Run the focused endpoint/admission tests and observe the missing cursor/idempotency failures.

  `uv run --env-file backend/keys.env pytest -q backend/tests/test_chat_stream_endpoint.py backend/tests/test_chat_durable_admission_bridge.py backend/tests/test_chat_local_turn_lease.py`

- [ ] Add one serializer for sequenced SSE frames. Preserve existing `event:` and JSON `data:` lines exactly, adding only `id:`.

  ```python
  def encode_journal_frame(frame: JournalFrame) -> bytes:
      data = json.dumps(frame.payload, separators=(",", ":"), ensure_ascii=False)
      return f"id: {frame.sequence}\nevent: {frame.event}\ndata: {data}\n\n".encode()
  ```

- [ ] Parse `Last-Event-ID` as a non-negative integer with `0` default and a typed `400 chat_stream_cursor_invalid` error for malformed values. Subscribe through the detached coordinator even when the source belongs to another API process.

- [ ] Move active-turn lookup ahead of message creation in durable admission. Return an attach result only when session, authenticated owner, and `client_message_id` all match the active turn; otherwise retain the one-active-turn conflict.

- [ ] Preserve current non-durable behavior behind the existing flag and verify anonymous/authenticated ownership checks remain unchanged.

- [ ] Run the focused suite and Ruff, then commit:

  `git commit -m "Make durable chat streams resumable"`

---

### Task 4: Carry the SSE cursor through the browser reconnect path

**Files:**

- Modify: `frontend/src/lib/chat.ts`
- Modify: `frontend/src/lib/api/chat.ts`
- Modify: `frontend/src/hooks/useChat.ts`
- Modify: `frontend/src/lib/chat.test.ts`
- Modify: `frontend/src/hooks/useChat.test.ts`

**Consumes:** SSE `id:` lines, the existing session resume endpoint, and the existing stable client message identity.

**Produces:** automatic same-turn reconnect with `Last-Event-ID`, without a second user message or provider request.

- [ ] Write Vitest cases for parsing `id:` before `event/data`, ignoring duplicate or older cursors, reconnecting after a transport-only failure with the latest cursor, retaining the same session and client message IDs, and stopping retry on a canonical terminal event or typed non-retryable error.

  ```ts
  expect(requests[1]).toMatchObject({
    method: "GET",
    headers: expect.objectContaining({ "Last-Event-ID": "12" }),
  });
  expect(postedClientMessageIds).toEqual([clientMessageId]);
  ```

- [ ] Run the focused tests and confirm the cursor assertions fail:

  `cd frontend && npm test -- --run src/lib/chat.test.ts src/hooks/useChat.test.ts`

- [ ] Extend the internal parsed frame type with `sequence: number | null`; parse `id:` without exposing it in the public chat event payload.

  ```ts
  type ParsedSSEFrame = {
    sequence: number | null;
    event: string;
    data: string;
  };
  ```

- [ ] Let `resumeChatOverSSE` accept `afterSequence` and send `Last-Event-ID` when it is greater than zero. Do not put cursors in query strings.

- [ ] In `useChat`, reconnect only transport interruptions for the same active turn with delays of 250 ms, 500 ms, and 1,000 ms. Reuse the original `client_message_id`; after three failed reconnects expose the existing retry UI without creating a new turn.

- [ ] Run focused tests, `npm run typecheck`, and `npm run lint`. Do not run the build.

- [ ] Commit:

  `git commit -m "Resume browser chat streams by event cursor"`

---

### Task 5: Bind external Pi transport to worker and turn generations

**Files:**

- Modify: `backend/chat_sandbox_worker/pi_worker/src/turn_protocol.ts`
- Modify: `backend/chat_sandbox_worker/pi_worker/src/external_server.ts`
- Modify: `backend/services/chat_external_pi_turn_runner.py`
- Modify: `backend/services/chat_external_worker_registry.py`
- Modify: `backend/tests/test_chat_external_pi_turn_runner.py`
- Modify: `backend/tests/test_chat_external_worker_registry.py`
- Modify: `backend/chat_sandbox_worker/pi_worker/src/external_server.test.ts`

**Consumes:** `ExternalWorkerClaim` and `TurnLeaseClaim`.

**Produces:** an authenticated external transport whose worker generation and durable turn lease are explicit on initial run and reconnect.

- [ ] Add Python and Node tests proving the WebSocket upgrade rejects missing/stale `X-PWC-Worker-Generation`, the initial `run_turn` frame carries all turn-claim fields, an attach frame must match the same claim, and the selected registry row is online with the exact instance/generation immediately before connection.

  ```ts
  expect(runFrame.turnClaim).toEqual({
    turnId: "turn-1",
    workerId: "api-1",
    workerGeneration: 4,
    leaseGeneration: 9,
  });
  ```

- [ ] Run focused Python and worker tests and record the expected failures.

  `uv run --env-file backend/keys.env pytest -q backend/tests/test_chat_external_pi_turn_runner.py backend/tests/test_chat_external_worker_registry.py`

  `cd backend/chat_sandbox_worker/pi_worker && npm test -- --run src/external_server.test.ts`

- [ ] Add `TurnClaimFrame` with `turnId`, `workerId`, `workerGeneration`, and `leaseGeneration` to the protocol. Require it for both `run_turn` and the later `attach_turn` message.

- [ ] Send the selected external worker generation as an upgrade header. In the Node server, compare it with the process generation established by `/v1/claim`; reject before accepting a run when they differ.

- [ ] Add a selector method that returns a validated `ExternalWorkerClaim`, not a bare URL. Revalidate the claim with `ChatExternalWorkerRegistry.require_claim` before opening the socket.

- [ ] Keep the worker bearer token and current loopback/TLS rules intact. Redact all claim headers from logs except logical IDs and numeric generations.

- [ ] Run focused suites plus TypeScript typechecking and commit:

  `git commit -m "Fence external Pi transport generations"`

---

### Task 6: Enforce the durable turn fence at every gateway entry point

**Files:**

- Modify: `backend/services/chat_capability_service.py`
- Modify: `backend/services/chat_external_pi_turn_runner.py`
- Modify: `backend/chat_gateway_app.py`
- Modify: `backend/tests/test_chat_capability_service.py`
- Modify: `backend/tests/test_chat_gateway_app.py`
- Modify: `backend/tests/test_chat_sandbox_contracts.py`

**Consumes:** external-turn capability scope and the three turn-fence headers.

**Produces:** central rejection of stale/absent external turn claims before catalog, provider, session-store, web, artifact, or executor-adjacent gateway work.

- [ ] Write parameterized gateway tests across paper catalog, HF catalog, session store, web search/fetch, OpenAI responses, Anthropic messages, and artifacts. For an `external_turn` capability, require all headers and reject stale worker/lease generations before the endpoint dependency executes. Prove legacy sandbox capabilities remain accepted without the new headers.

  ```python
  headers = {
      "X-PWC-Turn-Worker-ID": claim.worker_id,
      "X-PWC-Turn-Worker-Generation": str(claim.worker_generation),
      "X-PWC-Turn-Lease-Generation": str(claim.lease_generation),
  }
  assert gateway_call("/v1/responses", headers=headers).status_code == 200
  assert gateway_call("/v1/responses", headers={}).status_code == 403
  ```

- [ ] Run the focused gateway tests and confirm external fencing is absent.

- [ ] Add `external_turn` to the capability scope enum/allowlist. Mint it only in `ChatExternalPiTurnRunner`; do not add it to sandbox-Pi capabilities.

- [ ] Extend the central `_scope()` dependency to parse the three headers only when `external_turn` is present and call `ChatTurnJobRepository.require_live_claim` in a transaction. Return stable error codes `chat_turn_fence_missing` and `chat_turn_fence_stale`.

  ```python
  if "external_turn" in scope.allowed_scopes:
      claim = TurnLeaseClaim(
          turn_id=scope.turn_id,
          worker_id=turn_worker_id,
          worker_generation=turn_worker_generation,
          lease_generation=turn_lease_generation,
      )
      await transaction(lambda db: jobs.require_live_claim(db, claim=claim, now=clock()))
  ```

- [ ] Confirm every gateway route already depends on `_scope()` or add that dependency before any side effect. Do not duplicate fence logic inside individual adapters.

- [ ] Update the external provider, transcript, and Exa gateway clients to send the three headers from the immutable run context.

- [ ] Run gateway/capability/contract regressions, Ruff, and worker typechecking; then commit:

  `git commit -m "Fence external Pi gateway operations"`

---

### Task 7: Retain one external Pi run across WebSocket disconnects

**Files:**

- Create: `backend/chat_sandbox_worker/pi_worker/src/external_turn_registry.ts`
- Create: `backend/chat_sandbox_worker/pi_worker/src/external_turn_registry.test.ts`
- Modify: `backend/chat_sandbox_worker/pi_worker/src/external_server.ts`
- Modify: `backend/chat_sandbox_worker/pi_worker/src/turn_protocol.ts`
- Modify: `backend/services/chat_external_pi_turn_runner.py`
- Modify: `backend/tests/test_chat_external_pi_turn_runner.py`

**Consumes:** fenced `TurnClaimFrame`, ordered external Pi events, and the durable journal cursor acknowledged by the Python runner.

**Produces:** one live Pi harness run that can detach and reattach without replaying the model request.

- [ ] Write Node tests with a fake harness proving: socket close detaches rather than aborts; `attach_turn` with the same claim and last acknowledged sequence replays only later frames; a second simultaneous transport is rejected; stale claims are rejected; pending tool responses still reach the original run; overflow terminates with `external_turn_buffer_exhausted`; cancellation explicitly aborts the harness once.

  ```ts
  const run = registry.start(claim, fakeHarness);
  run.append({ sequence: 3, type: "delta", payload: { text: "x" } });
  run.detach(firstSocket);
  expect(run.attach(secondSocket, 2)).toEqual([{ sequence: 3, type: "delta", payload: { text: "x" } }]);
  expect(fakeHarness.startCount).toBe(1);
  ```

- [ ] Run the Node and Python runner tests and confirm disconnect currently cancels Pi.

- [ ] Implement an `ExternalTurnRegistry` keyed by `turnId`, retaining the harness task, current claim, bounded sequenced frames, pending tool-response routes, terminal state, and at most one attached transport.

- [ ] Change WebSocket-close handling to `detach`. Add explicit `cancel_turn` handling and a terminal grace expiry; never infer cancellation from network loss.

- [ ] Implement Python reconnect with the same worker claim, turn claim, and last worker sequence. If the exact worker generation is unavailable, mark the turn interrupted with `external_worker_lost`; do not open a fresh model run.

- [ ] Keep replay buffers under 4,096 events/8 MiB and release them after terminal acknowledgement or terminal grace expiry.

- [ ] Run worker tests/typecheck and Python runner/durable-stop tests, then commit:

  `git commit -m "Reconnect to live external Pi turns"`

---

### Task 8: Recover ambiguous Bash delivery by attachment only

**Files:**

- Modify: `backend/services/chat_sandbox_executor.py`
- Modify: `backend/services/chat_external_pi_turn_runner.py`
- Modify: `backend/tests/test_chat_sandbox_executor_client.py`
- Modify: `backend/tests/test_chat_sandbox_executor_daemon.py`
- Modify: `backend/tests/test_chat_external_pi_turn_runner.py`

**Consumes:** stable `ExecutorContext.execution_id`, daemon sequence cursors, and the current duplicate-exec attachment contract.

**Produces:** exactly-once Bash side effects across response loss and runner reconnect.

- [ ] Write a fault-injection test whose command appends one line to a file, whose first executor response is lost after acceptance, and whose recovery returns the result through `attach_execution`; assert the file contains exactly one line and the client called `exec` once.

  ```python
  result = await client.exec_resumable(context, "printf x >> marker", timeout_ms=1_000)
  assert marker.read_text() == "x"
  assert transport.exec_calls == 1
  assert transport.attach_calls >= 1
  assert result.exit_code == 0
  ```

- [ ] Run executor client/daemon and external runner tests and confirm the recovery API is missing.

- [ ] Extend `ExecutorExecutionLost` with immutable `execution_id` and `last_sequence` fields. Preserve all responses received before the loss.

- [ ] Add `exec_resumable(context, command, timeout_ms, max_attach_attempts=2)`: call `exec` exactly once, and on `ExecutorExecutionLost` call `attach_execution` with the same execution ID/cursor. On attachment exhaustion return `executor_execution_unknown`; never construct a replacement execution context.

  ```python
  try:
      return await self.exec(context, command, timeout_ms=timeout_ms)
  except ExecutorExecutionLost as lost:
      return await self.attach_execution(
          context,
          after_sequence=lost.last_sequence,
          timeout_ms=timeout_ms,
      )
  ```

- [ ] Route external Bash tool requests through `exec_resumable`. Keep read-only direct gateway CLI calls outside the sandbox; only commands requiring an executor use this path.

- [ ] Test loss before acceptance, after acceptance, during streaming output, after completion, and after runner reconnect. Require no duplicate side effect in every accepted case.

- [ ] Run focused executor/runner suites and Ruff, then commit:

  `git commit -m "Recover Bash executions by attachment"`

---

### Task 9: Lazily retain executor-only workspaces per session

**Files:**

- Modify: `backend/services/chat_sandbox_acquisition_coordinator.py`
- Create: `backend/services/chat_external_executor_workspace.py`
- Modify: `backend/services/chat_external_pi_turn_runner.py`
- Create: `backend/tests/test_chat_external_executor_workspace.py`
- Modify: `backend/tests/test_chat_sandbox_acquisition_coordinator.py`
- Modify: `backend/tests/test_chat_external_pi_turn_runner.py`

**Consumes:** `ChatSandboxLease`, capacity/spend admission, `ModalSandboxProviderAdapter.create(launch_mode=SandboxLaunchMode.EXECUTOR)`, and external Bash requests.

**Produces:** zero sandboxes for no-tool chats and one reusable live executor sandbox per active session that has used Bash.

- [ ] Write tests proving no-tool turns never acquire a workspace; the first Bash request creates one executor-only sandbox; later turns in the same session reuse the same sandbox ID/generation; concurrent acquisition is serialized by the existing lease; turn completion releases busy ownership to idle without termination; session deletion/expiry uses the existing eviction lifecycle.

  ```python
  first = await manager.acquire(session_id=session_id, turn_claim=claim_one)
  await manager.release(first)
  second = await manager.acquire(session_id=session_id, turn_claim=claim_two)
  assert second.sandbox_id == first.sandbox_id
  assert provider.create_calls == 1
  ```

- [ ] Run focused acquisition/runner tests and confirm the external retained manager is absent.

- [ ] Generalize `ChatSandboxAcquisitionCoordinator.acquire` with `launch_mode: SandboxLaunchMode = SandboxLaunchMode.LEGACY`; pass the value to provider creation while preserving all existing callers.

- [ ] Implement `ChatExternalExecutorWorkspaceManager.acquire/release` around the existing lease repository, acquisition coordinator, capacity/spend checks, executor health probe, and idle lifecycle. Require `SandboxLaunchMode.EXECUTOR`; keep snapshots disabled.

- [ ] Integrate lazily at the external runner's Bash boundary. Store no sandbox handle in the detached model-turn coordinator; resolve it from the durable session lease on every Bash request.

- [ ] Ensure failed executor health triggers fenced lease replacement through the existing lifecycle, not unbounded creation. Preserve the prior sandbox until the replacement claim is valid.

- [ ] Run acquisition, lease lifecycle, Modal adapter, external runner, and Ruff checks; then commit:

  `git commit -m "Retain lazy executor workspaces per chat"`

---

### Task 10: Complete cancellation, reconciliation, cleanup, and readiness contracts

**Files:**

- Modify: `backend/services/chat_detached_turn_service.py`
- Modify: `backend/services/chat_session_service.py`
- Modify: `backend/services/chat_cancellation_coordinator.py`
- Modify: `backend/services/chat_turn_job_repository.py`
- Modify: `backend/services/runtime_validation.py`
- Modify: `backend/config.py`
- Modify: `backend/services/chat_runtime_contract.py`
- Modify: `backend/tests/test_chat_durable_stop_expiry.py`
- Modify: `backend/tests/test_runtime_validation_decomposition.py`
- Modify: `backend/tests/test_chat_runtime_contract.py`

**Consumes:** terminal turn state, canonical assistant persistence, detached source ownership, external worker registry, journal cleanup, and executor lease lifecycle.

**Produces:** deterministic stop/failure behavior, stale-owner reconciliation, bounded cleanup, observable readiness, and deploy-time contract refusal.

- [ ] Add tests for user cancellation while connected and disconnected; API-process death before and after worker attach; expired turn lease; stale worker generation; journal overflow; executor loss; canonical terminal persistence followed by chunk deletion; and reconciliation that never replays an ambiguous model run.

  ```python
  await reconciler.reconcile(now=expired_at)
  job = jobs.get(db, turn_id)
  assert job.state == "interrupted"
  assert job.error_code == "external_worker_lost"
  assert model.start_calls == 1
  ```

- [ ] Run durable stop/runtime-contract tests and confirm the new failure codes and readiness gates are absent.

- [ ] Make cancellation set `cancelling`, deliver explicit cancel to the exact external worker generation when live, cancel executor attachment without re-executing, persist the canonical terminal response, set `interrupted`, then delete journal chunks.

- [ ] Add a bounded reconciler for expired detached leases. Classify `dispatch_failed`, `external_worker_lost`, `event_journal_exhausted`, `executor_execution_unknown`, and `cancelled`; never claim an expired ambiguous run for model replay.

- [ ] Add configuration/readiness checks requiring durable dispatch, event-journal schema, external admission, remote tools, lazy executor workspace, executor Bash/read support, and the new external worker/runtime contract versions before external admission can be enabled.

- [ ] Emit existing Langfuse/admin metrics for admitted/running/reconnecting/cancelling turns, journal bytes/events, worker reconnects, executor attach recoveries, workspace reuse/create/evict, typed failures, TTFT, and terminal latency. Keep labels bounded to states/codes, never user/session/turn IDs.

- [ ] Run focused durable stop, runtime validation, contract, session service, and cancellation tests plus Ruff.

- [ ] Commit:

  `git commit -m "Finalize durable external turn lifecycle"`

---

### Task 11: Add deterministic fault and 32/100-user qualification coverage

**Files:**

- Modify: `backend/loadtests/external_pi_fleet_core.py`
- Modify: `backend/loadtests/external_pi_fleet_locustfile.py`
- Create: `backend/loadtests/durable_external_turn_faults.py`
- Create: `backend/scripts/qualify_durable_external_turns.py`
- Create: `backend/tests/test_durable_external_turn_faults.py`
- Modify: `backend/tests/test_external_pi_fleet_qualification.py`
- Modify: `backend/loadtests/README.md`
- Modify: `docs/external-pi-shadow-activation.md`

**Consumes:** detached resume protocol, external worker reconnect, executor attachment, retained-workspace metrics, and the existing guarded fleet qualifier.

**Produces:** repeatable staging evidence for 32 simultaneous full turns followed by immediate admission of 100 simultaneous chats.

- [ ] Write pure tests for fault schedules covering browser disconnect, API subscriber process loss, external WebSocket loss, one worker drain, executor response loss, and cancellation. Assert one model start and at most one executor start per operation identity.

- [ ] Add 32-user functional profiles with a mix of no-tool, read-only CLI, and Bash turns. Add a 100-user admission/stream profile that starts all users immediately, uses no application-level queue, and records refusal, TTFT, completion, reconnect, memory, CPU, Modal create/reuse, and typed failure counts.

- [ ] Make the operator script refuse production, require the exact staging release, require all public external-admission flags off before setup, verify 8 GiB VPS headroom before each shape, redact content/tokens, and always restore the prior flags and transient workers.

  ```python
  if environment.name != "staging" or environment.production_release == environment.target_release:
      raise QualificationRefused("staging_isolation_required")
  if preflight.mem_available_bytes < profile.minimum_available_bytes:
      return QualificationResult(status="resource_refused", reason="memory_headroom")
  ```

- [ ] Run the pure load/fault tests and import-smoke Locust:

  `uv run --env-file backend/keys.env pytest -q backend/tests/test_durable_external_turn_faults.py backend/tests/test_external_pi_fleet_qualification.py`

  `uv run --isolated --with locust python -c "import backend.loadtests.external_pi_fleet_locustfile"`

- [ ] Document exact preflight, commands, success thresholds, cleanup proof, report permissions, and the rule that a refused shape is evidence rather than permission to overcommit the VPS.

- [ ] Run Ruff and commit:

  `git commit -m "Add durable external turn qualification"`

---

### Task 12: Review, publish to staging, migrate safely, and qualify

**Files:**

- Review all files changed since the pre-implementation commit.
- Do not commit local reports, scratch files, or older untracked planning artifacts.

**Consumes:** all implementation commits and staging-only operational guardrails.

**Produces:** exact-commit staging releases with admission kept off until migrations and fault/load gates pass; production remains unchanged.

- [ ] Use the repository `code-review` skill against commit `4a1d8986a0b70006bfa8c2c7c34cd4206fed6718`. Resolve every material Standards or Spec finding with tests before publishing.

- [ ] Run the focused backend union, worker tests/typecheck, frontend tests/typecheck/lint, Ruff, and `git diff --check`. Include at minimum every test file named in Tasks 1-11.

- [ ] Fetch `origin/main` and stop if it advanced into overlapping chat/runtime files. Integrate non-overlapping changes safely, re-run affected checks, push directly to `main` without force, and record the exact pushed SHA.

- [ ] Inspect `pwc-status`, the active staging/production releases, runtime contracts, external worker registry, disk/RAM, and the migration state. Confirm production stays on its current release.

- [ ] Deploy the exact pushed commit to staging with `pwc-deploy` while external admission remains disabled. Smoke-test staging `/health`, `/`, `/chat`, and one API route; roll back staging on failure.

- [ ] Follow `docs/database.md` and apply `add_chat_turn_event_chunks.sql` to staging only. Verify the table, counters, constraints, indexes, and downgrade-safe additive shape. Do not apply the migration to production.

- [ ] Restart/redeploy only through the supported immutable release interface so readiness observes the migrated schema. Confirm every new contract gate passes while public external admission is still off.

- [ ] Run deterministic disconnect/crash/Bash fault qualification at low concurrency. Require: one model start per turn, one executor execution ID per Bash call, no stale gateway action, successful same-turn resume, terminal canonical persistence, and transient journal cleanup.

- [ ] Run the guarded 32-user functional profile. Require zero duplicate model/Bash execution, zero cross-turn leakage, zero untyped failures, bounded journal/workspace use, and healthy staging after cleanup.

- [ ] If and only if the 32-user gate passes with safe RAM/CPU/disk headroom, run the guarded 100-user immediate-admission profile. Do not add a queue and do not force the shape when the preflight returns `resource_refused`.

- [ ] Restore staging admission flags to their prior disabled state, prove all qualification workers/ports/processes are removed, smoke-test staging again, and verify the production release/configuration/database were unchanged.

- [ ] Report exact SHAs, tests, fault outcomes, TTFT/completion percentiles, 32/100 admission and success counts, VPS peak memory/CPU, Modal sandbox create/reuse counts and estimated cost, cleanup proof, and the evidence-based next capacity step. Do not authorize production from a passing staging result; production still requires explicit user approval.
