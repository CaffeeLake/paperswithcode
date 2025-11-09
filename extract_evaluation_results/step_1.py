"""
This script automatically extracts evaluation results from a paper and returns them as a JSON string.

It uses the Datalab API to convert a PDF to Markdown.
Then it uses the OpenAI API to extract evaluation results from the Markdown content.

You can run it like so:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/step_1.py --arxiv_id 2201.03545
```
"""

import argparse
import asyncio
import json
import logging
from pydantic import BaseModel, Field
from typing import Optional

from backend.utils.pdf_utils import temp_pdf_download
from backend.utils.paper_utils import get_title

from datalab_sdk import AsyncDatalabClient

from backend.config import get_settings
from extract_evaluation_results.io import load_cached_markdown, save_markdown_to_cache
from extract_evaluation_results.step_base import AgentStep
from extract_evaluation_results.utils import get_formatted_tasks_list
from extract_evaluation_results.tools import (
    get_task_datasets,
    get_dataset_details,
    get_leaderboard_triples_tool,
)

settings = get_settings()
DATALAB_API_KEY = settings.datalab_api_key

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

datalab_client = AsyncDatalabClient(api_key=DATALAB_API_KEY)


# Input and Output models for the new API
class Step1Input(BaseModel):
    """Input for Step 1: Evaluation Results Extractor."""

    arxiv_id: str = Field(
        description="ArXiv ID of the paper to extract results from (e.g., '2201.03545')"
    )


class EvaluationResult(BaseModel):
    table_index: int
    model_name: str
    dataset_name: str
    metric_name: str
    metric_value: str


class DatasetDetail(BaseModel):
    dataset_name: str
    dataset_info: str
    split: Optional[str] = None
    paper_title: Optional[str] = None
    paper_arxiv_id: Optional[str] = None


class Step1Output(BaseModel):
    reasoning: str
    dataset_details: list[DatasetDetail]
    evaluation_results: list[EvaluationResult]


instructions_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape
by creating leaderboards for datasets and tasks within the field of machine learning and artificial intelligence (AI).

You are an expert in extracting evaluation results from AI research papers in order to be added to leaderboards.

We have converted an AI research PDF paper titled {paper_title} with arxiv ID {arxiv_id} to Markdown.

## Task

Your task is to extract evaluation results from the paper, if any, which are useful to be added for leaderboard data.
Only include evaluation results out of tables that are included in the paper.
Only include evaluation results of models that the paper introduces, not evaluation results of models of other works.
If the paper does not contain any evaluation results, return an empty list.

Each evaluation result should be of the tuple of the form (table_index, model_name, dataset_name, metric_name, metric_value),
e.g. (2, "BERT (large)", "GLUE", "Accuracy", "85.4").

Importantly, only the best performing results of the paper on each benchmark should be included, as otherwise we end up with too many evaluation results.
When a paper includes various model sizes (e.g. tiny, base, large), include only the best performing result of the largest model.
Evaluation results of the appendix of a paper should not be included.

## Tables

Each AI research paper typically contains tables which can be categorized into three categories: leaderboard tables, ablation tables and irrelevant tables:
* A leaderboard table contains the principal results of the paper on a selected benchmark, including comparisons with other papers.
* An ablation table compares different permutations of the paper's methodology.
* Lastly, irrelevant tables include hyperparameters, dataset statistics and other information that is not directly relevant for result extraction.

Your task is to only extract evaluation results from the leaderboard tables.

## Context: Available Tasks and Datasets

Below is a list of areas and tasks currently in the database of Hugging Face along with their associated datasets.
This provides context about the current information landscape for leaderboard data:

{tasks_list}

Use this context to better understand which tasks and datasets are commonly used, which can help you identify relevant evaluation results in the paper.

## Important Rules

