"""
Pydantic models for API responses.

These models match the original PapersWithCode API specification but are adapted
to our database schema. The main differences from the original API:
- No nips_id field (not supported in our schema)
- Added version and is_latest_version fields for ArXiv version tracking
- Enhanced URL construction based on our schema design
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic import ConfigDict


class Paper(BaseModel):
    """
    Paper object matching the original PapersWithCode API specification.

    Represents a single research paper with all its metadata, authors, and URLs.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core paper identification
    id: str = Field(..., description="Paper ID")
    arxiv_id: Optional[str] = Field(None, description="ArXiv ID")

    # URLs - computed from arxiv_id and version
    url_abs: str = Field(..., description="URL to the paper abstract")
    url_pdf: str = Field(..., description="URL to the paper PDF")
    thumbnail_url: Optional[str] = Field(
        None, description="URL to the paper thumbnail image"
    )

    # Paper content
    title: str = Field(..., description="Paper title")
    abstract: str = Field(..., description="Paper abstract")
    authors: List[str] = Field(..., description="List of paper authors")

    # Publication information
    published: Optional[date] = Field(None, description="Paper publication date")
    conference: Optional[str] = Field(
        None, description="ID of the conference in which the paper was published"
    )
    conference_url_abs: Optional[str] = Field(
        None, description="URL to the conference paper page"
    )
    conference_url_pdf: Optional[str] = Field(
        None, description="URL to the conference paper PDF"
    )
    proceeding: Optional[str] = Field(
        None, description="ID of the conference proceeding"
    )

    # Version tracking (our extension)
    version: str = Field(default="v1", description="Paper version (e.g., v1, v2, v3)")
    is_latest_version: bool = Field(
        default=True, description="Whether this is the latest version"
    )

    # Citation and importance metrics
    citation_count: int = Field(
        default=0, description="Number of citations from Semantic Scholar"
    )
    semantic_scholar_id: Optional[str] = Field(
        None, description="Semantic Scholar paper ID"
    )
    citation_updated_at: Optional[datetime] = Field(
        None, description="Last time citations were updated"
    )

    # ArXiv category classification
    primary_category: Optional[str] = Field(
        None, description="Primary ArXiv category (e.g., cs.CV, cs.LG)"
    )
    all_categories: List[str] = Field(
        default_factory=list, description="All ArXiv categories for this paper"
    )

    # URL extraction tracking
    urls_extracted: bool = Field(
        default=False, description="Whether URLs have been extracted for this paper"
    )

    # Associated resources (optional, populated when requested)
    repositories: Optional[List["Repository"]] = Field(
        None, description="GitHub repositories associated with this paper"
    )
    project_pages: Optional[List["ProjectPage"]] = Field(
        None, description="Project pages associated with this paper"
    )

    @field_validator("authors", mode="before")
    @classmethod
    def parse_authors(cls, v):
        """Parse authors from various input formats."""
        if isinstance(v, str):
            # If authors come as a single string, split by comma
            return [author.strip() for author in v.split(",")]
        elif isinstance(v, list):
            return v
        else:
            return []

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class Papers(BaseModel):
    """
    Object representing a paginated page of papers.

    Matches the original PapersWithCode API pagination structure.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Paper] = Field(..., description="List of papers on this page")


# Additional models for extended functionality


class PaperSummary(BaseModel):
    """
    Lightweight paper summary for list views.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Paper ID")
    title: str = Field(..., description="Paper title")
    arxiv_id: Optional[str] = Field(None, description="ArXiv ID")
    authors: List[str] = Field(..., description="List of paper authors")
    published: Optional[date] = Field(None, description="Paper publication date")
    url_abs: str = Field(..., description="URL to the paper abstract")
    citation_count: int = Field(
        default=0, description="Number of citations from Semantic Scholar"
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperVersion(BaseModel):
    """
    Information about a specific paper version.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Paper ID")
    version: str = Field(..., description="Version identifier")
    title: str = Field(..., description="Paper title")
    is_latest: bool = Field(..., description="Whether this is the latest version")
    published: Optional[date] = Field(None, description="Publication date")
    url_abs: str = Field(..., description="URL to the paper abstract")
    paper_url: str = Field(..., description="URL to the paper on our platform")
    abstract_preview: Optional[str] = Field(None, description="Preview of the abstract")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperVersions(BaseModel):
    """
    All versions of a paper.
    """

    model_config = ConfigDict(from_attributes=True)

    arxiv_id: str = Field(..., description="ArXiv ID")
    total_versions: int = Field(..., description="Total number of versions")
    versions: List[PaperVersion] = Field(..., description="List of all versions")


class VersionComparison(BaseModel):
    """
    Comparison between two paper versions.
    """

    model_config = ConfigDict(from_attributes=True)

    from_version: str = Field(..., description="Source version")
    to_version: str = Field(..., description="Target version")
    title_changed: bool = Field(..., description="Whether the title changed")
    abstract_changed: bool = Field(..., description="Whether the abstract changed")
    date_changed: bool = Field(..., description="Whether the publication date changed")
    time_between_versions: Optional[int] = Field(
        None, description="Days between versions"
    )


# Error models


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    error: str = Field(default="Validation error", description="Error type")
    detail: List[dict] = Field(..., description="Validation error details")


# Author models


class Author(BaseModel):
    """
    Author object matching the original PapersWithCode API specification.

    Represents a research paper author with optional Hugging Face integration.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core author identification
    id: str = Field(..., description="Author ID")
    full_name: str = Field(..., description="Author full name", alias="name")

    # Hugging Face integration (our extension)
    hf_username: Optional[str] = Field(None, description="Hugging Face username")
    hf_id: Optional[str] = Field(None, description="Hugging Face user ID")
    hf_avatar_url: Optional[str] = Field(None, description="Hugging Face avatar URL")
    hf_status: Optional[str] = Field(None, description="Hugging Face account status")
    hf_is_pro: bool = Field(
        default=False, description="Whether user has Hugging Face Pro"
    )

    # Statistics (computed fields)
    paper_count: int = Field(default=0, description="Number of papers by this author")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class Authors(BaseModel):
    """
    Object representing a paginated page of authors.

    Matches the original PapersWithCode API pagination structure.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Author] = Field(..., description="List of authors on this page")


class AuthorSummary(BaseModel):
    """
    Lightweight author summary for list views.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Author ID")
    full_name: str = Field(..., description="Author full name", alias="name")
    hf_username: Optional[str] = Field(None, description="Hugging Face username")
    paper_count: int = Field(default=0, description="Number of papers by this author")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


# Repository and Project Page models


class Repository(BaseModel):
    """
    GitHub repository (normalized, without direct paper association).

    Represents a unique code repository that can be associated with multiple papers.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core repository identification
    id: str = Field(..., description="Repository ID")

    # Repository details
    url: str = Field(..., description="Full GitHub repository URL")
    owner: Optional[str] = Field(None, description="GitHub username/organization")
    name: Optional[str] = Field(None, description="Repository name")

    # Repository metadata
    num_stars: int = Field(default=0, description="Number of GitHub stars")
    is_official: bool = Field(
        default=False,
        description="Whether this repository is generally considered official",
    )
    source: str = Field(
        default="unknown",
        description="Source of the repository data (pwc_archive, ai_extraction, manual, etc.)",
    )

    # Timestamps
    created_at: Optional[date] = Field(None, description="Repository creation date")
    updated_at: Optional[date] = Field(None, description="Repository last update date")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperRepository(BaseModel):
    """
    Simple association between a paper and a repository.

    Represents the many-to-many relationship between papers and repositories.
    All metadata is stored in the Repository table itself.
    """

    model_config = ConfigDict(from_attributes=True)

    # Relationship identification
    paper_id: str = Field(..., description="Associated paper ID")
    repository_id: str = Field(..., description="Associated repository ID")

    # Optional embedded repository data for convenience
    repository: Optional[Repository] = Field(
        None, description="Full repository details"
    )

    @field_validator("paper_id", mode="before")
    @classmethod
    def ensure_string_paper_id(cls, v):
        """Ensure paper_id is always a string."""
        return str(v)

    @field_validator("repository_id", mode="before")
    @classmethod
    def ensure_string_repository_id(cls, v):
        """Ensure repository_id is always a string."""
        return str(v)


class Repositories(BaseModel):
    """
    Object representing a paginated page of repositories.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Repository] = Field(
        ..., description="List of repositories on this page"
    )


