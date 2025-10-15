"""
Populate COCO dataset variants and splits from legacy PapersWithCode data.

This script:
1. Updates the base COCO dataset with full metadata
2. Creates split variants (test-dev, minival, val2017, etc.)
3. Creates major variants (COCO-Stuff, COCO Captions, COCO-Text, etc.)

Based on the analysis of data/legacy_pwc_data/jul-28-datasets.json
and data/legacy_pwc_data/evaluation-tables.json

Usage:
    uv run --env-file backend/keys.env backend/database/datasets_setup/populate_coco_variants.py
"""

import logging
import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def generate_slug(name: str) -> str:
    """Generate a URL-friendly slug from a dataset name."""
    import re

    slug = name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)  # Remove special characters
    slug = re.sub(r"[-\s]+", "-", slug)  # Replace spaces and multiple dashes
    return slug.strip("-")


def get_or_create_base_coco(cursor) -> int:
    """
    Get the COCO dataset ID or create it if it doesn't exist.

    Returns:
        int: The COCO dataset ID
    """
    # Check if COCO already exists
    cursor.execute("""
        SELECT id, name FROM datasets
        WHERE name IN ('COCO', 'MS COCO', 'COCO (Common Objects in Context)')
        LIMIT 1
    """)
    result = cursor.fetchone()

    if result:
        coco_id = result["id"]
        logger.info(
            f"Found existing COCO dataset with ID: {coco_id}, name: '{result['name']}'"
        )

        # Update with full metadata
        cursor.execute(
            """
            UPDATE datasets SET
                name = 'COCO',
                full_name = 'Common Objects in Context',
                description = 'The COCO (Common Objects in Context) dataset is a large-scale object detection, segmentation, and captioning dataset. It is designed to encourage research on a wide variety of object categories and is commonly used for benchmarking computer vision models. It is an essential dataset for researchers and developers working on object detection, segmentation, and pose estimation tasks.',
                short_description = 'Large-scale object detection, segmentation, and captioning dataset with 330K images and 80 object categories.',
                homepage = 'https://cocodataset.org',
                url = 'https://cocodataset.org/#download',
                introduced_year = 2014,
                introduced_date = '2014-05-01',
                introducing_paper_title = 'Microsoft COCO: Common Objects in Context',
                paper_url = 'https://arxiv.org/abs/1405.0312',
                license_name = 'CC BY 4.0',
                license_url = 'https://cocodataset.org/#termsofuse',
                pwc_url = 'https://paperswithcode.com/dataset/coco-common-objects-in-context',
                modalities = '["Images"]'::jsonb,
                parent_dataset_id = NULL,
                variant_type = NULL,
                split_name = NULL
            WHERE id = %s
        """,
            (coco_id,),
        )
        logger.info("Updated COCO dataset metadata")

        return coco_id
    else:
        # Create new COCO dataset
        cursor.execute("""
            INSERT INTO datasets (
                name, full_name, description, short_description,
                homepage, url, introduced_year, introduced_date,
                introducing_paper_title, paper_url,
                license_name, license_url, pwc_url,
                modalities, parent_dataset_id, variant_type, split_name
            ) VALUES (
                'COCO',
                'Common Objects in Context',
                'The COCO (Common Objects in Context) dataset is a large-scale object detection, segmentation, and captioning dataset. It is designed to encourage research on a wide variety of object categories and is commonly used for benchmarking computer vision models. It is an essential dataset for researchers and developers working on object detection, segmentation, and pose estimation tasks.',
                'Large-scale object detection, segmentation, and captioning dataset with 330K images and 80 object categories.',
                'https://cocodataset.org',
                'https://cocodataset.org/#download',
                2014,
                '2014-05-01',
                'Microsoft COCO: Common Objects in Context',
                'https://arxiv.org/abs/1405.0312',
                'CC BY 4.0',
                'https://cocodataset.org/#termsofuse',
                'https://paperswithcode.com/dataset/coco-common-objects-in-context',
                '["Images"]'::jsonb,
                NULL,
                NULL,
                NULL
            )
            RETURNING id
        """)
        coco_id = cursor.fetchone()["id"]
        logger.info(f"Created COCO dataset with ID: {coco_id}")

        return coco_id