- when authors specify the COCO dataset and it's unclear which COCO dataset exactly, assume it's COCO val2017.
- the validation split is different from the test split. If a split is mentioned, include this in the `dataset_info` field of the dataset details. Consider different splits as different datasets.
- prefer simple dataset and metric names, and bias towards including details in the model name rather than the dataset/metric
- when there's an "overall" column in a table, prefer to include the overall result rather than the results for each individual part of the dataset.
- when the metric value can be interpreted as a percentage (scale 0-100%), call the metric "accuracy" instead of "score".
- **NEVER use "Ours" or similar terms as model names**. Always extract the actual model name from the paper.
- for model names, prefer the template "Model Name (Model Size)" if available e.g. "BERT (large)", otherwise use the model name as is.
- **when a dataset is introduced in THIS paper (arxiv ID: {arxiv_id})**, populate the `paper_title` field with "{paper_title}" and the `paper_arxiv_id` field with "{arxiv_id}". Only use this for datasets that are explicitly stated as new/introduced/proposed in this paper.
- when a dataset is introduced in a different paper that is cited, extract that paper's title and arxiv_id from the citation.
- do not include evaluation results for datasets that are not publicly available. For example, internal benchmarks, private datasets, etc.
- do not include evaluation results which are super specific to the paper/have very little comparisons to other papers.

## Tools Available

You have access to tools to help you understand the current state of the database:

1. **`get_datasets_for_task`**: Get all datasets associated with a specific task. Use this when you need to look up which datasets are commonly used for a particular task. This can help you:
   - Identify if a dataset mentioned in the paper is already in the database
   - Understand which datasets are standard for a given task
   - Better match dataset names from the paper to datasets in the database

2. **`get_dataset_details`**: Get detailed information about a specific dataset by its ID. Use this after calling `get_datasets_for_task` to get comprehensive details about a dataset, including:
   - Full name and description
   - URLs (main URL, Hugging Face URL, paper URL)
   - All tasks the dataset is associated with
   - This helps you understand if a dataset matches what's mentioned in the paper

3. **`get_leaderboard_triples`**: Get all current leaderboards as (area, task, dataset, metric) tuples. Use this when you want to see what evaluation results are already being tracked for specific combinations of tasks, datasets, and metrics. This can help you:
   - Check if there's already a leaderboard for a task-dataset-metric combination
   - Ensure you're extracting results that match existing leaderboard structures
   - Understand which metrics are commonly used for specific datasets

## Output format

Use the following Pydantic model to format your response:
```python
class EvaluationResult(BaseModel):
    table_index: int
    model_name: str
    dataset_name: str
    metric_name: str
    metric_value: str

class DatasetDetail(BaseModel):
    dataset_name: str The name of the dataset as it appears in the paper. Include the split in the name if it covers a particular split of the dataset.
    dataset_info: str # What you know about this dataset - do not make up information, only use the information provided in the paper
    split: Optional[str] = None # The split of the dataset e.g. "validation", "test", "train", if mentioned in the paper
    paper_title: Optional[str] = None # The title of the paper that introduces the dataset. If introduced in THIS paper, use the paper title provided in the instructions. If introduced in a cited paper, use that paper's title.
    paper_arxiv_id: Optional[str] = None # The ArXiv ID of the paper that introduces the dataset, typically found in the citation section at the end of the paper. If introduced in THIS paper, use the arxiv_id provided in the instructions. If introduced in a cited paper, use that paper's arxiv_id.

class Response(BaseModel):
    reasoning: str # Your reasoning regarding the extraction of the dataset details and evaluation results
    dataset_details: Optional[list[DatasetDetail]] = None # The details of the datasets mentioned in the evaluation results. Leave as empty list if no evaluation results are found.
    evaluation_results: Optional[list[EvaluationResult]] = None # The evaluation results extracted from the paper. Leave as empty list if no evaluation results are found.
```