class ProjectPage(BaseModel):
    """
    Project page showcasing paper work - normalized without direct paper reference.

    Represents a demo site, project website, or other web resource.
    Use PaperProjectPage for relationships between papers and project pages.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core project page identification
    id: str = Field(..., description="Project page ID")

    # Project page details
    url: str = Field(..., description="Full URL to project page")
    is_official: bool = Field(
        default=False,
        description="Whether this is an official project page (use PaperProjectPage.is_official for relationship-specific data)",
    )
    source: str = Field(
        default="unknown",
        description="Source of the project page data (pwc_archive, ai_extraction, manual, etc.)",
    )

    # Timestamps
    created_at: Optional[date] = Field(None, description="Project page creation date")
    updated_at: Optional[date] = Field(
        None, description="Project page last update date"
    )

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class PaperProjectPage(BaseModel):
    """
    Junction table model for many-to-many relationship between papers and project pages.
    Simplified to only contain the two ID columns as requested.
    """

    model_config = ConfigDict(from_attributes=True)

    # Relationship identification (only the two ID columns)
    paper_id: str = Field(..., description="Associated paper ID")
    project_page_id: str = Field(..., description="Associated project page ID")

    @field_validator("paper_id", mode="before")
    @classmethod
    def ensure_string_paper_id(cls, v):
        """Ensure paper_id is always a string."""
        return str(v)

    @field_validator("project_page_id", mode="before")
    @classmethod
    def ensure_string_project_page_id(cls, v):
        """Ensure project_page_id is always a string."""
        return str(v)


class ProjectPageWithPapers(BaseModel):
    """
    Project page with associated papers information.

    Used for API responses that need to show which papers are associated with a project page.
    """

    model_config = ConfigDict(from_attributes=True)

    # Project page details
    project_page: ProjectPage = Field(..., description="Project page information")

    # Associated papers
    papers: List[str] = Field(..., description="List of associated paper IDs")

    # Relationship metadata (if needed)
    relationships: Optional[List[PaperProjectPage]] = Field(
        None, description="Detailed relationship information"
    )


class ProjectPages(BaseModel):
    """
    Object representing a paginated page of project pages.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[ProjectPage] = Field(
        ..., description="List of project pages on this page"
    )


