# Staging chat load harness

This is an operator-only Locust suite. It is not an application dependency and
must never target production. The dependency-free contracts live in
`chat_core.py`; `locustfile.py` is only a thin transport and metric adapter.

## Safety contract

The harness fails closed unless all of these are set:

- `PWC_LOADTEST_HOST=https://staging.paperswithcode.co` (the exact HTTPS origin;
  paths, credentials, aliases, production, and HTTP are rejected)
- `PWC_LOADTEST_CONFIRM=RUN_BOUNDED_STAGING_CHAT_LOAD`
- `PWC_LOADTEST_PROFILE=<profile>`
- `PWC_LOADTEST_SYNTHETIC_COOKIES` as a JSON array of dedicated, short-lived
  `pwc_staging_session` values created only for synthetic load-test owners
- explicit `PWC_LOADTEST_MAX_USERS`, `PWC_LOADTEST_MAX_SPEND_USD`,
  `PWC_LOADTEST_MAX_PROMPT_CHARS`, and `PWC_LOADTEST_MAX_OUTPUT_CHARS`
- for every provider-backed profile,
  `PWC_LOADTEST_MODEL=gpt-5.6-luna@openai`

The checkpoint hard ceiling is two users. Every user runs once, prompts are
fixed and bounded, web search is disabled, and streamed text is discarded after
counting characters. Provider profiles read only the direct-OpenAI daily budget
number from the root-owned regular file that is not group/world writable at
`/etc/paperswithcode/staging.env`. The required key must occur exactly once and
its value must exactly equal the declared spend envelope; caller-supplied
`PWC_CHAT_*` variables are ignored. This makes the server circuit, rather than
an unenforceable client estimate, the actual upper bound. The exact reviewed
model is sent as `initial_model`, so the audited provider is the provider under
load. No-provider profiles are model-free and require zero spend. Never put
prompts, responses, account IDs, session IDs, or cookies in profile names,
metric names, exceptions, terminal output, or saved reports.

The two-user `bridge-smoke` profile is a release-bound, no-provider PostgreSQL
probe. It requires exact durable capacity `2`, users `2`, spawn rate `2.0`, and a
single Locust process so both users share one process-local overlap gate. Each
Locust user creates one opaque synthetic owner and one uniquely identified
session/turn, exercises durable admission and fenced ownership, and commits a
`running` claim. Neither probe can terminalize until both committed claims have
reached the gate. Each then writes a terminal state through the application
coordinator/repository and deletes and verifies only its exact row IDs. It never
creates a message or invokes a provider, model, sandbox, or tool. It validates
the active immutable staging release, live worker contract, enabled bridge,
staging search path/role/schema, and protected runtime-file metadata before
writing. It refuses before creating probe rows if any expired durable claim is
awaiting normal reconciliation. There are no global sweeps.

`connection-only` describes a future SSE subscription-connection cohort and is
definition-only until that public endpoint exists. The separately named
`availability-connectivity` profile checks only the public, content-free
`/api/v1/chat/availability` endpoint and makes no SSE or admission claim.

## Profiles

| Profile | Users | Cohort | Checkpoint status |
|---|---:|---|---|
| `bridge-smoke` | 2 | durable PostgreSQL bridge | permitted |
| `availability-connectivity` | 2 | HTTP availability | permitted |
| `connection-only` | 2 | future SSE subscription | definition only |
| `same-account-contention` | 2 | one synthetic account | future provider run |
| `reconnect` | 2 | disconnect/resume | future provider run |
| `safe-cli` | 2 | exact `pwc paper info 1706.03762` command | future provider run |
| `general-bash` | 2 | bounded shell prompt | future provider run |
| `steady-10` / `steady-25` / `steady-50` / `steady-100` | named | steady | definition only |
| `burst` | 25 | burst | definition only |
| `overload` | 3 | overload/refusal | definition only |

Profiles over two cannot be armed by environment variables. A later protected
capacity qualification must deliberately change and review the source ceiling.

## Invocation

Do not add Locust to `pyproject.toml`, source the protected runtime file into a
shell, or run from a checkout. Resolve and enter the exact active immutable
staging release, derive its public release and worker identities from the
validated manifest, then let isolated `uv` load
`/etc/paperswithcode/staging.env` directly while preserving the manifest
identity and explicitly exported load-test envelope:

