"""OpenAI generator implementation using the Responses API."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import List, Optional, Tuple

from openai import AsyncOpenAI
from openai.types.responses import Response
from pydantic import BaseModel

from backend.config import get_settings
from backend.models.generators import Generator, Message
from backend.models.rate_limiting import RateLimitingMixin


logger = logging.getLogger(__name__)

# Resolve the API key from settings with an environment fallback.
_settings = get_settings()
OPENAI_API_KEY = _settings.openai_api_key or os.getenv("OPENAI_API_KEY")


class OpenAIGenerator(RateLimitingMixin, Generator):
    """Generator that calls OpenAI's Responses API."""

    def __init__(
        self,
        *,
        model_name: str = "gpt-4.1-mini",
        requests_per_minute: int = 100,
        requests_per_day: int = 5000,
        **kwargs,
    ) -> None:
        if not OPENAI_API_KEY:
            raise ValueError(
                "OpenAI API key not configured. Set `PWC_OPENAI_API_KEY` or `OPENAI_API_KEY`."
            )

        super().__init__(
            requests_per_minute=requests_per_minute,
            requests_per_day=requests_per_day,
            **kwargs,
        )

        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model_name = model_name

    @staticmethod
    def _encode_image(image_path: str) -> Optional[str]:
        """Encode an image file to a base64 string."""
        if not os.path.exists(image_path):
            logger.warning("Image path does not exist: %s", image_path)
            return None

        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to encode image %s: %s", image_path, exc)
            return None

    async def _upload_file(self, file_path: str) -> Optional[str]:
        """Upload a file to OpenAI for use in the Responses API."""
        if not file_path or not os.path.exists(file_path):
            if file_path:
                logger.warning("File path does not exist: %s", file_path)
            return None

        try:
            with open(file_path, "rb") as fh:
                uploaded = await self.client.files.create(
                    file=(os.path.basename(file_path), fh),
                    purpose="responses",
                )
            return uploaded.id
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to upload file %s: %s", file_path, exc)
            return None

    async def _cleanup_uploaded_files(self, file_ids: List[str]) -> None:
        """Remove temporary files from OpenAI's storage."""
        for file_id in file_ids:
            if not file_id:
                continue
            try:
                await self.client.files.delete(file_id)
            except Exception as exc:  # pragma: no cover - best-effort cleanup
                logger.debug("Failed to delete uploaded file %s: %s", file_id, exc)

    async def format_messages(
        self, messages: List[Message]
    ) -> Tuple[List[dict], List[str]]:
        """Convert internal Message objects to OpenAI Responses format."""

        formatted_messages: List[dict] = []
        uploaded_file_ids: List[str] = []

        for message in messages:
            content_parts: List[dict] = []

            # Normalize text content (string or list of strings)
            if isinstance(message.content, str):
                text_chunks = [message.content]
            else:
                text_chunks = list(message.content)

            for chunk in text_chunks:
                if chunk:
                    content_parts.append({"type": "text", "text": chunk})

            # Attach images from local paths
            if message.image_paths:
                for image_path in message.image_paths:
                    encoded = self._encode_image(image_path)
                    if encoded:
                        content_parts.append(
                            {"type": "input_image", "image_base64": encoded}
                        )

            # Attach images from URLs
            if message.image_urls:
                for image_url in message.image_urls:
                    if image_url:
                        content_parts.append(
                            {
                                "type": "input_image",
                                "image_url": {"url": image_url},
                            }
                        )

            # Attach PDFs or other files (if provided)
            if message.pdf_path:
                file_id = await self._upload_file(message.pdf_path)
                if file_id:
                    uploaded_file_ids.append(file_id)
                    content_parts.append({"type": "input_file", "file_id": file_id})

            # Ensure there's at least one text part to avoid empty content
            if not content_parts:
                logger.warning(
                    "Message for role '%s' had no content; inserting empty text part.",
                    message.role,
                )
                content_parts.append({"type": "text", "text": ""})

            formatted_messages.append({"role": message.role, "content": content_parts})

        return formatted_messages, uploaded_file_ids

    @staticmethod
    def _extract_response_content(response: Response) -> str:
        """Extract concatenated text content from a Responses API response."""

        if hasattr(response, "output_text") and response.output_text:
            return response.output_text

        response_dict = response.model_dump()
        output_items = response_dict.get("output", []) or []

        collected_text: List[str] = []
        for item in output_items:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    collected_text.append(content["text"])

        return "\n".join(collected_text).strip()

    async def _call_responses_api_internal(
        self, messages: List[Message], schema: Optional[BaseModel] = None
    ) -> Tuple[object, str]:
        formatted_messages, uploaded_file_ids = await self.format_messages(messages)

        try:
            request_payload = {
                "model": self.model_name,
                "input": formatted_messages,
            }

            if schema is not None:
                request_payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                    },
                }

            response = await self.client.responses.create(**request_payload)

            # Log token usage for observability (best effort).
            if response.usage:
                usage = response.usage
                logger.debug(
                    "OpenAI usage - input tokens: %s, output tokens: %s, total: %s",
                    getattr(usage, "input_tokens", None),
                    getattr(usage, "output_tokens", None),
                    getattr(usage, "total_tokens", None),
                )

            content = self._extract_response_content(response)

            if schema is not None:
                try:
                    if isinstance(content, str):
                        parsed_object = schema.model_validate_json(content)
                    else:
                        parsed_object = schema.model_validate(content)
                except (json.JSONDecodeError, ValueError, TypeError):
                    parsed_object = schema.model_validate(json.loads(content))
                return parsed_object, response.model

            return content, response.model
        finally:
            await self._cleanup_uploaded_files(uploaded_file_ids)

    async def generate(
        self, messages: List[Message], schema: Optional[BaseModel] = None
    ) -> Tuple[object, str]:
        """Generate a model response with optional structured output."""

        return await self._execute_with_rate_limiting(
            self._call_responses_api_internal, messages, schema
        )


__all__ = ["OpenAIGenerator"]
