# Private LaTeX compiler staging runbook

The LaTeX compiler is a staging-only, disabled-by-default boundary for
untrusted manuscript bundles. It is not a public API and it must never receive
PwC database, artifact-bucket, model-provider, user, or signing-private-key
credentials.

## Current qualification decision

**Do not enable paper compilation.** The private Docker Space remains
unqualified, so `PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false` is the required
staging state.

Evidence captured on 2026-08-25:

- The authenticated Hub identity is `nielsr`, but `hf spaces list --author
  nielsr --search pwc` returned only public curator Spaces; no existing private
  compiler Space was available to inspect.
- The staging example deliberately leaves the compiler URL, private-Space
  token, and signing key empty. No configured endpoint or public-key secret is
  available for a live request.
- The pinned Space image runs as an unprivileged user with a minimal
  environment and no application credentials, but its Docker Space deployment
  does not establish a per-job network boundary. A compiler compromise could
  make outbound requests with the manuscript it received. Serialized execution
  does not solve this confidentiality risk.

Consequently, a long-lived Docker Space is not adequate evidence for the
privacy boundary. Before enabling the feature, deploy a per-job Hugging Face
Sandbox or Job implementation that satisfies `LatexCompilerTransport` in
`backend/services/latex_compiler_service.py`; the paper service must continue
to use that transport interface, not a Space-specific API. The necessary
external inputs are: an approved staging namespace/Space or Job identity,
public-key secret placement, private endpoint/token configuration, and an
operator-authorized isolated runtime with an explicit egress policy. Do not
invent any of those values.

## Kill switch

To stop all **new** compiler submissions while preserving owner reads of stored
source and historical PDFs, set this in `/etc/paperswithcode/staging.env` and
deploy staging:

```text
PWC_CHAT_LATEX_COMPILER_JOBS_ENABLED=false
```

`PWC_CHAT_LATEX_PAPER_ENABLED=false` is the stricter paper-creation switch.
Neither control deletes artifacts or invalidates safe historical previews.

## Health and metrics

The Space exposes only content-free operational endpoints:

- `GET /health` reports readiness, serialized capacity, queue depth, active
  work, retained-job count, outcome totals, failure-category totals, and a
  bounded latency sample.
- `GET /metrics` returns the same bounded counters for collection.

No endpoint, application log, or metric contains a job ID, source digest,
manuscript bytes, diagnostics, signed envelope, or credential. Space access
logs are disabled in the Uvicorn command.

Alert on non-zero or rising `timeout`, `resource_limit`, `execution_error`,
`service_error`, `transport_failure`, or `lost` counts; alert immediately when
readiness fails or queue depth remains non-zero without active work.

## Restart and reconciliation

Each immutable paper version uses its UUID as its compiler idempotency key.
After a Space/backend restart or a transport outage, resubmission uses the same
source archive, root document, digest, and idempotency key. It cannot create a
second logical version.

After confirming the compiler is enabled and healthy, an operator can process
at most 100 pending versions at a time:

```bash
uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.reconcile_latex_compiler_jobs \
  --limit 20 --confirm RECONCILE_STAGING_LATEX_COMPILER_JOBS
```

The command refuses non-staging environments and an enabled kill switch. It
prints only `{"reconciled": N}`. A missing/corrupt durable source archive is
marked `lost`; a temporary transport fault remains queued for a later bounded
retry. Do not retry a failed qualification by changing a manuscript or its
digest under the same version ID.

## Qualification procedure

Only after the external inputs in the current decision are supplied and the
kill switch is intentionally enabled for this isolated staging exercise:

```bash
uv run --env-file /etc/paperswithcode/staging.env \
  python -m backend.scripts.qualify_latex_compiler_space \
  --confirm QUALIFY_PRIVATE_LATEX_COMPILER_SPACE
```

The suite uses fixed synthetic bundles for shell escape, host file reads,
network pipe input, recursive expansion, process pressure, oversized output,
path traversal, malformed archives, and malformed PDF figures. It prints only
case names, terminal outcomes, and elapsed milliseconds. Also perform one
manual cancellation while compiling and one controlled Space restart followed
by the reconciliation command; record `/health` and `/metrics` before and
after. Keep all manuscript content out of tickets, terminal capture, and Space
logs.

Passing local contract tests does **not** qualify the remote isolation. Do not
claim this procedure passed until a private endpoint, signing-key configuration,
and isolated runtime have actually run it successfully.