```bash
release_root=/srv/paperswithcode/releases
release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
case "$release" in
  "$release_root"/????????????-staging) ;;
  *) echo "staging current is not an immutable release" >&2; exit 1 ;;
esac
readarray -t release_identity < <(/srv/paperswithcode/.venv/bin/python -c '
import json, re, sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
sha = manifest.get("git_sha")
assert isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
assert manifest.get("release_id") == f"{sha[:12]}-staging"
runtime = manifest.get("chat_runtime")
assert isinstance(runtime, dict)
worker = runtime.get("worker_contract_version")
assert isinstance(worker, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", worker)
print(manifest["release_id"])
print(worker)
' "$release/release.json") || exit 1
test "${#release_identity[@]}" -eq 2 || exit 1
test "$(basename -- "$release")" = "${release_identity[0]}" || exit 1
export PWC_RELEASE_ID="${release_identity[0]}"
export PWC_CHAT_WORKER_CONTRACT_VERSION="${release_identity[1]}"
cd -- "$release" || exit 1

uv run --isolated --env-file /etc/paperswithcode/staging.env \
  --with 'locust>=2.40,<3' \
  locust -f backend/loadtests/locustfile.py --headless \
  --host https://staging.paperswithcode.co --users 2 --spawn-rate 2.0 \
  --run-time 30s
```

For the no-provider bridge checkpoint, use only `bridge-smoke`, set spend to
`0`, and run Locust in its default single-process local-runner mode. Use
`--users 2 --spawn-rate 2.0` exactly. A passing smoke requires two successful
`bridge.overlap` observations plus successful cleanup; this proves that two
distinct probes held concurrently committed `running` claims without invoking a
provider. Any expired durable claim must first be handled by normal
reconciliation. Use `availability-connectivity` only for the more limited HTTP
availability check. Do not run a live profile from a developer checkout or
connect this harness to staging until the controller has deployed the exact
reviewed commit and activated the bridge.
Provider profiles additionally require the fixed direct-OpenAI model above and
`PWC_LOADTEST_MAX_SPEND_USD` equal to the authoritative
`PWC_CHAT_OPENAI_DAILY_BUDGET_USD` value. Never copy that value out to a
caller-controlled `PWC_CHAT_*` variable; the harness reads it itself.

## Metrics

Locust's `<profile>/response_headers` duration is only HTTP response-header
latency. It is never terminal latency. The adapter parses SSE itself and emits
fixed-cardinality `CHAT` measurements:

- `chat.admission` and `chat.first_event`
- `chat.terminal`
- `chat.reconnect` and `chat.first_replay`
- `chat.stream_error`
- `chat.account_busy`
- `chat.overload`
- `chat.safe_cli_command` and `chat.safe_cli_contract` (one exact reviewed command,
  no other tool call, and a successful terminal)
- `bridge.admission`, `bridge.ownership`, `bridge.overlap`, `bridge.terminal`,
  and `bridge.cleanup`

HTTP refusal bodies are inspected only for typed codes. Error messages and SSE
content never become metric labels. A resumed stream is parsed and bounded until
`done`; malformed, truncated, transport-failed, or explicit error streams emit
`chat.stream_error` and cannot pass after the first replay event.

## External Pi single-worker overload baseline

This is a separate, staging-only safety baseline for the already-active external
Pi shadow worker. It does not change the two-user ceiling above. Resolve the
active slot and immutable staging release first, derive that slot's fixed
loopback endpoint, and run one local Locust process from that exact release:

