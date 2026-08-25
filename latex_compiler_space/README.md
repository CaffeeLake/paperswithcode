---
title: PwC Private LaTeX Compiler
emoji: 📄
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# PwC private LaTeX compiler

This is a private, staging-only service endpoint; it is not a user-facing
Space. It accepts only signed compiler envelopes from the PwC backend. It has
no bucket, database, model-provider, user, session, or signing-private-key
credential.

## Private Space setup

Create a **private Docker Space** on CPU Upgrade and configure it as always-on
through the Hugging Face Space settings. From the PwC checkout, deploy the
assembled service with the explicit staging-only command:

```bash
HF_TOKEN=<private-space-write-token> uv run python scripts/deploy_latex_compiler_space.py \
  --space <namespace>/pwc-latex-compiler-staging \
  --confirm DEPLOY_PRIVATE_LATEX_COMPILER_SPACE
```

Before it can accept a request, set only this Space secret:

```text
PWC_LATEX_COMPILER_PUBLIC_KEY=<base64url Ed25519 public key>
```

Set the matching private key, private-Space access token, and Space URL only in
the staging backend environment as `PWC_CHAT_LATEX_COMPILER_*` values. Do not
put any of those values in this repository, Space variables, image layers, or
build logs. The Space deliberately ignores request authorization headers; the
Hugging Face private-Space gateway validates the backend's access token before
requests reach this process.

The Dockerfile pins the TeX image by digest. Replacing it requires a reviewed
staging qualification covering the image digest, TeX engine versions, hostile
bundle handling, timeout/cancellation, and the no-network/no-shell-escape
controls. The in-memory queue is intentionally ephemeral: PwC owns durable job
intent and may safely resubmit the same signed job after a Space restart.
