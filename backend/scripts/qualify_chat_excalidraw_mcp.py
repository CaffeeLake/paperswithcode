#!/usr/bin/env python3
"""Disposable Modal probe for Excalidraw MCP App availability.

This is a feature-availability gate, not a gate for the entire chat release.
Ordinary staging chat may still deploy if this fails; Excalidraw must remain
disabled until a later successful probe.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid

from backend.chat_sandbox_worker.mcp_app_registry import (
    WORKER_MCP_PROVIDERS,
    enabled_worker_mcp_providers,
    sandbox_outbound_domains,
)
from backend.config import Settings
from backend.services.chat_runtime_contract import dedicated_gateway_hostname
from backend.services.chat_sandbox_provider import ModalSandboxProviderAdapter
from backend.services.chat_sandbox_service import create_isolated_sandbox

CONFIRMATION = "QUALIFY_EXCALIDRAW_MCP"
EXCALIDRAW = WORKER_MCP_PROVIDERS[0]
WORKER_QUALIFY = (
    "/opt/pwc/backend/chat_sandbox_worker/pi_worker/dist/src/qualify_mcp_apps.js"
)
WORKER_TSX = (
    "/opt/pwc/backend/chat_sandbox_worker/pi_worker/node_modules/tsx/dist/loader.mjs"
)


def validate_settings(settings: Settings) -> None:
    if settings.environment not in {"staging", "production"}:
        raise RuntimeError(
            "Excalidraw MCP qualification requires a deployed environment"
        )
    if not settings.chat_excalidraw_enabled:
        raise RuntimeError("Enable PWC_CHAT_EXCALIDRAW_ENABLED before probing")
    if not settings.chat_mcp_apps_host_enabled:
        raise RuntimeError("Enable PWC_CHAT_MCP_APPS_HOST_ENABLED before probing")
    gateway = dedicated_gateway_hostname(settings.chat_gateway_url)
    domains = sandbox_outbound_domains(settings)
    if domains != [gateway, EXCALIDRAW.hostname]:
        raise RuntimeError("Worker egress must be gateway plus Excalidraw only")


async def _exec(sandbox, *command, timeout: int = 30) -> tuple[int, str, str]:
    process = await sandbox.exec.aio(*command, timeout=timeout)
    await process.wait.aio()
    stdout = await process.stdout.read.aio()
    stderr = await process.stderr.read.aio()
    return (
        int(process.returncode or 0),
        stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else str(stdout),
        stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else str(stderr),
    )


async def qualify(settings: Settings) -> dict[str, object]:
    validate_settings(settings)
    name = f"chat-excalidraw-qualify-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    sandbox = await create_isolated_sandbox(
        settings,
        name=name,
        tags={
            "service": "pwc-chat",
            "environment": settings.environment,
            "purpose": "excalidraw-mcp-qualify",
            "release": settings.release_id,
            "image": settings.chat_modal_image_version,
        },
    )
    report: dict[str, object] = {
        "status": "failed",
        "sandbox_id": getattr(sandbox, "object_id", None),
        "egress_domains": sandbox_outbound_domains(settings),
        "enabled_providers": [
            provider.id for provider in enabled_worker_mcp_providers(settings)
        ],
    }
    adapter = ModalSandboxProviderAdapter(settings)
    try:
        gateway_code, _, _ = await _exec(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "python",
            "-c",
            (
                "import json,sys,urllib.error,urllib.request;"
                "req=urllib.request.Request(sys.argv[1].rstrip('/')+'/catalog',"
                "data=b'{}',headers={'Content-Type':'application/json'});\n"
                "try:\n urllib.request.urlopen(req,timeout=10)\n"
                "except urllib.error.HTTPError as error:\n"
                " raise SystemExit(0 if error.code in {401,403,422} else 2)\n"
                "raise SystemExit(3)"
            ),
            settings.chat_gateway_url,
            timeout=15,
        )
        report["gateway_reachable"] = gateway_code == 0
        if gateway_code != 0:
            report["failure_class"] = "configured_not_connected"
            return report
        tls_probe = (
            "import socket,ssl,sys\n"
            "from urllib.parse import urlsplit\n"
            "parsed=urlsplit(sys.argv[1])\n"
            "assert parsed.scheme=='https' and parsed.hostname=='mcp.excalidraw.com'\n"
            "context=ssl.create_default_context()\n"
            "with socket.create_connection((parsed.hostname, 443), timeout=12) as raw:\n"
            "    with context.wrap_socket(raw, server_hostname=parsed.hostname) as tls:\n"
            "        assert tls.server_hostname==parsed.hostname\n"
        )
        tls_code, _, _ = await _exec(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "python",
            "-c",
            tls_probe,
            EXCALIDRAW.endpoint,
            timeout=20,
        )
        report["mcp_tls_status"] = tls_code
        if tls_code != 0:
            report["failure_class"] = "configured_not_connected"
            return report
        http_probe = (
            "import json,sys,urllib.error,urllib.request\n"
            "from urllib.parse import urlsplit\n"
            "parsed=urlsplit(sys.argv[1])\n"
            "assert parsed.scheme=='https' and parsed.hostname=='mcp.excalidraw.com'\n"
            "body=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize',"
            "'params':{'protocolVersion':'2025-03-26','capabilities':{},"
            "'clientInfo':{'name':'pwc-qualify','version':'1'}}}).encode()\n"
            "req=urllib.request.Request(sys.argv[1], data=body, method='POST',"
            "headers={'Content-Type':'application/json',"
            "'Accept':'application/json, text/event-stream'})\n"
            "try:\n"
            " resp=urllib.request.urlopen(req, timeout=12)\n"
            " sys.stdout.write(str(resp.status))\n"
            "except urllib.error.HTTPError as error:\n"
            " sys.stdout.write(str(error.code)); raise SystemExit(0)\n"
            "except Exception as error:\n"
            " sys.stdout.write(type(error).__name__); raise SystemExit(2)\n"
        )
        http_code, http_stdout, _ = await _exec(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "python",
            "-c",
            http_probe,
            EXCALIDRAW.endpoint,
            timeout=20,
        )
        report["mcp_http_status"] = http_stdout.strip() or http_code
        node_probe = (
            "const url=process.argv[1];"
            "const ac=new AbortController();"
            "setTimeout(()=>ac.abort(),8000);"
            "fetch(url,{method:'POST',headers:{"
            "'content-type':'application/json',"
            "'accept':'application/json, text/event-stream'},"
            "body:JSON.stringify({jsonrpc:'2.0',id:1,method:'initialize',"
            "params:{protocolVersion:'2025-03-26',capabilities:{},"
            "clientInfo:{name:'pwc-qualify',version:'1'}}}),"
            "signal:ac.signal})"
            ".then(async(response)=>{"
            "const text=await response.text();"
            "process.stdout.write(text.includes('Excalidraw')?'sse_ok':'sse_empty');"
            "process.exit(0);"
            "}).catch((error)=>{"
            "process.stdout.write(String(error.cause?.code||error.code||error.name));"
            "process.exit(2);"
            "});"
        )
        node_code, node_stdout, _ = await _exec(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "node",
            "-e",
            node_probe,
            EXCALIDRAW.endpoint,
            timeout=20,
        )
        report["mcp_node_fetch_status"] = node_stdout.strip() or node_code
        get_probe = (
            "const url=process.argv[1];"
            "const ac=new AbortController();"
            "setTimeout(()=>ac.abort(),5000);"
            "fetch(url,{method:'GET',headers:{"
            "'accept':'text/event-stream, application/json'},"
            "signal:ac.signal})"
            ".then(async(response)=>{"
            "process.stdout.write('get_'+response.status);"
            "process.exit(0);"
            "}).catch((error)=>{"
            "process.stdout.write(String(error.cause?.code||error.code||error.name));"
            "process.exit(2);"
            "});"
        )
        get_code, get_stdout, _ = await _exec(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "node",
            "-e",
            get_probe,
            EXCALIDRAW.endpoint,
            timeout=15,
        )
        report["mcp_node_get_status"] = get_stdout.strip() or get_code
        code, stdout, stderr = await _exec(
            sandbox,
            "setpriv",
            "--reuid=pwc-chat",
            "--regid=pwc-chat",
            "--clear-groups",
            "env",
            "HOME=/home/pwc-chat",
            "PI_CODING_AGENT_DIR=/tmp/pwc-qualify-pi",
            "PWC_CHAT_EXCALIDRAW_ENABLED=true",
            "MCP_UI_VIEWER=none",
            "node",
            "--import",
            WORKER_TSX,
            WORKER_QUALIFY,
            timeout=45,
        )
        payload = {}
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                payload = json.loads(line)
                break
        names = payload.get("registered_tool_names") or []
        report["qualify_exit_code"] = code
        mcp_errors = [
            line.strip()
            for line in stderr.splitlines()
            if line.strip().startswith("MCP:")
        ]
        if mcp_errors:
            report["mcp_adapter_errors"] = mcp_errors[:5]
        if not payload:
            report["qualify_error"] = (
                " ".join(line.strip() for line in stderr.splitlines() if line.strip())[
                    :800
                ]
                or "empty_output"
            )
        elif code != 0 and stderr.strip():
            report["mcp_adapter_errors"] = [
                line.strip()[:200]
                for line in stderr.splitlines()
                if line.strip()
                and (
                    "MCP" in line
                    or "connect" in line.lower()
                    or "fetch" in line.lower()
                )
            ][:8] or mcp_errors
        report["pi_inventory"] = {
            "ready": payload.get("ready"),
            "failure_class": payload.get("failure_class"),
            "tool_count": len(names),
            "registered_tool_digest": payload.get("registered_tool_digest"),
            "read_me_ok": payload.get("read_me_ok"),
            "registration_latency_ms": payload.get("registration_latency_ms"),
        }
        if (
            code != 0
            or payload.get("ready") is not True
            or "read_me" not in names
            or "create_view" not in names
        ):
            report["failure_class"] = (
                payload.get("failure_class") or "connected_missing_tools"
            )
            return report
        report["status"] = "passed"
        report["latency_ms"] = round((time.perf_counter() - started) * 1000)
        return report
    finally:
        await adapter.terminate(getattr(sandbox, "object_id", name), sandbox)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit("Refusing Excalidraw MCP qualification without confirmation")
    settings = Settings()
    report = asyncio.run(qualify(settings))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
