# Deployment

Production and staging use the same immutable-release mechanism. Each
environment selects one complete backend-plus-frontend release through an
atomic `active` slot; `current` records that release and `previous` is its only
rollback target.

## Topology

```text
/srv/paperswithcode/
  repository.git
  .venv
  runtime-lock.sha256
  runtimes/<uv-lock-sha256>/
  releases/<sha12>-<environment>/
  environments/{production,staging}/
    current
    previous
    active -> slots/{blue,green}
    slots/{blue,green}/
      release -> ../../../releases/<release-id>
      backend.sock -> /run/paperswithcode/<environment>-<slot>.sock

/etc/paperswithcode/{production,staging}.env
/etc/paperswithcode/production-cron.env
/var/lib/paperswithcode/{shared,production,staging}
```

Nginx resolves backend requests through `active/backend.sock` and static files
through `active/release/frontend-dist`. New connections therefore move
together when `active` is replaced, while established SSE connections remain
attached to the old Unix socket. Each slot runs from the immutable runtime
whose ID is the release's `uv.lock` SHA-256. The legacy shared `.venv` and
fixed-port services remain a migration fallback until both environments have
passed a slot rollback window. Public staging is static and gated to
allowlisted project contributors and admins; it never runs Vite or HMR.

Both environments read the live `public` catalog and shared thumbnail mirror.
Staging connects as `pwc_staging`, can select catalog rows, and can write only
environment-owned user, workflow, and chat rows in the `staging` schema.

## Commands

Read-only status:

```bash
pwc-status
python deploy/topology_audit.py --json
```

Deploy:

```bash
sudo pwc-deploy staging <commit-or-ref>
sudo pwc-deploy production <commit-or-ref> --confirm DEPLOY_PRODUCTION
```

Production accepts only commits reachable from `origin/main`. Every slot deploy
builds the selected frontend profile and immutable runtime, starts the inactive
slot, checks its exact release/runtime/slot identity, validates rolling gateway
and database compatibility, and runs direct-socket checks before atomically
switching `previous`, `current`, and `active`. A failed live smoke restores all
three pointers. A successful activation drains the displaced slot without
blocking transcript callbacks; if streams remain at the reporting deadline the
result is `success-with-draining` and `pwc-reap` finishes cleanup later.

For the one-time migration from a legacy service, install the committed tools
and slot units. A source-only compatibility landing may use the explicit
staging-only bridge mode before any slot exists, but only when `uv.lock`
matches the installed shared runtime:

```bash
sudo python deploy/install_deploy_tools.py <exact-sha>
sudo python deploy/install_host_layout.py
sudo pwc-deploy staging <exact-sha> --legacy-bridge
sudo pwc-deploy staging <current-sha> --qualify-only
```

Production may use the same bridge only with the explicit production
confirmation when its current legacy release predates the slot operator
endpoints:

```bash
sudo pwc-deploy production <exact-main-sha> \
  --legacy-bridge --confirm DEPLOY_PRODUCTION
sudo pwc-deploy production <exact-main-sha> \
  --qualify-only --confirm DEPLOY_PRODUCTION
```

`--legacy-bridge` is rejected after nginx or an active slot is present and can
never mutate the shared dependency set. Production additionally requires the
candidate to be reachable from `origin/main`. Qualification creates
`active -> slots/blue` but leaves live nginx and the legacy service
unchanged. Applying the checked-in active-slot nginx template is a separately
authorized `pwc-nginx` operation. After that one-time cutover, verify both
staging hosts and run the ordinary exact-SHA slot deployment. After its live
smoke succeeds, that deployment gracefully retires only the legacy staging
service; a failure to stop it is recorded as `legacy-retirement-pending`
without rolling back an otherwise healthy slot activation.
`--defer-public-smoke` is retired.

Rollback:

```bash
sudo pwc-rollback staging
sudo pwc-rollback production --confirm ROLLBACK_PRODUCTION
sudo pwc-reap staging
```

Nginx has a separate lifecycle:

```bash
sudo pwc-nginx staging --confirm APPLY_NGINX_STAGING
sudo pwc-nginx production --confirm APPLY_NGINX_PRODUCTION
```

It displays the effective diff, runs `nginx -t`, reloads, and smokes the
selected host. Ordinary deploys never edit or reload nginx.

Install deployment tooling only from committed source:

```bash
sudo python deploy/install_deploy_tools.py <commit>
```

## Staging sandbox-chat bridge

The sandbox chat bridge has additional fail-closed prerequisites:

1. Publish the standalone CLI release and verify its checksums and provenance.
2. Build the Modal image from that committed source, then commit the emitted
   immutable `im-...` image ID as `MODAL_IMAGE_ID`. A source revision with an
   empty ID cannot pass release validation.
