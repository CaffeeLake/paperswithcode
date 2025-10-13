"""
This script can be used to extract organizations (e.g. NVIDIA, Google, etc.) from a paper.
"""

import argparse
import asyncio
import json
from typing import Optional

from pydantic import BaseModel

from huggingface_hub import hf_hub_download

from backend.utils.prompt_utils import load_prompt
from backend.utils.logging_utils import async_export_txt
from backend.utils.pdf_utils import (
    temp_pdf_download,
    extract_first_two_pages_pymupdf,
)
from backend.utils.paper_utils import get_title

from backend.models.generators import Message
from backend.generators.google_generator import GoogleGenerator


class OrgsOnPage(BaseModel):
    reasoning: str
    orgs: list[str]


# load variables
generator = GoogleGenerator()
template = load_prompt("extract_orgs.json")

# few-shots (only including examples with available PDFs in HuggingFace)
arxiv_ids = [
    "2508.16153",
    "2508.08240",
    "2508.13650",
    "2508.07877",
    "2508.14704",
]

paper_titles = [
    "Memento: Fine-tuning LLM Agents without Fine-tuning LLMs",
    "ODYSSEY: Open-World Quadrupeds Exploration and Manipulation for Long-Horizon Tasks",
    "CRISP: Persistent Concept Unlearning via Sparse Autoencoders",
    "Selective Contrastive Learning for Weakly Supervised Affordance Grounding",
    "MCP-Universe: Benchmarking Large Language Models with Real-World Model Context Protocol Servers",
]

paper_authors = [
    [
        "Huichi Zhou, Yihang Chen, Siyuan Guo, Xue Yan, Kin Hei Lee, Zihan Wang, Ka Yiu Lee, Guchun Zhang, Kun Shao, Linyi Yang, Jun Wang"
    ],
    [
        "Kaijun Wang, Liqin Lu, Mingyu Liu, Jianuo Jiang, Zeju Li, Bolin Zhang, Wancai Zheng, Xinyi Yu, Hao Chen, Chunhua Shen"
    ],
    ["Tomer Ashuach, Dana Arad, Aaron Mueller, Martin Tutek, Yonatan Belinkov"],
    ["WonJun Moon, Hyun Seok Seong, Jae-Pil Heo"],
    [
        "Ziyang Luo, Zhiqi Shen, Wenzhuo Yang, Zirui Zhao, Prathyusha Jwalapuram, Amrita Saha, Doyen Sahoo, Silvio Savarese, Caiming Xiong, Junnan Li"
    ],
]

reasoning_examples = [
    """
The first page of the PDF reveals that the authors are part of 4 different organizations:
1. AI Centre, UCL
2. Huawei Noah's Ark Lab, UK
3. Jilin University
4. Institute of Automation, CAS.
Hence, we return these as separate organizations.
""",
    """
The first page of the PDF reveals that the authors are part of 3 organizations:
1. Zhejiang University
2. Zhejiang University of Technology
3. The Chinese University of Hong Kong, Shenzhen.

Hence, we return these as separate organizations.
""",
    """
The first page of the PDF reveals that the authors part of the following organizations:
1. Technion – Israel Institute of Technology
2. Boston University
3. TakeLab, University of Zagreb.

Hence, we return these as 3 separate organizations.
""",
    """
The first page of the PDF reveals that all authors are part of the same organization: Sungkyunkwan University.

Hence, we return a single organization: Sungkyunkwan University.
""",
    """
The first page of the PDF reveals that all authors are part of the same organization: Salesforce AI Research.

Hence, we return a single organization: Salesforce AI Research.
""",
]

response_examples = [
    [
        "AI Centre, UCL",
        "Huawei Noah's Ark Lab, UK",
        "Jilin University",
        "Institute of Automation, CAS.",
    ],
    [
        "Zhejiang University",
        "Zhejiang University of Technology",
        "The Chinese University of Hong Kong, Shenzhen.",
    ],
    [
        "Technion – Israel Institute of Technology",
        "Boston University",
        "TakeLab, University of Zagreb.",
    ],
    ["Sungkyunkwan University"],
    ["Salesforce AI Research"],
]


async def create_user_message(
    arxiv_id: str, title: str, authors: list[str], pdf_path: Optional[str] = None
) -> Message:
    """
    Create a user message for the LLM API.
    """
    prompt = template.format(
        arxiv_id=arxiv_id,
        paper_title=title,
        paper_authors=str(authors),
    )

    user_message = Message(role="user", content=prompt, pdf_path=pdf_path)

    await async_export_txt(filename="extract_orgs", value=prompt)

    return user_message


async def extract_orgs(
    arxiv_id: str, title: str, authors: list[str], pdf_path: Optional[str] = None
) -> list[str]:
    """
    Extract organizations from a paper.
    """
    messages = []

    # add few-shot examples
    for (
        example_arxiv_id,
        example_title,
        example_authors,
        example_reasoning,
        example_response,
    ) in zip(
        arxiv_ids, paper_titles, paper_authors, reasoning_examples, response_examples
    ):
        example_pdf_path = await asyncio.to_thread(
            hf_hub_download,
            repo_id="nielsr/paper-page-assets",
            filename=f"orgs_on_page_few_shots/pdf_{example_arxiv_id}.pdf",
            repo_type="dataset",
        )
        user_message = await create_user_message(
            arxiv_id=example_arxiv_id,
            title=example_title,
            authors=example_authors,
            pdf_path=example_pdf_path,
        )
        messages.append(user_message)
        assistant_content = {"reasoning": example_reasoning, "orgs": example_response}
        messages.append(
            Message(role="assistant", content=json.dumps(assistant_content))
        )

    # add user message
    user_message = await create_user_message(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        pdf_path=pdf_path,
    )
    messages.append(user_message)

    # generate response
    response, model_name = await generator.generate(messages, schema=OrgsOnPage)

    # parse response
    reasoning = response["reasoning"]
    orgs = response["orgs"]

    return reasoning, orgs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arxiv_id", type=str, required=True)
    args = parser.parse_args()

    async def main(arxiv_id: str) -> tuple[str, list[str]]:
        title = await get_title(arxiv_id=arxiv_id)
        authors = []  # TODO: get authors from arXiv

        reasoning, orgs = None, None
        async with temp_pdf_download(arxiv_id=arxiv_id) as (pdf_path, error_message):
            if pdf_path is not None:
                pdf_path_processed = await extract_first_two_pages_pymupdf(pdf_path)
                if pdf_path_processed:
                    print(f"Extracting orgs from {arxiv_id}...")
                    reasoning, orgs = await extract_orgs(
                        arxiv_id=arxiv_id,
                        title=title,
                        authors=authors,
                        pdf_path=pdf_path_processed,
                    )
                else:
                    raise ValueError(
                        f"Failed to process PDF for {arxiv_id} due to error: {error_message}"
                    )
            else:
                raise ValueError(
                    f"Failed to download PDF for {arxiv_id} due to error: {error_message}"
                )

        return reasoning, orgs

    reasoning, orgs = asyncio.run(main(arxiv_id=args.arxiv_id))
    print("Reasoning:")
    print(reasoning)
    print("Orgs:")
    print(orgs)