def create_coco_splits(cursor, coco_id: int):
    """
    Create COCO dataset splits (test-dev, minival, val2017, etc.).

    These are different evaluation splits of the same dataset.
    """
    splits = [
        {
            "name": "COCO test-dev",
            "full_name": "COCO test-dev Split",
            "split_name": "test-dev",
            "description": "COCO test-dev evaluation split used for benchmark submissions and leaderboard rankings.",
        },
        {
            "name": "COCO test-challenge",
            "full_name": "COCO test-challenge Split",
            "split_name": "test-challenge",
            "description": "COCO test-challenge evaluation split used for official challenge submissions.",
        },
        {
            "name": "COCO minival",
            "full_name": "COCO minival Split",
            "split_name": "minival",
            "description": "COCO minival evaluation split (5K images), a subset commonly used for validation during development.",
        },
        {
            "name": "COCO val2017",
            "full_name": "COCO val2017 Split",
            "split_name": "val2017",
            "description": "COCO 2017 validation split (5K images) for model evaluation.",
        },
        {
            "name": "COCO 2017 val",
            "full_name": "COCO 2017 Validation Split",
            "split_name": "val",
            "description": "COCO 2017 validation split.",
        },
        {
            "name": "COCO 2014 val",
            "full_name": "COCO 2014 Validation Split",
            "split_name": "val",
            "description": "COCO 2014 validation split.",
        },
    ]

    for split in splits:
        # Check if split already exists
        cursor.execute(
            """
            SELECT id FROM datasets WHERE name = %s
        """,
            (split["name"],),
        )

        existing = cursor.fetchone()
        if existing:
            logger.info(f"Split '{split['name']}' already exists, skipping...")
            continue

        # Generate slug
        slug = generate_slug(split["name"])

        # Create the split
        cursor.execute(
            """
            INSERT INTO datasets (
                name, slug, full_name, description,
                parent_dataset_id, variant_type, split_name,
                homepage, url, license_name, license_url,
                introduced_year, modalities
            ) VALUES (
                %s, %s, %s, %s,
                %s, 'split', %s,
                'https://cocodataset.org',
                'https://cocodataset.org/#download',
                'CC BY 4.0',
                'https://cocodataset.org/#termsofuse',
                2014,
                '["Images"]'::jsonb
            )
        """,
            (
                split["name"],
                slug,
                split["full_name"],
                split["description"],
                coco_id,
                split["split_name"],
            ),
        )

        logger.info(f"Created split: {split['name']}")


def create_coco_variants(cursor, coco_id: int):
    """
    Create major COCO variants (COCO-Stuff, COCO Captions, etc.).

    These are different datasets based on COCO with different annotations or purposes.
    """
    variants = [
        {
            "name": "COCO-Stuff",
            "full_name": "Common Objects in COntext-stuff",
            "variant_type": "variant",
            "description": "COCO-Stuff augments COCO with pixel-level stuff annotations. It spans 164K images with 172 categories including 80 things, 91 stuff, and 1 unlabeled class.",
            "homepage": "https://github.com/nightrome/cocostuff",
            "introduced_year": 2018,
            "paper_title": "COCO-Stuff: Thing and Stuff Classes in Context",
            "paper_url": "https://arxiv.org/abs/1612.03716",
            "pwc_url": "https://paperswithcode.com/dataset/coco-stuff",
        },
        {
            "name": "COCO Captions",
            "full_name": "COCO Captions Dataset",
            "variant_type": "derived",
            "description": "COCO Captions contains over 1.5 million captions describing over 330,000 images. For training and validation images, five independent human-generated captions are provided for each image.",
            "homepage": "https://github.com/tylin/coco-caption",
            "introduced_year": 2015,
            "paper_title": "Microsoft COCO Captions: Data Collection and Evaluation Server",
            "paper_url": "https://arxiv.org/abs/1504.00325",
            "license_name": "CC BY 4.0",
            "pwc_url": "https://paperswithcode.com/dataset/coco-captions",
        },
        {
            "name": "COCO-Text",
            "full_name": "COCO-Text Dataset",
            "variant_type": "variant",
            "description": "COCO-Text is a dataset for text detection and recognition. Based on MS COCO, it contains 63,686 images with 173,589 text instances. It includes both legible and illegible text.",
            "homepage": "https://bgshih.github.io/cocotext/",
            "introduced_year": 2016,
            "paper_title": "COCO-Text: Dataset and Benchmark for Text Detection and Recognition in Natural Images",
            "paper_url": "https://arxiv.org/abs/1601.07140",
            "license_name": "CC BY 4.0",
            "pwc_url": "https://paperswithcode.com/dataset/coco-text",
        },
        {
            "name": "RefCOCO",
            "full_name": "Referring Expressions COCO",
            "variant_type": "derived",
            "description": "RefCOCO is a dataset for referring expression comprehension. It contains 142,209 referring expressions for 50,000 objects in 19,994 images from MS COCO.",
            "introduced_year": 2016,
            "paper_title": "Modeling Context in Referring Expressions",
            "paper_url": "https://arxiv.org/abs/1608.00272",
            "pwc_url": "https://paperswithcode.com/dataset/refcoco",
        },
        {
            "name": "COCO-WholeBody",
            "full_name": "COCO-WholeBody Dataset",
            "variant_type": "variant",
            "description": "COCO-WholeBody is an extension of COCO with whole-body pose annotations including body, foot, face, and hand keypoints.",
            "introduced_year": 2020,
            "paper_title": "Whole-Body Human Pose Estimation in the Wild",
            "paper_url": "https://arxiv.org/abs/2007.11858",
            "pwc_url": "https://paperswithcode.com/dataset/coco-wholebody",
        },
    ]

    for variant in variants:
        # Check if variant already exists
        cursor.execute(
            """
            SELECT id FROM datasets WHERE name = %s
        """,
            (variant["name"],),
        )

        existing = cursor.fetchone()
        if existing:
            logger.info(f"Variant '{variant['name']}' already exists, skipping...")
            continue

        # Generate slug
        slug = generate_slug(variant["name"])

        # Create the variant
        cursor.execute(
            """
            INSERT INTO datasets (
                name, slug, full_name, description,
                parent_dataset_id, variant_type,
                homepage, url,
                introduced_year, introducing_paper_title, paper_url,
                license_name, license_url, pwc_url,
                modalities
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                '["Images"]'::jsonb
            )
        """,
            (
                variant["name"],
                slug,
                variant["full_name"],
                variant["description"],
                coco_id,
                variant["variant_type"],
                variant.get("homepage", "https://cocodataset.org"),
                variant.get("url", "https://cocodataset.org"),
                variant.get("introduced_year"),
                variant.get("paper_title"),
                variant.get("paper_url"),
                variant.get("license_name", "CC BY 4.0"),
                variant.get("license_url", "https://cocodataset.org/#termsofuse"),
                variant.get("pwc_url"),
            ),
        )

        logger.info(f"Created variant: {variant['name']}")


