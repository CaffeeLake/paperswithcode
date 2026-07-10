from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class URLFindings(BaseModel):
    """Structured findings owned by the research agent."""

    model_config = ConfigDict(extra="forbid")

    reasoning: str = Field(
        description="Concise explanation of the sources checked and why the URLs are official."
    )
    github_url: HttpUrl | None = Field(
        default=None,
        description="Official GitHub repository URL for this paper, or null.",
    )
    project_page_url: HttpUrl | None = Field(
        default=None,
        description="Official project page URL for this paper, or null.",
    )


class PaperCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: int
    arxiv_id: str
    title: str
    abstract: str
    missing_github: bool
    missing_project_page: bool
    known_github_url: HttpUrl | None = None
    known_project_page_url: HttpUrl | None = None
    priority: int
    priority_source: str

    @model_validator(mode="after")
    def has_missing_url(self) -> "PaperCandidate":
        if not self.missing_github and not self.missing_project_page:
            raise ValueError("candidate must be missing at least one URL type")
        return self


class ToolEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_input: dict[str, Any]
    success: bool
    error: str | None = None
    response: str | None = None


class AgentAttempt(BaseModel):
    """Result envelope produced by trusted agent orchestration code."""

    model_config = ConfigDict(extra="forbid")

    paper_id: int
    arxiv_id: str
    findings: URLFindings | None = None
    attempt_complete: bool = False
    failure_reason: str | None = None
    result_subtype: str | None = None
    cost_usd: float = 0.0
    tool_events: list[ToolEvent] = Field(default_factory=list)


class PersistResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: int
    status: Literal["persisted", "partial", "retry", "skipped"]
    github_saved: bool = False
    project_page_saved: bool = False
    urls_extracted: bool = False
    message: str = ""
