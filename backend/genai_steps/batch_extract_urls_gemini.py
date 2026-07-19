"""
Gemini Batch API URL Extraction Script

This script processes papers in bulk using Google Gemini's Batch API to extract
GitHub repository URLs and project page URLs at 50% cost compared to real-time API.

Key Features:
- Processes papers with urls_extracted = FALSE
- Uploads PDFs to Gemini Files API
- Includes 10 few-shot examples per request for better accuracy
- Uses JSON Schema for structured output (Gemini 2.5 preview feature)
- Submits batch job and polls for completion
- Saves results to JSON file for manual review
- Optional database update with --apply-to-db flag

Cost Savings:
- Batch API: 50% discount on standard pricing
- Gemini 2.5 Flash: ~$0.15 per 1M tokens (batch rate)
- Average: ~20k tokens per paper = ~$0.003 per paper
- 100 papers: ~$0.30, 10,000 papers: ~$30

Usage:
```bash
# Process 100 papers, save results for review
uv run --env-file backend/keys.env -m backend.genai_steps.batch_extract_urls_gemini --limit 100

# Apply results to database after review
uv run --env-file backend/keys.env -m backend.genai_steps.batch_extract_urls_gemini --limit 100 --apply-to-db

# Resume a previous batch job
uv run --env-file backend/keys.env -m backend.genai_steps.batch_extract_urls_gemini --resume batches/abc123
```
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from google import genai
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.utils.pdf_utils import (
    temp_pdf_download,
    extract_first_two_pages_pymupdf,
)
from backend.utils.paper_utils import get_abstract, get_comments
from backend.utils.prompt_utils import load_prompt
from backend.utils.verify_url import verify_url
from backend.genai_steps.extract_github_and_project_page_url import (
    FewShotPDFCache,
    arxiv_ids as few_shot_arxiv_ids,
    responses as few_shot_responses,
    ARXIV_RATE_LIMIT_DELAY,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Response(BaseModel):
    """Schema for LLM response."""

    reasoning: str
    github_url: str
    project_page_url: str


class GeminiBatchExtractor:
    """Batch processor for extracting URLs using Gemini Batch API."""

    def __init__(
        self,
        output_dir: str = "./batch_results",
        start_year: int = 2014,
        poll_interval: int = 60,
        apply_to_db: bool = False,
    ):
        self.settings = get_settings()
        self.client = genai.Client(api_key=self.settings.gemini_api_key)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.start_year = start_year
        self.poll_interval = poll_interval
        self.apply_to_db = apply_to_db

        # Load prompt template
        self.prompt_template = load_prompt("extract_github_and_project_page_url.json")

        # Initialize PDF cache for few-shot examples
        self.pdf_cache = FewShotPDFCache()

        # Tracking
        self.uploaded_files = {}  # arxiv_id -> file_uri
        self.few_shot_file_uris = []  # List of file URIs for few-shot examples
        self.paper_data = {}  # arxiv_id -> paper metadata
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Rate limiting for ArXiv
        self._last_arxiv_request_time = None

    async def _rate_limit_arxiv(self):
        """Ensure we respect ArXiv's rate limit of 1 request per 3 seconds."""
        if self._last_arxiv_request_time is not None:
            elapsed = time.time() - self._last_arxiv_request_time
            if elapsed < ARXIV_RATE_LIMIT_DELAY:
                wait_time = ARXIV_RATE_LIMIT_DELAY - elapsed
                logger.debug(
                    f"Rate limiting: waiting {wait_time:.2f}s before ArXiv request"
                )
                await asyncio.sleep(wait_time)

        self._last_arxiv_request_time = time.time()

    def get_papers_to_process(self, db: Session, limit: int) -> List[Dict[str, Any]]:
        """Query papers that need URL extraction."""
        start_date = f"{self.start_year}-01-01"

        query = """
        SELECT
            p.id,
            p.arxiv_id,
            p.title,
            p.abstract,
            p.date_published
        FROM papers p
        WHERE p.abstract IS NOT NULL
          AND p.abstract != ''
          AND p.arxiv_id IS NOT NULL
          AND p.arxiv_id != ''
          AND p.date_published >= :start_date
          AND p.urls_extracted = FALSE
        ORDER BY
            p.date_published DESC NULLS LAST,
            p.id DESC
        LIMIT :limit
        """

        result = db.execute(
            text(query), {"start_date": start_date, "limit": limit}
        ).fetchall()

        papers = [
            {
                "id": row.id,
                "arxiv_id": row.arxiv_id,
                "title": row.title,
                "abstract": row.abstract,
                "date_published": str(row.date_published)
                if row.date_published
                else None,
            }
            for row in result
        ]

        logger.info(f"Found {len(papers)} papers to process")
        if papers:
            logger.info("Sample papers:")
            for i, paper in enumerate(papers[:3]):
                logger.info(
                    f"  {i + 1}. {paper['arxiv_id']} - {paper['title'][:80]}..."
                )

        return papers

    async def upload_pdf_to_gemini(self, arxiv_id: str, pdf_path: str) -> Optional[str]:
        """Upload a PDF file to Gemini Files API."""
        try:
            uploaded_file = await asyncio.to_thread(
                self.client.files.upload,
                file=pdf_path,
                config={
                    "display_name": f"paper_{arxiv_id}.pdf",
                    "mime_type": "application/pdf",
                },
            )
            logger.debug(f"Uploaded {arxiv_id}: {uploaded_file.name}")
            return uploaded_file.name
        except Exception as e:
            logger.error(f"Failed to upload PDF for {arxiv_id}: {e}")
            return None

    async def download_and_upload_papers(
        self, papers: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Download PDFs from ArXiv and upload to Gemini Files API."""
        logger.info(f"Downloading and uploading {len(papers)} PDFs to Gemini...")

        uploaded_files = {}
        failed_papers = []

        for i, paper in enumerate(papers):
            arxiv_id = paper["arxiv_id"]

            try:
                # Rate limit ArXiv requests
                await self._rate_limit_arxiv()

                logger.info(f"[{i + 1}/{len(papers)}] Processing {arxiv_id}...")

                # Download PDF from ArXiv
                async with temp_pdf_download(arxiv_id=arxiv_id) as (
                    pdf_path,
                    error_message,
                ):
                    if pdf_path is None or error_message is not None:
                        logger.warning(
                            f"Failed to download PDF for {arxiv_id}: {error_message}"
                        )
                        failed_papers.append(arxiv_id)
                        continue

                    # Extract first 2 pages
                    pdf_path_processed = await extract_first_two_pages_pymupdf(pdf_path)

                    # Upload to Gemini
                    file_uri = await self.upload_pdf_to_gemini(
                        arxiv_id, pdf_path_processed
                    )

                    if file_uri:
                        uploaded_files[arxiv_id] = file_uri
                        self.paper_data[arxiv_id] = paper
                        logger.info(f"✓ {arxiv_id}: PDF uploaded")
                    else:
                        failed_papers.append(arxiv_id)
                        logger.warning(f"✗ {arxiv_id}: Upload failed")

            except Exception as e:
                logger.error(f"Error processing {arxiv_id}: {e}")
                failed_papers.append(arxiv_id)
                continue

        logger.info(
            f"Successfully uploaded: {len(uploaded_files)}/{len(papers)} papers"
        )
        if failed_papers:
            logger.warning(f"Failed papers: {', '.join(failed_papers)}")

        self.uploaded_files = uploaded_files
        return uploaded_files

    async def prepare_few_shot_examples(self) -> List[Dict[str, Any]]:
        """Download and upload few-shot example PDFs, create example messages."""
        logger.info("Preparing few-shot examples...")

        few_shot_messages = []

        for idx, (arxiv_id, response_content) in enumerate(
            zip(few_shot_arxiv_ids, few_shot_responses)
        ):
            try:
                # Get cached PDF path
                pdf_path = await self.pdf_cache.get_pdf_path(idx)

                # Upload to Gemini if not already uploaded
                if idx >= len(self.few_shot_file_uris):
                    file_uri = await self.upload_pdf_to_gemini(
                        f"fewshot_{idx}_{arxiv_id}", pdf_path
                    )
                    if file_uri:
                        self.few_shot_file_uris.append(file_uri)
                        logger.debug(f"Uploaded few-shot example {idx}: {arxiv_id}")
                else:
                    file_uri = self.few_shot_file_uris[idx]

                if not file_uri:
                    logger.warning(
                        f"Failed to upload few-shot example {idx}: {arxiv_id}"
                    )
                    continue

                # Create user message (without downloading PDF again, reuse abstract/comments)
                abstract = await get_abstract(arxiv_id=arxiv_id)
                paper_page_comments = await get_comments(arxiv_id=arxiv_id)

                # For few-shot, we don't need PDF text extraction (the PDF image is enough)
                # But we'll include placeholder text to maintain format
                pdf_text = "[PDF content - see attached file]"
                hyperlinks = "[]"

                prompt = self.prompt_template.format(
                    abstract=abstract,
                    paper_page_comments=paper_page_comments,
                    pdf_text=pdf_text,
                    hyperlinks=hyperlinks,
                )

                # Create user/assistant pair for few-shot
                few_shot_messages.append(
                    {"role": "user", "content": prompt, "file_uri": file_uri}
                )
                few_shot_messages.append(
                    {"role": "assistant", "content": response_content}
                )

            except Exception as e:
                logger.error(
                    f"Failed to prepare few-shot example {idx} ({arxiv_id}): {e}"
                )
                continue

        logger.info(f"Prepared {len(few_shot_messages) // 2} few-shot examples")
        return few_shot_messages

    async def create_batch_requests(
        self, uploaded_files: Dict[str, str], few_shot_messages: List[Dict[str, Any]]
    ) -> str:
        """Create JSONL file with batch requests."""
        logger.info("Creating batch requests JSONL file...")

        jsonl_path = self.output_dir / f"batch_requests_{self.timestamp}.jsonl"

        # Generate JSON Schema from Response model
        response_schema = Response.model_json_schema()
        logger.debug(f"Generated JSON Schema: {json.dumps(response_schema, indent=2)}")

        with open(jsonl_path, "w") as f:
            for arxiv_id, file_uri in uploaded_files.items():
                try:
                    paper = self.paper_data[arxiv_id]

                    # Get paper metadata
                    abstract = paper["abstract"]
                    paper_page_comments = await get_comments(arxiv_id=arxiv_id)

                    # For batch API, we don't extract text from PDF (it's in the file)
                    # But we include hyperlinks and structure
                    pdf_text = "[PDF content - see attached file]"
                    hyperlinks = "[]"

                    # Create prompt
                    prompt = self.prompt_template.format(
                        abstract=abstract,
                        paper_page_comments=paper_page_comments,
                        pdf_text=pdf_text,
                        hyperlinks=hyperlinks,
                    )

                    # Build contents array with few-shot examples + query
                    contents = []

                    # Add few-shot examples
                    for msg in few_shot_messages:
                        if msg["role"] == "user":
                            contents.append(
                                {
                                    "role": "user",
                                    "parts": [
                                        {"text": msg["content"]},
                                        {"file_data": {"file_uri": msg["file_uri"]}},
                                    ],
                                }
                            )
                        else:
                            contents.append(
                                {"role": "model", "parts": [{"text": msg["content"]}]}
                            )

                    # Add main query
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {"file_data": {"file_uri": file_uri}},
                            ],
                        }
                    )

                    # Create batch request with JSON Schema for structured output
                    # Using response_json_schema (preview feature for Gemini 2.5)
                    batch_request = {
                        "key": f"paper_{paper['id']}_{arxiv_id}",
                        "request": {
                            "contents": contents,
                            "generation_config": {
                                "response_mime_type": "application/json",
                                "response_json_schema": response_schema,
                            },
                        },
                    }

                    # Write to JSONL
                    f.write(json.dumps(batch_request) + "\n")

                except Exception as e:
                    logger.error(f"Failed to create request for {arxiv_id}: {e}")
                    continue

        logger.info(f"Created batch requests file: {jsonl_path}")
        return str(jsonl_path)

    async def upload_batch_file(self, jsonl_path: str) -> str:
        """Upload JSONL file to Gemini Files API."""
        logger.info("Uploading batch requests file to Gemini...")

        try:
            uploaded_file = await asyncio.to_thread(
                self.client.files.upload,
                file=jsonl_path,
                config={
                    "display_name": f"batch_requests_{self.timestamp}.jsonl",
                    "mime_type": "text/jsonl",  # Changed from 'application/jsonl'
                },
            )
            logger.info(f"Uploaded batch file: {uploaded_file.name}")
            return uploaded_file.name  # Return file name, not URI
        except Exception as e:
            logger.error(f"Failed to upload batch file: {e}")
            raise

    async def submit_batch_job(self, input_file_name: str) -> Any:
        """Submit batch job to Gemini Batch API."""
        logger.info("Submitting batch job to Gemini Batch API...")

        try:
            # Create batch job with uploaded file
            batch_job = await asyncio.to_thread(
                self.client.batches.create,
                model="models/gemini-3.5-flash",
                src=input_file_name,  # File name, not URI
                config={"display_name": f"url_extraction_{self.timestamp}"},
            )

            logger.info(f"✓ Batch job created: {batch_job.name}")
            logger.info(f"  Status: {batch_job.state}")

            # Save job metadata
            metadata_path = self.output_dir / f"batch_job_{self.timestamp}.json"
            with open(metadata_path, "w") as f:
                json.dump(
                    {
                        "job_name": batch_job.name,
                        "timestamp": self.timestamp,
                        "state": str(batch_job.state)
                        if hasattr(batch_job.state, "__str__")
                        else batch_job.state,
                        "created_at": datetime.now().isoformat(),
                        "input_file_name": input_file_name,
                    },
                    f,
                    indent=2,
                )

            logger.info(f"Saved job metadata: {metadata_path}")

            return batch_job

        except Exception as e:
            logger.error(f"Failed to submit batch job: {e}")
            raise

    async def poll_batch_job(self, job_name: str) -> Any:
        """Poll batch job until completion."""
        logger.info(f"Polling batch job: {job_name}")
        logger.info(f"Check interval: {self.poll_interval}s")

        start_time = time.time()
        max_wait_time = 26 * 60 * 60  # 26 hours

        while True:
            elapsed = time.time() - start_time

            if elapsed > max_wait_time:
                logger.error("Batch job timed out after 26 hours")
                raise TimeoutError("Batch job exceeded maximum wait time")

            try:
                batch_job = await asyncio.to_thread(
                    self.client.batches.get, name=job_name
                )

                elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
                logger.info(f"[{elapsed_str}] Status: {batch_job.state}")

                if batch_job.state == "JOB_STATE_SUCCEEDED":
                    logger.info("✓ Batch job completed successfully!")
                    return batch_job

                elif batch_job.state == "JOB_STATE_FAILED":
                    error_msg = getattr(batch_job, "error", "Unknown error")
                    logger.error(f"✗ Batch job failed: {error_msg}")
                    raise RuntimeError(f"Batch job failed: {error_msg}")

                elif batch_job.state == "JOB_STATE_CANCELLED":
                    logger.error("✗ Batch job was cancelled")
                    raise RuntimeError("Batch job was cancelled")

                elif batch_job.state in ["JOB_STATE_PENDING", "JOB_STATE_PROCESSING"]:
                    # Still processing, continue polling
                    await asyncio.sleep(self.poll_interval)

                else:
                    logger.warning(f"Unknown job state: {batch_job.state}")
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                if "Batch job" in str(e):
                    raise  # Re-raise our own errors
                logger.error(f"Error polling batch job: {e}")
                await asyncio.sleep(self.poll_interval)

    async def download_and_parse_results(self, batch_job: Any) -> List[Dict[str, Any]]:
        """Download and parse batch job results."""
        logger.info("Downloading batch job results...")

        try:
            # Get output file name from batch job
            if hasattr(batch_job, "dest") and hasattr(batch_job.dest, "responsesFile"):
                output_file_name = batch_job.dest.responsesFile
                logger.info(f"Output file: {output_file_name}")
            elif hasattr(batch_job, "response") and hasattr(
                batch_job.response, "responsesFile"
            ):
                output_file_name = batch_job.response.responsesFile
                logger.info(f"Output file: {output_file_name}")
            else:
                logger.error("No output file in batch job response")
                logger.error(f"Batch job attributes: {dir(batch_job)}")
                return []

            # Download output file
            output_content = await asyncio.to_thread(
                self.client.files.download, name=output_file_name
            )

            # Parse JSONL content
            results = []

            # Handle both bytes and string responses
            if isinstance(output_content, bytes):
                lines = output_content.decode("utf-8").strip().split("\n")
            else:
                lines = output_content.strip().split("\n")

            logger.info(f"Parsing {len(lines)} result lines...")

            for line_num, line in enumerate(lines):
                if not line.strip():
                    continue

                try:
                    result_obj = json.loads(line)

                    # Extract key (paper identifier)
                    key = result_obj.get("key", "")

                    # Parse key to get paper_id and arxiv_id
                    # Format: "paper_{paper_id}_{arxiv_id}"
                    parts = key.split("_", 2)
                    if len(parts) >= 3:
                        paper_id = parts[1]
                        arxiv_id = parts[2]
                    else:
                        logger.warning(f"Invalid key format: {key}")
                        continue

                    # Check if response or error
                    if "response" in result_obj and result_obj["response"]:
                        response_data = result_obj["response"]

                        # Extract text from response structure
                        if isinstance(response_data, dict):
                            # Handle structured response
                            if "text" in response_data:
                                response_text = response_data["text"]
                            elif "candidates" in response_data:
                                # Handle candidates structure
                                candidates = response_data["candidates"]
                                if candidates and len(candidates) > 0:
                                    candidate = candidates[0]
                                    if "content" in candidate:
                                        content = candidate["content"]
                                        if (
                                            "parts" in content
                                            and len(content["parts"]) > 0
                                        ):
                                            response_text = content["parts"][0].get(
                                                "text", ""
                                            )
                                        else:
                                            response_text = str(content)
                                    else:
                                        response_text = str(candidate)
                                else:
                                    response_text = ""
                            else:
                                response_text = json.dumps(response_data)
                        else:
                            response_text = str(response_data)

                        # Parse JSON response text
                        try:
                            response_json = (
                                json.loads(response_text) if response_text else {}
                            )
                        except json.JSONDecodeError:
                            logger.error(
                                f"Failed to parse response JSON for {arxiv_id}"
                            )
                            logger.error(f"Response text: {response_text[:200]}")
                            response_json = {}

                        github_url = response_json.get("github_url", "").strip()
                        project_page_url = response_json.get(
                            "project_page_url", ""
                        ).strip()
                        reasoning = response_json.get("reasoning", "")

                        # Verify URLs
                        if github_url:
                            is_valid = await verify_url(github_url)
                            if not is_valid:
                                logger.warning(
                                    f"Invalid GitHub URL for {arxiv_id}: {github_url}"
                                )
                                github_url = ""

                        if project_page_url:
                            is_valid = await verify_url(project_page_url)
                            if not is_valid:
                                logger.warning(
                                    f"Invalid project page URL for {arxiv_id}: {project_page_url}"
                                )
                                project_page_url = ""

                        paper = self.paper_data.get(arxiv_id, {})

                        results.append(
                            {
                                "paper_id": paper_id,
                                "arxiv_id": arxiv_id,
                                "title": paper.get("title", ""),
                                "github_url": github_url,
                                "project_page_url": project_page_url,
                                "reasoning": reasoning,
                                "status": "success",
                            }
                        )

                    elif "error" in result_obj:
                        error_data = result_obj["error"]
                        error_msg = str(error_data) if error_data else "Unknown error"
                        logger.warning(f"Error for {arxiv_id}: {error_msg}")

                        paper = self.paper_data.get(arxiv_id, {})

                        results.append(
                            {
                                "paper_id": paper_id,
                                "arxiv_id": arxiv_id,
                                "title": paper.get("title", ""),
                                "github_url": "",
                                "project_page_url": "",
                                "reasoning": "",
                                "status": "error",
                                "error": error_msg,
                            }
                        )

                    else:
                        logger.warning(
                            f"Line {line_num}: Neither response nor error found"
                        )
                        logger.warning(f"Line content: {line[:200]}")

                except Exception as e:
                    logger.error(f"Failed to parse result line {line_num}: {e}")
                    logger.error(f"Line: {line[:200]}")
                    continue

            logger.info(f"Successfully parsed {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Failed to download/parse results: {e}")
            import traceback

            logger.error(traceback.format_exc())
            raise

    def save_results(self, results: List[Dict[str, Any]], batch_job: Any) -> str:
        """Save results to JSON file."""
        results_path = self.output_dir / f"batch_results_{self.timestamp}.json"

        # Calculate statistics
        successful = sum(1 for r in results if r["status"] == "success")
        failed = len(results) - successful
        with_github = sum(
            1 for r in results if r["status"] == "success" and r["github_url"]
        )
        with_project = sum(
            1 for r in results if r["status"] == "success" and r["project_page_url"]
        )
        with_both = sum(
            1
            for r in results
            if r["status"] == "success" and r["github_url"] and r["project_page_url"]
        )
        with_neither = sum(
            1
            for r in results
            if r["status"] == "success"
            and not r["github_url"]
            and not r["project_page_url"]
        )

        output = {
            "batch_info": {
                "job_name": batch_job.name,
                "timestamp": self.timestamp,
                "total_papers": len(results),
                "successful": successful,
                "failed": failed,
                "with_github": with_github,
                "with_project_page": with_project,
                "with_both": with_both,
                "with_neither": with_neither,
                "github_rate": f"{with_github / successful * 100:.1f}%"
                if successful > 0
                else "0%",
                "project_rate": f"{with_project / successful * 100:.1f}%"
                if successful > 0
                else "0%",
            },
            "results": results,
        }

        with open(results_path, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Results saved to: {results_path}")
        return str(results_path)

    def print_summary(self, results: List[Dict[str, Any]]):
        """Print summary of results."""
        successful = [r for r in results if r["status"] == "success"]
        failed = [r for r in results if r["status"] != "success"]

        with_github = [r for r in successful if r["github_url"]]
        with_project = [r for r in successful if r["project_page_url"]]
        with_both = [r for r in successful if r["github_url"] and r["project_page_url"]]
        with_neither = [
            r for r in successful if not r["github_url"] and not r["project_page_url"]
        ]

        print("\n" + "=" * 80)
        print("BATCH EXTRACTION RESULTS")
        print("=" * 80)
        print(f"Total papers processed: {len(results)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")

        if successful:
            print("\nURL Extraction Statistics:")
            print(
                f"  Papers with GitHub: {len(with_github)} ({len(with_github) / len(successful) * 100:.1f}%)"
            )
            print(
                f"  Papers with Project Page: {len(with_project)} ({len(with_project) / len(successful) * 100:.1f}%)"
            )
            print(
                f"  Papers with both: {len(with_both)} ({len(with_both) / len(successful) * 100:.1f}%)"
            )
            print(
                f"  Papers with neither: {len(with_neither)} ({len(with_neither) / len(successful) * 100:.1f}%)"
            )

        print("\nSample results (first 5):")
        for i, result in enumerate(successful[:5]):
            github_status = (
                f"✓ {result['github_url']}" if result["github_url"] else "✗ None"
            )
            project_status = (
                f"✓ {result['project_page_url']}"
                if result["project_page_url"]
                else "✗ None"
            )
            print(f"  {i + 1}. {result['arxiv_id']}")
            print(f"     GitHub: {github_status}")
            print(f"     Project: {project_status}")

        print("=" * 80)

    async def apply_results_to_database(self, results: List[Dict[str, Any]]):
        """Apply results to database."""
        logger.info("Applying results to database...")

        from backend.services.repository_service import RepositoryService
        from backend.services.project_page_service import ProjectPageService
        from backend.utils.github_utils import parse_github_url

        db_session_gen = get_database_session()
        db = next(db_session_gen)

        try:
            repo_service = RepositoryService(db)
            project_service = ProjectPageService(db)

            saved_github = 0
            saved_project = 0
            skipped_github = 0
            skipped_project = 0

            for result in results:
                if result["status"] != "success":
                    continue

                paper_id = result["paper_id"]
                github_url = result["github_url"]
                project_page_url = result["project_page_url"]

                # Save GitHub URL
                if github_url:
                    try:
                        owner, name = parse_github_url(github_url)
                        repository = repo_service.create_repository_for_paper(
                            paper_id=str(paper_id),
                            url=github_url,
                            owner=owner,
                            name=name,
                            num_stars=0,
                            is_official=True,
                            source="ai_extraction_batch",
                            skip_if_official_exists=True,
                        )
                        if repository:
                            saved_github += 1
                            logger.info(
                                f"✓ Saved GitHub for paper {paper_id}: {github_url}"
                            )
                        else:
                            skipped_github += 1
                            logger.debug(
                                f"Skipped GitHub (already exists) for paper {paper_id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to save GitHub URL for paper {paper_id}: {e}"
                        )

                # Save project page URL
                if project_page_url:
                    try:
                        project_page = project_service.create_project_page_for_paper(
                            paper_id=str(paper_id),
                            url=project_page_url,
                            is_official=True,
                            source="ai_extraction_batch",
                            skip_if_official_exists=True,
                        )
                        if project_page:
                            saved_project += 1
                            logger.info(
                                f"✓ Saved project page for paper {paper_id}: {project_page_url}"
                            )
                        else:
                            skipped_project += 1
                            logger.debug(
                                f"Skipped project page (already exists) for paper {paper_id}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to save project page URL for paper {paper_id}: {e}"
                        )

                # Mark paper as processed
                try:
                    update_query = """
                    UPDATE papers
                    SET urls_extracted = TRUE, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :paper_id
                    """
                    db.execute(text(update_query), {"paper_id": paper_id})
                    logger.debug(f"Marked paper {paper_id} as processed")
                except Exception as e:
                    logger.error(f"Failed to mark paper {paper_id} as processed: {e}")

            db.commit()

            logger.info("Database update complete:")
            logger.info(f"  GitHub URLs saved: {saved_github}")
            logger.info(f"  Project pages saved: {saved_project}")
            logger.info(f"  GitHub URLs skipped (existing): {skipped_github}")
            logger.info(f"  Project pages skipped (existing): {skipped_project}")

        except Exception as e:
            logger.error(f"Failed to apply results to database: {e}")
            db.rollback()
            raise
        finally:
            db.close()

    async def run(self, limit: int, input_file_name: Optional[str] = None) -> str:
        """Main execution flow."""
        logger.info("=" * 80)
        logger.info("GEMINI BATCH API URL EXTRACTION")
        logger.info("=" * 80)
        logger.info("Configuration:")
        logger.info(f"  Papers to process: {limit}")
        logger.info(f"  Start year: {self.start_year}")
        logger.info(f"  Output directory: {self.output_dir}")
        logger.info(f"  Apply to database: {self.apply_to_db}")
        if input_file_name:
            logger.info(f"  Using pre-uploaded file: {input_file_name}")
        logger.info("=" * 80)

        # If input file is provided, skip to batch job submission
        if input_file_name:
            logger.info("Skipping upload steps (using pre-uploaded file)")

            # Step 6: Submit batch job directly
            batch_job = await self.submit_batch_job(input_file_name)
        else:
            # Step 1: Query papers
            db_session_gen = get_database_session()
            db = next(db_session_gen)
            try:
                papers = self.get_papers_to_process(db, limit)
            finally:
                db.close()

            if not papers:
                logger.info("No papers found to process")
                return None

            # Step 2: Download and upload PDFs
            uploaded_files = await self.download_and_upload_papers(papers)

            if not uploaded_files:
                logger.error("No PDFs were successfully uploaded")
                return None

            # Step 3: Prepare few-shot examples
            few_shot_messages = await self.prepare_few_shot_examples()

            # Step 4: Create batch requests JSONL
            jsonl_path = await self.create_batch_requests(
                uploaded_files, few_shot_messages
            )

            # Step 5: Upload batch file
            input_file_name = await self.upload_batch_file(jsonl_path)

            # Step 6: Submit batch job
            batch_job = await self.submit_batch_job(input_file_name)

        # Step 7: Poll for completion
        completed_job = await self.poll_batch_job(batch_job.name)

        # Step 8: Download and parse results
        results = await self.download_and_parse_results(completed_job)

        # Step 9: Save results
        results_path = self.save_results(results, completed_job)

        # Step 10: Print summary
        self.print_summary(results)

        # Step 11: Apply to database if requested
        if self.apply_to_db:
            logger.info("\n" + "=" * 80)
            logger.info("APPLYING RESULTS TO DATABASE")
            logger.info("=" * 80)
            await self.apply_results_to_database(results)
            logger.info("✓ Database update complete")
        else:
            logger.info("\n" + "=" * 80)
            logger.info("RESULTS SAVED FOR REVIEW")
            logger.info("=" * 80)
            logger.info(f"Results file: {results_path}")
            logger.info("To apply to database, run with --apply-to-db flag")

        return results_path

    async def resume_from_job(self, job_name: str) -> str:
        """Resume from an existing batch job."""
        logger.info(f"Resuming batch job: {job_name}")

        # Poll for completion
        completed_job = await self.poll_batch_job(job_name)

        # Download and parse results
        results = await self.download_and_parse_results(completed_job)

        # Save results
        results_path = self.save_results(results, completed_job)

        # Print summary
        self.print_summary(results)

        # Apply to database if requested
        if self.apply_to_db:
            logger.info("\n" + "=" * 80)
            logger.info("APPLYING RESULTS TO DATABASE")
            logger.info("=" * 80)
            await self.apply_results_to_database(results)
            logger.info("✓ Database update complete")
        else:
            logger.info("\n" + "=" * 80)
            logger.info("RESULTS SAVED FOR REVIEW")
            logger.info("=" * 80)
            logger.info(f"Results file: {results_path}")
            logger.info("To apply to database, run with --apply-to-db flag")

        return results_path


async def main():
    parser = argparse.ArgumentParser(
        description="Extract GitHub and project page URLs using Gemini Batch API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process 100 papers, save results for review
  uv run --env-file backend/keys.env -m backend.genai_steps.batch_extract_urls_gemini --limit 100

  # Apply results to database
  uv run --env-file backend/keys.env -m backend.genai_steps.batch_extract_urls_gemini --limit 100 --apply-to-db

  # Process all papers
  uv run --env-file backend/keys.env -m backend.genai_steps.batch_extract_urls_gemini --limit 10000

  # Resume from existing job
  uv run --env-file backend/keys.env -m backend.genai_steps.batch_extract_urls_gemini --resume batches/abc123
        """,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of papers to process (default: 100)",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2014,
        help="Filter papers from this year onwards (default: 2014)",
    )
    parser.add_argument(
        "--output-dir",
        default="./batch_results",
        help="Directory for output files (default: ./batch_results)",
    )
    parser.add_argument(
        "--apply-to-db",
        action="store_true",
        help="Apply results to database immediately (default: save for review)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Seconds between status checks (default: 60)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        help="Resume from existing batch job (provide job name like batches/abc123)",
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Use pre-uploaded JSONL file (provide file name like files/abc123) to skip upload steps",
    )

    args = parser.parse_args()

    # Validate that only one of --resume or --input-file is provided
    if args.resume and args.input_file:
        print("Error: Cannot use both --resume and --input-file at the same time")
        sys.exit(1)

    extractor = GeminiBatchExtractor(
        output_dir=args.output_dir,
        start_year=args.start_year,
        poll_interval=args.poll_interval,
        apply_to_db=args.apply_to_db,
    )

    if args.resume:
        results_path = await extractor.resume_from_job(args.resume)
    elif args.input_file:
        results_path = await extractor.run(
            limit=args.limit, input_file_name=args.input_file
        )
    else:
        results_path = await extractor.run(limit=args.limit)

    if results_path:
        print(f"\n✓ Complete! Results saved to: {results_path}")
    else:
        print("\n✗ No results generated")


if __name__ == "__main__":
    asyncio.run(main())
