"""Job-scoped HTTP helper; intentionally contains no database configuration."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request

USER_AGENT = "PapersWithCode-Curation/1.0 (+https://paperswithcode.co)"


def request_json(
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    timeout: int = 30,
) -> dict:
    base = os.environ["PWC_CURATION_API_URL"].rstrip("/")
    job_id = os.environ["PWC_CURATION_JOB_ID"]
    token = os.environ["PWC_CURATION_JOB_TOKEN"]
    data = json.dumps(payload).encode() if payload is not None else None
    response = urllib.request.urlopen(
        urllib.request.Request(
            f"{base}/admin/codex-curation/jobs/{job_id}/{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method=method,
        ),
        timeout=timeout,
    )
    raw = response.read().decode()
    return json.loads(raw)


def request(
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    timeout: int = 30,
) -> dict:
    result = request_json(path, method, payload, timeout)
    print(json.dumps(result))
    return result


def wait_for_thumbnail(timeout_seconds: int, poll_seconds: int = 5) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        result = request_json("thumbnail")
        thumbnail = result["thumbnail"]
        if thumbnail["status"] in {"not_requested", "succeeded", "failed"}:
            print(json.dumps(result))
            return result
        if time.monotonic() >= deadline:
            print(json.dumps(result))
            return result
        time.sleep(min(poll_seconds, max(0, deadline - time.monotonic())))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("context")
    taxonomy = sub.add_parser("taxonomy")
    taxonomy.add_argument("query")
    leaderboards = sub.add_parser("leaderboards")
    leaderboards.add_argument("query")
    apply = sub.add_parser("apply")
    apply.add_argument("json_file")
    thumbnail_status = sub.add_parser("thumbnail-status")
    thumbnail_status.add_argument("--wait-seconds", type=int, default=240)
    thumbnail_status.add_argument("--poll-seconds", type=int, default=5)
    args = parser.parse_args()
    if args.command == "context":
        request("context")
    elif args.command == "taxonomy":
        request(f"taxonomy?q={urllib.parse.quote(args.query)}")
    elif args.command == "leaderboards":
        request(f"leaderboards?q={urllib.parse.quote(args.query)}")
    elif args.command == "thumbnail-status":
        wait_for_thumbnail(args.wait_seconds, args.poll_seconds)
    else:
        with open(args.json_file, encoding="utf-8") as handle:
            request("apply", "POST", json.load(handle), timeout=300)


if __name__ == "__main__":
    main()
