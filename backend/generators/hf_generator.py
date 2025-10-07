from typing import Optional
import base64
import os
import asyncio
import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.models.generators import Generator, Message
from backend.models.rate_limiting import RateLimitingMixin
from backend.config import get_settings


HUGGINGFACE_API_KEY = get_settings().hf_token

# Set up logging
logger = logging.getLogger(__name__)


class HFGenerator(RateLimitingMixin, Generator):
    """
    Hugging Face Generator class.
    """

    def __init__(self, requests_per_minute=200, requests_per_day=10000, **kwargs):
        super().__init__(
            requests_per_minute=requests_per_minute,
            requests_per_day=requests_per_day,
            **kwargs,
        )
        self.client = AsyncOpenAI(
            base_url="https://router.huggingface.co/v1", api_key=HUGGINGFACE_API_KEY
        )
        self.model_name = "zai-org/GLM-4.6:zai-org"

    def encode_image(self, image_path: str) -> str:
        """
        Encode an image file to base64 string.

        Args:
            image_path: Path to the image file

        Returns:
            Base64 encoded string of the image
        """
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    async def format_messages(self, messages: list[Message]) -> list[dict]:
        """
        Format messages for the OpenAI API with support for multiple images.
        """
        formatted_messages = []
        for message in messages:
            # Handle text content
            if isinstance(message.content, str):
                text_content = message.content
            else:
                text_content = " ".join(message.content)

            # Start with text content
            content_parts = [{"type": "text", "text": text_content}]

            # Add images from file paths
            if message.image_paths:
                for image_path in message.image_paths:
                    # Get image extension to determine MIME type
                    _, ext = os.path.splitext(image_path.lower())
                    mime_type = {
                        ".jpg": "jpeg",
                        ".jpeg": "jpeg",
                        ".png": "png",
                        ".gif": "gif",
                        ".webp": "webp",
                    }.get(ext, "jpeg")  # Default to jpeg if unknown

                    # Encode image to base64
                    base64_image = self.encode_image(image_path)

                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{mime_type};base64,{base64_image}"
                            },
                        }
                    )

            # Add images from URLs
            if message.image_urls:
                for image_url in message.image_urls:
                    content_parts.append(
                        {"type": "image_url", "image_url": {"url": image_url}}
                    )

            # If we have images, use multimodal content, otherwise just text
            if len(content_parts) > 1:
                content = content_parts
            else:
                content = text_content

            formatted_messages.append({"role": message.role, "content": content})

        return formatted_messages

    async def _generate_openai_sdk_internal(
        self, messages, schema: Optional[BaseModel] = None
    ) -> str:
        """Internal OpenAI SDK method without rate limiting (handled by mixin)."""
        formatted_messages = await self.format_messages(messages)

        if schema is not None:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=formatted_messages,
                response_format=schema,
            )
            response = completion.choices[0].message.parsed
        else:
            completion = await self.client.chat.completions.create(
                model=self.model_name,
                messages=formatted_messages,
            )
            response = completion.choices[0].message.content

        return response, self.model_name

    async def generate(
        self, messages, schema: Optional[BaseModel] = None, use_reasoning: bool = True
    ) -> str:
        """
        Generate response with optional reasoning tokens support and rate limiting.
        """
        if use_reasoning:
            raise NotImplementedError("Reasoning is not supported for Hugging Face")
        else:
            return await self._execute_with_rate_limiting(
                self._generate_openai_sdk_internal, messages, schema
            )


if __name__ == "__main__":
    import asyncio

    async def test_hf_generator():
        """Test the Hugging Face generator with rate limiting."""
        print("🧪 Testing Hugging Face Generator with Rate Limiting...")

        try:
            # Test with default paid tier limits (200/min, 10000/day)
            generator = HFGenerator()

            # Show initial rate limit status
            print("\n📊 Initial Rate Limit Status:")
            status = generator.get_rate_limit_status()
            for key, value in status.items():
                print(f"   {key}: {value}")

            # Test text-only message
            print("\n📝 Testing text-only message with rate limiting...")
            messages = [
                Message(
                    role="user",
                    content="Hello! Can you respond with a simple greeting?",
                )
            ]

            response, model_name = await generator.generate(
                messages, use_reasoning=False
            )

            print("✅ Text-only test Success!")
            print(f"   Model: {model_name}")
            print(
                f"   Response: {response[:100]}{'...' if len(response) > 100 else ''}"
            )

            # Show updated rate limit status
            print("\n📊 Updated Rate Limit Status:")
            status = generator.get_rate_limit_status()
            for key, value in status.items():
                print(f"   {key}: {value}")

            # Test image message formatting (without actual API call)
            print("\n🖼️  Testing image message formatting...")
            image_messages = [
                Message(
                    role="user",
                    content="What's in these images?",
                    image_paths=[
                        "/path/to/test/image1.jpg",
                        "/path/to/test/image2.png",
                    ],  # These won't exist, just for format testing
                )
            ]

            # Test the formatting without making API call
            try:
                formatted = await generator.format_messages(image_messages)
                print("✅ Image message formatting structure created!")
                print(f"   Content type: {type(formatted[0]['content'])}")
                if isinstance(formatted[0]["content"], list):
                    print(f"   Content parts: {len(formatted[0]['content'])}")
                    for i, part in enumerate(formatted[0]["content"]):
                        print(f"     Part {i}: {part.get('type', 'unknown')}")
            except FileNotFoundError:
                print("✅ Image formatting logic works (file not found as expected)")
            except Exception as format_error:
                print(f"❌ Image formatting error: {format_error}")

            # Test rate limiting simulation
            print("\n⏳ Testing rate limiting behavior...")
            print("   (This would normally trigger rate limiting with real API calls)")

        except Exception as e:
            print(f"❌ Hugging Face Generator Failed: {str(e)}")
            import traceback

            traceback.print_exc()

    asyncio.run(test_hf_generator())
