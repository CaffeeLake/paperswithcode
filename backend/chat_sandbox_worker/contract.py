"""Immutable public identifiers for one worker/image contract."""

import hashlib
from pathlib import Path

WORKER_CONTRACT_VERSION = "57"
# Web search extends the catalog operation set without changing its request or
# response framing, so it remains on the rollback-compatible gateway protocol.
GATEWAY_CONTRACT_VERSION = 27
GATEWAY_COMPATIBLE_FROM = 27
DATABASE_CONTRACT_VERSION = 1
SDK_VERSION = "0.2.115"
PWC_CLI_VERSION = "0.1.12"
RESTRICTED_HF_CLI_VERSION = "0.1.0"
RESTRICTED_HF_CLI_SHA256 = (
    "4151cd20e415958e6ef7b3d15a21d1837feb9867ecbea7e079a09dadef56f4bc"
)
HF_CLI_SKILL_SHA256 = "048688214baf58cbb4ea5820e2ebeaea980b48fde43afabd860f5f74ccd8bbcb"
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
MODAL_IMAGE_ID = "im-yfKfv118IxoZNYzlOpWy0D"
# Production chat remains disabled and pinned to its previously qualified
# contract; the distinct ID avoids cross-Environment image lookup.
PRODUCTION_MODAL_IMAGE_ID = "im-sARh8uQCMV2hQmjXxckrtI"
DEFAULT_BACKEND = "modal_cli"
NEW_CHAT_MODAL_PERCENTAGE = 100


def restricted_hf_cli_digest(package_root: Path, wrapper: Path) -> str:
    """Digest the exact restricted CLI sources copied into the worker image."""
    digest = hashlib.sha256()
    files = [
        (f"src/restricted_hf_cli/{path.name}", path)
        for path in package_root.glob("*.py")
    ]
    files.append(("bin/hf", wrapper))
    for relative, path in sorted(files):
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()
