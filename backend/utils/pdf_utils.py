from typing import List, Generator
from contextlib import contextmanager, asynccontextmanager
import asyncio
import aiohttp
import tempfile
import os
import re

import fitz
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


def cleanup_image_files(image_paths: List[str]):
    """
    Clean up temporary image files.
    """
    for image_path in image_paths:
        try:
            os.unlink(image_path)
        except Exception:
            pass


def _is_valid_pdf(content: bytes) -> tuple[bool, str]:
    """
    Check if the downloaded content is a valid PDF file.

    Args:
        content: The downloaded file content

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check PDF magic bytes (PDF files start with "%PDF-")
    if not content.startswith(b"%PDF-"):
        # Check if it's HTML (common for reCAPTCHA pages)
        if content.startswith(b"<!DOCTYPE") or content.startswith(b"<html"):
            if b"recaptcha" in content.lower() or b"captcha" in content.lower():
                return False, "ArXiv returned reCAPTCHA page (rate limited)"
            return False, "ArXiv returned HTML page instead of PDF"
        return False, "Downloaded file is not a valid PDF (missing PDF magic bytes)"

    # Additional validation: check if file ends properly
    # PDF files should end with "%%EOF" (possibly followed by whitespace)
    content_stripped = content.rstrip()
    if not content_stripped.endswith(b"%%EOF"):
        return False, "Downloaded file appears to be truncated (missing PDF EOF marker)"

    # Check minimum size (valid PDFs are typically at least 1KB)
    if len(content) < 1024:
        return (
            False,
            f"Downloaded file too small ({len(content)} bytes) to be a valid PDF",
        )

    return True, ""


@asynccontextmanager
async def temp_pdf_download(arxiv_id: str):
    """
    Temporarily download a PDF from arXiv asynchronously.

    Validates that the downloaded file is actually a PDF and not HTML (e.g., reCAPTCHA page).

    Raises:
        aiohttp.ClientError: If HTTP request fails (includes 429 rate limiting)
        asyncio.TimeoutError: If download times out
        IOError: If file cannot be saved
        Exception: If downloaded file is not a valid PDF or for other critical failures
    """

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Get the PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            # Download the PDF asynchronously with timeout and retry
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(pdf_url) as response:
                    # Check for rate limiting specifically
                    if response.status == 429:
                        raise Exception(f"ArXiv rate limit (429) for {arxiv_id}")

                    response.raise_for_status()  # Raise an exception for bad responses
                    content = await response.read()

            # Validate that the content is actually a PDF
            is_valid, error_msg = _is_valid_pdf(content)
            if not is_valid:
                raise Exception(f"Failed to download PDF for {arxiv_id}: {error_msg}")

            # Generate a filename for the PDF
            filename = f"{arxiv_id}.pdf"
            filepath = os.path.join(temp_dir, filename)

            # Save the PDF asynchronously
            with open(filepath, "wb") as f:
                await asyncio.to_thread(f.write, content)

            print(f"PDF downloaded successfully to temporary location: {filepath}")

        except Exception as e:
            # Add context to the error and re-raise
            error_msg = f"Failed to download PDF for {arxiv_id}: {str(e)}"
            print(error_msg)
            raise Exception(error_msg) from e

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


async def extract_first_two_pages_pymupdf_sync(input_path: str) -> str:
    """
    Synchronous part of extracting first 2 pages from a PDF file using PyMuPDF.
    Attempts to clean the input PDF first by re-saving it.
    """
    input_doc = None
    writer_doc = None
    cleaned_temp_pdf = None

    try:
        # --- Attempt to clean the input PDF first ---
        try:
            initial_doc = fitz.open(input_path)
            # Create a temporary file for the cleaned version
            with tempfile.NamedTemporaryFile(
                delete=False, suffix="_cleaned.pdf"
            ) as temp_clean_file:
                cleaned_pdf_path = temp_clean_file.name
            # Save with cleanup options
            initial_doc.save(cleaned_pdf_path, garbage=4, deflate=True)
            initial_doc.close()
            print(f"Attempted to clean PDF, saved to: {cleaned_pdf_path}")
            # Use the cleaned PDF path as the new input
            input_path_to_use = cleaned_pdf_path
            cleaned_temp_pdf = cleaned_pdf_path  # Keep track for cleanup
        except Exception as clean_e:
            print(
                f"Warning: Failed to clean PDF, proceeding with original. Error: {clean_e}"
            )
            input_path_to_use = input_path  # Fallback to original if cleaning fails
        # --------------------------------------------

        # Open the source PDF (either original or cleaned)
        input_doc = fitz.open(input_path_to_use)

        # Create a new empty PDF document
        writer_doc = fitz.open()

        # Check if the document has at least one page
        if len(input_doc) == 0:
            # Close potentially opened docs before raising
            if input_doc:
                input_doc.close()
            if writer_doc:
                writer_doc.close()
            raise ValueError("Input PDF has no pages.")

        # Determine the number of pages to extract (max 2)
        num_pages_to_extract = min(len(input_doc), 2)

        # Insert the first two pages (or fewer if the doc is shorter)
        writer_doc.insert_pdf(input_doc, from_page=0, to_page=num_pages_to_extract - 1)

        # Create a temporary file for the final output
        with tempfile.NamedTemporaryFile(
            delete=False, suffix="_extract.pdf"
        ) as temp_extract_file:
            # Write the output to the temporary file
            # Using garbage collection here too, just in case
            writer_doc.save(temp_extract_file.name, garbage=4, deflate=True)
            output_temp_file_path = temp_extract_file.name

        # Close the documents
        input_doc.close()
        writer_doc.close()

        print(f"Extracted first {num_pages_to_extract} pages using PyMuPDF.")
        # Return the path of the temporary file containing the extraction
        return output_temp_file_path

    except Exception as e:
        print(f"Error using PyMuPDF to extract pages: {e}")
        # Clean up documents if they were potentially opened
        try:
            if input_doc:
                input_doc.close()
            if writer_doc:
                writer_doc.close()
        except Exception as cleanup_e:
            print(f"Error during exception cleanup: {cleanup_e}")
        raise  # Re-raise the original exception

    finally:
        # Clean up the intermediate cleaned PDF if it was created
        if cleaned_temp_pdf and os.path.exists(cleaned_temp_pdf):
            try:
                os.unlink(cleaned_temp_pdf)
                print(f"Cleaned up intermediate file: {cleaned_temp_pdf}")
            except Exception as final_cleanup_e:
                print(
                    f"Error cleaning up intermediate file {cleaned_temp_pdf}: {final_cleanup_e}"
                )


async def extract_first_two_pages_pymupdf(input_path: str) -> str:
    """
    Function to extract the first 2 pages from a PDF file using PyMuPDF.
    Attempts to clean the input PDF first by re-saving it.
    This version runs synchronous file operations in a separate thread.
    """
    return await extract_first_two_pages_pymupdf_sync(input_path)


if __name__ == "__main__":

    async def main():
        async with temp_pdf_download(arxiv_id="2509.22622") as pdf_path:
            print("Successfully downloaded PDF to: ", pdf_path)

    try:
        asyncio.run(main())
    except Exception as e:
        print(e)
    print("Done")
