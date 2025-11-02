"""
This script automatically extracts evaluation results from a paper and writes them to a JSON file.

It uses the Datalab API to convert a PDF to Markdown.
Then it uses the OpenAI API to extract evaluation results from the Markdown content.

You can run it like so:

```bash
uv run --env-file backend/keys.env extract_evaluation_results/step_1.py --arxiv_id 2201.03545
```
"""

import argparse
import asyncio
import logging
import os

from backend.utils.logging_utils import async_export_txt
from backend.utils.pdf_utils import temp_pdf_download

from datalab_sdk import AsyncDatalabClient

from openai import AsyncOpenAI

from backend.config import get_settings

settings = get_settings()
DATALAB_API_KEY = settings.datalab_api_key

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
datalab_client = AsyncDatalabClient(api_key=DATALAB_API_KEY)


instructions_prompt = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI).

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
* An ablation table compares different permutations of the paper’s methodology.
* Lastly, irrelevant tables include hyperparameters, dataset statistics and other information that is not directly relevant for result extraction.

Your task is to only extract evaluation results from the leaderboard tables.

## Evaluation results

Importantly, only the best performing results of the paper on each benchmark should be included, as otherwise we end up with too many evaluation results.
Hence, evaluation results of the appendix of a paper should not be included.

## Output format

Use the following Pydantic model to format your response:
```python
class EvaluationResult(BaseModel):
    table_index: int
    model_name: str
    dataset_name: str
    paper_title: Optional[str] = None # The title of the paper that introduces the dataset (potentially cited)
    paper_arxiv_id: Optional[str] = None # The ArXiv ID of the paper that introduces the dataset (potentially cited)
    metric_name: str
    metric_value: str


class EvaluationResults(BaseModel):
    evaluation_results: list[EvaluationResult]
```

Return the response as a JSON string. Do not include any other text in your response.
"""


instructions_prompt_2 = """
You are part of the community science team at Hugging Face, whose goal is to provide a comprehensive overview of the AI research landscape by creating leaderboards for datasets and tasks
within the field of machine learning and artificial intelligence (AI).

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
* An ablation table compares different permutations of the paper’s methodology.
* Lastly, irrelevant tables include hyperparameters, dataset statistics and other information that is not directly relevant for result extraction.

Your task is to only extract evaluation results from the leaderboard tables.

## Evaluation results

Importantly, only the best performing results of the paper on each benchmark should be included, as otherwise we end up with too many evaluation results.
Hence, evaluation results of the appendix of a paper should not be included.

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
    input_prompt = (
        f"""Here is the paper to extract evaluation results from: {paper_markdown}"""
    )

    logger.info("Calling OpenAI Responses API...")
    response = await asyncio.wait_for(
        openai_client.responses.create(
            model="gpt-5",
            instructions=instructions_prompt_2,
            input=input_prompt,
        ),
        timeout=300.0,
    )

    # Extract content from response
    if hasattr(response, "output_text"):
        result = response.output_text
    elif hasattr(response, "output") and response.output:
        result = (
            "\n".join(
                [
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in response.output
                ]
            )
            if isinstance(response.output, list)
            else str(response.output)
        )
    else:
        result = str(response)

    logger.info(f"Extracted text length: {len(result) if result else 0}")
    return result


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
    print(response)

    # Close clients to avoid unclosed session warnings
    asyncio.run(datalab_client.close())