```bash
release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
active="$(readlink -e /srv/paperswithcode/environments/staging/active)" || exit 1
case "$release" in
  /srv/paperswithcode/releases/????????????-staging) ;;
  *) echo "staging current is not an immutable release" >&2; exit 1 ;;
esac
case "$active" in
  /srv/paperswithcode/environments/staging/slots/blue)
    slot=blue; worker_url=http://127.0.0.1:8766 ;;
  /srv/paperswithcode/environments/staging/slots/green)
    slot=green; worker_url=http://127.0.0.1:8767 ;;
  *) echo "staging active slot is invalid" >&2; exit 1 ;;
esac
test "$(readlink -e "$active/release")" = "$release" || exit 1
report=/var/lib/paperswithcode/staging/external-pi-100-user-baseline.json
cd -- "$release" || exit 1

PWC_EXTERNAL_PI_BASELINE_CONFIRM=RUN_EXTERNAL_PI_SHADOW_BASELINE \
PWC_EXTERNAL_PI_BASELINE_PROFILE=single-worker-overload-baseline \
PWC_EXTERNAL_PI_BASELINE_USERS=100 \
PWC_EXTERNAL_PI_BASELINE_SPAWN_RATE=100 \
PWC_EXTERNAL_PI_BASELINE_SLOT="$slot" \
PWC_EXTERNAL_PI_BASELINE_WORKER_URL="$worker_url" \
PWC_EXTERNAL_PI_BASELINE_TOKEN_FILE=/etc/paperswithcode/external-pi-worker.env \
PWC_EXTERNAL_PI_BASELINE_REPORT="$report" \
uv run --isolated --with 'locust>=2.40,<3' \
  locust -f backend/loadtests/external_pi_shadow_locustfile.py --headless \
  --host "$worker_url" --users 100 --spawn-rate 100 --run-time 30s
```

The retained mode-0600 report is content-free. The workload restores only
synthetic native transcript structure, invokes no model, provider, tool, or
Modal runtime, and costs zero provider/Modal spend. It does not measure TTFT.
For the current worker capped at eight sessions, `safety_passed=true` with
`capacity_target_passed=false` proves bounded fail-fast overload behavior; the
false capacity verdict is expected until separately reviewed scale-out exists
and does not itself fail this safety-baseline command.

## External Pi transient fleet qualification

Run this staging-only controller only after deploying the reviewed commit to
staging and restoring the active blue/green worker to authenticated `ready`
health. The current and requested release must be the same immutable staging
release; external admission, sandbox executor routing, remote workspace tools,
remote Bash/Read, and lazy workspace must all remain false. Confirm that ports
8780-8795 have no listeners, `MemAvailable` and host CPU are within the guarded
limits, and the active worker has zero active sessions and zero forbidden work.
The controller repeats these checks before and after every transition. Every
checkpoint inspects all 16 reserved slots regardless of the current shape: all
32 exact supervisor/worker units and all ports 8780-8795. Only current-shape
slots owned by the current attempt may be active; every other unit must be
`not-found`/`inactive` and every other port free.

Resolve the release without sourcing a protected environment into the shell,
then run one isolated Locust dependency in the controller process:

```bash
release="$(readlink -e /srv/paperswithcode/environments/staging/current)" || exit 1
case "$release" in
  /srv/paperswithcode/releases/????????????-staging) ;;
  *) echo "staging current is not an immutable release" >&2; exit 1 ;;
esac
release_id="$(basename -- "$release")"
test -z "$(ss -H -ltn '( sport >= :8780 and sport <= :8795 )')" || exit 1
grep '^MemAvailable:' /proc/meminfo
pwc-status staging
cd -- "$release" || exit 1

sudo uv run --isolated --env-file /etc/paperswithcode/staging.env \
  --with 'locust>=2.40,<3' \
  python -m backend.scripts.qualify_external_pi_fleet \
  --environment staging --release-id "$release_id" \
  --confirm RUN_EXTERNAL_PI_FLEET_QUALIFICATION \
  --report /var/lib/paperswithcode/staging/external-pi-fleet-qualification.json
```

Shapes run sequentially in the fixed order 5x32, 8x16, and 16x8. An unsafe
projected-memory or CPU check records `resource_refused`; it is never overridden.
Each admitted shape runs exactly 100 healthy users, drains and stops one exact
observed generation, then runs exactly 100 users against the survivors. The
mode-0600 report is atomically replaced and contains only bounded counters,
identities, generations, latencies, resource peaks, and cleanup evidence.
Each round uses a bounded in-process arrival barrier: all exactly 100 Locust
users must be resident at the barrier before any user sends its one request.
Barrier timeout, controller resource abort, or overall round timeout releases
and stops all waiters and refuses the round; partial arrivals cannot pass.

`p95_ms` and `p99_ms` measure synthetic transcript compatibility/restore
latency. They are not model time-to-first-token: the qualifier performs no
generation and permits no model, provider, tool, Modal, or billing activity.

