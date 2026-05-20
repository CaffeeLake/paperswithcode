#!/usr/bin/env python3
"""
Check OpenRouter API usage and remaining quota.

This script checks the current API usage for your OpenRouter account
and provides recommendations for batch processing.

Usage:
    uv run --env-file backend/keys.env backend/utils/check_openrouter_usage.py
"""

import asyncio
import aiohttp
from backend.config import get_settings


async def check_openrouter_usage():
    """Check OpenRouter API usage and rate limits."""
    settings = get_settings()
    api_key = settings.openrouter_api_key

    if not api_key:
        print("❌ No OpenRouter API key found in environment")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://openrouter.ai/api/v1/key", headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"❌ API Error {response.status}: {error_text}")
                    return None

                data = await response.json()
                return data.get("data", {})

    except Exception as e:
        print(f"❌ Error checking API usage: {e}")
        return None


def analyze_usage_data(usage_data):
    """Analyze usage data and provide recommendations."""
    if not usage_data:
        return

    usage = usage_data.get("usage", 0)
    limit = usage_data.get("limit")
    is_free_tier = usage_data.get("is_free_tier", True)
    label = usage_data.get("label", "Unknown")

    print("=" * 60)
    print("📊 OPENROUTER API USAGE STATUS")
    print("=" * 60)
    print(f"🏷️  API Key Label: {label}")
    print(f"💰 Account Type: {'Free Tier' if is_free_tier else 'Paid Tier'}")
    print(f"📈 Credits Used: {usage}")

    if limit is not None:
        remaining = limit - usage
        print(f"🎯 Credit Limit: {limit}")
        print(f"✅ Credits Remaining: {remaining}")

        if remaining <= 0:
            print("🚫 NO CREDITS REMAINING - Cannot process more papers today")
            return False

        # Calculate processing capacity
        print("\n📋 PROCESSING CAPACITY:")
        print(f"   • Remaining credits can process ~{remaining} papers")

        if is_free_tier:
            # Free tier limits
            daily_free_limit = 50 if usage < 10 else 1000 if usage >= 10 else 50
            print(f"   • Free tier daily limit: {daily_free_limit} requests")

            if remaining < daily_free_limit:
                print(f"   • Limited by credits: {remaining} papers max")
            else:
                print(f"   • Limited by daily quota: {daily_free_limit} papers max")

        return remaining > 0
    else:
        print("🔄 Unlimited Credits")
        if is_free_tier:
            daily_free_limit = 50 if usage < 10 else 1000
            print(f"   • Free tier daily limit: {daily_free_limit} requests")
            print(f"   • Can process ~{daily_free_limit} papers today")
        else:
            print("   • No daily limits (paid tier)")
        return True


def provide_recommendations(usage_data):
    """Provide recommendations based on usage data."""
    if not usage_data:
        return

    is_free_tier = usage_data.get("is_free_tier", True)
    usage = usage_data.get("usage", 0)
    limit = usage_data.get("limit")

    print("\n💡 RECOMMENDATIONS:")

    if is_free_tier:
        if usage < 10:
            print("   • You're on free tier with <10 credits purchased")
            print("   • Daily limit: 50 free requests")
            print("   • Consider purchasing 10+ credits to unlock 1000 daily requests")
        else:
            print("   • You have 1000 free requests per day (purchased 10+ credits)")

        print("   • Free models end with ':free' (e.g., 'x-ai/grok-4.3:free')")

        if limit and (limit - usage) < 100:
            print("   • ⚠️  Low credits remaining - consider upgrading to paid tier")
            print("   • Paid tier removes daily limits and provides more models")
    else:
        print("   • You're on paid tier - no daily limits")
        print("   • Can process large batches efficiently")

    print("\n🚀 BATCH PROCESSING SUGGESTIONS:")

    if is_free_tier:
        remaining = (limit - usage) if limit else 1000
        daily_limit = 50 if usage < 10 else 1000
        max_today = min(remaining, daily_limit) if limit else daily_limit

        print(f"   • Max papers today: ~{max_today}")
        print("   • Recommended batch size: 10-20 papers")
        print(f"   • Use: --limit {max_today} --batch-size 20")
    else:
        print("   • No daily limits - can process thousands of papers")
        print("   • Recommended batch size: 50-100 papers")
        print("   • Use: --limit 5000 --batch-size 50 --paid-tier")


async def main():
    """Main function to check usage and provide recommendations."""
    print("🔍 Checking OpenRouter API usage...")

    usage_data = await check_openrouter_usage()

    if usage_data:
        can_process = analyze_usage_data(usage_data)
        provide_recommendations(usage_data)

        if can_process:
            print("\n✅ Ready to process more papers!")
            print("📝 Example command:")

            is_free_tier = usage_data.get("is_free_tier", True)
            if is_free_tier:
                usage = usage_data.get("usage", 0)
                limit = usage_data.get("limit")
                remaining = (limit - usage) if limit else 1000
                daily_limit = 50 if usage < 10 else 1000
                max_today = min(remaining, daily_limit) if limit else daily_limit

                print(
                    f"   uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --limit {max_today} --batch-size 20"
                )
            else:
                print(
                    "   uv run --env-file backend/keys.env -m backend.database.repos_and_pages_setup.batch_extract --limit 5000 --batch-size 50 --paid-tier"
                )
        else:
            print("\n🛑 Cannot process more papers today")
            print("💳 Consider upgrading to paid tier for unlimited processing")
    else:
        print("❌ Could not retrieve usage information")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