Return the response as a JSON string. Do not include any other text in your response.
"""


class Step1(AgentStep[Step1Input, Step1Output]):
    """Agent-based step for extracting evaluation results from a paper."""

    input_model = Step1Input
    output_model = Step1Output

    def __init__(self):
        super().__init__(
            name="Step1: Evaluation Results Extractor",
            description="Extracts evaluation results and dataset details from a research paper",
            instructions=instructions_prompt,
            tools=[
                get_task_datasets,
                get_dataset_details,
                get_leaderboard_triples_tool,
            ],
            agent_output_type=Step1Output,
            model="gpt-5-mini",
        )

    async def build_agent_prompt(self, inputs: Step1Input) -> str:
        """
        Convert inputs to agent prompt by downloading and converting PDF to markdown.
        """
        arxiv_id = inputs.arxiv_id

        # Check if we have cached markdown first
        cached_markdown = await load_cached_markdown(arxiv_id)

        if cached_markdown:
            logger.info(f"Using cached markdown for {arxiv_id}")
            paper_markdown = cached_markdown
        else:
            # Need to download PDF and convert to markdown
            async with temp_pdf_download(arxiv_id=arxiv_id) as (
                pdf_path,
                error_message,
            ):
                if pdf_path is None or error_message is not None:
                    logger.warning(
                        f"Failed to download PDF for {arxiv_id}: {error_message}"
                    )
                    raise RuntimeError(f"Failed to download PDF: {error_message}")

                # Convert PDF to markdown
                logger.info(f"Converting PDF to markdown for {arxiv_id}")
                result = await datalab_client.convert(pdf_path)
                logger.info(
                    f"PDF conversion completed. Markdown length: {len(result.markdown) if result.markdown else 0}"
                )

                paper_markdown = result.markdown

                # Save to cache for future use
                await save_markdown_to_cache(arxiv_id, paper_markdown)

        # Build the input prompt with the paper markdown
        return f"""Here is the paper to extract evaluation results from: {paper_markdown}"""

    async def format_instructions(self, inputs: Step1Input) -> str:
        """
        Format instructions with paper-specific context.
        """
        arxiv_id = inputs.arxiv_id

        # Get paper title and tasks list for context
        paper_title = await get_title(arxiv_id=arxiv_id)
        tasks_list = get_formatted_tasks_list()

        # Format instructions with context
        return self.instructions.format(
            tasks_list=tasks_list, paper_title=paper_title, arxiv_id=arxiv_id
        )


async def step_1(arxiv_id: str):
    """
    Extract evaluation results from a paper (wrapper for Step1).

    Args:
        arxiv_id: The ArXiv ID of the paper

    Returns:
        JSON string with evaluation results and dataset details
    """
    step = Step1()
    result = await step.run({"arxiv_id": arxiv_id})

    if not result.success:
        logger.error(f"Step 1 failed: {result.error_message}")
        return None

    # result.outputs is now a Pydantic model (Step1Output)
    # Serialize it to JSON string
    return result.outputs.model_dump_json()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract evaluation results from a paper."
    )
    parser.add_argument(
        "--arxiv_id",
        type=str,
        required=False,
        default="2406.09414",
    )
    args = parser.parse_args()

    response = asyncio.run(step_1(arxiv_id=args.arxiv_id))
    if response:
        # Pretty print the JSON
        response_dict = json.loads(response)
        print(json.dumps(response_dict, indent=2))
    else:
        print("No response received")

    # Close clients to avoid unclosed session warnings
    asyncio.run(datalab_client.close())


# Workflow integration
class Step1WorkflowStep:
    """Workflow step wrapper for Step1."""

    name = "Step1WorkflowStep"

    def __init__(self):
        self.step = Step1()

    async def execute(self, state):
        """
        Execute Step1 using data from workflow state.

        Reads from state.data:
        - arxiv_id: str

        Writes to state.data:
        - reasoning: str
        - dataset_details: list[DatasetDetail]
        - evaluation_results: list[EvaluationResult]
        """

        # Build inputs from state.data
        inputs = {"arxiv_id": state.data.get("arxiv_id", state.arxiv_id)}

        # Execute the step
        result = await self.step.run(inputs)

        return result
