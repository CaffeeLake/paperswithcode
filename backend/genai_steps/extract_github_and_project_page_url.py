"""
This step uses an LLM to get the Github URL and project page URL
from a given paper, using the comments of the paper page + first 2 pages of the PDF.
"""

import argparse
from typing import Optional
import asyncio

from pydantic import BaseModel

from huggingface_hub import hf_hub_download

from backend.utils.prompt_utils import load_prompt
from backend.utils.logging_utils import async_export_txt
from backend.utils.verify_url import verify_url
from backend.utils.pdf_utils import (
    extract_text_from_pdf,
    safe_extract_hyperlinks_async,
    temp_pdf_download,
    find_project_page_url,
    safe_pdf_to_images_async,
)
from backend.utils.paper_utils import (
    get_abstract,
    get_comments,
    find_github_url,
    get_github_and_project_page_urls_from_daily_papers,
)

from backend.models.generators import Message
from backend.generators.openrouter_generator import OpenRouterGenerator


class Response(BaseModel):
    reasoning: str
    github_url: str
    project_page_url: str


# Initialize variables
template = load_prompt("extract_github_and_project_page_url.json")


# add few-shots
arxiv_ids = [
    "2409.18313",
    "2410.00337",
    "2410.02760",
    "2410.02613",
    "2410.02362",
    "2410.04534",
    "2410.05080",
    "2410.04422",
    "2410.13852",
    "2408.00714",
]

responses = [
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper does not mention any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page does not mention any Github or project page URL.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a footnote, which mentions the project page URL: https://quanting-xie.github.io/Embodied-RAG-web/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://quanting-xie.github.io/Embodied-RAG-web/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper does not mention any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment mentioning the project page: https://len-li.github.io/syntheocc-web/. The Github URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF also mentions the same project page: https://len-li.github.io/syntheocc-web/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://len-li.github.io/syntheocc-web/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper mentions \\"Our code, data, and trained models are available at https://elm.baulab.info\\". Hence, the project page URL is https://elm.baulab.info/.\\nThe Github URL is not mentioned.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment mentioning the project page: https://elm.baulab.info/, link to the Github repository: https://github.com/rohitgandikota/erasing-llm\\nand trained models: https://elm.baulab.info/models/elm-wmdp/.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF mentions the project page at the end of the abstract: https://elm.baulab.info/. The Github URL is not mentioned.", "github_url": "https://github.com/rohitgandikota/erasing-llm", "project_page_url": "https://elm.baulab.info/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract of the paper does not mention any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes one comment, but does not include any links to the project page or Github repository.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a footnote which mentions the project page URL: https://venturamor.github.io/NLEye/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://venturamor.github.io/NLEye/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract mentions \\"A comprehensive list of Mamba architectures applied in the medical field, reviewed in this work, is available at Github\\", but\\ndoes not include a direct link to the repository. The project page URL is not mentioned.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment mentioning \\"You can access the papers covered in this survey through the following link: https://github.com/madhavaprasath23/awesome-mamba-papers-on-medical-domain\\".\\nHence, the Github URL is https://github.com/madhavaprasath23/awesome-mamba-papers-on-medical-domain. The project page URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the Github repository: https://github.com/Madhavaprasath23/Awesome-Mamba-Papers-On-Medical-Domain. The project page is not mentioned.", "github_url": "https://github.com/Madhavaprasath23/Awesome-Mamba-Papers-On-Medical-Domain", "project_page_url": ""}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract mentions: \\"Quantitative results are available in the https://hanyangclarence.github.io/unimumo_demo/{project page}.\\" Hence, the project page URL\\nis https://hanyangclarence.github.io/unimumo_demo. The Github URL is not mentioned.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment by akhaliq mentioning the project page: https://hanyangclarence.github.io/unimumo_demo/.\\nA similar link is present in the abstract. The Github URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the project page: https://hanyangclarence.github.io/unimumo_demo/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://hanyangclarence.github.io/unimumo_demo/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page does not mention any Github or project page URL in the comments.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the project page: https://osu-nlp-group.github.io/ScienceAgentBench/. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://osu-nlp-group.github.io/ScienceAgentBench/"}',
    '{"reasoning": "**Abstract**\\n\\nThe abstract does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment by the author, stating that \\"Our code is publicly available at https://github.com/yuyijiong/hard_retrieval_for_llm\\".\\nHence, the Github URL is https://github.com/yuyijiong/hard_retrieval_for_llm. The project page URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF includes a link to the Github repository: https://github.com/yuyijiong/hard_retrieval_for_llm/. The project page URL is not mentioned.", "github_url": "https://github.com/yuyijiong/hard_retrieval_for_llm", "project_page_url": ""}',
    '{"reasoning": "**Abstract**\\nThe abstract does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment by the author, but it does not include a Github or project page URL.\\n\\n**PDF (First 2 Pages):**\\n\\nThe second page of the PDF includes the sentence \\"Our code, data, and models are at https://lil-lab.github.io/respect.\\". Given this link includes\\ngithub.io, it is likely the project page URL. The Github URL is not mentioned.", "github_url": "", "project_page_url": "https://lil-lab.github.io/respect"}',
    '{"reasoning": "**Abstract**\\nThe abstract mentions \\"We are releasing a version of our model, the dataset and an interactive demo.\\", but does not include any Github or project page URL.\\n\\n**Hugging Face Paper Page:**\\n\\nThe Hugging Face paper page includes a comment specifying https://ai.meta.com/sam2/, hence this refers to the project page. A Github URL is not mentioned.\\n\\n**PDF (First 2 Pages):**\\n\\nThe first page of the PDF mentions \\"Code: https://github.com/facebookresearch/sam2, Website: https://ai.meta.com/sam2/\\". Hence both the Github URL and project page\\nURL are mentioned.", "github_url": "https://github.com/facebookresearch/sam2", "project_page_url": "https://ai.meta.com/sam2/"}',
]


