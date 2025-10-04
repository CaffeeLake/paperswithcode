"""
Populate paper_tasks table with object detection papers.

This script tags papers with the "object detection" task based on their arxiv IDs.
Includes papers from the user-provided list and papers from the detrex repository.
"""

import sys
from pathlib import Path
from typing import List

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Task, Paper, PaperTask
from backend.config import get_settings


# User-provided arxiv IDs
USER_PROVIDED_ARXIV_IDS = [
    "2005.12872",
    "2410.13842",
    "2408.15857",
    "2304.08069",
    "2412.04234",
    "2509.20787",  # Note: This may not exist yet (year 2509)
    "1703.06870",
    "1506.01497",
    "2211.12860",
    "2108.06152",
    "2207.08914",
]

# Papers from detrex repository README
# Mapping paper names to arxiv IDs (based on common knowledge of these papers)
DETREX_PAPERS = {
    "DETR": "2005.12872",  # End-to-end object detection with transformers
    "Deformable-DETR": "2010.04159",  # Deformable DETR: Deformable Transformers for End-to-End Object Detection
    "Conditional-DETR": "2108.06152",  # Already in user list
    "DAB-DETR": "2201.12329",  # DAB-DETR: Dynamic Anchor Boxes are Better Queries for DETR
    "DN-DETR": "2203.01305",  # DN-DETR: Accelerate DETR Training by Introducing Query DeNoising
    "DINO": "2203.03605",  # DINO: DETR with Improved DeNoising Anchor Boxes for End-to-End Object Detection
    "Group-DETR": "2207.13085",  # Group DETR: Fast DETR Training with Group-Wise One-to-Many Assignment
    "H-Deformable-DETR": "2207.13080",  # DETRs with Hybrid Matching
    "Mask-DINO": "2206.02777",  # Mask DINO: Towards a Unified Transformer-based Framework
    "CO-MOT": "2305.12724",  # Bridging the Gap Between End-to-end and Non-End-to-end Multi-Object Tracking
    "SQR-DETR": "2212.11259",  # Enhanced Training of Query-Based Object Detection via Selective Query Recollection
    "Anchor-DETR": "2109.07107",  # Anchor DETR: Query Design for Transformer-Based Detector
    "PnP-DETR": "2109.07036",  # PnP-DETR: Towards Efficient Visual Analysis with Transformers
    "DETA": "2212.06137",  # NMS Strikes Back
    "Align-DETR": "2304.07527",  # Align-DETR: Improving DETR with Simple IoU-aware Binary-Class Classification
    "Focus-DETR": "2307.12612",  # Focus-DETR: Less is More for Efficient DETR
}


def get_all_arxiv_ids() -> List[str]:
    """Get all unique arxiv IDs to process."""
    all_ids = set(USER_PROVIDED_ARXIV_IDS)
    all_ids.update(DETREX_PAPERS.values())
    return sorted(list(all_ids))


