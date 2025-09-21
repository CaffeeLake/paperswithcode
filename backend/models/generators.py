"""
Base models for AI generators and messages.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Union
from pydantic import BaseModel


class Message(BaseModel):
    """Message model for generator inputs."""

    role: str  # "user" or "assistant"
    content: Union[str, List[str]]  # Text content, can be string or list of strings
    image_url: Optional[str] = None  # Optional image URL
    pdf_path: Optional[str] = None  # Optional PDF file path


class Generator(ABC):
    """Abstract base class for AI generators."""

    @abstractmethod
    async def generate(
        self, messages: List[Message], schema: Optional[BaseModel] = None
    ) -> tuple[str, str]:
        """
        Generate a response from the given messages.

        Args:
            messages: List of Message objects
            schema: Optional Pydantic schema for structured output

        Returns:
            Tuple of (response, model_name)
        """
        pass

    @abstractmethod
    async def format_messages(self, messages: List[Message]):
        """Format messages for the specific API."""
        pass
