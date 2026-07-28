#!/usr/bin/env python3
"""Read-only release and HTTP smoke checks used by deploys and monitoring."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from deploy.release import profile_features
except ModuleNotFoundError:
    from release import profile_features  # type: ignore[no-redef]

ASSET_RE = re.compile(
    r"""(?:src|href)=["'](?P<url>/assets/[^"'?#]+\.(?P<kind>js|css))(?:[?#][^"']*)?["']"""
)
PAPER_LINK_RE = re.compile(rb'href=["\']/paper/[^"\']+["\']')


class DiscoveryHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paper_links = 0
        self.entity_links = 0
        self.discovery_documents = 0
        self.h1_count = 0
        self.canonicals: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        attributes = dict(attrs)
        if attributes.get("data-pwc-initial-document") == "discovery":
            self.discovery_documents += 1
        if tag == "h1":
            self.h1_count += 1
        if tag == "link" and attributes.get("rel") == "canonical":
            self.canonicals.append(attributes.get("href", ""))
        if tag != "a":
            return
        href = attributes.get("href", "")
        if href.startswith("/paper/"):
            self.paper_links += 1
        elif href.startswith(
            ("/tasks/", "/methods/", "/benchmark/", "/conferences/", "/authors/")
        ):
            self.entity_links += 1


def header_value(headers: dict, name: str) -> str:
    expected = name.lower()
    return next(
        (str(value) for key, value in headers.items() if key.lower() == expected),
        "",
    )


def _run_markdown_smoke(base_url: str) -> list[str]:
    failures: list[str] = []
    pages = (
        ("/", "/", 100_000),
        ("/paper/2607.24653", "/paper/2607.24653", 250_000),
        ("/tasks/image-classification", "/tasks/image-classification", 100_000),
        ("/papers/recent", "/papers/recent", 250_000),
    )
    for path, canonical_path, byte_limit in pages:
        status, headers, body = request(
            urljoin(base_url, path),
            headers={"Accept": "text/markdown"},
        )
        content_type = header_value(headers, "Content-Type").lower()
        vary = {
            item.strip().lower() for item in header_value(headers, "Vary").split(",")
        }
        canonical = f"https://paperswithcode.co{canonical_path}"
        text = body.decode("utf-8", "replace")
        if status != 200:
            failures.append(f"Markdown {path} returned {status}")
        if not content_type.startswith("text/markdown"):
            failures.append(f"Markdown {path} returned {content_type or 'no type'}")
        if "accept" not in vary:
            failures.append(f"Markdown {path} is missing Vary: Accept")
        if canonical not in header_value(headers, "Link"):
            failures.append(f"Markdown {path} canonical Link is missing")
        if not text.startswith("---\n") or not any(
            line.startswith("# ") for line in text.splitlines()
        ):
            failures.append(f"Markdown {path} has no frontmatter and H1")
        lowered = text.lower()
        if any(marker in lowered for marker in ("<html", "<script", "/assets/")):
            failures.append(f"Markdown {path} contains frontend HTML or assets")
        if len(body) > byte_limit:
            failures.append(f"Markdown {path} exceeds {byte_limit} bytes ({len(body)})")
    return failures


