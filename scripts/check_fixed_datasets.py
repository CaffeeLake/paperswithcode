#!/usr/bin/env python3
"""
Check what I actually did - show the datasets and their descriptions
to verify if my task choices were correct.
"""

import sys
from sqlalchemy import text
from backend.database.connection import get_engine


def check_dataset_descriptions():
    """Show dataset descriptions to verify task choices."""
    engine = get_engine()

    # The datasets I fixed
    fixed_datasets = [
        "omnibench",
        "oxford-iiit-pets",
        "mmlu",
        "mmmu",
        "mmmu-pro",
        "ai2d",
        "alignbench",
        "calvin-abcd-to-d",
        "cosyvoice3-cross-lingual-test-set-zh-to-en",
        "covost2-enzh",
        "dailyomni",
        "eth3d",
        "gpqa-diamond",
        "gtzan-genre",
        "libero",
        "lvbench",
        "meta-world-authors-collected-dataset",
        "minimax-multilingual-test-set-chinese",
        "mlvu",
        "muchomusic",
        "mvbench",
        "ocrbench",
        "openaudiobench-llamaquestions",
        "perception-test",
        "seed-seed-tts-test-zh",
        "so100-real-world-pick-place-stacking-sorting",
        "so101-real-world-pick-place-lego",
        "videoholmes",
        "videomme",
        "voicebench-overall",
        "worldsense",
        "writingbench",
        "mmlu-redux",
    ]

    query = text("""
        SELECT
            d.name,
            d.slug,
            d.full_name,
            d.description,
            t.name as task_name
        FROM datasets d
        INNER JOIN task_datasets td ON d.id = td.dataset_id
        INNER JOIN tasks t ON td.task_id = t.id
        WHERE d.slug = ANY(:slugs)
        ORDER BY d.name, t.name
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"slugs": fixed_datasets})
        rows = result.fetchall()

        current_dataset = None
        for name, slug, full_name, description, task_name in rows:
            if current_dataset != slug:
                if current_dataset is not None:
                    print()
                current_dataset = slug
                display_name = full_name if full_name else name
                print(f"📦 {display_name}")
                print(f"   Slug: {slug}")
                if description:
                    desc_preview = (
                        description[:200] + "..."
                        if len(description) > 200
                        else description
                    )
                    print(f"   Description: {desc_preview}")
                print(f"   Current Task: {task_name}")


if __name__ == "__main__":
    try:
        check_dataset_descriptions()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
