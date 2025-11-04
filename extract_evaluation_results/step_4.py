"""
This script defines an agent that can add datasets to the database.

You can run it like so:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/step_4.py --dataset_details "{\"name\": \"COCO\", \"description\": \"COCO is a large-scale object detection, segmentation, and captioning dataset.\", \"task_ids\": [2]}"
```
"""

from backend.database.connection import db_manager
from backend.services.dataset_service import DatasetService
from backend.schemas.dataset_schema import DatasetCreateRequest
from backend.utils.paper_utils import get_title, get_authors, get_abstract
from agents import Agent, function_tool, Runner
import argparse
import asyncio
import json
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def get_paper_details(arxiv_id: str) -> str:
    """Get formatted paper details including title, authors, and abstract."""
    paper_title = await get_title(arxiv_id)
    paper_authors = await get_authors(arxiv_id)
    paper_abstract = await get_abstract(arxiv_id)

    return f"""
### Title:
{paper_title}
### Authors:
{paper_authors}
### ArXiv ID
{arxiv_id}
### Abstract
{paper_abstract}
"""


dataset_adder_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI).

You are an expert in managing datasets in the database. Your responsibility includes
adding new datasets to the database with comprehensive information when requested.

When adding a new dataset, use the add_dataset tool.
**IMPORTANT**: Every dataset MUST be linked to one or more tasks.
Ensure you provide all relevant information including:
- name (required): The name of the dataset
- description (required): A description of what the dataset contains and its purpose
- task_ids (required): List of task IDs this dataset is used for (e.g., [1] for Image Classification, [2, 3] for multiple tasks)
- full_name (optional): The full name of the dataset
- url (optional): Main URL for the dataset
- hf_url (optional): Hugging Face dataset URL
- paper_url (optional): URL to the paper that introduced this dataset

AVAILABLE TASKS IN DATABASE:
============================

Computer Vision:
- ID: 1  - Image Classification
- ID: 2  - Object Detection
- ID: 3  - Image segmentation
- ID: 4  - OCR
- ID: 13 - 3D generation
- ID: 16 - Depth estimation
- ID: 18 - Image editing
- ID: 19 - Image generation
- ID: 25 - Video generation
- ID: 257 - Object counting

Natural Language Processing:
- ID: 5  - Language Modeling
- ID: 6  - Machine Translation
- ID: 30 - Text classification

Audio:
- ID: 10 - Audio-Language Models
- ID: 12 - Automatic Speech Recognition
- ID: 24 - Text-to-speech
- ID: 27 - Voice cloning
- ID: 259 - Audio Classification

General/Multimodal:
- ID: 7  - Computer Use Agents
- ID: 8  - Vision-Language Models
- ID: 9  - Video-Language Models
- ID: 14 - Agents
- ID: 15 - Coding Agents
- ID: 17 - Embedding models
- ID: 20 - Omni models
- ID: 21 - Reasoning
- ID: 22 - Reinforcement Learning
- ID: 23 - Retrieval
- ID: 26 - World Models
- ID: 256 - General

Other:
- ID: 11 - Robotics
- ID: 28 - Time-series forecasting
- ID: 29 - Time-series classification