def run_seo_http_smoke(base_url: str, environment: str = "production") -> list[str]:
    """Qualify raw paper HTML, canonical errors, discovery HTML, and XML."""
    failures: list[str] = []
    status, headers, body = request(urljoin(base_url, "/robots.txt"))
    robots = body.decode("utf-8", "replace")
    if status != 200 or "text/plain" not in header_value(headers, "Content-Type"):
        failures.append(f"robots returned {status} non-text")
    elif any(
        marker in robots.lower() for marker in ("<!doctype", "<html", 'id="root"')
    ):
        failures.append("robots contains SPA HTML")
    elif environment == "staging":
        if "User-agent: *\nDisallow: /" not in robots or "Sitemap:" in robots:
            failures.append("staging robots does not disallow crawling")
    elif robots.count("Sitemap: https://paperswithcode.co/sitemap.xml") != 1:
        failures.append("production robots sitemap directive is missing or duplicated")

    status, headers, body = request(urljoin(base_url, "/paper/2607.24653"))
    paper_html = body.decode("utf-8", "replace")
    if status != 200:
        failures.append(f"SEO paper returned {status}")
    else:
        for marker in (
            'data-pwc-initial-document="paper"',
            "<h1>Kimi K3: Open Frontier Intelligence</h1>",
            'id="abstract-heading"',
            'name="citation_arxiv_id" content="2607.24653"',
            'type="application/ld+json"',
        ):
            if marker not in paper_html:
                failures.append(f"SEO paper is missing {marker}")
        if "paperswithcode.co/paper/2607.24653" not in header_value(headers, "Link"):
            failures.append("SEO paper canonical Link header is missing")

    status, _, _ = request(urljoin(base_url, "/paper/9999.99999"))
    if status != 404:
        failures.append(f"missing SEO paper returned {status}")
    status, headers, _ = request(
        urljoin(base_url, "/papers/2607.24653"), allow_redirects=False
    )
    if status != 301 or header_value(headers, "Location") != "/paper/2607.24653":
        failures.append("legacy paper route is not a direct canonical 301")

    status, headers, body = request(urljoin(base_url, "/sitemap.xml"))
    sitemap_locations: list[str] = []
    if status != 200 or "xml" not in header_value(headers, "Content-Type"):
        failures.append(f"sitemap index returned {status} non-XML")
    else:
        try:
            root = ElementTree.fromstring(body)
            sitemap_locations = [
                node.text
                for node in root.iter()
                if node.tag.endswith("loc") and node.text
            ]
            shard = next(
                (
                    node.text
                    for node in root.iter()
                    if node.tag.endswith("loc")
                    and node.text
                    and "/sitemaps/papers-" in node.text
                ),
                None,
            )
            if not shard:
                failures.append("sitemap index has no paper shard")
            else:
                shard_candidate_url = urljoin(base_url, urlsplit(shard).path)
                shard_status, shard_headers, shard_body = request(shard_candidate_url)
                if shard_status != 200 or "xml" not in header_value(
                    shard_headers, "Content-Type"
                ):
                    failures.append("paper sitemap shard returned non-XML")
                else:
                    ElementTree.fromstring(shard_body)
        except (ElementTree.ParseError, StopIteration):
            failures.append("sitemap XML did not parse")

    status, _, body = request(urljoin(base_url, "/papers/recent"))
    if status != 200 or not PAPER_LINK_RE.search(body):
        failures.append(f"recent paper archive returned {status} without paper links")

    status, _, body = request(urljoin(base_url, "/"))
    parser = DiscoveryHTMLParser()
    if status == 200:
        parser.feed(body.decode("utf-8", "replace"))
    if (
        status != 200
        or parser.discovery_documents != 1
        or parser.paper_links < 20
        or parser.entity_links < 5
    ):
        failures.append(
            f"homepage discovery HTML returned {status} with "
            f"{parser.paper_links} paper links and {parser.entity_links} entity links"
        )

    entity_sitemaps = (
        "tasks",
        "methods",
        "benchmarks",
        "conferences",
        "organizations",
        "authors-",
    )
    for entity_kind in entity_sitemaps:
        sitemap_url = next(
            (
                location
                for location in sitemap_locations
                if f"/sitemaps/{entity_kind}" in location
            ),
            None,
        )
        if sitemap_url is None:
            failures.append(f"sitemap index has no {entity_kind} entity sitemap")
            continue
        entity_status, entity_headers, entity_body = request(
            urljoin(base_url, urlsplit(sitemap_url).path)
        )
        if entity_status != 200 or "xml" not in header_value(
            entity_headers, "Content-Type"
        ):
            failures.append(f"{entity_kind} entity sitemap returned non-XML")
            continue
        try:
            entity_root = ElementTree.fromstring(entity_body)
            entity_url = next(
                node.text
                for node in entity_root.iter()
                if node.tag.endswith("loc") and node.text
            )
        except (ElementTree.ParseError, StopIteration):
            failures.append(f"{entity_kind} entity sitemap has no URL")
            continue
        page_status, _, page_body = request(
            urljoin(base_url, urlsplit(entity_url).path)
        )
        page_parser = DiscoveryHTMLParser()
        if page_status == 200:
            page_parser.feed(page_body.decode("utf-8", "replace"))
        if (
            page_status != 200
            or page_parser.discovery_documents != 1
            or page_parser.h1_count != 1
            or page_parser.paper_links < 1
            or entity_url not in page_parser.canonicals
        ):
            failures.append(
                f"{entity_kind} sitemap sample is not indexable discovery HTML"
            )
    failures.extend(_run_markdown_smoke(base_url))
    return failures