3. Provision TLS for `chat-gateway-staging.paperswithcode.co`, install the
   committed nginx template with the explicit `pwc-nginx staging` lifecycle,
   and set `PWC_CHAT_GATEWAY_URL` to
   `https://chat-gateway-staging.paperswithcode.co/api/internal/chat-gateway`.
   The dedicated host exposes only the four capability-authenticated gateway
   routes.
4. Apply `add_chat_sandbox_runtime.sql`, `add_chat_turn_latency.sql`,
   `add_chat_sandbox_pool.sql`, `add_chat_active_cost.sql`,
   `add_chat_user_billing.sql`, `add_chat_qualification_metadata.sql`,
   `add_chat_openrouter_user_budget.sql`, and
   `add_chat_sandbox_spend_cap.sql` as
   PostgreSQL superuser with
   `search_path=staging,public`. The guarded migrations refuse any other schema,
   assign the new tables to `pwc_staging_owner`, grant `pwc_staging`, and
   revoke the production application role. The pool migration remains required
   even while `PWC_CHAT_BLANK_POOL_ENABLED=false`, because readiness validates
   the rollback-safe audit schema before pool activation.
5. Keep `PWC_CHAT_WORKSPACE_SNAPSHOTS_ENABLED=false`; snapshot activation is
   outside the latency project and requires a separate approved plan. V1 uses
   Modal's isolated, automatically reclaimed ephemeral disk; PID and memory
   ceilings remain hard qualification probes.

The worker system prompt embeds
`backend/chat_sandbox_worker/PWC_CLI_SKILL.md` plus the bounded area/task
taxonomy in `backend/chat_sandbox_worker/TASK_CATALOG.md`. The hourly
`sync-pwc-cli-skill.yml` workflow compares the skill with
`huggingface/pwc-cli:standalone_cli/SKILL.md`, regenerates the taxonomy from the
public catalog, and opens a review pull request when either prompt input
changes. After merging a prompt sync, publish a new immutable Modal image,
commit its `MODAL_IMAGE_ID`, and deploy that exact commit to staging; an
application deploy cannot alter an already-published worker image.

Before any non-zero rollout, deploy two distinct zero-percent bridge commits so
both `current` and `previous` understand `modal_cli`. Then run the operator-only
infrastructure qualification from the selected immutable release:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.qualify_chat_sandbox \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --starts 100 --parallel 4 --snapshot-samples 0 --resource-probes \
  --confirm QUALIFY_STAGING_SANDBOX
```

The runner creates only tagged disposable qualification sandboxes. It verifies
the pinned CLI, dedicated-gateway reachability without a capability, blocked
general egress, agent/broker UID and `/proc` isolation, and cancellation by
sandbox termination. Directory snapshots remain disabled for this latency
project. It emits timings and no environment values, commands, prompts,
credentials, or tool output. Full model,
SDK compaction, resume, edit/retry, and citation qualification still runs
through authenticated staging chats before increasing the rollout percentage.

The release-scoped reliability gate uses explicit qualification metadata rather
than synthetic usernames. Run the naturally paced SLO cohort and the broader
follow-up/cancellation matrix from the active immutable release, then audit the
same exact release and start time:

```bash
uv run --env-file /etc/paperswithcode/staging.env python \
  -m backend.scripts.qualify_chat_latency \
  --sessions 25 \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --confirm QUALIFY_STAGING_CHAT_LATENCY

uv run --env-file /etc/paperswithcode/staging.env python \
  -m backend.scripts.qualify_chat_soak \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --confirm QUALIFY_STAGING_CHAT_SOAK

uv run --env-file /etc/paperswithcode/staging.env python \
  -m backend.scripts.audit_chat_soak \
  --started-at <candidate-activation-time> \
  --release-dir /srv/paperswithcode/environments/staging/current \
  --confirm AUDIT_STAGING_CHAT_SOAK
```

The auditor reads all legacy and blue/green staging journal units, reports only
content-free error codes and aggregates, scopes health and SLO gates to the
active release, and keeps insufficient pre-soak samples distinct from failures.
Ordinary chat models require the signed-in user's Hugging Face billing. Staging
may additionally enable the shared OpenRouter-backed DeepSeek V4 Flash preview.
Admission checks provider-authoritative monthly usage before each turn, and the
provider key must prove an exact monthly `$5` staging workspace limit. Durable
PostgreSQL reservations enforce the separate `$1` per-user ceiling before each
funded gateway dispatch. Production continues to prohibit shared OpenRouter
credentials.

Provision the staging-only credential without printing it:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env backend/keys.env \
  --staging-openrouter-only
```

The application fails closed if OpenRouter cannot prove the exact provider
guardrail, or if durable per-user accounting is unavailable. Staging runs
bounded reconciliation and retention maintenance daily. An operator can also
run the release-scoped maintenance script explicitly, including an intentional
encryption-key rotation batch:

