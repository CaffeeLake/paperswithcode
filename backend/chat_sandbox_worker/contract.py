"""Immutable public identifiers for one worker/image contract."""

WORKER_CONTRACT_VERSION = "28"
# A release emits this gateway protocol and accepts workers back to the
# compatible-from floor while an old slot drains or a rollback is qualified.
GATEWAY_CONTRACT_VERSION = 26
GATEWAY_COMPATIBLE_FROM = 26
DATABASE_CONTRACT_VERSION = 1
SDK_VERSION = "0.2.115"
PWC_CLI_VERSION = "0.1.4"
MODAL_APP_NAME = "pwc-chat-sandbox-v1"
IMAGE_PUBLISH_NAME = "pwc-chat-v1"
BASE_IMAGE = (
    "python:3.12-slim-bookworm@"
    "sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"
)
# Immutable image emitted by publish_image.py for the selected worker contract.
MODAL_IMAGE_ID = "im-BHAKYma5Dt4cHzxOveHfiZ"
DEFAULT_BACKEND = "modal_cli"
NEW_CHAT_MODAL_PERCENTAGE = 100
