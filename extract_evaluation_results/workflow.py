"""
Workflow orchestration system for evaluation extraction pipeline.

This module provides the core workflow engine that:
- Manages workflow state with automatic data flow between steps
- Supports step persistence and resume functionality
- Executes steps sequentially with error handling
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from extract_evaluation_results.io import get_cache_dir
from extract_evaluation_results.step_base import StepResult

logger = logging.getLogger(__name__)


@dataclass
class WorkflowOptions:
    """Configuration options for workflow execution."""

    arxiv_id: str
    resume: bool = False
    skip_addition: bool = False
    skip_step_6: bool = False


@dataclass
class WorkflowState:
    """
    Maintains the state of data flowing through the workflow.

    The state stores all intermediate data in a dictionary that steps can
    read from and write to. This enables automatic data flow between steps
    by matching field names.
    """

    arxiv_id: str
    options: WorkflowOptions
    data: Dict[str, Any] = field(default_factory=dict)
    completed_steps: List[str] = field(default_factory=list)
    skipped_steps: List[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
    message: str = ""

    def __post_init__(self):
        """Initialize the data dict with arxiv_id."""
        if "arxiv_id" not in self.data:
            self.data["arxiv_id"] = self.arxiv_id

    def is_step_completed(self, step_name: str) -> bool:
        """Check if a step has been completed."""
        return step_name in self.completed_steps

    def is_step_skipped(self, step_name: str) -> bool:
        """Check if a step has been skipped."""
        return step_name in self.skipped_steps

    def mark_completed(self, step_name: str) -> None:
        """Mark a step as completed."""
        if step_name not in self.completed_steps:
            self.completed_steps.append(step_name)

    def mark_skipped(self, step_name: str) -> None:
        """Mark a step as skipped."""
        if step_name not in self.skipped_steps:
            self.skipped_steps.append(step_name)


@runtime_checkable
class WorkflowStep(Protocol):
    """
    Protocol for workflow steps.

    Each step must implement:
    - name: str identifier
    - execute(state): async method that processes state and returns StepResult
    """

    name: str

    async def execute(self, state: WorkflowState) -> StepResult:
        """
        Execute the workflow step.

        Args:
            state: Current workflow state with data dictionary

        Returns:
            StepResult with success status and outputs
        """
        ...


class Workflow:
    """
    Main workflow execution engine.

    Orchestrates sequential execution of steps with:
    - Automatic data flow by field name matching
    - Persistence and caching support
    - Resume functionality
    - Skip logic for conditional execution
    """

    def __init__(self, steps: List[WorkflowStep]):
        """
        Initialize the workflow with a list of steps.

        Args:
            steps: List of workflow steps to execute sequentially
        """
        self.steps = steps
        self.logger = logging.getLogger(f"{__name__}.Workflow")

    def _should_skip_step(self, step: WorkflowStep, options: WorkflowOptions) -> bool:
        """
        Determine if a step should be skipped based on options.

        Args:
            step: The workflow step
            options: Workflow options

        Returns:
            True if step should be skipped
        """
        step_name = step.name.lower()

        # Skip steps 4, 5, 6 if skip_addition is True
        if options.skip_addition:
            if any(
                s in step_name
                for s in ["step_4", "step_5", "step_6", "step4", "step5", "step6"]
            ):
                return True

        # Skip step 6 if skip_step_6 is True
        if options.skip_step_6:
            if "step_6" in step_name or "step6" in step_name:
                return True

        return False

    async def _load_cached_step(
        self, step_name: str, arxiv_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Load cached step data if it exists.

        Args:
            step_name: Name of the step
            arxiv_id: ArXiv ID for cache directory

        Returns:
            Cached data dictionary or None
        """
        cache_dir = get_cache_dir(arxiv_id)

        # Try different cache file naming patterns
        cache_patterns = [
            f"{step_name}.json",
            f"{step_name.replace('WorkflowStep', '')}.json",
            f"{step_name.replace('Step', 'step_')}.json",
        ]

        # Also try extracting step number
        import re

        match = re.search(r"(\d+)", step_name)
        if match:
            step_num = match.group(1)
            cache_patterns.append(f"step_{step_num}.json")

        for pattern in cache_patterns:
            cache_path = cache_dir / pattern
            if cache_path.exists():
                try:
                    import json

                    data = json.loads(cache_path.read_text())
                    self.logger.info(
                        f"Loaded cached data for {step_name} from {cache_path.name}"
                    )
                    return data
                except Exception as e:
                    self.logger.warning(f"Failed to load cache {cache_path}: {e}")

        return None

    async def _save_step_data(
        self, step_name: str, arxiv_id: str, data: Dict[str, Any]
    ) -> None:
        """
        Save step data to cache.

        Args:
            step_name: Name of the step
            arxiv_id: ArXiv ID for cache directory
            data: Data to save
        """
        cache_dir = get_cache_dir(arxiv_id)

        # Extract step number for cache file naming
        import re

        match = re.search(r"(\d+)", step_name)
        if match:
            step_num = match.group(1)
            cache_path = cache_dir / f"step_{step_num}.json"
        else:
            cache_path = cache_dir / f"{step_name}.json"

        try:
            import json

            cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            self.logger.info(f"Saved {step_name} data to {cache_path.name}")
        except Exception as e:
            self.logger.warning(f"Failed to save cache {cache_path}: {e}")

    async def run(self, options: WorkflowOptions) -> WorkflowState:
        """
        Execute all workflow steps sequentially.

        Args:
            options: Workflow configuration options

        Returns:
            Final workflow state with all data
        """
        # Initialize workflow state
        state = WorkflowState(arxiv_id=options.arxiv_id, options=options)

        self.logger.info(f"Starting workflow for arxiv_id: {options.arxiv_id}")
        self.logger.info(
            f"Options: resume={options.resume}, skip_addition={options.skip_addition}, skip_step_6={options.skip_step_6}"
        )

        # Execute steps sequentially
        for i, step in enumerate(self.steps):
            step_name = step.name

            # Check if step should be skipped
            if self._should_skip_step(step, options):
                self.logger.info(
                    f"[{i + 1}/{len(self.steps)}] Skipping {step_name} (skip option enabled)"
                )
                state.mark_skipped(step_name)
                continue

            # Check for cached data if resume is enabled
            if options.resume:
                cached_data = await self._load_cached_step(step_name, options.arxiv_id)
                if cached_data:
                    self.logger.info(
                        f"[{i + 1}/{len(self.steps)}] Using cached data for {step_name}"
                    )

                    # Update state.data with cached outputs
                    # Handle both dict and list outputs
                    if isinstance(cached_data, dict):
                        for key, value in cached_data.items():
                            state.data[key] = value
                    elif isinstance(cached_data, list):
                        # For list outputs, store under a step-specific key
                        step_key = f"{step_name.lower()}_results"
                        state.data[step_key] = cached_data

                    state.mark_completed(step_name)
                    continue

            # Execute the step
            self.logger.info(f"[{i + 1}/{len(self.steps)}] Executing {step_name}...")

            try:
                result = await step.execute(state)

                if result.success:
                    self.logger.info(
                        f"[{i + 1}/{len(self.steps)}] ✓ {step_name} completed"
                    )

                    # Extract outputs and update state.data
                    if result.outputs:
                        output_dict = result.outputs.model_dump()
                        for field_name, value in output_dict.items():
                            state.data[field_name] = value
                            self.logger.debug(f"  Stored: {field_name}")

                        # Save to cache
                        await self._save_step_data(
                            step_name, options.arxiv_id, output_dict
                        )

                    state.mark_completed(step_name)
                else:
                    # Step failed
                    self.logger.error(
                        f"[{i + 1}/{len(self.steps)}] ✗ {step_name} failed: {result.error_message}"
                    )
                    state.success = False
                    state.error = f"{step_name} failed: {result.error_message}"
                    state.message = result.error_message
                    break

            except Exception as e:
                self.logger.error(
                    f"[{i + 1}/{len(self.steps)}] ✗ {step_name} exception: {e}",
                    exc_info=True,
                )
                state.success = False
                state.error = f"{step_name} exception: {str(e)}"
                state.message = str(e)
                break

        if state.success:
            self.logger.info(
                f"Workflow completed successfully. {len(state.completed_steps)} steps executed."
            )
        else:
            self.logger.error(f"Workflow failed: {state.error}")

        return state

    async def run_single_step(
        self, step_index: int, state: WorkflowState
    ) -> WorkflowState:
        """
        Execute a single step of the workflow.

        Args:
            step_index: Index of the step to execute
            state: Current workflow state

        Returns:
            Updated workflow state
        """
        if step_index < 0 or step_index >= len(self.steps):
            state.success = False
            state.error = f"Invalid step index: {step_index}"
            return state

        step = self.steps[step_index]
        step_name = step.name

        self.logger.info(f"Executing single step: {step_name}")

        try:
            result = await step.execute(state)

            if result.success:
                self.logger.info(f"✓ {step_name} completed")

                # Extract outputs and update state.data
                if result.outputs:
                    output_dict = result.outputs.model_dump()
                    for field_name, value in output_dict.items():
                        state.data[field_name] = value

                    # Save to cache
                    await self._save_step_data(step_name, state.arxiv_id, output_dict)

                state.mark_completed(step_name)
            else:
                self.logger.error(f"✗ {step_name} failed: {result.error_message}")
                state.success = False
                state.error = result.error_message
                state.message = result.error_message

        except Exception as e:
            self.logger.error(f"✗ {step_name} exception: {e}", exc_info=True)
            state.success = False
            state.error = str(e)
            state.message = str(e)

        return state
