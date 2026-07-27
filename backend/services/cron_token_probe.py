"""Safe, rule-based credential probes for CRON dependencies."""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class TokenProbe:
    environment_variable: str
    service: str
    success: bool
    http_status: int | None
    rate_limit_remaining: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "environment_variable": self.environment_variable,
            "service": self.service,
            "success": self.success,
            "http_status": self.http_status,
            "rate_limit_remaining": self.rate_limit_remaining,
            "error": self.error,
        }


TOKEN_PROBES = {
    "PWC_GITHUB_TOKEN_HOT": (
        "GitHub",
        "https://api.github.com/repos/huggingface/transformers",
        lambda token: {
            "Authorization": f"token {token}",
            "User-Agent": "PapersWithCode-Stars/1.0",
        },
    ),
    "PWC_GITHUB_TOKEN": (
        "GitHub",
        "https://api.github.com/repos/huggingface/transformers",
        lambda token: {
            "Authorization": f"token {token}",
            "User-Agent": "PapersWithCode-Stars/1.0",
        },
    ),
    "PWC_OPENROUTER_API_KEY": (
        "OpenRouter",
        "https://openrouter.ai/api/v1/auth/key",
        lambda token: {"Authorization": f"Bearer {token}"},
    ),
    "PWC_HF_TOKEN": (
        "Hugging Face",
        "https://huggingface.co/api/whoami-v2",
        lambda token: {"Authorization": f"Bearer {token}"},
    ),
    "PWC_GEMINI_API_KEY": (
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/models",
        lambda token: {"x-goog-api-key": token},
    ),
    "PWC_SEMANTIC_SCHOLAR_API_KEY": (
        "Semantic Scholar",
        "https://api.semanticscholar.org/graph/v1/paper/DOI:10.18653/v1/N18-3011",
        lambda token: {"x-api-key": token},
    ),
}


def probe_cron_token(environment_variable: str) -> TokenProbe:
    if environment_variable not in TOKEN_PROBES:
        raise ValueError(f"Unsupported CRON token: {environment_variable}")
    token = os.environ.get(environment_variable)
    if not token:
        raise ValueError(f"{environment_variable} is not set")

    service, url, headers_factory = TOKEN_PROBES[environment_variable]
    try:
        response = requests.get(url, headers=headers_factory(token), timeout=15)
    except requests.RequestException as error:
        return TokenProbe(
            environment_variable=environment_variable,
            service=service,
            success=False,
            http_status=None,
            error=str(error),
        )
    return TokenProbe(
        environment_variable=environment_variable,
        service=service,
        success=response.status_code == 200,
        http_status=response.status_code,
        rate_limit_remaining=response.headers.get("x-ratelimit-remaining"),
    )
