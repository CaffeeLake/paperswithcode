"""
Populate tasks table with initial AI/ML tasks.

This script populates the tasks table with common AI/ML tasks organized by research area.
Task descriptions are based on the original PapersWithCode data.
"""

import sys
from pathlib import Path

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from backend.models.database import Task, Area
from backend.config import get_settings


def create_slug(name: str) -> str:
    """Create URL-friendly slug from task name."""
    return name.lower().replace(" ", "-").replace("/", "-")


def populate_tasks(db: Session):
    """
    Populate tasks table with initial tasks.

    Args:
        db: Database session
    """

    # Get area IDs
    areas = {area.name: area.id for area in db.query(Area).all()}

    # Define tasks with their descriptions
    tasks_data = [
        # Vision tasks
        {
            "name": "Image Classification",
            "description": "Image Classification is a fundamental task in computer vision that aims to assign a label or class to an entire image. The goal is to train a model that can recognize and categorize images into predefined classes.",
            "area": "Vision",
            "parent": None,
            "level": 0,
        },
        {
            "name": "Object Detection",
            "description": "Object Detection is a computer vision task that involves identifying and localizing objects within an image. The goal is to detect instances of semantic objects of a certain class (such as humans, buildings, or cars) in digital images and videos.",
            "area": "Vision",
            "parent": None,
            "level": 0,
        },
        # Robotics tasks
        {
            "name": "Vision Language Action Models",
            "description": "Vision Language Action Models combine visual perception, natural language understanding, and action prediction to enable robots to understand and execute complex tasks described in natural language while grounding them in visual observations.",
            "area": "Robotics",
            "parent": None,
            "level": 0,
        },
        # General tasks (no specific area)
        {
            "name": "Image Understanding",
            "description": "Image Understanding refers to understanding the contents of an image, including image captioning, classification, visual question answering, and more. Vision-language models (VLMs) are one way to solve image understanding, but the task is not limited to VLMs.",
            "area": "General",
            "parent": None,
            "level": 0,
        },
        {
            "name": "Computer Use Agents",
            "description": "Computer Use Agents are AI systems that can interact with computer interfaces, understand graphical user interfaces, execute tasks, and navigate software applications autonomously. These agents combine vision, language understanding, and action planning to perform complex computer-based tasks.",
            "area": "General",
            "parent": None,
            "level": 0,
        },
        # Language tasks
        {
            "name": "Language Modeling",
            "description": "Language Modeling is the task of predicting the next word or character in a sequence given the previous context. Language models learn the probability distribution of word sequences and are foundational for many NLP applications including text generation, machine translation, and speech recognition.",
            "area": "General",
            "parent": None,
            "level": 0,
        },
        {
            "name": "Machine Translation",
            "description": "Machine Translation is the task of automatically translating text from one natural language to another. The goal is to produce translations that preserve the meaning, style, and grammatical correctness of the source text while being fluent in the target language.",
            "area": "Language",
            "parent": None,
            "level": 0,
        },
    ]

    # Create tasks
    created_tasks = []
    for task_data in tasks_data:
        area_name = task_data["area"]

        # Get area ID (handle "General" area which might not exist)
        if area_name == "General":
            # For general tasks, we set area_id to None
            area_id = None
        elif area_name in areas:
            area_id = areas[area_name]
        else:
            print(
                f"Warning: Area '{area_name}' not found. Task '{task_data['name']}' will be created without an area."
            )
            area_id = None

        # Check if task already exists
        existing_task = db.query(Task).filter(Task.name == task_data["name"]).first()

        if existing_task:
            print(f"Task '{task_data['name']}' already exists, skipping.")
            created_tasks.append(existing_task)
            continue

        # Create task
        task = Task(
            name=task_data["name"],
            description=task_data["description"],
            slug=create_slug(task_data["name"]),
            parent_id=None,  # All these are top-level tasks
            area_id=area_id,
            level=task_data["level"],
        )

        db.add(task)
        db.flush()  # Flush to get the ID

        created_tasks.append(task)
        print(f"Created task: {task.name} (ID: {task.id}, Area: {area_name})")

    db.commit()
    print(f"\nSuccessfully created/verified {len(created_tasks)} tasks")

    # Print summary
    print("\n=== Task Summary ===")
    for area_name in [
        "Vision",
        "Robotics",
        "General",
        "Language",
    ]:
        if area_name == "General":
            count = sum(1 for t in created_tasks if t.area_id is None)
        else:
            area_id = areas.get(area_name)
            count = sum(1 for t in created_tasks if t.area_id == area_id)
        print(f"{area_name}: {count} tasks")


def main():
    """Main function to populate tasks."""
    print("=" * 70)
    print("Populating Tasks Table")
    print("=" * 70)

    # Get database connection
    settings = get_settings()
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        populate_tasks(db)
        print("\n" + "=" * 70)
        print("Task population completed successfully!")
        print("=" * 70)
    except Exception as e:
        print(f"\nError: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
