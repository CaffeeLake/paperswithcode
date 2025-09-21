from typing import List, Generator
from contextlib import contextmanager, asynccontextmanager
import asyncio
import aiohttp
import tempfile
import os
import re

from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pdfplumber


PROJECT_PAGE_URL_PATTERN = r"\bhttps?://[a-zA-Z0-9.-]+\.github\.io[^\s]*"


async def safe_regex_search_async(pattern: str, text: str, timeout_seconds: int = 5):
    """
    Perform regex search with asyncio timeout to prevent hanging.
    """
    try:
        # Run the regex search in a separate thread with timeout
        match = await asyncio.wait_for(
            asyncio.to_thread(re.search, pattern, text), timeout=timeout_seconds
        )
        return match
    except asyncio.TimeoutError:
        print(f"Regex search timed out after {timeout_seconds} seconds")
        return None
    except Exception as e:
        print(f"Error during regex search: {e}")
        return None


def extract_text_from_pdf(pdf_path: str, num_pages: int = 2) -> str:
    """
    Extract text of the first number of pages from a PDF file.
    """
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages[:num_pages]:
        text += page.extract_text()

    return text


@contextmanager
def pdf_to_images(
    pdf_path: str, pages: List[int] = [1, 2]
) -> Generator[List[str], None, None]:
    """
    Convert PDF pages to images.
    """
    temp_files = []
    try:
        # Convert PDF pages to images
        images = convert_from_path(pdf_path, first_page=pages[0], last_page=pages[-1])

        # Create temporary files for each image
        for i, image in enumerate(images):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                image.save(temp_file.name, "PNG")
                temp_files.append(temp_file.name)
                print(f"Page {pages[i]} saved temporarily at: {temp_file.name}")

        yield temp_files
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            os.unlink(temp_file)
            print(f"Temporary file {temp_file} has been deleted.")


def extract_hyperlinks_from_pdf(pdf_path):
    """
    Extract all hyperlinks from a PDF file.

    Args:
        pdf_path (str): Path to PDF file

    Returns:
        list: List of dictionaries containing link text and URL
    """
    links = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Extract hyperlinks
                annotations = page.hyperlinks
                if annotations:
                    for link in annotations:
                        if "uri" in link:
                            # Get the text near the link if available
                            text = ""
                            if "text" in link:
                                text = link["text"]
                            elif "bbox" in link:
                                # Extract text from the bounding box area
                                bbox = link["bbox"]
                                crop = page.crop(bbox)
                                text = crop.extract_text() or ""

                            links.append({"text": text.strip(), "url": link["uri"]})
    except Exception as e:
        print(f"Error extracting hyperlinks from PDF: {e}")
        # Return empty list if extraction fails
        return []

    return links


async def safe_extract_hyperlinks_async(pdf_path: str, timeout_seconds: int = 10):
    """
    Extract hyperlinks with timeout protection.
    """
    try:
        links = await asyncio.wait_for(
            asyncio.to_thread(extract_hyperlinks_from_pdf, pdf_path),
            timeout=timeout_seconds,
        )
        return links
    except asyncio.TimeoutError:
        print(f"Hyperlink extraction timed out after {timeout_seconds} seconds")
        return []
    except Exception as e:
        print(f"Error during hyperlink extraction: {e}")
        return []


def pdf_to_images_sync(pdf_path: str, pages: List[int] = [1, 2]) -> List[str]:
    """
    Convert PDF pages to images and return list of image paths.
    """
    temp_files = []
    try:
        # Convert PDF pages to images
        images = convert_from_path(pdf_path, first_page=pages[0], last_page=pages[-1])

        # Create temporary files for each image
        for i, image in enumerate(images):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                image.save(temp_file.name, "PNG")
                temp_files.append(temp_file.name)

        return temp_files
    except Exception as e:
        print(f"Error converting PDF to images: {e}")
        # Clean up any created files on error
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except:  # noqa: E722
                pass
        return []


async def safe_pdf_to_images_async(pdf_path: str, timeout_seconds: int = 30):
    """
    Convert PDF to images with timeout protection.
    """
    try:
        image_paths = await asyncio.wait_for(
            asyncio.to_thread(pdf_to_images_sync, pdf_path), timeout=timeout_seconds
        )
        return image_paths
    except asyncio.TimeoutError:
        print(f"PDF to images conversion timed out after {timeout_seconds} seconds")
        return []
    except Exception as e:
        print(f"Error during PDF to images conversion: {e}")
        return []


@asynccontextmanager
async def temp_pdf_download(arxiv_id: str):
    """
    Temporarily download a PDF from arXiv asynchronously.
    """

    with tempfile.TemporaryDirectory() as temp_dir:
        filepath = None
        try:
            # Get the PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            # Download the PDF asynchronously with timeout and retry
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(pdf_url) as response:
                    response.raise_for_status()  # Raise an exception for bad responses
                    content = await response.read()

            # Generate a filename for the PDF
            filename = f"{arxiv_id}.pdf"
            filepath = os.path.join(temp_dir, filename)

            # Save the PDF asynchronously
            with open(filepath, "wb") as f:
                await asyncio.to_thread(f.write, content)

            print(f"PDF downloaded successfully to temporary location: {filepath}")

        except Exception as e:
            print(f"An error occurred while downloading PDF at {pdf_url}: {str(e)}")
            filepath = None

        try:
            yield filepath
        except GeneratorExit:
            # Handle cleanup when the generator is being closed
            pass
        except Exception:
            # Handle any other exceptions thrown into the generator
            pass


async def find_project_page_url(pdf_path: str) -> str:
    """
    Try to extract the first matched Project page URL
    from text using a regular expression.

    Args:
        pdf_path (str): Path to the PDF file

    Returns:
        list: List of found GitHub URLs
    """
    text = await asyncio.to_thread(extract_text_from_pdf, pdf_path, num_pages=2)
    match = await safe_regex_search_async(PROJECT_PAGE_URL_PATTERN, text, 5)
    return match.group(0) if match else ""
