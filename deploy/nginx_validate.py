#!/usr/bin/env python3
"""Static cross-environment safety checks for checked-in nginx templates."""

from __future__ import annotations

import argparse
from pathlib import Path

CURATION_CALLBACK_LOCATION = (
    'location ~ "^/api/v1/admin/codex-curation/jobs/'
    "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    '(context|taxonomy|leaderboards|apply|complete)$"'
)
SEO_LOCATIONS = (
    "location = /robots.txt",
    "location = /sitemap.xml",
    "location ^~ /sitemaps/",
    "location = /papers/recent",
    "location = /papers/archive",
    r'location ~ "^/papers/archive/[0-9]{4}(/[0-9]{2})?$"',
    "location = / {",
    r'location ~ "^/(tasks|task|methods|benchmark|conferences|authors|organizations)/[^/]+(/[^/]+)?$"',
)
SHARE_PAGE_LOCATION = (
    r'location ~ "^/share/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-'
    r'[0-9a-f]{4}-[0-9a-f]{12}$"'
)
SHARE_API_LOCATION = (
    r'location ~ "^/api/v1/chat/shares/[0-9a-f]{8}-[0-9a-f]{4}-'
    r'[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"'
)


def _validate_seo_routes(config: str, backend: str, environment: str) -> list[str]:
    failures: list[str] = []
    catch_all = config.find("location / {")
    for location in SEO_LOCATIONS:
        index = config.find(location)
        if index < 0:
            failures.append(f"{environment} SEO route is missing: {location}")
            continue
        if catch_all >= 0 and index > catch_all:
            failures.append(
                f"{environment} SEO route follows the SPA catch-all: {location}"
            )
        line_end = config.find("\n", index)
        block_end = config.find("}", line_end)
        block = config[index : block_end + 1]
        if f"proxy_pass http://{backend};" not in block:
            failures.append(f"{environment} SEO route misses {backend}: {location}")
        if "try_files" in block or "index.html" in block:
            failures.append(
                f"{environment} SEO route falls through to SPA HTML: {location}"
            )
    return failures


def location_block(config: str, location: str) -> str:
    """Return a complete nginx location block, including nested limit blocks."""

    start = config.find(location)
    if start < 0:
        return ""
    opening = config.find("{", start + len(location))
    if opening < 0:
        return ""
    depth = 0
    for index in range(opening, len(config)):
        if config[index] == "{":
            depth += 1
        elif config[index] == "}":
            depth -= 1
            if depth == 0:
                return config[start : index + 1]
    return ""


def validate(production: str, staging: str) -> list[str]:
    failures: list[str] = []
    if "pwc_staging_backend" in production or "127.0.0.1:8001" in production:
        failures.append("production references staging backend")
    if "pwc_production_backend" in staging or "127.0.0.1:8000" in staging:
        failures.append("staging references production backend")
    if "/environments/production/current/frontend-dist" not in production:
        failures.append("production root is not its current release")
    if "/environments/staging/current/frontend-dist" not in staging:
        failures.append("staging root is not its current release")
    if "8081" in staging or "proxy_set_header Upgrade" in staging:
        failures.append("staging exposes Vite/HMR")
    access_block = location_block(staging, "location = /_staging_access_check")
    if (
        not access_block
        or "internal;" not in access_block
        or "/api/v1/auth/staging-check" not in access_block
    ):
        failures.append("staging access-check contract is invalid")
    if "_staging_access_check" in production:
        failures.append("production acquires staging-wide admission gate")
    if CURATION_CALLBACK_LOCATION not in staging:
        failures.append("staging job-token callback route is missing")
    else:
        callback_block = staging.split(CURATION_CALLBACK_LOCATION, 1)[1].split("}", 1)[
            0
        ]
        if "auth_request" in callback_block:
            failures.append("staging job-token callback route uses browser auth")
        if "proxy_pass http://pwc_staging_backend;" not in callback_block:
            failures.append("staging job-token callback route misses staging backend")
    gateway_host = "server_name chat-gateway-staging.paperswithcode.co;"
    if gateway_host not in staging:
        failures.append("staging chat gateway hostname is missing")
    for endpoint in ("catalog", "session-store", "web-fetch", "v1/messages"):
        location = f"location = /api/internal/chat-gateway/{endpoint}"
        if location not in staging:
            failures.append(f"staging chat gateway {endpoint} route is missing")
    if "client_max_body_size 512k;" not in staging:
        failures.append("staging chat gateway body limit is missing")
    if staging.count("location / {") != 1 or production.count("location / {") != 1:
        failures.append("ambiguous catch-all location")
    failures.extend(
        _validate_seo_routes(production, "pwc_production_backend", "production")
    )
    failures.extend(_validate_seo_routes(staging, "pwc_staging_backend", "staging"))
    staging_robots = staging.split("location = /robots.txt", 1)
    if len(staging_robots) == 2:
        robots_block = staging_robots[1].split("}", 1)[0]
        if "auth_request" in robots_block:
            failures.append("staging robots route is browser-authenticated")
    if "try_files $uri @public_pages;" not in production:
        failures.append("production public-page fallback is missing")
    if "try_files $uri @staging_public_pages;" not in staging:
        failures.append("staging public-page fallback is missing")
    for config, backend, environment in (
        (production, "pwc_production_backend", "production"),
        (staging, "pwc_staging_backend", "staging"),
    ):
        if SHARE_PAGE_LOCATION not in config:
            failures.append(f"{environment} public share page route is missing")
        else:
            block = location_block(config, SHARE_PAGE_LOCATION)
            if "auth_request" in block:
                failures.append(f"{environment} public share page uses browser auth")
            if 'X-Robots-Tag "noindex, nofollow" always' not in block:
                failures.append(f"{environment} public share page permits indexing")
            if 'Cache-Control "no-store"' not in block:
                failures.append(f"{environment} public share page may be cached")
        if SHARE_API_LOCATION not in config:
            failures.append(f"{environment} public share API route is missing")
        else:
            block = location_block(config, SHARE_API_LOCATION)
            if "auth_request" in block:
                failures.append(f"{environment} public share API uses browser auth")
            if f"proxy_pass http://{backend};" not in block:
                failures.append(f"{environment} public share API misses {backend}")
            if "limit_except GET" not in block:
                failures.append(f"{environment} public share API accepts writes")
    assets = staging.split("location ^~ /assets/", 1)
    if len(assets) != 2 or "auth_request" in assets[1].split("}", 1)[0]:
        failures.append("staging hashed assets are browser-authenticated")
    auth_me = staging.split("location = /api/v1/auth/me", 1)
    if len(auth_me) != 2 or "auth_request" in auth_me[1].split("}", 1)[0]:
        failures.append("staging auth status route is browser-authenticated")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent / "nginx"
    )
    args = parser.parse_args()
    failures = validate(
        (args.root / "paperswithcode.co.conf").read_text(),
        (args.root / "staging.paperswithcode.co.conf").read_text(),
    )
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