SIGINT, SIGTERM, test failures, and partial startup use the same exact-unit
cleanup. A failed attempt atomically replaces the report at the same path with
`report_type=recovery`, a fresh `attempt_id`, the exact release and owner, and
one bounded record for every current-shape attempted replica plus any foreign,
stale, status-retaining, or listening slot found by a fresh all-16-slot
inspection. Fully cleaned earlier shapes are not duplicated in later-shape
recovery. Treat only that current-attempt record as recovery evidence;
`cleanup_complete=false`, any `unresolved_units`, or `ports_free=false` requires
operator recovery. Do not kill processes by pattern and do not rerun
while any qualification unit or port remains. Inspect only the exact
`paperswithcode-staging-external-pi-qualification@NN.service` and
`paperswithcode-staging-external-pi-qualification-worker@NN.service` units plus
their content-free status files under
`/run/paperswithcode/external-pi-qualification/`. Recovery must drain the exact
recorded generation through `deploy.external_pi_qualification_lifecycle`, wait
for `offline`/`drained`, stop supervisor before worker, reset only those units,
and prove the status file, listener, and process are gone. If exact drain proof
is unavailable, leave the worker fenced for operator recovery; never force it.

Before any replica start, the controller snapshots immutable descriptors for
all 16 slots in every requested shape while the exact-current release gate is
healthy. Normal checkpoints still refuse a missing, changed, or invalid
`current` pointer. Failure reporting uses only that snapshot, so pointer drift
cannot suppress or redirect the current-attempt recovery report.

For each retained replica in that recovery report, first compare the report's
`owner_id` and `owned_units` with the live unit metadata. Every live owned unit
must have the exact Description
`Papers With Code staging external Pi qualification <role> NN owner <owner_id>`;
its `ExecStart` must name the report's exact release, index, allowlisted port,
and session limit. A unit omitted from `owned_units` must be `not-found` and
`inactive`; a foreign or ambiguous unit is not safe to remove. Derive the
allowlisted shape and index from those checked `ExecStart` arguments (which
contain no token), then run the Task 2 cleanup contract from the exact active
release. Repeat only for explicitly inspected report entries:

```bash
systemctl show --property=LoadState --property=ActiveState \
  --property=Description --property=ExecStart \
  paperswithcode-staging-external-pi-qualification@NN.service \
  paperswithcode-staging-external-pi-qualification-worker@NN.service
shape=5x32  # set to the exact observed 5x32, 8x16, or 16x8 shape
index=0     # set to the exact observed 0-15 replica index
owned=worker  # exact report value: worker, supervisor, or supervisor,worker

sudo uv run --env-file /etc/paperswithcode/staging.env python -c '
import json, sys
from backend.loadtests.external_pi_fleet_core import resolve_fleet_shape
from deploy.external_pi_qualification_lifecycle import (
    cleanup_replica, resolve_qualification_replica,
)
release_id, shape_name, raw_index, raw_owned = sys.argv[1:]
shape = resolve_fleet_shape(shape_name)
index = int(raw_index)
replica = shape.replicas[index]
resolved = resolve_qualification_replica(
    "staging", release_id, index, replica.port, shape.sessions_per_worker
)
names = {
    "supervisor": resolved.supervisor_unit,
    "worker": resolved.worker_unit,
}
owned_units = {names[item] for item in raw_owned.split(",") if item}
status = (
    json.loads(resolved.status_path.read_text(encoding="utf-8"))
    if resolved.status_path.exists()
    else {}
)
generation = status.get("generation")
if generation is not None and (type(generation) is not int or generation < 1):
    raise SystemExit("invalid bounded generation evidence")
if not status and resolved.supervisor_unit in owned_units:
    raise SystemExit("owned supervisor has no durable generation evidence")
cleanup_replica(resolved, generation=generation, owned_units=owned_units)
' "$release_id" "$shape" "$index" "$owned"
```

An absent status file is acceptable only for a worker-only partial start when
the supervisor is omitted from the report's `owned_units` and its live metadata
affirmatively proves `not-found`/`inactive`; it is not permission to assume both
units are owned. After each recovery command, require both exact units to be `not-found` and
inactive, the corresponding status file absent, and its loopback port absent
from `ss -H -ltn`. Do not continue to another pair if any proof fails.
