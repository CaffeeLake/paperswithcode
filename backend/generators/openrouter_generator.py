from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from ..models import Generator, Message

from ..config import get_settings


OPENROUTER_API_KEY = get_settings().openrouter_api_key


class OpenRouterGenerator(Generator):
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY
        )
        self.model_name = "x-ai/grok-4-fast:free"

    async def format_messages(self, messages: list[Message]) -> list[dict]:
        """
        Format messages for the OpenAI API.
        """
        formatted_messages = []
        for message in messages:
            content = (
                message.content
                if isinstance(message.content, str)
                else " ".join(message.content)
            )
            formatted_messages.append({"role": message.role, "content": content})

        return formatted_messages

    async def generate(self, messages, schema: Optional[BaseModel] = None) -> str:
        messages = await self.format_messages(messages)

        if schema is not None:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model_name,
                messages=messages,
                response_format=schema,
            )
            response = completion.choices[0].message.parsed

        else:
            completion = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
            )
            response = completion.choices[0].message.content

        return response, self.model_name


if __name__ == "__main__":
    import asyncio

    async def test_openrouter_generator():
        """Test the OpenRouter generator."""
        print("🧪 Testing OpenRouter Generator...")

        try:
            generator = OpenRouterGenerator()
            messages = [
                Message(
                    role="user",
                    content="Hello! Can you respond with a simple greeting?",
                )
            ]

            response, model_name = await generator.generate(messages)

            print("✅ OpenRouter Generator Success!")
            print(f"   Model: {model_name}")
            print(
                f"   Response: {response[:100]}{'...' if len(response) > 100 else ''}"
            )

        except Exception as e:
            print(f"❌ OpenRouter Generator Failed: {str(e)}")
            import traceback

            traceback.print_exc()

    asyncio.run(test_openrouter_generator())
