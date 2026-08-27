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
- for every provider-backed profile, the protected server circuit already
  loaded as `PWC_CHAT_OPENAI_DAILY_BUDGET_USD` and/or
  `PWC_CHAT_OPENROUTER_DAILY_BUDGET_USD`

The checkpoint hard ceiling is two users. Every user runs once, prompts are
fixed and bounded, web search is disabled, and streamed text is discarded after
counting characters. Provider profiles require the declared spend envelope to
exactly equal every loaded protected provider daily cap; otherwise the harness
refuses to start. This makes the server circuit, rather than an unenforceable
client estimate, the actual upper bound. Connection-only profiles require zero
spend. Never put prompts, responses, account IDs, session IDs, or cookies in
profile names, metric names, exceptions, terminal output, or saved reports.

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

Do not add Locust to `pyproject.toml`. Run it ephemerally, from the repository
root, after exporting the complete envelope above:

```bash
uv run --env-file backend/keys.env --with 'locust>=2.40,<3' \
  locust -f backend/loadtests/locustfile.py --headless \
  --host https://staging.paperswithcode.co --users 2 --spawn-rate 1 \
  --run-time 30s
```

For the no-provider checkpoint, use only `bridge-smoke` or `connection-only`,
set spend to `0`, and do not infer chat admission from the result. Do not run a
live profile from a developer checkout or connect this harness to staging until
the controller has deployed the exact reviewed commit and activated the bridge.

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