async def create_user_message(arxiv_id: str, pdf_file_path: str = None) -> Message:
    """
    Create a user message for the Gemini API in an asynchronous manner.
    """
    # Get the abstract of the paper
    abstract = await get_abstract(arxiv_id=arxiv_id)

    # Get the comments of the paper page
    paper_page_comments = await get_comments(arxiv_id)

    # Get the text of the first two pages of the PDF
    pdf_text = await asyncio.to_thread(extract_text_from_pdf, pdf_path=pdf_file_path)

    # Get the hyperlinks from the PDF
    hyperlinks = await safe_extract_hyperlinks_async(pdf_file_path, timeout_seconds=10)

    prompt = template.format(
        abstract=abstract,
        paper_page_comments=paper_page_comments,
        pdf_text=pdf_text,
        hyperlinks=hyperlinks,
    )

    await async_export_txt(
        filename="extract_github_and_project_page_url_prompt", value=prompt
    )

    # extract the images from the PDF
    image_paths = await safe_pdf_to_images_async(pdf_file_path, timeout_seconds=30)

    message = Message(
        role="user", content=prompt, pdf_path=pdf_file_path, image_paths=image_paths
    )

    return message


async def get_project_github_urls(
    arxiv_id: str,
    pdf_path: str,
    session_id: str,
    github_url: Optional[str] = None,
    use_reasoning: bool = True,
) -> str:
    generator = OpenRouterGenerator()

    assert len(arxiv_ids) == len(responses)

    # First try simple things: daily papers API and regex
    print("Trying simple methods...")
    (
        github_url,
        project_page_url,
    ) = await get_github_and_project_page_urls_from_daily_papers(arxiv_id)

    if github_url == "":
        github_url = await find_github_url(arxiv_id)
    if project_page_url == "":
        project_page_url = await find_project_page_url(pdf_path)

    print("Github URL:", github_url, flush=True)
    print("Project page URL:", project_page_url, flush=True)

    reasoning = ""
    response = {"github_url": github_url, "project_page_url": project_page_url}
    if github_url == "":
        print("No Github URL found, trying LLM...")
        # Add few-shots
        messages = []
        for idx, (few_shot_arxiv_id, response_content) in enumerate(
            zip(arxiv_ids, responses)
        ):
            # Get PDF
            pdf_file_path = await asyncio.to_thread(
                hf_hub_download,
                repo_id="nielsr/paper-page-assets",
                filename=f"paper_pdfs_step_1/pdf_{idx}.pdf",
                repo_type="dataset",
            )

            message = await create_user_message(few_shot_arxiv_id, pdf_file_path)
            messages.append(message)
            messages.append(Message(role="assistant", content=response_content))

        # Add query
        print("Processing main query...")
        message = await create_user_message(arxiv_id, pdf_path)
        messages.append(message)

        response_str, _ = await generator.generate(
            messages=messages, schema=Response, use_reasoning=use_reasoning
        )

        reasoning = response_str.reasoning
        project_page_url = response_str.project_page_url
        github_url = response_str.github_url

        # verify the project page URL
        if isinstance(project_page_url, str):
            is_valid_url = await asyncio.to_thread(verify_url, project_page_url)
            project_page_url = project_page_url if is_valid_url else ""
            # Update the main response dictionary with potentially modified LLM response
            response = {"github_url": github_url, "project_page_url": project_page_url}
        else:
            # Handle case where LLM response wasn't a dict as expected
            # or if get_section_content returned something else
            response = {"github_url": "", "project_page_url": ""}

    return reasoning, response


async def main(arxiv_id: str, use_reasoning: bool = True):
    async with temp_pdf_download(arxiv_id=arxiv_id) as pdf_path:
        reasoning, response = await get_project_github_urls(
            arxiv_id=arxiv_id,
            pdf_path=pdf_path,
            session_id=None,
            use_reasoning=use_reasoning,
        )

        print("\n" + "=" * 50)
        print("FINAL RESULTS:")
        print("=" * 50)
        print(f"ArXiv ID: {arxiv_id}")
        print(f"GitHub URL: {response.get('github_url', 'Not found')}")
        print(f"Project Page URL: {response.get('project_page_url', 'Not found')}")
        if reasoning:
            print(f"Reasoning: {reasoning}")
        print("=" * 50)


if __name__ == "__main__":
    # Create an argument parser
    parser = argparse.ArgumentParser(
        description="Get Github URL and project page URL from paper."
    )
    parser.add_argument(
        "--arxiv_id", type=str, help="Arxiv ID of the paper.", default="2509.14033"
    )
    parser.add_argument(
        "--no-reasoning", action="store_true", help="Disable reasoning tokens"
    )

    # Parse the arguments
    args = parser.parse_args()

    # Call the main function with the parsed arguments
    asyncio.run(main(args.arxiv_id, use_reasoning=not args.no_reasoning))
