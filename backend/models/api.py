"""
Pydantic models for API responses.

These models match the original PapersWithCode API specification but are adapted
to our database schema. The main differences from the original API:
- No nips_id field (not supported in our schema)
- Added version and is_latest_version fields for ArXiv version tracking
- Enhanced URL construction based on our schema design
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, computed_field
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
    
    # Paper content
    title: str = Field(..., description="Paper title")
    abstract: str = Field(..., description="Paper abstract")
    authors: List[str] = Field(..., description="List of paper authors")
    
    # Publication information
    published: Optional[date] = Field(None, description="Paper publication date")
    conference: Optional[str] = Field(None, description="ID of the conference in which the paper was published")
    conference_url_abs: Optional[str] = Field(None, description="URL to the conference paper page")
    conference_url_pdf: Optional[str] = Field(None, description="URL to the conference paper PDF")
    proceeding: Optional[str] = Field(None, description="ID of the conference proceeding")
    
    # Version tracking (our extension)
    version: str = Field(default="v1", description="Paper version (e.g., v1, v2, v3)")
    is_latest_version: bool = Field(default=True, description="Whether this is the latest version")
    
    # Citation and importance metrics
    citation_count: int = Field(default=0, description="Number of citations from Semantic Scholar")
    semantic_scholar_id: Optional[str] = Field(None, description="Semantic Scholar paper ID")
    
    @field_validator('authors', mode='before')
    @classmethod
    def parse_authors(cls, v):
        """Parse authors from various input formats."""
        if isinstance(v, str):
            # If authors come as a single string, split by comma
            return [author.strip() for author in v.split(',')]
        elif isinstance(v, list):
            return v
        else:
            return []
    
    @field_validator('id', mode='before')
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
    previous_page: Optional[int] = Field(None, description="Number of the previous page")
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
    citation_count: int = Field(default=0, description="Number of citations from Semantic Scholar")
    
    @field_validator('id', mode='before')
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
    
    @field_validator('id', mode='before')
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
    time_between_versions: Optional[int] = Field(None, description="Days between versions")


# Error models

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    detail: str = Field(..., description="Error details")


class ValidationErrorResponse(BaseModel):
    """Validation error response."""
    error: str = Field(default="Validation error", description="Error type")
    detail: List[dict] = Field(..., description="Validation error details")