class Area(BaseModel):
    """
    Research area object representing a broad field of AI/ML research.

    Examples: Computer Vision, Natural Language Processing, Reinforcement Learning, etc.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core area identification
    id: str = Field(..., description="Area ID")
    name: str = Field(..., description="Area name (e.g., 'Computer Vision')")
    description: Optional[str] = Field(None, description="Area description")

    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Area creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure ID is always a string."""
        return str(v)


class Areas(BaseModel):
    """
    Object representing a paginated page of areas.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Area] = Field(..., description="List of areas on this page")


class Task(BaseModel):
    """
    Task object representing a specific AI/ML task.

    Tasks are hierarchical and can have parent-child relationships.
    Examples: Image Classification, Object Detection, Language Modeling, etc.
    """

    model_config = ConfigDict(from_attributes=True)

    # Core task identification
    id: str = Field(..., description="Task ID")
    name: str = Field(..., description="Task name (e.g., 'Image Classification')")
    description: Optional[str] = Field(None, description="Task description")
    slug: Optional[str] = Field(None, description="URL-friendly task slug")

    # Hierarchical structure
    parent_id: Optional[str] = Field(None, description="ID of the parent task")
    area_id: Optional[str] = Field(None, description="ID of the research area")
    level: int = Field(default=0, description="Depth in task hierarchy (0=top-level)")

    # Metadata
    paper_count: Optional[int] = Field(
        None, description="Number of papers for this task"
    )

    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Task creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")

    @field_validator("id", "parent_id", "area_id", mode="before")
    @classmethod
    def ensure_string_id(cls, v):
        """Ensure IDs are strings."""
        if v is None:
            return v
        return str(v)


class Tasks(BaseModel):
    """
    Object representing a paginated page of tasks.
    """

    model_config = ConfigDict(from_attributes=True)

    count: int = Field(..., description="Number of elements matching the query")
    next_page: Optional[int] = Field(None, description="Number of the next page")
    previous_page: Optional[int] = Field(
        None, description="Number of the previous page"
    )
    results: List[Task] = Field(..., description="List of tasks on this page")


# Resolve forward references
Paper.model_rebuild()
