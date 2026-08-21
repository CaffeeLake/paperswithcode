"""Closed, reviewed MCP App destinations for model-worker sandbox egress.

This module is release configuration, not a runtime marketplace. Adding a
provider requires a new compiled entry, tests, and a threat review.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from backend.config import Settings

MANIFEST_PATH = Path(__file__).with_name("mcp_app_providers.json")
# SHA-256 of the canonical empty provider list (`[]`).
EMPTY_EGRESS_POLICY_DIGEST = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


@dataclass(frozen=True)
class WorkerMcpProvider:
    id: str
    endpoint: str
    hostname: str
    worker_flag: str
    model_tools: tuple[str, ...]
    app_tools: tuple[str, ...]
    resource_uri: str
    app_html_sha256: str


def _load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _reject_ip_literal(hostname: str) -> None:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return
    raise ValueError("MCP provider hostname must not be an IP literal")


def validate_provider_entry(entry: dict[str, object]) -> WorkerMcpProvider:
    provider_id = entry.get("id")
    endpoint = entry.get("endpoint")
    hostname = entry.get("hostname")
    worker_flag = entry.get("worker_flag")
    model_tools = entry.get("model_tools")
    app_tools = entry.get("app_tools")
    resource_uri = entry.get("resource_uri")
    app_html_sha256 = entry.get("app_html_sha256")
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError("MCP provider id is required")
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("MCP provider endpoint is required")
    if not isinstance(hostname, str) or not hostname:
        raise ValueError("MCP provider hostname is required")
    if not isinstance(worker_flag, str) or not worker_flag:
        raise ValueError("MCP provider worker flag is required")
    if not isinstance(model_tools, list) or not model_tools:
        raise ValueError("MCP provider model tools are required")
    if not isinstance(app_tools, list) or not app_tools:
        raise ValueError("MCP provider App tools are required")
    if not isinstance(resource_uri, str) or not resource_uri:
        raise ValueError("MCP provider resource URI is required")
    if (
        not isinstance(app_html_sha256, str)
        or len(app_html_sha256) != 64
        or any(character not in "0123456789abcdef" for character in app_html_sha256)
    ):
        raise ValueError("MCP provider App HTML SHA-256 is required")
    if any(not isinstance(name, str) or not name for name in model_tools):
        raise ValueError("MCP provider model tools must be names")
    if any(not isinstance(name, str) or not name for name in app_tools):
        raise ValueError("MCP provider App tools must be names")
    if "*" in hostname or hostname.startswith("."):
        raise ValueError("MCP provider hostname must be an exact host")
    normalized = hostname.strip(".").lower()
    if hostname != normalized:
        raise ValueError("MCP provider hostname must be normalized")
    _reject_ip_literal(normalized)
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https":
        raise ValueError("MCP provider endpoint must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("MCP provider endpoint must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("MCP provider endpoint must not include a query or fragment")
    if not parsed.hostname:
        raise ValueError("MCP provider endpoint hostname is required")
    if parsed.hostname.lower() != normalized:
        raise ValueError("MCP provider endpoint hostname must match egress hostname")
    return WorkerMcpProvider(
        id=provider_id,
        endpoint=endpoint,
        hostname=normalized,
        worker_flag=worker_flag,
        model_tools=tuple(model_tools),
        app_tools=tuple(app_tools),
        resource_uri=resource_uri,
        app_html_sha256=app_html_sha256,
    )


def load_worker_mcp_providers() -> tuple[WorkerMcpProvider, ...]:
    payload = _load_manifest()
    providers = payload.get("providers")
    if not isinstance(providers, list):
        raise ValueError("MCP provider manifest is invalid")
    entries = [validate_provider_entry(entry) for entry in providers]
    ids = [entry.id for entry in entries]
    hostnames = [entry.hostname for entry in entries]
    model_tools = [name for entry in entries for name in entry.model_tools]
    if len(ids) != len(set(ids)):
        raise ValueError("MCP provider ids must be unique")
    if len(hostnames) != len(set(hostnames)):
        raise ValueError("MCP provider hostnames must be unique")
    if len(model_tools) != len(set(model_tools)):
        raise ValueError("MCP provider model tools must be unique")
    return tuple(sorted(entries, key=lambda entry: entry.id))


WORKER_MCP_PROVIDERS = load_worker_mcp_providers()


def provider_enabled(settings: Settings, provider: WorkerMcpProvider) -> bool:
    enabled = bool(getattr(settings, provider.worker_flag, False))
    if provider.id == "excalidraw":
        return enabled and settings.chat_mcp_apps_host_enabled
    return enabled


def enabled_worker_mcp_providers(settings: Settings) -> tuple[WorkerMcpProvider, ...]:
    return tuple(
        provider
        for provider in WORKER_MCP_PROVIDERS
        if provider_enabled(settings, provider)
    )


def egress_policy_digest(
    settings: Settings | None = None,
    *,
    providers: tuple[WorkerMcpProvider, ...] | None = None,
) -> str:
    selected = (
        providers
        if providers is not None
        else enabled_worker_mcp_providers(settings)
        if settings is not None
        else ()
    )
    payload = json.dumps(
        [
            {
                "endpoint": provider.endpoint,
                "hostname": provider.hostname,
                "id": provider.id,
                "model_tools": sorted(provider.model_tools),
            }
            for provider in sorted(selected, key=lambda item: item.id)
        ],
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    if selected:
        return digest
    if digest != EMPTY_EGRESS_POLICY_DIGEST:
        raise RuntimeError("empty MCP egress digest drifted")
    return EMPTY_EGRESS_POLICY_DIGEST


def sandbox_outbound_domains(settings: Settings) -> list[str]:
    """Exact Modal allowlist: dedicated gateway plus enabled reviewed MCP hosts."""

    from backend.services.chat_runtime_contract import dedicated_gateway_hostname

    gateway_host = dedicated_gateway_hostname(settings.chat_gateway_url)
    domains = [gateway_host]
    seen = {gateway_host}
    for provider in enabled_worker_mcp_providers(settings):
        if provider.hostname in seen:
            continue
        seen.add(provider.hostname)
        domains.append(provider.hostname)
    return domains
