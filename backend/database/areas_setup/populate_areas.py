"""
Populate the areas table with common AI/ML research areas.

This script checks if the areas table is empty and populates it with
common research areas like Computer Vision, NLP, Reinforcement Learning, etc.
"""

import sys
from pathlib import Path

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Area
from backend.config import get_settings


# Research areas based on PapersWithCode data dump analysis
# These areas correspond to the main categorizations in papers-with-abstracts.json
COMMON_AREAS = [
    {
        "name": "Computer Vision",
        "description": "Research focused on enabling computers to interpret and understand visual information from images and videos, including tasks such as image classification, object detection, segmentation, and visual recognition.",
    },
    {
        "name": "Natural Language Processing",
        "description": "The field of AI concerned with the interaction between computers and human language, encompassing text understanding, generation, translation, sentiment analysis, and question answering.",
    },
    {
        "name": "General",
        "description": "A broad category encompassing machine learning research and tasks that don't fit specifically into vision or language domains, including general ML methods, optimization, and cross-domain approaches.",
    },
    {
        "name": "Time Series Forecasting",
        "description": "Machine learning methods for analyzing, modeling, and predicting sequential temporal data, including financial forecasting, weather prediction, and temporal pattern recognition.",
    },
    {
        "name": "Robotics",
        "description": "Research at the intersection of AI and physical systems, focusing on autonomous robots, control systems, robot learning, manipulation, and navigation in real-world environments.",
    },
    {
        "name": "Audio",
        "description": "Research on processing, understanding, and generating audio signals, including speech recognition, music generation, sound classification, and audio synthesis.",
    },
]


def populate_areas():
    """Populate the areas table with common research areas."""
    print("=" * 70)
    print("Populating Areas Table")
    print("=" * 70)

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check if areas already exist
        existing_count = db.query(Area).count()
        print(f"\nCurrent areas in database: {existing_count}")

        if existing_count > 0:
            response = input("\nAreas already exist. Do you want to add more? (y/N): ")
            if response.lower() != "y":
                print("Aborted.")
                return

        # Add areas
        added_count = 0
        for area_data in COMMON_AREAS:
            # Check if area with this name already exists
            existing = db.query(Area).filter(Area.name == area_data["name"]).first()
            if existing:
                print(f"⚠ Skipping '{area_data['name']}' - already exists")
                continue

            # Create new area
            area = Area(**area_data)
            db.add(area)
            added_count += 1
            print(f"✓ Added: {area_data['name']}")

        # Commit changes
        db.commit()

        print(f"\n{'=' * 70}")
        print(f"✓ Successfully added {added_count} new areas")
        print(f"Total areas in database: {db.query(Area).count()}")
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


def list_areas():
    """List all areas in the database."""
    print("\n" + "=" * 70)
    print("Current Areas in Database")
    print("=" * 70)

    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        areas = db.query(Area).order_by(Area.name).all()

        if not areas:
            print("\nNo areas found in database.")
        else:
            print(f"\nTotal areas: {len(areas)}\n")
            for area in areas:
                print(f"{area.id:3d}. {area.name}")
                if area.description:
                    print(f"     {area.description[:80]}...")
                print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Manage research areas in the database"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all areas in the database",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Populate the database with common research areas",
    )

    args = parser.parse_args()

    if args.list:
        list_areas()
    elif args.populate:
        populate_areas()
    else:
        # Default: populate
        populate_areas()
        list_areas()
