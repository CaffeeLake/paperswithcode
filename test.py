"""
This script automatically extracts evaluation results from a paper and writes them to a JSON file.

You can run it like so:

```bash
uv run --env-file keys.env test.py
```
"""

import argparse
import asyncio

from datalab_sdk import AsyncDatalabClient

from generators import init_generator
from models import Message

generator = init_generator()

# You can also set DATALAB_API_KEY
client = AsyncDatalabClient(api_key="037LoXuxCP_p5qKxNRi08FyxvnItZdGdLuWH7ls7y4s")


async def extract_evaluation_results(paper_markdown: str) -> str:
    prompt = f"""
We have converted an AI research PDF paper on Arxiv to Markdown.

Your task is to extract the evaluation results which are useful to be added for leaderboard data. Only include evaluation results out of tables that are included in the paper.
Only include evaluation results of models that the paper introduces, not evaluation results of models of other works.

Each evaluation result should be of the tuple of the form (model_name, dataset_name, metric_name, metric_value).

Make sure to only return evaluation results which are useful for leaderboards (which compare performance across different models on the same datasets), do not include results from ablation tables or other tables.

Here is the paper:
{paper_markdown}
"""

    messages = [Message(role="user", content=prompt)]
    response, _ = await generator.generate(messages)
    return response


async def main(pdf_path: str):
    # step 1: convert PDF to markdown
    result = await client.convert(pdf_path)
    print(result.markdown)

    # step 2: extract evaluation results
    evaluation_results = await extract_evaluation_results(result.markdown)

    return evaluation_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract evaluation results from a paper."
    )
    parser.add_argument(
        "--pdf_path",
        type=str,
        required=False,
        default="/Users/nielsrogge/Downloads/2508.03983v1 (1).pdf",
    )
    args = parser.parse_args()

    evaluation_results = asyncio.run(main(args.pdf_path))
    print(evaluation_results)
