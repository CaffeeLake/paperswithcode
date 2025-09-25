#!/usr/bin/env python3
"""
Calculate time and space estimates for downloading all 2025 papers.
"""


def calculate_2025_estimates():
    """Calculate estimates based on our test download."""

    # Data from our test
    test_papers = 10
    test_time_minutes = 7  # Approximately 7 minutes for 10 papers
    test_size_mb = 59.5  # 59.5 MB for 10 papers

    # Target: All 2025 papers
    total_2025_papers = 14061

    # Calculate averages from test
    avg_time_per_paper = test_time_minutes / test_papers  # minutes per paper
    avg_size_per_paper = test_size_mb / test_papers  # MB per paper

    # Calculate totals
    total_time_minutes = total_2025_papers * avg_time_per_paper
    total_size_mb = total_2025_papers * avg_size_per_paper

    # Convert to more readable units
    total_time_hours = total_time_minutes / 60
    total_time_days = total_time_hours / 24
    total_size_gb = total_size_mb / 1024

    print("📊 2025 ARXIV PAPERS DOWNLOAD ESTIMATES")
    print("=" * 50)
    print(f"🎯 Target papers: {total_2025_papers:,}")
    print()

    print("📈 Based on test results:")
    print(f"   • Test papers: {test_papers}")
    print(f"   • Test time: {test_time_minutes} minutes")
    print(f"   • Test size: {test_size_mb:.1f} MB")
    print("   • Success rate: 100%")
    print()

    print("⏱️  TIME ESTIMATES:")
    print(f"   • Per paper: {avg_time_per_paper:.1f} minutes")
    print(f"   • Total time: {total_time_minutes:,.0f} minutes")
    print(f"   • Total time: {total_time_hours:,.1f} hours")
    print(f"   • Total time: {total_time_days:.1f} days")
    print()

    print("💾 SPACE ESTIMATES:")
    print(f"   • Per paper: {avg_size_per_paper:.1f} MB")
    print(f"   • Total size: {total_size_mb:,.0f} MB")
    print(f"   • Total size: {total_size_gb:.1f} GB")
    print()

    print("🔥 OPTIMIZATION SCENARIOS:")
    print()

    # Scenario 1: Faster rate limiting
    faster_time_per_paper = 0.3  # 18 seconds average instead of 42
    faster_total_hours = (total_2025_papers * faster_time_per_paper) / 60
    print("📈 Scenario 1: Faster rate limiting (20s delays)")
    print(f"   • Time per paper: {faster_time_per_paper:.1f} minutes")
    print(
        f"   • Total time: {faster_total_hours:.1f} hours ({faster_total_hours / 24:.1f} days)"
    )
    print("   • Risk: Higher chance of rate limiting")
    print()

    # Scenario 2: Parallel downloads (if IP allows)
    parallel_streams = 2
    parallel_hours = total_time_hours / parallel_streams
    print(f"🚀 Scenario 2: Parallel downloads ({parallel_streams} streams)")
    print(
        f"   • Total time: {parallel_hours:.1f} hours ({parallel_hours / 24:.1f} days)"
    )
    print("   • Risk: Much higher chance of IP blocking")
    print()

    # Batch analysis for 80GB constraint
    batch_size_gb = 15
    papers_per_batch = int(batch_size_gb * 1024 / avg_size_per_paper)
    num_batches = (total_2025_papers + papers_per_batch - 1) // papers_per_batch
    time_per_batch_hours = (papers_per_batch * avg_time_per_paper) / 60

    print("📦 BATCH DOWNLOAD ANALYSIS (for 80GB disk):")
    print(f"   • Batch size: {batch_size_gb} GB")
    print(f"   • Papers per batch: ~{papers_per_batch:,}")
    print(f"   • Number of batches: {num_batches}")
    print(f"   • Time per batch: {time_per_batch_hours:.1f} hours")
    print(f"   • Total calendar time: {num_batches} batches × processing time")
    print()

    print("💡 RECOMMENDATIONS:")
    print()

    if total_size_gb > 80:
        print("⚠️  DISK SPACE CONSTRAINT:")
        print(f"   • Total size ({total_size_gb:.1f} GB) > Available space (80 GB)")
        print(f"   • You'll need {num_batches} batches to download everything")
        print(
            f"   • Each batch: ~{time_per_batch_hours:.1f} hours download + processing time"
        )
        print()

    print("🎯 PRACTICAL APPROACH:")
    print("1. 📊 Start with 1-2 batches to test your processing pipeline")
    print("2. 🔄 Optimize your PDF processing workflow")
    print("3. ⚡ Consider focusing on most recent months first (Sept 2025)")
    print("4. 📈 Scale up once you have a smooth workflow")
    print()

    print("🚀 ALTERNATIVE STRATEGIES:")
    print("1. 🎯 Download only papers from specific months (e.g., Sept-Dec 2025)")
    print("2. 📊 Filter by categories (e.g., cs.AI, cs.LG, cs.CV)")
    print("3. 💰 Use S3 approach for bulk download if budget allows")
    print("4. 🤝 Coordinate with others to share download costs/effort")

    # Calculate monthly breakdown
    print()
    print("📅 MONTHLY BREAKDOWN (estimated):")
    papers_per_month = total_2025_papers / 9  # 9 months of 2025 so far
    size_per_month_gb = (papers_per_month * avg_size_per_paper) / 1024
    time_per_month_hours = (papers_per_month * avg_time_per_paper) / 60

    months_2025 = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    for month in months_2025:
        print(
            f"   • {month} 2025: ~{papers_per_month:,.0f} papers, {size_per_month_gb:.1f} GB, {time_per_month_hours:.1f} hours"
        )


if __name__ == "__main__":
    calculate_2025_estimates()
