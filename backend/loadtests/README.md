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
load. Connection-only profiles are model-free and require zero spend. Never put
prompts, responses, account IDs, session IDs, or cookies in profile names,
metric names, exceptions, terminal output, or saved reports.

The two-user `bridge-smoke` and `connection-only` profiles call only the public,
content-free `/api/v1/chat/availability` endpoint. They perform no admission,
provider, model, or sandbox work. Consequently they can qualify connectivity
and harness refusal gates, but they do **not** prove admitted durable turns or
the bridge itself. A controller must use release-scoped database qualification
for that no-provider bridge evidence.

## Profiles

| Profile | Users | Cohort | Checkpoint status |
|---|---:|---|---|
| `bridge-smoke` | 2 | connection only | permitted |
| `connection-only` | 2 | connection only | permitted |
| `same-account-contention` | 2 | one synthetic account | future provider run |
| `reconnect` | 2 | disconnect/resume | future provider run |
| `safe-cli` | 2 | no-tool prompt | future provider run |
| `general-bash` | 2 | bounded shell prompt | future provider run |
| `steady-10` / `steady-25` / `steady-50` / `steady-100` | named | steady | definition only |
| `burst` | 25 | burst | definition only |
| `overload` | 3 | overload/refusal | definition only |

Profiles over two cannot be armed by environment variables. A later protected
capacity qualification must deliberately change and review the source ceiling.

## Invocation

Do not add Locust to `pyproject.toml`, source the protected runtime file, or run
from a checkout. Resolve and enter the exact active immutable staging release,
then run Locust ephemerally after exporting only the load-test envelope above:

```bash
release="$(readlink -f /srv/paperswithcode/environments/staging/current)"
case "$release" in
  /srv/paperswithcode/releases/*) ;;
  *) echo "staging current is not an immutable release" >&2; exit 1 ;;
esac
cd -- "$release"

uv run --with 'locust>=2.40,<3' \
  locust -f backend/loadtests/locustfile.py --headless \
  --host https://staging.paperswithcode.co --users 2 --spawn-rate 1 \
  --run-time 30s
```

For the no-provider checkpoint, use only `bridge-smoke` or `connection-only`,
set spend to `0`, and do not infer chat admission from the result. Do not run a
live profile from a developer checkout or connect this harness to staging until
the controller has deployed the exact reviewed commit and activated the bridge.
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

HTTP refusal bodies are inspected only for typed codes. Error messages and SSE
content never become metric labels. A resumed stream is parsed and bounded until
`done`; malformed, truncated, transport-failed, or explicit error streams emit
`chat.stream_error` and cannot pass after the first replay event.
