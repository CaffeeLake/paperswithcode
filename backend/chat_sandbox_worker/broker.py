"""Local broker process: the only sandbox process holding a turn capability."""

from __future__ import annotations

import hmac
import http.client
import json
import os
import re
import ssl
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, unquote, urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_PAPER_INFO = re.compile(r"^/api/v1/papers/([^/]+)$")
_PAPER_RELATED = re.compile(r"^/api/v1/papers/([^/]+)/related$")
_PAPER_READ = re.compile(r"^/api/v1/research/papers/([^/]+)/read$")
_PAPER_LINEAGE = re.compile(r"^/api/v1/research/papers/([^/]+)/lineage$")
_BENCHMARK_TRENDS = re.compile(r"^/api/v1/tasks/([^/]+)/trending-benchmarks$")
_BENCHMARK_EVALUATIONS = re.compile(r"^/api/v1/datasets/([^/]+)/evaluations/$")


def _load_config() -> dict:
    fd = int(os.environ["PWC_BROKER_CONFIG_FD"])
    with os.fdopen(fd, "rb", closefd=True) as handle:
        config = json.loads(handle.read(16 * 1024))
    required = {
        "capability",
        "gateway_url",
        "session_id",
        "turn_id",
        "proxy_token",
    }
    if set(config) != required:
        raise RuntimeError("Invalid broker configuration")
    return config


CONFIG = _load_config()
UPSTREAM = urlsplit(CONFIG["gateway_url"])
PROXY_CA_PATH = Path("/tmp/pwc-webfetch-ca.pem")
PROXY_GRANTS: dict[str, list[float]] = {}
PROXY_GRANTS_LOCK = Lock()


def _grant_proxy_url(url: str) -> None:
    with PROXY_GRANTS_LOCK:
        PROXY_GRANTS.setdefault(url, []).append(monotonic() + 10)


def _consume_proxy_url(url: str) -> bool:
    now = monotonic()
    with PROXY_GRANTS_LOCK:
        grants = [expiry for expiry in PROXY_GRANTS.pop(url, []) if expiry > now]
        if not grants:
            return False
        if len(grants) > 1:
            PROXY_GRANTS[url] = grants[1:]
        return True


def _connection():
    connection = (
        http.client.HTTPSConnection
        if UPSTREAM.scheme == "https"
        else http.client.HTTPConnection
    )
    return connection(UPSTREAM.hostname, UPSTREAM.port, timeout=180)


