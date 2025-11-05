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
from pydantic import BaseModel
from typing import Optional

from backend.utils.logging_utils import async_export_txt
from backend.utils.pdf_utils import temp_pdf_download

from datalab_sdk import AsyncDatalabClient

from agents import Agent, Runner

from backend.config import get_settings
from extract_evaluation_results.utils import (
    get_formatted_tasks_list,
    get_task_datasets,
    get_leaderboard_triples_tool,
)

settings = get_settings()
DATALAB_API_KEY = settings.datalab_api_key

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

datalab_client = AsyncDatalabClient(api_key=DATALAB_API_KEY)


class EvaluationResult(BaseModel):
    table_index: int
    model_name: str
    dataset_name: str
    metric_name: str
    metric_value: str


class DatasetDetail(BaseModel):
    dataset_name: str
    dataset_info: str  # What you know about this dataset - do not make up information, only use the information provided in the paper
    paper_title: Optional[str] = (
        None  # The title of the paper that introduces the dataset (cited in the paper)
    )
    paper_arxiv_id: Optional[str] = (
        None  # The ArXiv ID of the paper that introduces the dataset (cited in the paper)
    )


class Step1Response(BaseModel):
    reasoning: str  # Your reasoning regarding the extraction of the evaluation results and dataset details
    dataset_details: list[
        DatasetDetail
    ]  # The details of the datasets mentioned in the evaluation results
    evaluation_results: list[
        EvaluationResult
    ]  # The evaluation results extracted from the paper. Leave as empty list if no evaluation results are found.


instructions_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape
by creating leaderboards for datasets and tasks within the field of machine learning and artificial intelligence (AI).

You are an expert in extracting evaluation results from AI research papers in order to be added to leaderboards.

We have converted an AI research PDF paper on Arxiv to Markdown.

## Task

Your task is to extract evaluation results from the paper, if any, which are useful to be added for leaderboard data.
Only include evaluation results out of tables that are included in the paper.
Only include evaluation results of models that the paper introduces, not evaluation results of models of other works.
If the paper does not contain any evaluation results, return an empty list.

Each evaluation result should be of the tuple of the form (model_name, dataset_name, metric_name, metric_value).

Make sure to only return evaluation results which are useful for leaderboards (which compare performance across different models on the same datasets), do not include results from ablation tables or other tables.

## Tables

Each AI research paper typically contains tables which can be categorized into three categories: leaderboard tables, ablation tables and irrelevant tables:
* A leaderboard table contains the principal results of the paper on a selected benchmark, including comparisons with other papers.
* An ablation table compares different permutations of the paper's methodology.
* Lastly, irrelevant tables include hyperparameters, dataset statistics and other information that is not directly relevant for result extraction.

Your task is to only extract evaluation results from the leaderboard tables.

## Evaluation results

Importantly, only the best performing results of the paper on each benchmark should be included, as otherwise we end up with too many evaluation results.
When a paper includes various model sizes (e.g. tiny, base, large), include only the best performing result of the largest model.
Hence, evaluation results of the appendix of a paper should not be included.

## Context: Available Tasks and Datasets

Below is a list of areas and tasks currently in the database along with their associated datasets.
This provides context about the current information landscape for leaderboard data:

{tasks_list}

Use this context to better understand which tasks and datasets are commonly used, which can help you identify relevant evaluation results in the paper.

Important notes:
- when authors specify the COCO dataset and it's unclear which COCO dataset exactly, assume it's COCO val2017.
- prefer simple dataset and metric names, and bias towards including details in the model name rather than the dataset/metric
- when there's an "overall" column in a table, prefer to include the overall result rather than the results for each individual part of the dataset.
- **NEVER use "Ours" or similar terms as model names**. Always extract the actual model name from the paper. Look for the model name in the paper title, abstract, methodology section, or table captions.

## Tools Available

You have access to tools to help you understand the current state of the database:

1. **`get_datasets_for_task`**: Get all datasets associated with a specific task. Use this when you need to look up which datasets are commonly used for a particular task. This can help you:
   - Identify if a dataset mentioned in the paper is already in the database
   - Understand which datasets are standard for a given task
   - Better match dataset names from the paper to datasets in the database

