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
probe. Each Locust user creates one opaque synthetic owner and one uniquely
identified session/turn, exercises durable admission, fenced ownership, and a
terminal write through the application coordinator/repository, then deletes and
verifies only those exact row IDs. It never creates a message or invokes a
provider, model, sandbox, or tool. It validates the active immutable staging
release, live worker contract, enabled bridge, staging search path/role/schema,
and protected runtime-file metadata before writing. There are no global sweeps.

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
staging release, then let `uv` load `/etc/paperswithcode/staging.env` directly
while preserving the explicitly exported load-test envelope above:

```bash
release="$(readlink -f /srv/paperswithcode/environments/staging/current)"
case "$release" in
  /srv/paperswithcode/releases/*) ;;
  *) echo "staging current is not an immutable release" >&2; exit 1 ;;
esac
cd -- "$release"

uv run --env-file /etc/paperswithcode/staging.env --with 'locust>=2.40,<3' \
  locust -f backend/loadtests/locustfile.py --headless \
  --host https://staging.paperswithcode.co --users 2 --spawn-rate 1 \
  --run-time 30s
```

For the no-provider bridge checkpoint, use only `bridge-smoke` and set spend to
`0`. Use `availability-connectivity` only for the more limited HTTP availability
check. Do not run a live profile from a developer checkout or connect this
harness to staging until the controller has deployed the exact reviewed commit
and activated the bridge.
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
- `bridge.admission`, `bridge.ownership`, `bridge.terminal`, and `bridge.cleanup`

HTTP refusal bodies are inspected only for typed codes. Error messages and SSE
content never become metric labels. A resumed stream is parsed and bounded until
`done`; malformed, truncated, transport-failed, or explicit error streams emit
`chat.stream_error` and cannot pass after the first replay event.
