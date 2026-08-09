"""Immutable public identifiers for one worker/image contract."""

WORKER_CONTRACT_VERSION = "46"
# Web search extends the catalog operation set without changing its request or
# response framing, so it remains on the rollback-compatible gateway protocol.
GATEWAY_CONTRACT_VERSION = 26
GATEWAY_COMPATIBLE_FROM = 26
DATABASE_CONTRACT_VERSION = 1
SDK_VERSION = "0.2.115"
PWC_CLI_VERSION = "0.1.10"
MODAL_APP_NAME = "pwc-chat-sandbox-v1"
IMAGE_PUBLISH_NAME = "pwc-chat-v1"
CHAT_SANDBOX_REGION = "eu-west"
CONTROL_PORT = 8080
PROVIDER_OUTPUT_TOKEN_LIMIT = 8_000
BASE_IMAGE = (
    "python:3.12-slim-bookworm@"
    "sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"
)
# Immutable image emitted by publish_image.py for the selected worker contract.
MODAL_IMAGE_ID = "im-yh9n3xBPquaraDIprZyCLU"
# The same worker contract published into the production Modal Environment.
# Keep this distinct so future Environment RBAC never requires a cross-
# Environment image lookup.
PRODUCTION_MODAL_IMAGE_ID = "im-BsjRSDFfby2tHKljyvPxaU"
DEFAULT_BACKEND = "modal_cli"
NEW_CHAT_MODAL_PERCENTAGE = 100
