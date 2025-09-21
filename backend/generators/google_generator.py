from typing import Optional
from dataclasses import dataclass
import re
import io
import tempfile
import shutil
import asyncio
import json

from backend.config import get_settings
from backend.models.generators import Generator, Message

from google import genai
from google.genai.types import Content, Part, FileData
from pydantic import BaseModel


gemini_roles = {
    "user": "user",
    "assistant": "model",
}

GEMINI_API_KEY = get_settings().gemini_api_key


@dataclass
class RateLimitInfo:
    """Information about rate limiting from API response."""

    retry_delay: float  # in seconds
    quota_metric: str = ""
    quota_value: str = ""


# Global semaphore to limit concurrent API calls
# Adjust this value based on your API quota
API_CONCURRENCY_LIMIT = 10
api_semaphore = asyncio.Semaphore(API_CONCURRENCY_LIMIT)


class GoogleGenerator(Generator):
    def __init__(self):
        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def _parse_retry_delay(self, error_str: str) -> Optional[RateLimitInfo]:
        """
        Parse retry delay from Gemini API error response.

        Args:
            error_str: The error string from the API

        Returns:
            RateLimitInfo object with retry delay in seconds, or None if not found
        """
        try:
            # Look for retryDelay in the error string
            retry_delay_match = re.search(r"'retryDelay':\s*'(\d+)s'", error_str)
            if retry_delay_match:
                delay_seconds = int(retry_delay_match.group(1))
                return RateLimitInfo(retry_delay=delay_seconds)

            # Fallback: look for the delay in a different format
            retry_delay_match = re.search(r'"retryDelay":\s*"(\d+)s"', error_str)
            if retry_delay_match:
                delay_seconds = int(retry_delay_match.group(1))
                return RateLimitInfo(retry_delay=delay_seconds)

        except (ValueError, AttributeError) as e:
            print(f"Error parsing retry delay: {e}")

        return None

    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if the error is a rate limit error (429)."""
        error_str = str(error)
        return "429" in error_str and "RESOURCE_EXHAUSTED" in error_str

    def _is_service_unavailable_error(self, error: Exception) -> bool:
        """Check if the error is a service unavailable error (503)."""
        error_str = str(error)
        return (
            "503" in error_str
            or "Service Unavailable" in error_str
            or "UNAVAILABLE" in error_str
        )

    async def format_messages(
        self, messages: list[Message]
    ) -> tuple[list[Content], list[str]]:
        """
        Format messages for the Gemini API.
        """
        contents = []

        # create a temporary directory
        temp_dir = await asyncio.to_thread(tempfile.mkdtemp)

        uploaded_file_names = []
        try:
            for message in messages:
                # can be either a string or a list of strings
                is_string_content = isinstance(message.content, str)
                parts = (
                    [Part(text=message.content)]
                    if is_string_content
                    else [Part(text=text) for text in message.content]
                )
                # Handle image URLs (new multiple images support)
                if message.image_urls:
                    # TODO: Implement image handling when media_utils is available
                    print(
                        f"Warning: Image URLs provided but media_utils not available: {message.image_urls}"
                    )
                    pass
                elif message.image_url:  # Backward compatibility
                    # TODO: Implement image handling when media_utils is available
                    print(
                        f"Warning: Image URL provided but media_utils not available: {message.image_url}"
                    )
                    pass

                # Handle image paths (new multiple images support)
                if message.image_paths:
                    # TODO: Implement image handling when media_utils is available
                    print(
                        f"Warning: Image paths provided but media_utils not available: {message.image_paths}"
                    )
                    pass
                elif message.image_path:  # Backward compatibility
                    # TODO: Implement image handling when media_utils is available
                    print(
                        f"Warning: Image path provided but media_utils not available: {message.image_path}"
                    )
                    pass

                if message.pdf_path is not None:
                    # Read and upload the PDF using the File API
                    def _read_and_upload_pdf():
                        with open(message.pdf_path, "rb") as f_read:
                            doc_io_bytes = f_read.read()
                        doc_io = io.BytesIO(doc_io_bytes)
                        return self.client.files.upload(
                            file=doc_io, config=dict(mime_type="application/pdf")
                        )

                    pdf_file = await asyncio.to_thread(_read_and_upload_pdf)
                    pdf_part = Part(
                        file_data=FileData(
                            mime_type=pdf_file.mime_type, file_uri=pdf_file.uri
                        )
                    )
                    parts = parts + [pdf_part]
                    uploaded_file_names.append(pdf_file.name)

                content = Content(role=gemini_roles[message.role], parts=parts)
                contents.append(content)
        finally:
            # clean up the temporary directory
            await asyncio.to_thread(shutil.rmtree, temp_dir)

        return contents, uploaded_file_names

    def _parse_retry_delay(self, error_str: str) -> Optional[RateLimitInfo]:
        """
        Parse retry delay from Gemini API error response.

        Args:
            error_str: The error string from the API

        Returns:
            RateLimitInfo object with retry delay in seconds, or None if not found
        """
        try:
            # Look for retryDelay in the error string
            retry_delay_match = re.search(r"'retryDelay':\s*'(\d+)s'", error_str)
            if retry_delay_match:
                delay_seconds = int(retry_delay_match.group(1))
                return RateLimitInfo(retry_delay=delay_seconds)

            # Fallback: look for the delay in a different format
            retry_delay_match = re.search(r'"retryDelay":\s*"(\d+)s"', error_str)
            if retry_delay_match:
                delay_seconds = int(retry_delay_match.group(1))
                return RateLimitInfo(retry_delay=delay_seconds)

        except (ValueError, AttributeError) as e:
            print(f"Error parsing retry delay: {e}")

        return None

    async def call_gemini_api(
        self,
        model_name: str,
        messages: list[Content],
        schema: Optional[BaseModel] = None,
        uploaded_file_names: list[str] = None,
        max_retries: int = 5,
    ) -> str:
        config = None
        if schema is not None:
            config = {
                "response_mime_type": "application/json",
                "response_schema": schema,
            }

        # Use semaphore to limit concurrent API calls
        async with api_semaphore:
            retry_count = 0
            base_delay = 1.0  # Base delay for exponential backoff

            while retry_count <= max_retries:
                try:
                    response = await self.client.aio.models.generate_content(
                        model=model_name,
                        contents=messages,
                        config=config,
                    )

                    # Log usage metadata (removed langfuse dependency)
                    if response.usage_metadata:
                        print(
                            f"Token usage - Prompt: {response.usage_metadata.prompt_token_count}, "
                            f"Completion: {response.usage_metadata.candidates_token_count}, "
                            f"Total: {response.usage_metadata.total_token_count}"
                        )

                    # clean up the files from Gemini storage
                    if uploaded_file_names:
                        for file_name in uploaded_file_names:
                            await asyncio.to_thread(
                                self.client.files.delete, name=file_name
                            )

                    return response.text

                except Exception as e:
                    if self._is_rate_limit_error(e):
                        retry_info = self._parse_retry_delay(str(e))

                        if retry_info and retry_count < max_retries:
                            # Use the API-suggested delay, or fall back to exponential backoff
                            delay = retry_info.retry_delay
                            print(
                                f"Rate limit hit for {model_name}. Retrying in {delay} seconds (attempt {retry_count + 1}/{max_retries + 1})"
                            )
                            await asyncio.sleep(delay)
                            retry_count += 1
                            continue
                        elif retry_count < max_retries:
                            # Exponential backoff if no retry delay is provided
                            delay = base_delay * (2**retry_count)
                            print(
                                f"Rate limit hit for {model_name}. Retrying in {delay} seconds (attempt {retry_count + 1}/{max_retries + 1})"
                            )
                            await asyncio.sleep(delay)
                            retry_count += 1
                            continue
                        else:
                            print(
                                f"Max retries ({max_retries}) exceeded for {model_name} due to rate limiting"
                            )
                            raise e
                    elif self._is_service_unavailable_error(e):
                        retry_info = self._parse_retry_delay(str(e))
                        if retry_info and retry_count < max_retries:
                            # Use the API-suggested delay, or fall back to exponential backoff
                            delay = retry_info.retry_delay
                            print(
                                f"Service Unavailable for {model_name}. Retrying in {delay} seconds (attempt {retry_count + 1}/{max_retries + 1})"
                            )
                            await asyncio.sleep(delay)
                            retry_count += 1
                            continue
                        elif retry_count < max_retries:
                            # Exponential backoff if no retry delay is provided
                            delay = base_delay * (2**retry_count)
                            print(
                                f"Service Unavailable for {model_name}. Retrying in {delay} seconds (attempt {retry_count + 1}/{max_retries + 1})"
                            )
                            await asyncio.sleep(delay)
                            retry_count += 1
                            continue
                        else:
                            print(
                                f"Max retries ({max_retries}) exceeded for {model_name} due to service unavailability"
                            )
                            raise e
                    else:
                        # Not a rate limit error, re-raise immediately
                        raise e

            # This should never be reached, but just in case
            raise Exception(f"Max retries exceeded for {model_name}")

    async def chat(
        self,
        messages: list[dict],
        schema: Optional[BaseModel] = None,
        uploaded_file_names: list[str] = None,
    ) -> tuple[str, str]:
        """
        Given a list of messages, this function generates a response using the Gemini API
        along with the model name used.
        """
        models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.5-flash-preview-06-17",
            "gemini-2.5-pro",
        ]
        last_exception = None
        for model_name in models:
            try:
                response = await self.call_gemini_api(
                    model_name=model_name,
                    messages=messages,
                    schema=schema,
                    uploaded_file_names=uploaded_file_names,
                )
                return response, model_name
            except Exception as e:
                print(f"An error occurred with model {model_name}: {str(e)}")
                last_exception = e
                # Add a small delay before trying the next model to avoid immediate rate limiting
                if self._is_rate_limit_error(e):
                    print("Adding delay before trying next model...")
                    await asyncio.sleep(5)  # Small delay before trying next model
                elif self._is_service_unavailable_error(e):
                    print(
                        "Service unavailable - adding delay before trying next model..."
                    )
                    await asyncio.sleep(3)  # Small delay before trying next model
                continue
        if last_exception:
            raise last_exception
        return "", "No model succeeded"

    async def generate(
        self, messages: list[Message], schema: Optional[BaseModel] = None
    ) -> tuple[str, str]:
        formatted_messages, uploaded_file_names = await self.format_messages(messages)

        response, model_name = await self.chat(
            messages=formatted_messages,
            schema=schema,
            uploaded_file_names=uploaded_file_names,
        )

        if len(response) == 0 and model_name != "No model succeeded":
            print(
                "!!!! Gemini not returning anything, retrying with fewer messages (if applicable)"
            )
            if len(messages) > 4:
                messages_retry = messages[4:]
                (
                    formatted_messages_retry,
                    uploaded_file_names_retry,
                ) = await self.format_messages(messages_retry)
                response, model_name = await self.chat(
                    messages=formatted_messages_retry,
                    schema=schema,
                    uploaded_file_names=uploaded_file_names_retry,
                )
            else:
                print("!!!! Not enough messages to retry by slicing.")

        if schema is not None:
            response = json.loads(response) if isinstance(response, str) else response

        return response, model_name

    async def count_tokens(self, messages: list[Message]) -> int:
        formatted_messages, _ = await self.format_messages(messages)

        model_for_counting = self.client.GenerativeModel("gemini-1.5-flash-latest")
        count_response = await model_for_counting.count_tokens_async(
            contents=formatted_messages
        )
        return count_response.total_tokens


if __name__ == "__main__":
    import asyncio

    async def test_google_generator():
        """Test the Google Gemini generator."""
        print("🧪 Testing Google Gemini Generator...")
        print(
            f"API Key loaded: {'Yes' if GEMINI_API_KEY else 'No'} (length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0})"
        )

        try:
            generator = GoogleGenerator()
            messages = [
                Message(
                    role="user",
                    content="Hello! Can you respond with a simple greeting?",
                )
            ]

            response, model_name = await generator.generate(messages)

            print("✅ Google Generator Success!")
            print(f"   Model: {model_name}")
            print(
                f"   Response: {response[:100]}{'...' if len(response) > 100 else ''}"
            )

        except Exception as e:
            print(f"❌ Google Generator Failed: {str(e)}")
            import traceback

            traceback.print_exc()

    asyncio.run(test_google_generator())
