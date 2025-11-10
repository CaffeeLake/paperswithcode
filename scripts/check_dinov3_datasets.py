"""
Final summary: Check which DINOv3 evaluation datasets exist and report missing ones.

This script checks all datasets mentioned in Tables 7, 8, and 9 of the DINOv3 paper
and reports which ones are missing from the database.
"""

import sys
from typing import Optional
from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.utils.dataset_utils import find_dataset_by_name

# All datasets from Tables 7, 8, and 9
ALL_DATASETS = {
    # Table 7: Classification accuracy
    "ImageNet Val": {"value": "88.4", "metric": "Top-1"},
    "ImageNet V2": {"value": "81.4", "metric": "Top-1"},
    "ImageNet RealL": {"value": "90.4", "metric": "Top-1"},
    "Rendition R": {"value": "91.1", "metric": "Top-1"},
    "Rendition S": {"value": "71.3", "metric": "Top-1"},
    "Hard A": {"value": "86.9", "metric": "Top-1"},
    "Hard C↓": {"value": "19.6", "metric": "Top-1"},
    "Hard Obj.": {"value": "79.0", "metric": "Top-1"},
    # Table 8: Finegrained classification
    "Fine-S": {"value": "93.0", "metric": "Top-1"},
    "Places": {"value": "70.0", "metric": "Top-1"},
    "iNat18": {"value": "85.6", "metric": "Top-1"},
    "iNat21": {"value": "89.8", "metric": "Top-1"},
    # Table 9: Instance recognition
    "Oxford-H": {"value": "60.7", "metric": "mAP"},
    "Paris-H": {"value": "87.1", "metric": "mAP"},
    "Met (GAP)": {"value": "55.4", "metric": "GAP"},
    "AmsterTime": {"value": "56.5", "metric": "mAP"},
}


def find_dataset_comprehensive(db, dataset_name: str) -> Optional[DBDataset]:
    """Comprehensive search for a dataset."""
    # Try various name variations
    variations = [
        dataset_name,
        dataset_name.replace("-", " "),
        dataset_name.replace(" ", "-"),
        dataset_name.replace("↓", ""),
    ]

    # Add common variations for ImageNet datasets
    if "ImageNet" in dataset_name:
        if "V2" in dataset_name:
            variations.extend(["ImageNet-V2", "ImageNetV2", "ImageNet 2"])
        elif "Real" in dataset_name or "RealL" in dataset_name:
            variations.extend(["ImageNet Real", "ImageNet-Real", "ImageNet-RealL"])
        elif "Rendition" in dataset_name:
            if "R" in dataset_name:
                variations.extend(["ImageNet-R", "ImageNet-Rendition-R"])
            elif "S" in dataset_name:
                variations.extend(
                    ["ImageNet-Rendition-S", "ImageNet-Sketch", "ImageNet-S"]
                )
        elif "A" in dataset_name or "Adversarial" in dataset_name:
            variations.extend(["ImageNet-A", "ImageNet-Adversarial"])
        elif "C" in dataset_name or "Corruption" in dataset_name:
            variations.extend(["ImageNet-C", "ImageNet-Corruption"])
        elif "Hard" in dataset_name:
            if "A" in dataset_name:
                variations.extend(["ImageNet-A", "ImageNet-Adversarial"])
            elif "C" in dataset_name:
                variations.extend(["ImageNet-C", "ImageNet-Corruption"])
            elif "Obj" in dataset_name:
                variations.extend(["ObjectNet"])

    # Add variations for other datasets
    if "Places" in dataset_name:
        variations.extend(["Places365", "Places-365"])
    if "iNat" in dataset_name or "iNaturalist" in dataset_name:
        if "18" in dataset_name:
            variations.extend(["iNaturalist 2018", "iNaturalist18", "iNat-2018"])
        elif "21" in dataset_name:
            variations.extend(["iNaturalist 2021", "iNaturalist21", "iNat-2021"])
    if "Oxford" in dataset_name:
        variations.extend(["Oxford Buildings", "Oxford-Hard"])
    if "Paris" in dataset_name:
        variations.extend(["Paris Buildings", "Paris-Hard"])

    # Try all variations
    for variation in variations:
        # Exact match
        dataset = db.query(DBDataset).filter(DBDataset.name.ilike(variation)).first()
        if dataset:
            return dataset
        # Partial match in name
        dataset = (
            db.query(DBDataset).filter(DBDataset.name.ilike(f"%{variation}%")).first()
        )
        if dataset:
            return dataset
        # Partial match in full_name
        dataset = (
            db.query(DBDataset)
            .filter(DBDataset.full_name.ilike(f"%{variation}%"))
            .first()
        )
        if dataset:
            return dataset
        # Use utility function
        dataset = find_dataset_by_name(db, variation)
        if dataset:
            return dataset

    return None


def check_all_datasets():
    """Check which datasets exist and report missing ones."""
    db = db_manager.session_local()
    try:
        print("=" * 80)
        print("DINOv3 Evaluation Datasets Check")
        print("=" * 80)
        print()

        found_datasets = []
        missing_datasets = []

        for dataset_name, data in ALL_DATASETS.items():
            dataset = find_dataset_comprehensive(db, dataset_name)
            if dataset:
                found_datasets.append(
                    {
                        "name": dataset_name,
                        "db_name": dataset.name,
                        "db_id": dataset.id,
                        "value": data["value"],
                        "metric": data["metric"],
                    }
                )
                print(f"✓ Found: {dataset_name} → {dataset.name} (ID: {dataset.id})")
            else:
                missing_datasets.append(
                    {
                        "name": dataset_name,
                        "value": data["value"],
                        "metric": data["metric"],
                    }
                )
                print(f"✗ Missing: {dataset_name}")

        print()
        print("=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Found: {len(found_datasets)}")
        print(f"Missing: {len(missing_datasets)}")
        print()

        if found_datasets:
            print("Found datasets:")
            for ds in found_datasets:
                print(f"  - {ds['name']} → {ds['db_name']} (ID: {ds['db_id']})")
            print()

        if missing_datasets:
            print("Missing datasets:")
            for ds in missing_datasets:
                print(f"  - {ds['name']}: {ds['value']} ({ds['metric']})")

        return found_datasets, missing_datasets

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return [], []
    finally:
        db.close()


def main():
    """Main entry point."""
    found, missing = check_all_datasets()
    sys.exit(0)


if __name__ == "__main__":
    main()