def main():
    """Main function to populate COCO dataset variants."""
    logger.info("=" * 80)
    logger.info("Starting COCO dataset variants population")
    logger.info("=" * 80)

    # Database connection parameters
    db_params = {
        "host": os.getenv("PWC_DB_HOST", "localhost"),
        "port": os.getenv("PWC_DB_PORT", "5432"),
        "database": os.getenv("PWC_DB_NAME", "paperswithcode_hf"),
        "user": os.getenv("PWC_DB_USER", "postgres"),
        "password": os.getenv("PWC_DB_PASSWORD", ""),
    }

    try:
        # Connect to database
        logger.info("Connecting to database...")
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Step 1: Get or create base COCO dataset
        logger.info("\n" + "=" * 80)
        logger.info("Step 1: Setting up base COCO dataset")
        logger.info("=" * 80)
        coco_id = get_or_create_base_coco(cursor)
        conn.commit()

        # Step 2: Create COCO splits
        logger.info("\n" + "=" * 80)
        logger.info("Step 2: Creating COCO splits (test-dev, minival, etc.)")
        logger.info("=" * 80)
        create_coco_splits(cursor, coco_id)
        conn.commit()

        # Step 3: Create COCO variants
        logger.info("\n" + "=" * 80)
        logger.info("Step 3: Creating COCO variants (COCO-Stuff, COCO Captions, etc.)")
        logger.info("=" * 80)
        create_coco_variants(cursor, coco_id)
        conn.commit()

        # Get final counts
        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE parent_dataset_id IS NULL) as base_count,
                COUNT(*) FILTER (WHERE parent_dataset_id = %s AND variant_type = 'split') as split_count,
                COUNT(*) FILTER (WHERE parent_dataset_id = %s AND variant_type IN ('variant', 'derived')) as variant_count
            FROM datasets
        """,
            (coco_id, coco_id),
        )

        counts = cursor.fetchone()

        logger.info("\n" + "=" * 80)
        logger.info("COCO Dataset Variants Population Complete!")
        logger.info("=" * 80)
        logger.info(f"Base COCO dataset ID: {coco_id}")
        logger.info(f"Total COCO splits created: {counts['split_count']}")
        logger.info(f"Total COCO variants created: {counts['variant_count']}")
        logger.info("=" * 80)

        cursor.close()
        conn.close()

        return 0

    except Exception as e:
        logger.error(f"Error populating COCO variants: {e}", exc_info=True)
        if "conn" in locals():
            conn.rollback()
        return 1


if __name__ == "__main__":
    sys.exit(main())
