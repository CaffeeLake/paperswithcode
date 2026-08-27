# External Pi shadow activation

This checkpoint activates only the staging shadow worker and its durable
supervisor. It does not admit turns, execute tools, call a model or provider,
start Modal work, or create billing activity. Production is explicitly outside
the checkpoint.

## Qualification

Publish Task 3 as a second immutable staging release only after both `current`
and `previous` contain the inert external Pi runtime. Keep every external Pi
flag false while publishing, and confirm both external Pi units are inactive.
Do not start either unit manually. The guarded enable command below temporarily
starts the exact active-slot candidate, waits for authenticated registration and
a heartbeat, crashes only the supervisor, waits for its durable lease to expire,
and proves a higher replacement generation. A staging-role database probe then
submits the old generation to the real repository and requires it to be fenced.
The guard performs a real drain/offline stop, starts one final recovery
generation, runs the qualification command with the exact release runtime, and
always drains/stops the temporary units before it changes either flag.

The integrated command is equivalent to:

```bash
cd /srv/paperswithcode/environments/staging/current
uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.qualify_external_pi_shadow \
  --environment staging \
  --app-root /srv/paperswithcode \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --worker-url http://127.0.0.1:8766 \
  --worker-id staging-blue \
  --expected-generation <recovery-generation> \
  --initial-generation <initial-generation> \
  --restarted-generation <lease-expiry-generation> \
  --stale-fenced --drain-recovered \
  --qualification-nonce <single-use-activation-nonce> \
  --token-file /etc/paperswithcode/external-pi-worker.env \
  --prompt-file <immutable-runtime>/assets/pi-system-prompt.txt \
  --report /var/lib/paperswithcode/staging/external-pi-shadow-qualification.json
```

The guard supplies the active slot's actual worker ID, port, and immutable
prompt path. The command refuses production and a release other than the exact staging
`current`. It submits linear, branching, tool-history, and eight concurrent
isolated native JSONL trees. It compares current leaf, entry count, canonical
transcript digest, system-prompt digest, and registered-tool-name digest. It
also proves immediate capacity rejection without a queue, lease-expiry restart
with a higher generation, stale-generation fencing, drain, and clean recovery.

The JSON report is deliberately content-free: exact release/worker/recovery
generation, a single-use nonce, a bounded freshness timestamp, case names,
booleans, bounded integer counts/durations, typed failure codes, and six
external-work counters only. The observed shadow-request counter must be
positive. Model, tool, provider, Modal, and billing counters must be exactly
zero, and the live worker must report no provider/Modal credentials and zero
registered tools. Do not retain request bodies or temporary native sessions.

## Guarded enable and disable

Activate and qualify the exact current release atomically:

```bash
sudo /usr/bin/python3 \
  /usr/local/lib/paperswithcode-deploy/external_pi_shadow_activation.py \
  staging enable \
  --release-id <exact-release-id> \
  --report /var/lib/paperswithcode/staging/external-pi-shadow-qualification.json
```

The guard first bootstraps the content-free qualification while both flags stay
false. It always proves drain and stops the temporary units, then checks every
required successful case, validates the exact identity/nonce/freshness and live
content-free evidence, creates or preserves the
mode-0640 token-only worker environment, and refreshes that exact git SHA. It
sets shadow and supervisor together. It explicitly forces external admission,
the sandbox executor, remote workspace tools, remote Bash, remote Read, and
lazy workspace false. Production invocation fails. A failed refresh restores
the prior protected environment; the normal deployment refresh owns service
and pointer rollback.

The CLI converts normal `SIGTERM` and `SIGINT` delivery on its main thread into
a transaction interruption. This runs the same temporary-unit `finally` stop
and protected-environment rollback used for other failures, then restores the
process's prior signal handlers. `SIGKILL`, host power loss, and kernel failure
cannot run in-process cleanup. After one of those events, run the guarded
`disable` command before retrying enable; disable checks both supervisor and
worker units in both slots even when the flags already read false/false, and
leaves the configuration fail closed until all units prove inactive.

Disable is qualification-independent but still exact-release guarded, including
when the protected flags already read false/false so orphan units cannot be
skipped. The guard
keeps true/true in the protected environment while it exact-evidence drains and
stops the current and any old-slot external units. If a slot release cannot be
resolved, both its supervisor and worker systemd units must still prove
inactive. Only after proven stop does
it write false/false and refresh the exact release:

```bash
sudo /usr/bin/python3 \
  /usr/local/lib/paperswithcode-deploy/external_pi_shadow_activation.py \
  staging disable --release-id <exact-current-release-id>
```

If the refresh fails after proven stop, the helper deliberately leaves the
units stopped and both flags false and returns an explicit recovery error. It
does not restore true configuration over stopped services. If drain proof
fails, it makes no configuration change and leaves the lifecycle enabled for
authenticated operator recovery; never kill or abandon an unproven worker.

## Observation and alerts

The dashboard must group by exact release and worker identity and show:

- supervisor registration, heartbeat age, lease expiry, generation, state,
  active sessions, maximum sessions, and drain result;
- shadow case pass rate and duration, capacity rejections, projection mismatch
  codes, restart generation advances, stale-generation rejection, and recovery;
- the positive shadow-request counter and all five forbidden external-work
  counters, each forbidden counter with an alert threshold above zero;
- worker availability, authentication failures, unexpected generation changes,
  missed heartbeat/expired lease, non-zero active sessions during drain, and
  repeated qualification failures.

Page immediately for any external-work count above zero, admission/executor/
remote/lazy flag becoming true, a stale claim being accepted, transcript or
prompt digest mismatch, or failure to reach durable offline state within the
configured drain bound. Alert after two heartbeat intervals for heartbeat age
and before lease expiry leaves less than one heartbeat interval.

## Rollback

Run the guarded disable command first. Confirm `pwc-status staging` shows the
exact worker durably `offline` with `drained=true`, or use the existing exact
inactive-unit proof when it never registered. Do not kill an unproven worker.
If the release itself must roll back, use `pwc-rollback staging` only after the
shadow lifecycle is disabled; both current and previous understand the runtime.
Re-run the normal health, root, SPA, and API smoke checks.

## Gate for later real admission

This checkpoint does not authorize real admission. A later, separately
reviewed phase requires all of the following:

- a sustained staging observation window with no projection mismatch, lease
  loss, stale-generation acceptance, drain failure, or recovery failure;
- eight-session isolation and no-queue capacity behavior remaining green under
  repeated qualification;
- zero model/tool/provider/Modal/billing work throughout shadow observation;
- approved executor and remote-tool capability, credential, cost, audit, and
  rollback contracts, each independently qualified;
- explicit production authorization and a new production qualification plan.

Until then, `PWC_CHAT_EXTERNAL_PI_ADMISSION_ENABLED`, executor, remote tool,
remote Bash/Read, and lazy workspace controls remain false in every environment.
