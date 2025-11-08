"""
Base classes for defining workflow steps in agent-based pipelines.

This module provides reusable abstractions for creating declarative steps that:
- Use Pydantic models for type-safe inputs and outputs
- Execute agent-based or deterministic computations
- Support parallel processing and validation
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar, Union

from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Generic type variables for input and output models
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


def create_mcp_server(server_name: str) -> Optional[MCPServerStdio]:
    """
    Factory function to create MCP servers by name.

    Args:
        server_name: Name of the server ("exa" or "huggingface")

    Returns:
        MCPServerStdio instance or None if credentials not available
    """
    if server_name == "exa":
        exa_api_key = os.getenv("EXA_API_KEY")
        if not exa_api_key:
            logger.warning("EXA_API_KEY not found. Exa search will not be available.")
            return None

        return MCPServerStdio(
            name="Exa AI MCP Server",
            params={
                "command": "npx",
                "args": ["-y", "mcp-remote", "https://mcp.exa.ai/mcp"],
                "env": {"EXA_API_KEY": exa_api_key},
            },
            client_session_timeout_seconds=30,
        )

    elif server_name == "huggingface":
        hf_token = (
            os.getenv("HF_TOKEN")
            or os.getenv("HUGGINGFACE_API_KEY")
            or os.getenv("HUGGINGFACE_TOKEN")
        )
        if not hf_token:
            logger.info(
                "HF_TOKEN not found. Hugging Face MCP server will not be available."
            )
            return None

        return MCPServerStdio(
            name="Hugging Face MCP Server",
            params={
                "command": "npx",
                "args": [
                    "-y",
                    "mcp-remote",
                    "https://huggingface.co/mcp",
                    "--header",
                    f"Authorization: Bearer {hf_token}",
                ],
            },
            client_session_timeout_seconds=30,
        )

    else:
        logger.warning(f"Unknown MCP server name: {server_name}")
        return None


@dataclass
class StepResult(Generic[OutputT]):
    """Result from executing a step with typed outputs."""

    success: bool
    outputs: Optional[OutputT] = None
    error_message: str = ""
    reasoning: str = ""


class Step(ABC, Generic[InputT, OutputT]):
    """
    Base class for workflow steps with typed inputs and outputs.

    A Step encapsulates:
    - Type-safe input/output models (Pydantic)
    - Validation logic (via Pydantic)
    - Execution logic (agent-based or deterministic)

    Subclasses should:
    - Define input_model and output_model as class attributes
    - Implement execute(): Process typed inputs and return typed outputs
    """

    # Subclasses should define these as class attributes
    input_model: type[InputT]
    output_model: type[OutputT]

    def __init__(
        self,
        *,
        name: str,
        description: str = "",
    ):
        """
        Initialize a Step.

        Args:
            name: Name of the step
            description: Description of what this step does
        """
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def execute(self, inputs: InputT) -> OutputT:
        """
        Execute the step with typed inputs and return typed outputs.

        Args:
            inputs: Validated input model instance

        Returns:
            Output model instance
        """
        pass

    async def run(self, inputs: Union[InputT, Dict[str, Any]]) -> StepResult[OutputT]:
        """
        Run the step with validation.

        Args:
            inputs: Either an input model instance or a dict to be validated

        Returns:
            StepResult with success status and typed outputs
        """
        # If dict provided, parse it into the input model
        if isinstance(inputs, dict):
            try:
                validated_inputs = self.input_model(**inputs)
            except Exception as e:
                self.logger.error(f"Input validation failed: {e}")
                return StepResult(
                    success=False,
                    error_message=f"Input validation failed: {e}",
                    outputs=None,
                )
        else:
            validated_inputs = inputs

        # Execute step
        self.logger.info(f"[{self.name}] Starting execution")
        try:
            outputs = await self.execute(validated_inputs)
            self.logger.info(f"[{self.name}] Completed successfully")
            return StepResult(
                success=True,
                outputs=outputs,
            )
        except Exception as e:
            self.logger.error(f"[{self.name}] Exception: {e}", exc_info=True)
            return StepResult(
                success=False,
                error_message=str(e),
                outputs=None,
            )


class AgentStep(Step[InputT, OutputT]):
    """
    Step that uses OpenAI Agents SDK for execution with typed inputs/outputs.

    This is a specialized Step that:
    - Constructs an agent with instructions, tools, and MCP servers
    - Processes typed inputs through the agent
    - Handles structured output (Pydantic models)

    Subclasses should override:
    - build_agent_prompt(): Convert typed inputs to agent prompt string
    - process_agent_output() (optional): Transform agent output into typed output
    """

    def __init__(
        self,
        *,
        name: str,
        description: str = "",
        instructions: str = "",
        tools: Optional[List[Callable]] = None,
        agent_output_type: Optional[type[BaseModel]] = None,
        model: str = "gpt-5-mini",
        mcp_servers: Optional[List[str]] = None,
    ):
        """
        Initialize an AgentStep.

        Args:
            name: Name of the step
            description: Description of the step
            instructions: Instructions/prompt for the agent
            tools: List of tools available to the agent
            agent_output_type: Pydantic model for structured output (can differ from output_model)
            model: OpenAI model to use
            mcp_servers: List of MCP server names to use
        """
        super().__init__(name=name, description=description)
        self.instructions = instructions
        self.tools = tools or []
        self.agent_output_type = agent_output_type or self.output_model
        self.model = model
        self.mcp_server_names = mcp_servers or []
        self._mcp_servers = None  # Cache MCP servers for reuse in parallel processing

    @abstractmethod
    async def build_agent_prompt(self, inputs: InputT) -> str:
        """
        Convert typed inputs to agent prompt string.

        Args:
            inputs: Validated input model instance

        Returns:
            Prompt string to pass to the agent
        """
        pass

    async def process_agent_output(self, agent_output: Any, inputs: InputT) -> OutputT:
        """
        Process agent output into typed output model.

        Default implementation:
        - If agent_output is already the output model, return it
        - If it's a Pydantic model, convert to dict then to output_model
        - Otherwise, assume it's a dict and construct output_model

        Override this to customize output processing.

        Args:
            agent_output: Raw output from the agent
            inputs: Original inputs (for context)

        Returns:
            Typed output model instance
        """
        # If agent_output is already the output model, return it
        if isinstance(agent_output, self.output_model):
            return agent_output

        # If it's a Pydantic model, convert to dict then to output_model
        if isinstance(agent_output, BaseModel):
            return self.output_model(**agent_output.model_dump())

        # Otherwise, assume it's a dict and construct output_model
        return self.output_model(**agent_output)

    async def format_instructions(self, inputs: InputT) -> str:
        """
        Format instructions with input-specific context.

        Default implementation returns instructions as-is.
        Override to inject dynamic context into instructions.

        Args:
            inputs: Validated input model instance

        Returns:
            Formatted instructions string
        """
        return self.instructions

    async def _setup_mcp_servers(self) -> List[MCPServerStdio]:
        """Set up MCP servers based on configured server names."""
        if not self.mcp_server_names:
            return []

        entered_servers = []
        for server_name in self.mcp_server_names:
            server = create_mcp_server(server_name)
            if server is None:
                self.logger.warning(
                    f"Skipping MCP server '{server_name}' - credentials not available"
                )
                continue

            try:
                await asyncio.wait_for(server.__aenter__(), timeout=35.0)
                entered_servers.append(server)
                self.logger.info(f"Successfully connected to MCP server: {server_name}")
            except (Exception, asyncio.TimeoutError) as e:
                self.logger.warning(
                    f"Could not connect to MCP server '{server_name}': {e}"
                )
                try:
                    if hasattr(server, "_process") and server._process:
                        server._process.terminate()
                except Exception:
                    pass

        return entered_servers

    async def _run_agent(self, prompt: str, formatted_instructions: str):
        """
        Run the agent with the given prompt and instructions.

        This is a helper method that allows running the agent multiple times
        for parallel processing, reusing MCP server connections.

        Args:
            prompt: The prompt to pass to the agent
            formatted_instructions: Pre-formatted instructions

        Returns:
            Agent output (type depends on agent_output_type)
        """
        # Set up MCP servers if not already set up
        if self._mcp_servers is None:
            self._mcp_servers = await self._setup_mcp_servers()

        try:
            # Create agent
            agent = Agent(
                name=self.name,
                instructions=formatted_instructions,
                tools=self.tools,
                model=self.model,
                output_type=self.agent_output_type,
                mcp_servers=self._mcp_servers,
            )

            # Run agent
            result = await Runner.run(agent, prompt, max_turns=15)

            if result is None:
                raise RuntimeError("Agent returned None")

            # Extract final output
            if hasattr(result, "final_output"):
                agent_output = result.final_output
            else:
                agent_output = result

            if agent_output is None:
                raise RuntimeError("Agent final_output is None")

            return agent_output

        except Exception as e:
            self.logger.error(f"Agent execution failed: {e}", exc_info=True)
            raise

    async def _cleanup_mcp_servers(self):
        """Clean up MCP server connections."""
        if self._mcp_servers is not None:
            for server in self._mcp_servers:
                try:
                    await server.__aexit__(None, None, None)
                except asyncio.CancelledError:
                    # Cleanup was cancelled, ignore it
                    self.logger.debug("MCP server cleanup was cancelled")
                except Exception as e:
                    self.logger.warning(f"Error closing MCP server: {e}")
            self._mcp_servers = None

    async def execute(self, inputs: InputT) -> OutputT:
        """Execute the agent step with typed inputs."""
        # Format instructions with input context
        formatted_instructions = await self.format_instructions(inputs)

        # Set up MCP servers
        mcp_servers = await self._setup_mcp_servers()

        try:
            # Create agent
            agent = Agent(
                name=self.name,
                instructions=formatted_instructions,
                tools=self.tools,
                model=self.model,
                output_type=self.agent_output_type,
                mcp_servers=mcp_servers,
            )

            # Build prompt from inputs
            prompt = await self.build_agent_prompt(inputs)

            # Run agent
            self.logger.debug(f"Running agent with model {self.model}")
            result = await Runner.run(agent, prompt, max_turns=15)

            if result is None:
                raise RuntimeError("Agent returned None")

            # Extract final output
            if hasattr(result, "final_output"):
                agent_output = result.final_output
            else:
                agent_output = result

            if agent_output is None:
                raise RuntimeError("Agent final_output is None")

            # Process output into typed output model
            return await self.process_agent_output(agent_output, inputs)

        finally:
            # Clean up MCP servers
            for server in mcp_servers:
                try:
                    await server.__aexit__(None, None, None)
                except Exception as e:
                    self.logger.warning(f"Error closing MCP server: {e}")