def populate_object_detection_papers():
    """Populate paper_tasks table with object detection papers."""
    print("=" * 70)
    print("Populating Object Detection Papers")
    print("=" * 70)

    # Get database settings
    settings = get_settings()

    # Create engine and session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the "object detection" task
        print("\n🔍 Looking up 'Object Detection' task...")
        task = db.query(Task).filter(Task.name == "Object Detection").first()

        if not task:
            print("❌ Error: 'Object Detection' task not found in database!")
            print("   Please ensure tasks have been populated first.")
            return

        print(f"✓ Found task: {task.name} (ID: {task.id})")

        # Get all arxiv IDs to process
        arxiv_ids = get_all_arxiv_ids()
        print(f"\n📋 Processing {len(arxiv_ids)} unique arxiv IDs...")

        # Statistics
        stats = {
            "found": 0,
            "not_found": 0,
            "added": 0,
            "already_tagged": 0,
            "errors": 0,
        }

        # Process each arxiv ID
        for arxiv_id in arxiv_ids:
            try:
                # Find paper by arxiv_id (get latest version)
                paper = (
                    db.query(Paper)
                    .filter(Paper.arxiv_id == arxiv_id)
                    .filter(Paper.is_latest_version)
                    .first()
                )

                if not paper:
                    print(f"  ⚠️  {arxiv_id} - Paper not found in database")
                    stats["not_found"] += 1
                    continue

                stats["found"] += 1

                # Check if relationship already exists
                existing = (
                    db.query(PaperTask)
                    .filter(PaperTask.paper_id == paper.id)
                    .filter(PaperTask.task_id == task.id)
                    .first()
                )

                if existing:
                    print(f"  ℹ️  {arxiv_id} - Already tagged with Object Detection")
                    stats["already_tagged"] += 1
                    continue

                # Create new paper-task relationship
                paper_task = PaperTask(paper_id=paper.id, task_id=task.id)
                db.add(paper_task)
                stats["added"] += 1

                # Get paper title for display (truncate if too long)
                title = (
                    paper.title[:60] + "..." if len(paper.title) > 60 else paper.title
                )
                print(f"  ✓ {arxiv_id} - Tagged: {title}")

            except Exception as e:
                print(f"  ❌ {arxiv_id} - Error: {e}")
                stats["errors"] += 1
                continue

        # Commit all changes
        db.commit()

        # Print summary
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Total arxiv IDs processed: {len(arxiv_ids)}")
        print(f"  ✓ Papers found:          {stats['found']}")
        print(f"  ⚠️  Papers not found:      {stats['not_found']}")
        print(f"  ✓ New tags added:        {stats['added']}")
        print(f"  ℹ️  Already tagged:        {stats['already_tagged']}")
        print(f"  ❌ Errors:                {stats['errors']}")
        print("=" * 70)

        # Show some example detrex papers
        print("\n📚 Notable papers from detrex repository:")
        example_papers = ["DETR", "Deformable-DETR", "DINO", "Mask-DINO"]
        for name in example_papers:
            arxiv_id = DETREX_PAPERS.get(name)
            if arxiv_id:
                paper = (
                    db.query(Paper)
                    .filter(Paper.arxiv_id == arxiv_id)
                    .filter(Paper.is_latest_version)
                    .first()
                )
                if paper:
                    print(f"  • {name:20s} - {paper.title[:50]}...")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


def list_tagged_papers():
    """List all papers tagged with Object Detection."""
    print("\n" + "=" * 70)
    print("Papers Tagged with Object Detection")
    print("=" * 70)

    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get the "object detection" task
        task = db.query(Task).filter(Task.name == "Object Detection").first()

        if not task:
            print("\n❌ 'Object Detection' task not found in database.")
            return

        # Get all papers with this task
        papers = (
            db.query(Paper)
            .join(PaperTask, Paper.id == PaperTask.paper_id)
            .filter(PaperTask.task_id == task.id)
            .filter(Paper.is_latest_version)
            .order_by(Paper.date_published.desc())
            .all()
        )

        if not papers:
            print("\nNo papers found tagged with Object Detection.")
        else:
            print(f"\nTotal papers: {len(papers)}\n")
            for i, paper in enumerate(papers[:20], 1):  # Show first 20
                print(f"{i:3d}. [{paper.arxiv_id}] {paper.title}")
                print(f"     Published: {paper.date_published}")
                print()

            if len(papers) > 20:
                print(f"... and {len(papers) - 20} more papers")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Populate paper_tasks with object detection papers"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all papers currently tagged with Object Detection",
    )
    parser.add_argument(
        "--populate",
        action="store_true",
        help="Populate the database with object detection paper tags",
    )

    args = parser.parse_args()

    if args.list:
        list_tagged_papers()
    elif args.populate:
        populate_object_detection_papers()
    else:
        # Default: populate then list
        populate_object_detection_papers()
        list_tagged_papers()
