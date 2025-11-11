#!/usr/bin/env python3
"""
Add paper URL to GPQA and GPQA Diamond datasets.

Usage:
    uv run --env-file backend/keys.env scripts/add_gpqa_paper_url.py
"""

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from sqlalchemy.orm import Session


def main():
    paper_url = "https://arxiv.org/abs/2311.12022"

    session: Session = db_manager.session_local()
    try:
        # Update GPQA (ID=312)
        print("Updating GPQA dataset...")
        gpqa = session.query(DBDataset).filter(DBDataset.id == 312).first()
        if gpqa:
            gpqa.paper_url = paper_url
            session.commit()
            print(f"✓ Updated GPQA (ID={gpqa.id}):")
            print(f"  Name: {gpqa.name}")
            print(f"  Paper URL: {gpqa.paper_url}")
        else:
            print("✗ GPQA dataset not found")

        # Update GPQA Diamond (ID=38)
        print("\nUpdating GPQA Diamond dataset...")
        gpqa_diamond = session.query(DBDataset).filter(DBDataset.id == 38).first()
        if gpqa_diamond:
            gpqa_diamond.paper_url = paper_url
            session.commit()
            print(f"✓ Updated GPQA Diamond (ID={gpqa_diamond.id}):")
            print(f"  Name: {gpqa_diamond.name}")
            print(f"  Paper URL: {gpqa_diamond.paper_url}")
        else:
            print("✗ GPQA Diamond dataset not found")

    except Exception as e:
        session.rollback()
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