```bash
sudo systemd-run --quiet --wait --pipe --collect \
  --uid=pwc-staging --gid=pwc-staging \
  --working-directory=/srv/paperswithcode/environments/staging/current \
  --property=EnvironmentFile=/etc/paperswithcode/staging.env \
  /srv/paperswithcode/.venv/bin/python \
  -m backend.scripts.maintain_openrouter_accounting \
  --batch-size 100 --rotate-credentials
```

Generate a new active staging AES key and tracking secret without removing old
decryption versions, then deploy the intended release so processes load it:

```bash
sudo python deploy/configure_host_env.py \
  --legacy-env backend/keys.env \
  --staging-openrouter-secrets-rotate-only
```

After the explicit credential-rotation batch has re-encrypted every older row,
retire unused decryption versions in a separately reviewed environment change.

To retire the preview, use the provisioning command with
`--staging-openrouter-disable-only`. This leaves the ledger intact for
reconciliation and keeps Hugging Face-backed chat available.

## Release cleanup

Remove releases and runtimes not referenced by either environment's
`current`/`previous` pointers or either running/draining slot:

```bash
sudo pwc-cleanup --confirm CLEAN_RELEASES
```

The cleanup command takes the same host mutation lock as deploy, rollback, and
reaping. Never remove a release or runtime directory by hand.

## Invariants

`release.json` stores the full SHA, build profile, build time, frontend
entrypoint, backend/frontend feature manifests, and rolling gateway/database
contracts. `features.json` lives
beside built `index.html`. Startup fails if a deployed shell references
`/src/main.tsx`, assets are missing, paths are relative or inside a release,
or feature manifests disagree.

While chat remains staging-only, production build and runtime configuration
disable it; its backend router is absent and `/chat` redirects home.
Production is the sole OAuth/session authority. It signs
`pwc_shared_session` with an Ed25519 private key and scopes the cookie to
`.paperswithcode.co`; staging receives only the public verification key.
The host-only `pwc_session` and `pwc_staging_session` cookies and their
distinct HS256 secrets remain temporarily readable for rollback compatibility.
Staging login redirects through the production callback, whose return
destinations are restricted to the production and staging HTTPS origins.

Codex add-evals and enrich-paper buttons are enabled only in production and
remain protected by Hugging Face admin authentication in both the frontend and
API. Production owns the writable catalog and receives the remote-job
credentials through its protected environment. Staging keeps both controls
disabled because its catalog role is read-only and it has no job credentials.
Each release launcher derives the non-secret capability flags from that
release's validated manifest, so rolling back also restores the matching
frontend/backend feature state.

Slot processes expose deployment status, drain, and undrain operators only
through their Unix socket. Checked-in nginx templates return 404 for those
paths. `pwc-status` shows each slot's service/socket state, immutable
release/runtime identity, drain counts, and the activation journal. A deploy
never edits or reloads nginx.

## Scheduled work and backup

GitHub Actions calls `sudo /usr/local/sbin/pwc-cron <registered-job>`. The
launcher runs as `pwc-cron`, loads production plus CRON-only configuration,
resolves `production/current`, records its release ID, and uses absolute
lock/log directories.

```bash
sudo pwc-cron status
pwc cron health refresh_paper_embeddings --strict --json
```

`pwc-postgres-backup.timer` remains at 03:15 UTC. It runs the backup script from
`production/current` as `pwc-cron`, dumps both `public` and `staging` with the
read-only `pwc_backup` role, verifies the local checksum and remote object
listing, keeps three local dumps, and keeps thirty remote dumps.

`pwc-curation-thumbnails.timer` invokes the allowlisted
`pwc-cron process_curation_thumbnails` command every minute. Web identities only
enqueue work on `paper_curation_jobs`; the timer's `pwc-cron` transient unit is
the curation path that enables thumbnail mutations and writes the shared
thumbnail mirror. Stale processing claims are recoverable, and an operator can
retry terminal failures once per invocation with
`sudo pwc-cron process_curation_thumbnails --retry-failed`.
Install the committed deploy tools and apply
`backend/database/migrations/add_curation_thumbnail_queue.sql` before enabling
the timer with `sudo systemctl enable --now pwc-curation-thumbnails.timer`.

The hourly GitHub Actions monitor uses the same
`deploy/smoke_test.py --monitor-subset` implementation as releases. It checks
the production SPA and hashed asset MIME types plus the staging health/auth
boundary without creating an authenticated session.

## Development

Use `uv run --env-file backend/keys.env ...` for local backend commands and
`npm run dev` for a localhost frontend. `start_services.sh` and
`stop_services.sh` are non-mutating retirement notices; `check_services.sh`
delegates to `pwc-status`.