2. **`get_leaderboard_triples`**: Get all current leaderboards as (area, task, dataset, metric) tuples. Use this when you want to see what evaluation results are already being tracked for specific combinations of tasks, datasets, and metrics. This can help you:
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
    dataset_name: str
    dataset_info: str # What you know about this dataset - do not make up information, only use the information provided in the paper
    paper_title: Optional[str] = None # The title of the paper that introduces the dataset (cited in the paper)
    paper_arxiv_id: Optional[str] = None # The ArXiv ID of the paper that introduces the dataset (cited in the paper)

class Response(BaseModel):
    reasoning: str # Your reasoning regarding the extraction of the evaluation results and dataset details
    dataset_details: list[DatasetDetail] # The details of the datasets mentioned in the evaluation results
    evaluation_results: list[EvaluationResult] # The evaluation results extracted from the paper. Leave as empty list if no evaluation results are found.
```

Return the response as a JSON string. Do not include any other text in your response.
"""


async def extract_evaluation_results(paper_markdown: str) -> str:
    # Get tasks list for context
    tasks_list = get_formatted_tasks_list()

    # Build prompt with tasks context
    instructions_with_context = instructions_prompt.format(tasks_list=tasks_list)

    input_prompt = (
        f"""Here is the paper to extract evaluation results from: {paper_markdown}"""
    )

    logger.info("Calling OpenAI Agents SDK...")

    try:
        # Create agent with instructions and tools
        agent = Agent(
            name="Evaluation Results Extractor",
            instructions=instructions_with_context,
            tools=[get_task_datasets, get_leaderboard_triples_tool],
            model="gpt-5-mini",
            output_type=Step1Response,
        )

        # Run the agent with the paper markdown as input
        result_obj = await Runner.run(agent, input_prompt)

        logger.info(f"Runner.run returned: type={type(result_obj)}, value={result_obj}")

        if result_obj is None:
            logger.error("Agent returned None")
            return None

        # When using structured output_type, the result is in .final_output
        # (as seen in step_3.py and other files)
        if not hasattr(result_obj, "final_output"):
            logger.error(
                f"Result object does not have final_output attribute. Type: {type(result_obj)}, Attributes: {dir(result_obj)}"
            )
            return None

        response_obj = result_obj.final_output

        logger.info(f"final_output: type={type(response_obj)}, value={response_obj}")

        if response_obj is None:
            logger.error("result_obj.final_output is None")
            return None

        # The structured output should be a Step1Response object
        if not isinstance(response_obj, Step1Response):
            logger.warning(
                f"Response object is not Step1Response, got {type(response_obj)}. Trying to serialize anyway..."
            )
            # Try to serialize it anyway - might be a dict or other format
            if isinstance(response_obj, dict):
                return json.dumps(response_obj)
            else:
                logger.error(
                    f"Cannot serialize response object of type {type(response_obj)}"
                )
                return None

        # Serialize the Response object to JSON
        result_json = response_obj.model_dump_json()

        logger.info(f"Extracted response: {result_json[:200]}...")
        return result_json
    except Exception as e:
        logger.error(
            f"Error running agent: {type(e).__name__}: {str(e)}", exc_info=True
        )
        raise


async def step_1(arxiv_id: str):
    async with temp_pdf_download(arxiv_id=arxiv_id) as (pdf_path, error_message):
        if pdf_path is None or error_message is not None:
            logger.warning(f"Failed to download PDF for {arxiv_id}: {error_message}")
            return None

        # step 1: convert PDF to markdown
        logger.info(f"Converting PDF to markdown for {arxiv_id}")
        result = await datalab_client.convert(pdf_path)
        logger.info(
            f"PDF conversion completed. Markdown length: {len(result.markdown) if result.markdown else 0}"
        )

        # step 2: extract evaluation results
        logger.info(f"Extracting evaluation results for {arxiv_id}")
        response = await extract_evaluation_results(result.markdown)
        await async_export_txt(filename=f"step_1_{arxiv_id}", value=response)
        logger.info(
            f"Extraction completed. Response: {response[:200] if response else 'None'}..."
        )
        return response


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
