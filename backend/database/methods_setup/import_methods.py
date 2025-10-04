#!/usr/bin/env python3
"""
Import methods from curated CSV file into the database.

This script:
1. Reads methods from 'data/Methods, areas and tasks - Methods.csv'
2. Matches method names to areas using 'data/jul-28-methods.json'
3. Populates the methods table with area associations
"""

import sys
import csv
import json
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Method, Area


# Area name mappings (CSV format -> Database format)
AREA_NAME_MAPPINGS = {
    "General": "General",
    "NLP": "Natural Language Processing",
    "Computer vision": "Computer Vision",
    "Robotics": "Robotics",
    "3D generation": "Computer Vision",  # Map 3D to Computer Vision
    "": None,  # Empty area
}


def load_json_area_mappings(json_path: Path) -> Dict[str, str]:
    """
    Load area mappings from jul-28-methods.json.

    Returns a dict mapping lowercase method names to area names.
    """
    print(f"Loading area mappings from {json_path}...")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    mappings = {}
    for method_obj in data:
        method_name = method_obj.get("name", "").strip().lower()
        collections = method_obj.get("collections", [])

        if collections and len(collections) > 0:
            area = collections[0].get("area", "")
            if area and method_name:
                mappings[method_name] = area

    print(f"✓ Loaded {len(mappings)} method->area mappings from JSON")
    return mappings


def get_area_id_map(db) -> Dict[str, int]:
    """Get mapping of area names to area IDs."""
    areas = db.query(Area).all()
    area_map = {}
    for area in areas:
        area_map[area.name.lower()] = area.id
    return area_map


def determine_area(
    method_name: str,
    csv_area: str,
    json_mappings: Dict[str, str],
    area_id_map: Dict[str, int],
) -> Optional[int]:
    """
    Determine the area_id for a method.

    Priority:
    1. CSV area (if provided)
    2. JSON area (if found)
    3. None (no area assigned)
    """
    # Try CSV area first
    if csv_area and csv_area in AREA_NAME_MAPPINGS:
        mapped_area = AREA_NAME_MAPPINGS[csv_area]
        if mapped_area:
            area_id = area_id_map.get(mapped_area.lower())
            if area_id:
                return area_id

    # Try JSON mapping
    method_lower = method_name.lower()
    if method_lower in json_mappings:
        json_area = json_mappings[method_lower]
        area_id = area_id_map.get(json_area.lower())
        if area_id:
            return area_id

    # Default to General if no mapping found
    return area_id_map.get("general")


def import_methods():
    """Import methods from CSV file into the database."""

    # Database connection
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/paperswithcode_hf"

    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()

        # Get area ID mappings
        area_id_map = get_area_id_map(db)
        print("\nArea mappings in database:")
        for area_name, area_id in sorted(area_id_map.items()):
            print(f"  {area_id}: {area_name.title()}")

        # Load JSON mappings
        json_path = "data/jul-28-methods.json"
        json_mappings = load_json_area_mappings(json_path)

        # Read CSV file
        csv_path = "data/Methods, areas and tasks - Methods.csv"
        print(f"\nReading methods from {csv_path}...")

        methods_to_add = []
        methods_count = 0
        area_stats = {}

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                method_name = row["Method"].strip()
                csv_area = row.get("Area", "").strip()

                if not method_name:
                    continue

                methods_count += 1

                # Determine area_id
                area_id = determine_area(
                    method_name, csv_area, json_mappings, area_id_map
                )

                # Track stats
                area_name = "Unassigned"
                if area_id:
                    for name, aid in area_id_map.items():
                        if aid == area_id:
                            area_name = name.title()
                            break

                area_stats[area_name] = area_stats.get(area_name, 0) + 1

                # Check if method already exists
                existing = db.query(Method).filter(Method.name == method_name).first()
                if existing:
                    print(f"  ⊘ Skipping '{method_name}' (already exists)")
                    continue

                # Create method object
                method = Method(
                    name=method_name,
                    full_name=method_name,  # Use name as full_name for now
                    area_id=area_id,
                )
                methods_to_add.append(method)

        print(f"\n✓ Parsed {methods_count} methods from CSV")
        print(f"✓ {len(methods_to_add)} new methods to import")

        # Display area distribution
        print("\nArea distribution:")
        for area_name in sorted(area_stats.keys()):
            count = area_stats[area_name]
            print(f"  {area_name:30} {count:3} methods")

        # Import methods
        if methods_to_add:
            print(f"\nImporting {len(methods_to_add)} methods...")
            db.add_all(methods_to_add)
            db.commit()
            print(f"✅ Successfully imported {len(methods_to_add)} methods!")
        else:
            print("\n✓ No new methods to import")

        # Display final stats
        total_methods = db.query(Method).count()
        print(f"\nTotal methods in database: {total_methods}")

        # Show methods by area
        print("\nMethods by area:")
        for area_name, area_id in sorted(area_id_map.items()):
            count = db.query(Method).filter(Method.area_id == area_id).count()
            print(f"  {area_name.title():30} {count:3} methods")

        unassigned = db.query(Method).filter(Method.area_id is None).count()
        if unassigned > 0:
            print(f"  {'Unassigned':30} {unassigned:3} methods")

        db.close()

    except Exception as e:
        print(f"\n❌ Error importing methods: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import_methods()
