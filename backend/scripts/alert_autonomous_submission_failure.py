"""Send a content-free alert when scheduled submission review fails."""

from __future__ import annotations

import httpx

from backend.config import Settings, get_settings


def build_alert_payload(settings: Settings) -> dict[str, str]:
    return {
        "text": (
            "PwC autonomous submission review failed; severity=critical; "
            f"environment={settings.environment}; release={settings.release_id}; "
            f"runbook={settings.autonomous_alert_runbook_url or 'not-configured'}"
        )
    }


def send_failure_alert(settings: Settings) -> str:
    payload = build_alert_payload(settings)
    routes = (
        ("primary", settings.autonomous_alert_slack_webhook_url),
        ("fallback", settings.autonomous_alert_fallback_webhook_url),
    )
    with httpx.Client(timeout=5) as client:
        for name, url in routes:
            if not url:
                continue
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            return name
    raise RuntimeError("autonomous submission failure alert delivery failed")


def main() -> int:
    delivered = send_failure_alert(get_settings())
    print(f"autonomous submission failure alert delivered via {delivered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
