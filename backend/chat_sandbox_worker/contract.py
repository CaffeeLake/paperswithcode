"""Immutable public identifiers for one worker/image contract."""

WORKER_CONTRACT_VERSION = "54"
# Web search extends the catalog operation set without changing its request or
# response framing, so it remains on the rollback-compatible gateway protocol.
GATEWAY_CONTRACT_VERSION = 26
GATEWAY_COMPATIBLE_FROM = 26
DATABASE_CONTRACT_VERSION = 1
SDK_VERSION = "0.2.115"
PWC_CLI_VERSION = "0.1.12"
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
MODAL_IMAGE_ID = "im-1y8C9jNAn7rwgBBQry18sy"
# Production chat remains disabled and separately pinned. Publish and qualify
# contract 54 in its Modal Environment before any production enablement; the
# distinct ID avoids cross-Environment image lookup.
PRODUCTION_MODAL_IMAGE_ID = "im-sARh8uQCMV2hQmjXxckrtI"
DEFAULT_BACKEND = "modal_cli"
NEW_CHAT_MODAL_PERCENTAGE = 100
