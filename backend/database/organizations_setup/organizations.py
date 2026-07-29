"""Strict, reviewable launch manifest for featured Hugging Face organizations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeaturedOrganization:
    hf_slug: str
    slug: str
    display_order: int
    name_override: str | None = None


FEATURED_ORGANIZATIONS: tuple[FeaturedOrganization, ...] = (
    FeaturedOrganization("microsoft", "microsoft", 1),
    FeaturedOrganization("google", "google", 2),
    FeaturedOrganization("nvidia", "nvidia", 3),
    FeaturedOrganization("Anthropic", "anthropic", 4),
    FeaturedOrganization("deepseek-ai", "deepseek-ai", 5),
    FeaturedOrganization("meta-llama", "meta-llama", 6),
    FeaturedOrganization("Qwen", "qwen", 7),
    FeaturedOrganization("black-forest-labs", "black-forest-labs", 8),
    FeaturedOrganization("stabilityai", "stabilityai", 9),
    FeaturedOrganization("moonshotai", "moonshotai", 10),
    FeaturedOrganization("facebook", "facebook", 11),
    FeaturedOrganization("zai-org", "zai-org", 12),
    FeaturedOrganization("ByteDance", "bytedance", 13),
    FeaturedOrganization("ByteDance-Seed", "bytedance-seed", 14),
    FeaturedOrganization("mistralai", "mistralai", 15, "Mistral AI"),
    FeaturedOrganization("allenai", "allenai", 16),
    FeaturedOrganization("xai-org", "xai-org", 17),
    FeaturedOrganization("openai", "openai", 18),
    FeaturedOrganization("apple", "apple", 19),
    FeaturedOrganization("tencent", "tencent", 20),
    FeaturedOrganization("MiniMaxAI", "minimaxai", 21),
)


def normalize_hf_handle(value: str) -> str:
    return value.strip().lower()


BY_HF_SLUG = {
    normalize_hf_handle(item.hf_slug): item for item in FEATURED_ORGANIZATIONS
}
BY_PWC_SLUG = {item.slug: item for item in FEATURED_ORGANIZATIONS}

if len(BY_HF_SLUG) != len(FEATURED_ORGANIZATIONS):
    raise RuntimeError("Featured organization HF handles must be unique")
if len(BY_PWC_SLUG) != len(FEATURED_ORGANIZATIONS):
    raise RuntimeError("Featured organization PwC slugs must be unique")
if sorted(item.display_order for item in FEATURED_ORGANIZATIONS) != list(
    range(1, len(FEATURED_ORGANIZATIONS) + 1)
):
    raise RuntimeError("Featured organization display_order must be contiguous")


def featured_for_hf_handle(value: str | None) -> FeaturedOrganization | None:
    if not value:
        return None
    return BY_HF_SLUG.get(normalize_hf_handle(value))