def request(
    url: str,
    *,
    allow_redirects: bool = True,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict, bytes]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = (
        urllib.request.build_opener()
        if allow_redirects
        else urllib.request.build_opener(NoRedirect())
    )
    try:
        with opener.open(
            urllib.request.Request(
                url,
                headers={"User-Agent": "pwc-smoke/1", **(headers or {})},
            ),
            timeout=20,
        ) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def validate_local_bundle(
    release_dir: Path, expected_features: dict[str, bool] | bool
) -> list[str]:
    failures: list[str] = []
    dist = release_dir / "frontend-dist"
    try:
        features = json.loads((dist / "features.json").read_text())
        if isinstance(expected_features, bool):
            manifest = json.loads((release_dir / "release.json").read_text())
            expected_features = manifest.get(
                "frontend_features", {"chat": expected_features}
            )
        if features != expected_features:
            failures.append(f"unexpected frontend features: {features!r}")
        html = (dist / "index.html").read_text()
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read frontend bundle: {exc}"]
    if "/src/main.tsx" in html:
        failures.append("frontend references /src/main.tsx")
    assets = list(ASSET_RE.finditer(html))
    if not any(match.group("kind") == "js" for match in assets):
        failures.append("no JavaScript asset found")
    for match in assets:
        path = dist / match.group("url").removeprefix("/")
        if not path.is_file():
            failures.append(f"missing asset: {match.group('url')}")
        expected_mime = (
            "text/css" if match.group("kind") == "css" else "text/javascript"
        )
        guessed = mimetypes.guess_type(path.name)[0]
        if guessed not in {expected_mime, "application/javascript"}:
            failures.append(f"unexpected local MIME for {path.name}: {guessed}")
    return failures


def run_http_smoke(
    environment: str,
    base_url: str,
    *,
    expected_release: str | None = None,
    monitor_subset: bool = False,
    candidate: bool = False,
) -> list[str]:
    failures: list[str] = []
    status, _, body = request(urljoin(base_url, "/health"))
    if status != 200:
        failures.append(f"/health returned {status}")
    else:
        try:
            health = json.loads(body)
            if expected_release and health.get("release_id") != expected_release:
                failures.append("/health release ID mismatch")
        except json.JSONDecodeError:
            failures.append("/health did not return JSON")

    if environment == "staging":
        if candidate:
            failures.extend(run_seo_http_smoke(base_url, environment))
            status, _, _ = request(urljoin(base_url, "/api/v1/papers/1"))
            if status not in {200, 404}:
                failures.append(f"numeric paper API returned {status}")
            status, _, _ = request(urljoin(base_url, "/api/v1/chat/sessions"))
            if status not in {401, 403}:
                failures.append(f"staging chat auth boundary returned {status}")
            return failures
        status, _, _ = request(urljoin(base_url, "/"), allow_redirects=False)
        if status not in {302, 401, 403}:
            failures.append(f"staging / was not admin-gated: {status}")
        return failures

    if candidate:
        failures.extend(run_seo_http_smoke(base_url, environment))
        status, _, body = request(
            urljoin(base_url, "/api/v1/papers/?page=1&page_size=1")
        )
        if status != 200:
            failures.append(f"paper API returned {status}")
        else:
            try:
                json.loads(body)
            except json.JSONDecodeError:
                failures.append("paper API did not return JSON")
        status, _, _ = request(urljoin(base_url, "/api/v1/chat/sessions"))
        if status not in {404, 405}:
            failures.append(f"production chat API is reachable: {status}")
        return failures

    for path in ("/", "/paper/2605.13517"):
        status, headers, body = request(urljoin(base_url, path))
        if status != 200:
            failures.append(f"{path} returned {status}")
            continue
        html = body.decode("utf-8", "replace")
        if "/src/main.tsx" in html:
            failures.append(f"{path} references /src/main.tsx")
        if path.startswith("/paper/"):
            assets = list(ASSET_RE.finditer(html))
            if not assets:
                failures.append("paper page has no built assets")
            for match in assets:
                asset_status, asset_headers, _ = request(
                    urljoin(base_url, match.group("url"))
                )
                content_type = asset_headers.get("Content-Type", "").split(";")[0]
                allowed = (
                    {"text/css"}
                    if match.group("kind") == "css"
                    else {"text/javascript", "application/javascript"}
                )
                if asset_status != 200 or content_type not in allowed:
                    failures.append(
                        f"{match.group('url')} returned {asset_status} {content_type}"
                    )
    if monitor_subset:
        return failures
    status, _, body = request(urljoin(base_url, "/api/v1/papers/?page=1&page_size=1"))
    if status != 200:
        failures.append(f"paper API returned {status}")
    else:
        try:
            json.loads(body)
        except json.JSONDecodeError:
            failures.append("paper API did not return JSON")
    status, _, _ = request(urljoin(base_url, "/api/v1/chat/sessions"))
    if status not in {404, 405}:
        failures.append(f"production chat API is reachable: {status}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--environment", choices=("production", "staging"), required=True
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-release")
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--monitor-subset", action="store_true")
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    failures = []
    if args.release_dir:
        failures.extend(
            validate_local_bundle(args.release_dir, profile_features(args.environment))
        )
    failures.extend(
        run_http_smoke(
            args.environment,
            args.base_url,
            expected_release=args.expected_release,
            monitor_subset=args.monitor_subset,
            candidate=args.candidate,
        )
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"{args.environment} smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