Example: To add the COCO dataset for Object Detection, use task_ids=[2]
Example: To add ImageNet for both Image Classification and Image Generation, use task_ids=[1, 19]
"""


@function_tool
async def get_available_tasks() -> str:
    """Get a list of all available tasks in the database that datasets can be linked to.

    Returns:
        A formatted list of all available tasks with their IDs, names, and areas.
    """
    session: Session = db_manager.session_local()

    try:
        from backend.models.database import Task as DBTask

        tasks = session.query(DBTask).order_by(DBTask.id).all()

        if not tasks:
            session.close()
            return "No tasks found in database"

        # Group tasks by area
        tasks_by_area = {}
        for task in tasks:
            area_name = task.area.name if task.area else "Other"
            if area_name not in tasks_by_area:
                tasks_by_area[area_name] = []
            tasks_by_area[area_name].append((task.id, task.name))

        # Format response
        response = "Available Tasks in Database:\n" + "=" * 60 + "\n\n"
        for area_name in sorted(tasks_by_area.keys()):
            response += f"{area_name}:\n"
            for task_id, task_name in tasks_by_area[area_name]:
                response += f"  - ID: {task_id:<4} - {task_name}\n"
            response += "\n"

        response += "=" * 60
        response += f"\nTotal Tasks: {len(tasks)}"

        session.close()
        return response

    except Exception as e:
        session.close()
        return f"Error retrieving tasks: {str(e)}"


@function_tool
async def add_dataset(
    name: str,
    description: str,
    task_ids: list[int],
    full_name: str | None = None,
    url: str | None = None,
    hf_url: str | None = None,
    paper_url: str | None = None,
) -> str:
    """Add a new dataset to the database and link it to one or more tasks.

    IMPORTANT: Every dataset must be linked to at least one task. Use get_available_tasks() to see all available tasks.

    Args:
        name: The name of the dataset (required). E.g., "COCO", "ImageNet", "SpeechCommands"
        description: A description of the dataset (required). Should explain what the dataset contains and its purpose.
        task_ids: List of task IDs this dataset is used for (required). MUST contain at least one valid task ID.
                 E.g., [1] for Image Classification, [2] for Object Detection, [1, 19] for multiple tasks.
                 Use get_available_tasks() to see all available task IDs.
        full_name: The full name of the dataset (optional). E.g., "Common Objects in Context" for COCO.
        url: The main URL for the dataset (optional). E.g., official website or documentation.
        hf_url: Hugging Face dataset URL (optional). E.g., "https://huggingface.co/datasets/..."
        paper_url: URL to the paper that introduced this dataset (optional). E.g., ArXiv URL.

    Returns:
        A success message with the created dataset details, or an error message if creation failed.
    """
    session: Session = db_manager.session_local()
    service = DatasetService(session)

    try:
        # Validate task_ids is not empty
        if not task_ids or len(task_ids) == 0:
            session.close()
            return "✗ Failed to create dataset: task_ids cannot be empty. Every dataset must be linked to at least one task. Use get_available_tasks() to see available tasks."

        # Create the dataset request
        dataset_request = DatasetCreateRequest(
            name=name,
            description=description,
            task_ids=task_ids,
            full_name=full_name,
            url=url,
            hf_url=hf_url,
            paper_url=paper_url,
        )

        # Add the dataset using the service
        dataset = service.create_dataset(dataset_request)

        # Format success response
        response = f"✓ Successfully created dataset: ID={dataset.id}, Name={dataset.name}, Slug={dataset.slug}"
        if dataset.full_name:
            response += f", Full Name={dataset.full_name}"
        response += f", Linked to Task IDs={task_ids}"
        if hf_url:
            response += f", Hugging Face URL={hf_url}"

        session.close()
        return response

    except ValueError as e:
        session.close()
        error_msg = str(e)
        if "Task IDs not found" in error_msg:
            return f"✗ Failed to create dataset: {error_msg}. Use get_available_tasks() to see valid task IDs."
        return f"✗ Failed to create dataset: {error_msg}"
    except Exception as e:
        session.close()
        return f"✗ Failed to create dataset: {str(e)}"


async def step_4(dataset_details_json: str) -> str:
    """Add a dataset to the database using the dataset adder agent.

    Args:
        dataset_details_json: JSON string containing dataset details including:
            - name: Dataset name (required)
            - description: Dataset description (required)
            - task_ids: List of task IDs (required)
            - full_name: Optional full name
            - url: Optional main URL
            - hf_url: Optional Hugging Face URL
            - paper_url: Optional paper URL
            - paper_arxiv_id: Optional ArXiv ID of introducing paper (used to fetch paper details)

    Returns:
        The result from the dataset adder agent
    """
    # Parse dataset details
    try:
        dataset_details = json.loads(dataset_details_json)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in dataset_details: {e}"

    # Extract paper ArXiv ID if available
    paper_arxiv_id = dataset_details.get("paper_arxiv_id")

    # Build prompt
    prompt_parts = [
        "Add the following dataset to the database:",
        json.dumps(dataset_details, indent=2),
    ]

    # Fetch and include paper details if arxiv_id is available
    if paper_arxiv_id:
        try:
            paper_details = await get_paper_details(paper_arxiv_id)
            prompt_parts.append("\n## Paper details")
            prompt_parts.append(paper_details)
        except Exception as e:
            logger.warning(f"Could not fetch paper details for {paper_arxiv_id}: {e}")

    prompt = "\n".join(prompt_parts)

    # Create and run the agent
    dataset_adder_agent = Agent(
        name="Dataset Adder",
        instructions=dataset_adder_prompt,
        tools=[add_dataset, get_available_tasks],
    )

    result = await Runner.run(dataset_adder_agent, prompt)
    return result.final_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add a dataset to the database.")
    parser.add_argument(
        "--dataset_details",
        type=str,
        required=True,
        help="JSON string containing dataset details (name, description, task_ids, etc.). May include paper_arxiv_id to fetch paper context.",
    )
    args = parser.parse_args()

    result = asyncio.run(step_4(args.dataset_details))
    print("Result:", result)