def _gateway_headers(*, content_type: str = "application/json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {CONFIG['capability']}",
        "X-PWC-Session": CONFIG["session_id"],
        "X-PWC-Turn": CONFIG["turn_id"],
        "Content-Type": content_type,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "pwc-broker/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _connection(self):
        return _connection()

    def _forward(
        self,
        path: str,
        body: bytes,
        *,
        content_type: str = "application/json",
        accept: str = "application/json",
    ) -> None:
        connection = self._connection()
        prefix = UPSTREAM.path.rstrip("/")
        connection.request(
            "POST",
            f"{prefix}/{path.lstrip('/')}",
            body=body,
            headers={**_gateway_headers(content_type=content_type), "Accept": accept},
        )
        response = connection.getresponse()
        self.send_response(response.status)
        upstream_type = response.getheader("Content-Type")
        if upstream_type:
            self.send_header("Content-Type", upstream_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while chunk := response.read(16 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            connection.close()

    def do_POST(self) -> None:
        length = min(int(self.headers.get("Content-Length", "0")), 512 * 1024)
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        if path == "/proxy-authorize":
            supplied = self.headers.get("X-PWC-Proxy-Token", "")
            if not hmac.compare_digest(supplied, CONFIG["proxy_token"]):
                self.send_error(403)
                return
            try:
                payload = json.loads(body)
                url = payload["url"]
                if not isinstance(url, str) or len(url) > 2000:
                    raise ValueError
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_error(422)
                return
            _grant_proxy_url(url)
            self.send_response(204)
            self.end_headers()
            return
        if path == "/session-store":
            self._forward("session-store", body)
            return
        if path == "/v1/messages":
            self._forward(
                "v1/messages",
                body,
                content_type=self.headers.get("Content-Type", "application/json"),
                accept=self.headers.get("Accept", "application/json"),
            )
            return
        self.send_error(404)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        operation: str | None = None
        arguments: dict = query
        match = None
        if parsed.path == "/api/v1/papers/search":
            operation = "search"
            arguments = {
                "query": query.get("q", ""),
                "page": query.get("page", 1),
                "limit": query.get("page_size", 10),
                "mode": query.get("mode"),
            }
        elif parsed.path in {"/api/v1/papers", "/api/v1/papers/"}:
            operation = "paper_list"
            arguments = {
                **query,
                "all_versions": query.get("latest_only") == "false",
                "include_resources": query.get("include_resources") == "true",
            }
        elif parsed.path == "/api/v1/papers/recent":
            operation = "paper_recent"
        elif parsed.path == "/api/v1/papers/trending":
            operation = "paper_trending"
        elif parsed.path in {"/api/v1/datasets", "/api/v1/datasets/"}:
            operation = "benchmark_list"
            arguments = {
                "page": query.get("page", 1),
                "page_size": query.get("page_size", 50),
                "search": query.get("q"),
                "task": query.get("task"),
                "include_descendants": query.get("include_descendants") == "true",
                "min_eval_count": query.get("min_eval_count"),
                "is_open": query.get("is_open"),
                "order_by": (query.get("ordering") or "name").lstrip("-"),
                "order_dir": "desc"
                if (query.get("ordering") or "").startswith("-")
                else "asc",
            }
        elif match := _BENCHMARK_TRENDS.match(parsed.path):
            operation = "benchmark_trending"
            arguments = {
                "task": unquote(match.group(1)),
                "limit": query.get("limit", 100),
                "min_recent_papers": query.get("min_recent_papers", 0),
                "include_descendants": query.get("include_descendants") == "true",
                "is_open": query.get("is_open"),
            }
        elif match := _BENCHMARK_EVALUATIONS.match(parsed.path):
            operation = "benchmark_evaluations"
            arguments = {
                "dataset": unquote(match.group(1)),
                "page": query.get("page", 1),
                "page_size": query.get("page_size", 100),
                "is_open": query.get("is_open"),
            }
        elif match := _PAPER_RELATED.match(parsed.path):
            operation = "paper_related"
            arguments = {"paper": match.group(1), "limit": query.get("limit", 4)}
        elif match := _PAPER_READ.match(parsed.path):
            operation = "paper_read"
            arguments = {"paper": match.group(1)}
        elif match := _PAPER_LINEAGE.match(parsed.path):
            operation = "paper_lineage_list"
            arguments = {"paper": match.group(1)}
        elif match := _PAPER_INFO.match(parsed.path):
            operation = "paper_info"
            arguments = {
                "paper": match.group(1),
                "include_resources": query.get("include_resources") == "true",
            }
        if operation is None:
            self.send_error(404)
            return
        connection = self._connection()
        payload = json.dumps(
            {"operation": operation, "arguments": arguments}, separators=(",", ":")
        ).encode()
        prefix = UPSTREAM.path.rstrip("/")
        connection.request(
            "POST",
            f"{prefix}/catalog",
            body=payload,
            headers=_gateway_headers(),
        )
        response = connection.getresponse()
        raw = response.read(2 * 1024 * 1024)
        connection.close()
        if response.status >= 400:
            self.send_response(response.status)
            self.end_headers()
            self.wfile.write(raw)
            return
        result = json.loads(raw).get("result")
        if operation == "paper_read":
            output = str(result.get("markdown", "")).encode()
            content_type = "text/plain; charset=utf-8"
        else:
            output = json.dumps(
                result, ensure_ascii=False, separators=(",", ":")
            ).encode()
            content_type = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(output)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(output)


class _CertificateAuthority:
    def __init__(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="pwc-webfetch-", dir="/var/empty/pwc-broker"
        )
        self.directory = Path(self.temporary_directory.name)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        name = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, "PwC WebFetch Ephemeral CA")]
        )
        self.certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .sign(self.key, hashes.SHA256())
        )
        PROXY_CA_PATH.write_bytes(
            self.certificate.public_bytes(serialization.Encoding.PEM)
        )
        PROXY_CA_PATH.chmod(0o644)
        self.contexts: dict[str, ssl.SSLContext] = {}

    def context(self, host: str) -> ssl.SSLContext:
        if host in self.contexts:
            return self.contexts[host]
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self.certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(minutes=30))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False
            )
            .sign(self.key, hashes.SHA256())
        )
        stem = str(len(self.contexts))
        cert_path = self.directory / f"{stem}.crt"
        key_path = self.directory / f"{stem}.key"
        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        cert_path.chmod(0o600)
        key_path.chmod(0o600)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        self.contexts[host] = context
        return context


CERTIFICATES: _CertificateAuthority | None = None


class OriginHandler(BaseHTTPRequestHandler):
    server_version = "pwc-webfetch-proxy/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_GET(self) -> None:
        host = str(getattr(self.server, "target_host", ""))
        requested_host = (self.headers.get("Host") or "").partition(":")[0].lower()
        if (
            not host
            or requested_host != host
            or self.path.startswith(("http://", "https://"))
        ):
            self.send_error(403)
            return
        body = json.dumps(
            {"url": f"https://{host}{self.path}"}, separators=(",", ":")
        ).encode()
        url = json.loads(body)["url"]
        if not _consume_proxy_url(url):
            self.send_error(403)
            return
        connection = _connection()
        prefix = UPSTREAM.path.rstrip("/")
        connection.request(
            "POST",
            f"{prefix}/web-fetch",
            body=body,
            headers=_gateway_headers(),
        )
        response = connection.getresponse()
        self.send_response(response.status)
        for header in ("Content-Type", "Content-Length"):
            if value := response.getheader(header):
                self.send_header(header, value)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while chunk := response.read(16 * 1024):
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            connection.close()


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "pwc-webfetch-connect/1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_CONNECT(self) -> None:
        try:
            parsed = urlsplit(f"//{self.path}")
            host = parsed.hostname
            if (
                not host
                or not host.isascii()
                or parsed.port not in {None, 443}
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError
        except ValueError:
            self.send_error(400)
            return
        assert CERTIFICATES is not None
        self.send_response(200, "Connection Established")
        self.end_headers()
        try:
            connection = CERTIFICATES.context(host.lower()).wrap_socket(
                self.connection, server_side=True
            )
            server = type("OriginServer", (), {"target_host": host.lower()})()
            OriginHandler(connection, self.client_address, server)
        except (OSError, ssl.SSLError):
            return


def main() -> int:
    global CERTIFICATES
    CERTIFICATES = _CertificateAuthority()
    broker = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    proxy = ThreadingHTTPServer(("127.0.0.1", 8766), ProxyHandler)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    broker.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
