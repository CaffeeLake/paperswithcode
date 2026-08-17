"""
SQLAlchemy database models.

These models represent the database schema and provide ORM functionality
for interacting with the PostgreSQL database.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship
from sqlalchemy.sql import func, text

Base = declarative_base()


class Paper(Base):
    """
    Paper model representing research papers.

    Corresponds to the papers table in the database schema.
    """

    __tablename__ = "papers"

    # Primary key
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Core paper information
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Maintained by papers_search_vector_update() in PostgreSQL. Application
    # code reads this column for ranking but never constructs it in Python.
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )

    # Source split: `arxiv` for ArXiv papers, `external` for blog posts,
    # technical reports, model release pages, etc. Existing rows default to
    # `arxiv`. External rows must populate `source_url`; ArXiv rows leave it
    # NULL and continue to derive their URLs from `arxiv_id` + `version`.
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="arxiv", server_default="arxiv"
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)

    # ArXiv information with versioning support. `arxiv_id` is NULL for
    # `source='external'` rows and required for `source='arxiv'` rows
    # (enforced by `papers_source_identifier_check`).
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    version: Mapped[str] = mapped_column(String(10), default="v1")
    is_latest_version: Mapped[bool] = mapped_column(Boolean, default=True)

    # Publication information
    date_published: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    proceeding: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    conference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    conference_url_abs: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    conference_url_pdf: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # Citation and importance metrics
    citation_count: Mapped[int] = mapped_column(Integer, default=0)
    semantic_scholar_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    citation_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ArXiv category classification
    primary_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    all_categories: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )

    # URL extraction tracking
    urls_extracted: Mapped[bool] = mapped_column(Boolean, default=False)

    # References-based method tagging tracking. NULL means the references-based
    # cron has never processed this paper; populated rows are skipped.
    methods_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Optional explicit thumbnail URL. ArXiv rows usually leave this NULL and
    # derive thumbnails from arxiv_id/version; external rows can point at a
    # captured source-page thumbnail.
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Frontend v2 schema additions (PLAN.md §11). Schema-only; no data ingestion in this migration.
    # tldr      -> AI-generated summary surfaced in PaperDetailView "TL;DR" panel.
    # num_pages -> source PDF page count; not surfaced in UI yet.
    tldr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    num_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Hugging Face artifact URLs explicitly linked to this paper. External rows
    # need these because they have no reliable arxiv_id. ArXiv rows usually
    # derive artifacts from arxiv_id, but retain curated URLs when an external
    # release is later canonicalized onto an ArXiv paper.
    hf_models: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    hf_datasets: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    hf_spaces: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)

    # Composite trending score (GitHub star velocity + Hugging Face artifact
    # trending). Computed by the calculate_paper_trending_scores cron and only
    # consumed for ranking when PWC_TRENDING_RANKING_MODE=composite. The
    # GitHub-only path keeps reading repositories.trending_score, so this column
    # can stay populated-but-unused for an instant rollback.
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    trending_score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Normalized 0-1.5 components retained for debugging odd rankings.
    github_trending_component: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    hf_trending_component: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    # When this paper was last scanned for linked Hugging Face artifacts.
    hf_artifacts_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    authors: Mapped[List["Author"]] = relationship(
        "Author", secondary="paper_authors", back_populates="papers"
    )
    tasks: Mapped[List["Task"]] = relationship(
        "Task", secondary="paper_tasks", back_populates="papers"
    )
    methods: Mapped[List["Method"]] = relationship(
        "Method", secondary="paper_methods", back_populates="papers"
    )
    datasets: Mapped[List["Dataset"]] = relationship(
        "Dataset", secondary="paper_datasets", back_populates="papers"
    )
    repositories: Mapped[List["Repository"]] = relationship(
        "Repository", secondary="paper_repositories", back_populates="papers"
    )
    project_pages: Mapped[List["ProjectPage"]] = relationship(
        "ProjectPage", secondary="paper_project_pages", back_populates="papers"
    )
    conferences: Mapped[List["Conference"]] = relationship(
        "Conference", secondary="paper_conferences", back_populates="papers"
    )
    organizations: Mapped[List["Organization"]] = relationship(
        "Organization", secondary="paper_organizations", back_populates="papers"
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="paper"
    )
    hf_artifacts: Mapped[List["HfArtifact"]] = relationship(
        "HfArtifact", secondary="paper_hf_artifacts", back_populates="papers"
    )

    # Constraints
    __table_args__ = (
        # Partial unique indexes replace the prior `(arxiv_id, version)` UNIQUE
        # constraint so external rows can omit ArXiv identifiers.
        Index(
            "uq_papers_arxiv_id_version_when_present",
            "arxiv_id",
            "version",
            unique=True,
            postgresql_where=text("arxiv_id IS NOT NULL"),
        ),
        Index(
            "uq_papers_source_url_external",
            "source_url",
            unique=True,
            postgresql_where=text("source = 'external' AND source_url IS NOT NULL"),
        ),
        CheckConstraint(
            "source IN ('arxiv', 'external')",
            name="papers_source_check",
        ),
        CheckConstraint(
            "(source = 'arxiv' AND arxiv_id IS NOT NULL) "
            "OR (source = 'external' AND source_url IS NOT NULL)",
            name="papers_source_identifier_check",
        ),
        Index("idx_papers_arxiv_id", "arxiv_id"),
        Index("idx_papers_source", "source"),
        Index("idx_papers_date_published", "date_published"),
        Index("idx_papers_conference", "conference"),
        Index("idx_papers_title_search", "title"),  # For text search
        Index("idx_papers_latest_version", "is_latest_version"),
        Index("idx_papers_citation_count", "citation_count"),
        Index("idx_papers_semantic_scholar_id", "semantic_scholar_id"),
        Index("idx_papers_primary_category", "primary_category"),
        Index("idx_papers_urls_extracted", "urls_extracted"),
        Index(
            "idx_papers_methods_scanned_at",
            "methods_scanned_at",
            postgresql_where=text("methods_scanned_at IS NULL"),
        ),
        Index("idx_papers_trending_score", "trending_score"),
        Index("idx_papers_trending_score_updated_at", "trending_score_updated_at"),
        Index("idx_papers_hf_artifacts_scanned_at", "hf_artifacts_scanned_at"),
    )

    def __repr__(self) -> str:
        return f"<Paper(id={self.id}, arxiv_id='{self.arxiv_id}', version='{self.version}', title='{self.title[:50]}...')>"


class Author(Base):
    """
    Author model with Hugging Face integration.
    """

    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Hugging Face integration
    hf_username: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    hf_id: Mapped[Optional[str]] = mapped_column(String(50), unique=True, nullable=True)
    hf_avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hf_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hf_is_pro: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_authors", back_populates="authors"
    )

    # Indexes
    __table_args__ = (
        Index("idx_authors_hf_username", "hf_username"),
        Index("idx_authors_hf_id", "hf_id"),
        Index("idx_authors_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Author(id={self.id}, name='{self.name}', hf_username='{self.hf_username}')>"


class Area(Base):
    """
    Research areas (Vision, Video, Language, Audio, General, Other, etc.).
    """

    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="area")

    def __repr__(self) -> str:
        return f"<Area(id={self.id}, name='{self.name}')>"


class Task(Base):
    """
    AI tasks with hierarchical structure.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    research_trends: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    slug: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Hierarchical structure
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("tasks.id"), nullable=True
    )
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("areas.id"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata columns
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # DB-backed hero image. `image_data` holds the raw bytes and is deferred so
    # list queries never load the (potentially large) blob; `image_mime_type`
    # is small, always loaded, and doubles as the "has a DB image" flag the API
    # layer checks to build the `/api/v1/tasks/{slug}/image` URL.
    image_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    useful_leaderboards: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    parent: Mapped[Optional["Task"]] = relationship(
        "Task", remote_side=[id], back_populates="children"
    )
    children: Mapped[List["Task"]] = relationship(
        "Task", back_populates="parent", overlaps="parent"
    )
    area: Mapped[Optional[Area]] = relationship("Area", back_populates="tasks")
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_tasks", back_populates="tasks"
    )
    datasets: Mapped[List["Dataset"]] = relationship(
        "Dataset", secondary="task_datasets", back_populates="tasks"
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="task"
    )

    # Indexes
    __table_args__ = (
        Index("idx_tasks_parent_id", "parent_id"),
        Index("idx_tasks_area_id", "area_id"),
        Index("idx_tasks_slug", "slug"),
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, name='{self.name}', level={self.level})>"


class Method(Base):
    """
    AI methods and techniques.
    """

    __tablename__ = "methods"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )
    slug: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Area assignment (methods belong to one area)
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("areas.id"), nullable=True
    )

    introduced_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    code_snippet_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # DB-backed figure (see Task.image_data for the deferred/flag rationale).
    image_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    collection_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    collection_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collection_parent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    area: Mapped[Optional[Area]] = relationship("Area")
    source_paper: Mapped[Optional[Paper]] = relationship("Paper")
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_methods", back_populates="methods"
    )

    __table_args__ = (Index("idx_methods_source_paper_id", "source_paper_id"),)

    def __repr__(self) -> str:
        return f"<Method(id={self.id}, name='{self.name}')>"


class Dataset(Base):
    """
    Benchmark datasets.
    """

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )
    slug: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Additional metadata from PapersWithCode
    short_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    homepage: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Dataset hierarchy and variants
    parent_dataset_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True
    )
    variant_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    split_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Image/media URLs
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    verified_image_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # Paper reference (the paper that introduced this dataset)
    introducing_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    introducing_paper_title: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    paper_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Licensing information
    license_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    license_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Introduction date/year
    introduced_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    introduced_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # JSONB fields for arrays
    modalities: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # e.g., ["Images", "Videos"]
    languages: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # e.g., ["English", "Chinese"]
    variants: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # e.g., ["COCO test-dev", "COCO 2017"]

    # Usage count
    num_papers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Warning/notes
    warning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # PWC source URL
    pwc_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_datasets", back_populates="datasets"
    )
    tasks: Mapped[List[Task]] = relationship(
        "Task", secondary="task_datasets", back_populates="datasets"
    )
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="dataset"
    )

    # Self-referential relationship for parent datasets
    parent_dataset: Mapped[Optional["Dataset"]] = relationship(
        "Dataset", remote_side=[id], foreign_keys=[parent_dataset_id]
    )

    def __repr__(self) -> str:
        return f"<Dataset(id={self.id}, name='{self.name}')>"


class Repository(Base):
    """
    GitHub repositories (normalized, no direct paper relationship).

    This table stores unique repositories. The relationship to papers
    is handled through the PaperRepository junction table.

    Note: is_official is now stored in the PaperRepository junction table
    since repositories can have different official status for different papers.
    """

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    num_stars: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(50), default="unknown")

    # Trending metrics (EMA-based)
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, comment="EMA trending score (stars/hour)"
    )
    trending_score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    num_stars_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Many-to-many relationship with papers through PaperRepository
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_repositories", back_populates="repositories"
    )

    # One-to-many relationship with star history
    star_history: Mapped[List["RepositoryStarHistory"]] = relationship(
        "RepositoryStarHistory",
        back_populates="repository",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("idx_repositories_url", "url"),
        Index("idx_repositories_stars", "num_stars"),
        Index("idx_repositories_owner", "owner"),
        Index("idx_repositories_name", "name"),
        Index("idx_repositories_source", "source"),
        Index("idx_repositories_num_stars_updated_at", "num_stars_updated_at"),
        Index("idx_repositories_trending_score", "trending_score"),
        Index(
            "idx_repositories_trending_score_updated_at", "trending_score_updated_at"
        ),
        Index("idx_repositories_created_at", "created_at"),
        Index("idx_repositories_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Repository(id={self.id}, url='{self.url}', stars={self.num_stars})>"


class RepositoryStarHistory(Base):
    """
    Repository star history model for tracking GitHub star counts over time.

    This enables trending metrics by storing historical snapshots of star counts.
    """

    __tablename__ = "repository_star_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    num_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="star_history"
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("repository_id", "snapshot_at", name="uq_repo_snapshot_time"),
        Index("idx_star_history_repository_id", "repository_id"),
        Index("idx_star_history_snapshot_at", "snapshot_at"),
        Index("idx_star_history_repo_time", "repository_id", "snapshot_at"),
    )

    def __repr__(self) -> str:
        return f"<RepositoryStarHistory(id={self.id}, repository_id={self.repository_id}, stars={self.num_stars}, snapshot_at='{self.snapshot_at}')>"


class HfArtifact(Base):
    """
    Normalized Hugging Face artifact (model, dataset, or space) with Hub
    popularity metrics. The relationship to papers is handled through the
    PaperHfArtifact junction table.

    `trending_score` is the Hugging Face Hub trendingScore (fetched via the
    `expand[]=trendingScore` parameter). These rows feed the composite paper
    trending score; they do not affect the GitHub-only ranking.
    """

    __tablename__ = "hf_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # One of: 'model', 'dataset', 'space'.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Hugging Face repo id, e.g. 'deepseek-ai/DeepSeek-V4-Pro'.
    repo_id: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    likes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    downloads: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_hf_artifacts", back_populates="hf_artifacts"
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('model', 'dataset', 'space')",
            name="hf_artifacts_kind_check",
        ),
        UniqueConstraint("kind", "repo_id", name="uq_hf_artifacts_kind_repo"),
        Index("idx_hf_artifacts_trending_score", "trending_score"),
        Index("idx_hf_artifacts_fetched_at", "fetched_at"),
        Index("idx_hf_artifacts_kind", "kind"),
    )

    def __repr__(self) -> str:
        return (
            f"<HfArtifact(id={self.id}, kind='{self.kind}', "
            f"repo_id='{self.repo_id}', trending_score={self.trending_score})>"
        )


class PaperHfArtifact(Base):
    """Junction table linking papers to Hugging Face artifacts."""

    __tablename__ = "paper_hf_artifacts"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    hf_artifact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hf_artifacts.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_paper_hf_artifacts_paper", "paper_id"),
        Index("idx_paper_hf_artifacts_artifact", "hf_artifact_id"),
    )


class ProjectPage(Base):
    """
    Project pages showcasing paper work - normalized without direct paper reference.
    """

    __tablename__ = "project_pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_official: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Use paper_project_pages.is_official for relationship-specific data
    source: Mapped[str] = mapped_column(String(50), default="unknown")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_project_pages", back_populates="project_pages"
    )

    # Indexes
    __table_args__ = (
        Index("idx_project_pages_url", "url"),
        Index("idx_project_pages_source", "source"),
        Index("idx_project_pages_is_official", "is_official"),
    )

    def __repr__(self) -> str:
        return f"<ProjectPage(id={self.id}, url='{self.url}', official={self.is_official})>"


class PaperProjectPage(Base):
    """
    Junction table for many-to-many relationship between papers and project pages.
    Simplified to only contain the two ID columns as requested.
    """

    __tablename__ = "paper_project_pages"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    project_page_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("project_pages.id", ondelete="CASCADE"), primary_key=True
    )

    # Relationships
    paper: Mapped["Paper"] = relationship("Paper", overlaps="project_pages,papers")
    project_page: Mapped["ProjectPage"] = relationship(
        "ProjectPage", overlaps="papers,project_pages"
    )

    # Indexes
    __table_args__ = (
        Index("idx_paper_project_pages_paper_id", "paper_id"),
        Index("idx_paper_project_pages_project_page_id", "project_page_id"),
    )

    def __repr__(self) -> str:
        return f"<PaperProjectPage(paper_id={self.paper_id}, project_page_id={self.project_page_id})>"


class PaperCurationJob(Base):
    """Durable request for a remote Codex paper-curation Job."""

    __tablename__ = "paper_curation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    paper_route: Mapped[str] = mapped_column(String(255), nullable=False)
    paper_title: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    hf_job_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True
    )
    callback_token_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    thumbnail_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    thumbnail_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_previous_width: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_previous_height: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_generated_width: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_generated_height: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    thumbnail_warnings: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    thumbnail_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    paper: Mapped[Paper] = relationship("Paper")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('add-evals', 'enrich-paper')",
            name="paper_curation_jobs_kind_check",
        ),
        CheckConstraint(
            "status IN ('queued', 'dispatching', 'running', 'completed', 'failed', 'canceled')",
            name="paper_curation_jobs_status_check",
        ),
        CheckConstraint(
            "thumbnail_status IS NULL OR thumbnail_status IN ('queued', 'processing', 'succeeded', 'failed')",
            name="paper_curation_jobs_thumbnail_status_check",
        ),
        Index("idx_paper_curation_jobs_queue", "status", "created_at"),
        Index("idx_paper_curation_jobs_paper", "paper_id", "created_at"),
        Index(
            "idx_paper_curation_jobs_thumbnail_queue",
            "thumbnail_status",
            "thumbnail_requested_at",
        ),
    )


class Evaluation(Base):
    """
    Benchmark evaluation results.
    """

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )

    model_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Optional harness/runtime used to evaluate the model (e.g. "Claude Code",
    # "Terminus"). Some benchmarks like Terminal-Bench are effectively
    # model+harness combinations; this column lets us render them separately
    # from `model_name` instead of cramming both into the model column.
    harness: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    methodology: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)  # JSONB field
    uses_additional_data: Mapped[bool] = mapped_column(Boolean, default=False)
    # Whether the evaluated model is open-source. Defaults to True; closed-source
    # models (proprietary APIs, unreleased flagship LLMs) set this to False so the
    # frontend can optionally hide them based on a per-user preference.
    is_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    best_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    best_metric: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    evaluated_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    external_source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    # Raw number of model parameters for this evaluation row (e.g. 7000000000
    # for a 7B model). Kept on the evaluation rather than baked into
    # `model_name` so future leaderboards can filter / sort by size.
    num_parameters: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Optional link to the Hugging Face model page for the evaluated model
    # (e.g. https://huggingface.co/MiniMaxAI/MiniMax-M3). Stored per evaluation
    # so each leaderboard row can link the model name directly to its HF page.
    hf_model_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    paper: Mapped[Paper] = relationship("Paper", back_populates="evaluations")
    task: Mapped[Task] = relationship("Task", back_populates="evaluations")
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="evaluations")

    # Indexes
    __table_args__ = (
        Index(
            "idx_evaluations_paper_task_dataset", "paper_id", "task_id", "dataset_id"
        ),
        Index("idx_evaluations_best_rank", "best_rank"),
        Index("idx_evaluations_external", "external"),
        Index("idx_evaluations_source_url", "source_url"),
    )

    def __repr__(self) -> str:
        return f"<Evaluation(id={self.id}, paper_id={self.paper_id}, task_id={self.task_id}, dataset_id={self.dataset_id})>"


class EvaluationBadgeTombstone(Base):
    """Durable lookup data for leaderboard badges after an evaluation is deleted."""

    __tablename__ = "evaluation_badge_tombstones"

    evaluation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    paper_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dataset_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    task_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dataset_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_evaluation_badge_tombstones_paper_id", "paper_id"),
        Index(
            "idx_evaluation_badge_tombstones_target",
            "paper_id",
            "task_id",
            "dataset_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            "<EvaluationBadgeTombstone("
            f"evaluation_id={self.evaluation_id}, paper_id={self.paper_id})>"
        )


class CatalogMutationEvent(Base):
    """Append-only audit ledger for covered paper-page catalog mutations."""

    __tablename__ = "catalog_mutation_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_hf_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_username: Mapped[Optional[str]] = mapped_column(String(255))
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    before_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    after_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_environment: Mapped[str] = mapped_column(String(32), nullable=False)
    release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rollback_of_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_mutation_events.id", ondelete="RESTRICT"),
    )
    schema_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('admin', 'contributor')",
            name="catalog_mutation_events_actor_role_check",
        ),
        Index("idx_catalog_mutation_events_actor", "actor_hf_subject", "created_at"),
        Index("idx_catalog_mutation_events_created", "created_at", "id"),
    )


class CatalogMutationIdempotency(Base):
    __tablename__ = "catalog_mutation_idempotency"

    actor_hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_mutation_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CatalogAuditReadProgress(Base):
    __tablename__ = "catalog_audit_read_progress"

    admin_hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    read_through_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Metric(Base):
    """
    Metric definitions with ranking direction and scale.

    Defines evaluation metrics and whether they should rank with higher or lower values as better.
    Also tracks the canonical scale for metric values to help normalize them correctly.

    Examples:
    - Higher is better: AP, accuracy, F1, BLEU
    - Lower is better: WER, error rates, perplexity
    - Scale examples: "0-1" (ratios/decimals), "0-100" (percentages), "unbounded" (loss functions)
    """

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "higher_is_better" or "lower_is_better"
    scale: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., "0-1", "0-100", "percentage", "milliseconds", "unbounded"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Indexes
    __table_args__ = (Index("idx_metrics_name", "name"),)

    def __repr__(self) -> str:
        return f"<Metric(id={self.id}, name={self.name}, direction={self.direction})>"


# Junction tables for many-to-many relationships


class PaperAuthor(Base):
    """Junction table for papers and authors."""

    __tablename__ = "paper_authors"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True
    )
    author_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Indexes
    __table_args__ = (
        Index("idx_paper_authors_paper_id", "paper_id"),
        Index("idx_paper_authors_author_id", "author_id"),
    )


class PaperTask(Base):
    """Junction table for papers and tasks."""

    __tablename__ = "paper_tasks"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    # 'auto' = inserted by keyword matcher (rebuild may delete/re-insert).
    # 'manual' = set via admin API / one-off script (rebuild leaves alone).
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="auto")

    __table_args__ = (
        Index("idx_paper_tasks_paper_id", "paper_id"),
        Index("idx_paper_tasks_task_id", "task_id"),
        Index("idx_paper_tasks_source", "source"),
    )


class PaperMethod(Base):
    """Junction table for papers and methods."""

    __tablename__ = "paper_methods"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("methods.id", ondelete="CASCADE"), primary_key=True
    )

    # Indexes
    __table_args__ = (
        Index("idx_paper_methods_paper_id", "paper_id"),
        Index("idx_paper_methods_method_id", "method_id"),
    )


class PaperMethodEvidence(Base):
    """Auditable evidence for one paper-method association."""

    __tablename__ = "paper_method_evidence"

    paper_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    method_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evidence_type: Mapped[str] = mapped_column(String(24), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["paper_id", "method_id"],
            ["paper_methods.paper_id", "paper_methods.method_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "evidence_type IN "
            "('source', 'keyword', 'reference', 'manual', 'legacy_unknown')",
            name="paper_method_evidence_type_check",
        ),
        Index("idx_paper_method_evidence_method_type", "method_id", "evidence_type"),
    )


class PaperMethodExclusion(Base):
    """Durable curator veto against automated paper-method linking."""

    __tablename__ = "paper_method_exclusions"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("methods.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_paper_method_exclusions_method", "method_id", "paper_id"),
    )


class MethodReferenceBackfillMonth(Base):
    """Resumable reference-scan coverage for one method and publication month."""

    __tablename__ = "method_reference_backfill_months"

    method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("methods.id", ondelete="CASCADE"), primary_key=True
    )
    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    eligible_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unresolvable_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retryable_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_published_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    cursor_paper_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'failed')",
            name="method_reference_backfill_months_status_check",
        ),
        Index("idx_method_reference_backfill_status", "status", "updated_at"),
    )


class MethodKeywordBackfillRun(Base):
    """Versioned, resumable cursor for catalog-wide keyword matching."""

    __tablename__ = "method_keyword_backfill_runs"

    keyword_catalog_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    eligible_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_papers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cursor_paper_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'failed')",
            name="method_keyword_backfill_runs_status_check",
        ),
        Index(
            "uq_method_keyword_backfill_one_running",
            "status",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )


class PaperDataset(Base):
    """Junction table for papers and datasets."""

    __tablename__ = "paper_datasets"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )

    # Indexes
    __table_args__ = (
        Index("idx_paper_datasets_paper_id", "paper_id"),
        Index("idx_paper_datasets_dataset_id", "dataset_id"),
    )


class PaperRepository(Base):
    """Junction table for papers and repositories (many-to-many relationship)."""

    __tablename__ = "paper_repositories"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)

    # Indexes
    __table_args__ = (
        Index("idx_paper_repositories_paper_id", "paper_id"),
        Index("idx_paper_repositories_repository_id", "repository_id"),
    )


class Conference(Base):
    """Normalized conference metadata (CVPR, ICCV, NeurIPS, etc.)."""

    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DB-backed hero image (see Task.image_data for the deferred/flag rationale).
    image_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    image_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tier: Mapped[Optional[str]] = mapped_column(String(1), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_conferences", back_populates="conferences"
    )
    deadlines: Mapped[List["ConferenceDeadline"]] = relationship(
        "ConferenceDeadline",
        back_populates="conference",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_conferences_slug", "slug"),
        Index("idx_conferences_year", "year"),
    )

    def __repr__(self) -> str:
        return f"<Conference(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class ConferenceDeadline(Base):
    """A submission/abstract/rebuttal deadline for a conference instance."""

    __tablename__ = "conference_deadlines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conference_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conferences.id", ondelete="CASCADE"),
        nullable=False,
    )
    deadline_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    timezone: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conference: Mapped["Conference"] = relationship(
        "Conference", back_populates="deadlines"
    )

    __table_args__ = (
        Index("idx_conference_deadlines_conference_id", "conference_id"),
        Index("idx_conference_deadlines_deadline_at", "deadline_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ConferenceDeadline(id={self.id}, "
            f"conference_id={self.conference_id}, type='{self.deadline_type}')>"
        )


class PaperConference(Base):
    """Junction table linking papers to conferences."""

    __tablename__ = "paper_conferences"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    conference_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conferences.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    award: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("idx_paper_conferences_conference_id", "conference_id"),
        Index("idx_paper_conferences_paper_id", "paper_id"),
        Index(
            "idx_paper_conferences_award",
            "conference_id",
            "award",
            postgresql_where=text("award IS NOT NULL"),
        ),
    )


class Organization(Base):
    """Normalized organization metadata (NVIDIA, Google, Meta, etc.).

    Organizations are sourced primarily from Hugging Face org profiles
    (``hf_url``) and used to tag papers by the lab/company behind them.
    """

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    hf_slug: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    logo_data: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    logo_mime_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    logo_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    display_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_hf_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hf_paper_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trending_score: Mapped[Optional[float]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    trending_score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    papers: Mapped[List["Paper"]] = relationship(
        "Paper", secondary="paper_organizations", back_populates="organizations"
    )

    trending_history: Mapped[List["OrganizationTrendingHistory"]] = relationship(
        "OrganizationTrendingHistory",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_organizations_slug", "slug"),
        Index(
            "uq_organizations_hf_slug",
            "hf_slug",
            unique=True,
            postgresql_where=text("hf_slug IS NOT NULL"),
        ),
        Index(
            "idx_organizations_featured_trending",
            "is_featured",
            text("trending_score DESC"),
        ),
        Index("idx_organizations_featured_order", "is_featured", "display_order"),
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class PaperOrganization(Base):
    """Junction table linking papers to organizations."""

    __tablename__ = "paper_organizations"

    paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    added_by_hf_subject: Mapped[Optional[str]] = mapped_column(String(255))
    added_by_hf_username: Mapped[Optional[str]] = mapped_column(String(255))

    __table_args__ = (
        Index("idx_paper_organizations_organization_id", "organization_id"),
        Index("idx_paper_organizations_paper_id", "paper_id"),
    )


class OrganizationTrendingHistory(Base):
    """One raw daily organization-momentum snapshot."""

    __tablename__ = "organization_trending_history"

    organization_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    raw_score: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="trending_history"
    )


class PaperRelation(Base):
    """Directed lineage edges between papers.

    ``source_paper_id`` is the predecessor (earlier) paper; ``target_paper_id``
    is the successor (follow-up) paper. The relation is many-to-many in both
    directions: a paper can have multiple successors and multiple predecessors.
    """

    __tablename__ = "paper_relations"

    source_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    target_paper_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "source_paper_id <> target_paper_id",
            name="paper_relations_no_self_link",
        ),
        Index("idx_paper_relations_source_paper_id", "source_paper_id"),
        Index("idx_paper_relations_target_paper_id", "target_paper_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<PaperRelation(source_paper_id={self.source_paper_id}, "
            f"target_paper_id={self.target_paper_id})>"
        )


class TaskSisterTask(Base):
    """Explicit, ordered sister-task relationships for a task page.

    ``task_id`` is the task whose page renders the sister list;
    ``sister_task_id`` is a task shown in that page's sister-task sidebar,
    sorted by ``display_order``. The relation is directed and not
    automatically symmetric. A self-edge is forbidden via CHECK constraint.
    """

    __tablename__ = "task_sister_tasks"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    sister_task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "task_id <> sister_task_id",
            name="task_sister_tasks_no_self_link",
        ),
        Index("idx_task_sister_tasks_task_id", "task_id"),
        Index("idx_task_sister_tasks_sister_task_id", "sister_task_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<TaskSisterTask(task_id={self.task_id}, "
            f"sister_task_id={self.sister_task_id}, "
            f"display_order={self.display_order})>"
        )


class TaskRecommendedFramework(Base):
    """Ordered repositories recommended as starting points for a task."""

    __tablename__ = "task_recommended_frameworks"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    repository_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_task_recommended_frameworks_task_id", "task_id"),
        Index(
            "idx_task_recommended_frameworks_repository_id",
            "repository_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TaskRecommendedFramework(task_id={self.task_id}, "
            f"repository_id={self.repository_id}, "
            f"display_order={self.display_order})>"
        )


class FrameworkDomain(Base):
    """Top-level grouping on the framework catalogue."""

    __tablename__ = "framework_domains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class FrameworkCategory(Base):
    """Ordered framework category within a domain."""

    __tablename__ = "framework_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("framework_domains.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    guide_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    guide_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "domain_id", "slug", name="framework_categories_domain_slug_key"
        ),
        Index("idx_framework_categories_domain_id", "domain_id"),
    )


class Framework(Base):
    """First-class software framework with canonical paper and repository."""

    __tablename__ = "frameworks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("framework_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    introducing_paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_use: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    docs_url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_frameworks_category_id", "category_id"),
        Index("idx_frameworks_repository_id", "repository_id"),
        Index("idx_frameworks_introducing_paper_id", "introducing_paper_id"),
    )


class FrameworkPlatform(Base):
    """Hardware platform supported by a framework."""

    __tablename__ = "framework_platforms"

    framework_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("frameworks.id", ondelete="CASCADE"), primary_key=True
    )
    platform: Mapped[str] = mapped_column(String(20), primary_key=True)

    __table_args__ = (
        CheckConstraint(
            "platform IN ('gpu', 'cpu', 'apple')",
            name="framework_platforms_platform_check",
        ),
    )


class TaskFramework(Base):
    """Ordered first-class framework recommendations for a task."""

    __tablename__ = "task_frameworks"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    framework_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("frameworks.id", ondelete="CASCADE"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_task_frameworks_task_id", "task_id"),
        Index("idx_task_frameworks_framework_id", "framework_id"),
    )


class TaskDataset(Base):
    """
    Task-specific dataset membership and display metadata.

    Leaderboard metric definitions remain in TaskDatasetMetric; this table stores
    one row per task-benchmark pair so display metadata cannot conflict across
    multiple metrics.
    """

    __tablename__ = "task_datasets"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )
    supports_harness: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_task_datasets_task_id", "task_id"),
        Index("idx_task_datasets_dataset_id", "dataset_id"),
    )


class TaskDatasetMetric(Base):
    """
    Junction table for task-dataset-metric triples (leaderboard definitions).

    Each triple (task, dataset, metric) defines a unique leaderboard.
    For example: (Image Classification, ImageNet, Top-1 Accuracy)
    """

    __tablename__ = "task_dataset_metrics"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )
    metric_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("metrics.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Indexes
    __table_args__ = (
        Index("idx_task_dataset_metrics_task_id", "task_id"),
        Index("idx_task_dataset_metrics_dataset_id", "dataset_id"),
        Index("idx_task_dataset_metrics_metric_id", "metric_id"),
        Index("idx_task_dataset_metrics_task_dataset", "task_id", "dataset_id"),
    )


class UserBookmark(Base):
    """Per-HF-user paper bookmarks.

    Keyed on the HF username carried in the ``pwc_session`` JWT (see
    ``backend.routers.auth``). Rows are removed via ``ON DELETE CASCADE`` when
    the underlying paper is deleted.
    """

    __tablename__ = "user_bookmarks"

    hf_username: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False
    )
    paper_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("papers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_user_bookmarks_user", "hf_username"),
        Index("idx_user_bookmarks_paper", "paper_id"),
    )

    def __repr__(self) -> str:
        return f"<UserBookmark(hf_username='{self.hf_username}', paper_id={self.paper_id})>"


class ChatSession(Base):
    """Durable user-owned research chat metadata and generation lease."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    hf_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    hf_username: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="New chat"
    )
    title_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    title_source: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    title_generation_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    title_prompt_revision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    selected_model: Mapped[str] = mapped_column(String(255), nullable=False)
    execution_backend: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="local_mcp"
    )
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="claude"
    )
    web_search_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    active_turn_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    active_turn_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sdk_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True, unique=True
    )
    sdk_project_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transcript_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    transcript_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    projection_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )

    messages: Mapped[list["ChatMessageRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    share: Mapped[Optional["ChatShare"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    sandbox_lease: Mapped[Optional["ChatSandboxLease"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    __table_args__ = (
        CheckConstraint(
            "execution_backend IN ('local_mcp', 'modal_cli')",
            name="chat_sessions_execution_backend_check",
        ),
        CheckConstraint(
            "agent_harness IN ('claude', 'pi')",
            name="chat_sessions_agent_harness_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','high','max')",
            name="chat_sessions_reasoning_effort_check",
        ),
        Index(
            "idx_chat_sessions_owner_updated",
            "hf_user_id",
            text("updated_at DESC"),
            text("id DESC"),
        ),
        Index(
            "idx_chat_sessions_owner_active_updated",
            "hf_user_id",
            text("updated_at DESC"),
            text("id DESC"),
            postgresql_where=text("archived_at IS NULL"),
        ),
    )


class ChatMessageRecord(Base):
    """Sanitized UI projection for one durable user or assistant message."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    paper_mentions: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    effective_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    langfuse_trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    client_message_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    web_search_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    supersedes_message_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    sdk_resume_boundary_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    agent_resume_boundary_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_harness: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    followups: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    display_blocks: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    model_route: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    app_release_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sandbox_image_version: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    worker_contract_version: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    pwc_cli_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    system_prompt_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    finish_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    prepared_fork_sdk_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    prepared_fork_sdk_project_key: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')", name="chat_messages_role_check"
        ),
        CheckConstraint(
            "agent_harness IS NULL OR agent_harness IN ('claude', 'pi')",
            name="chat_messages_agent_harness_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','high','max')",
            name="chat_messages_reasoning_effort_check",
        ),
        CheckConstraint(
            "(prepared_fork_sdk_session_id IS NULL) = "
            "(prepared_fork_sdk_project_key IS NULL)",
            name="chat_messages_prepared_fork_pair_check",
        ),
        UniqueConstraint(
            "session_id", "sequence", name="uq_chat_messages_session_sequence"
        ),
        Index("idx_chat_messages_session_turn", "session_id", "turn_id"),
        Index(
            "idx_chat_messages_client_id",
            "session_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
        Index(
            "idx_chat_messages_current_revision",
            "session_id",
            "turn_id",
            unique=True,
            postgresql_where=text("role = 'user' AND status <> 'superseded'"),
        ),
    )


class ChatShare(Base):
    """Stable public capability and self-contained public transcript snapshot."""

    __tablename__ = "chat_shares"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    snapshot_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="1"
    )
    messages: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[ChatSession] = relationship(back_populates="share")
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(messages) = 'array'",
            name="chat_shares_messages_array_check",
        ),
    )


class ChatSandboxLease(Base):
    """Durable ownership and recoverable state for one per-chat sandbox."""

    __tablename__ = "chat_sandbox_leases"

    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    modal_sandbox_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    image_version: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    worker_generation: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="starting"
    )
    lease_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    workspace_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    snapshot_image_version: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    snapshot_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    workspace_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    session: Mapped[ChatSession] = relationship(back_populates="sandbox_lease")
    __table_args__ = (
        CheckConstraint(
            "state IN ('starting','ready','busy','idle','terminating','terminated','failed')",
            name="chat_sandbox_leases_state_check",
        ),
        Index("idx_chat_sandbox_leases_state_activity", "state", "last_activity_at"),
    )


class ChatSandboxPool(Base):
    """Auditable lifecycle for one unassigned blank chat sandbox."""

    __tablename__ = "chat_sandbox_pool"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    modal_sandbox_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, unique=True
    )
    state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="starting"
    )
    image_version: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="generic"
    )
    agent_harness_version: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="generic"
    )
    model_profile: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="generic"
    )
    reasoning_profile: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="generic"
    )
    prompt_digest: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="generic"
    )
    provider_adapter_contract: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="generic"
    )
    worker_generation: Mapped[str] = mapped_column(String(64), nullable=False)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    claim_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    claim_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terminated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    cpu_request: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    cpu_limit: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    memory_request_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_limit_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    blank_billable_seconds: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    estimated_blank_cost_usd: Mapped[float] = mapped_column(
        Numeric(14, 6), nullable=False, server_default="0"
    )
    billing_month: Mapped[date] = mapped_column(Date, nullable=False)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_health_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "state IN "
            "('starting','blank_ready','claimed','draining','terminated','failed')",
            name="chat_sandbox_pool_state_check",
        ),
        CheckConstraint(
            "cpu_request > 0 AND cpu_limit >= cpu_request",
            name="chat_sandbox_pool_cpu_check",
        ),
        CheckConstraint(
            "memory_request_mib > 0 AND memory_limit_mib >= memory_request_mib",
            name="chat_sandbox_pool_memory_check",
        ),
        Index(
            "idx_chat_sandbox_pool_claim",
            "state",
            "image_version",
            "worker_contract_version",
            "app_release_id",
            "expires_at",
            "ready_at",
        ),
        Index("idx_chat_sandbox_pool_billing", "billing_month", "state"),
    )


class ChatSandboxComputeInterval(Base):
    """Append-only billing lifecycle for one provider sandbox instance."""

    __tablename__ = "chat_sandbox_compute_intervals"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    modal_sandbox_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    modal_app: Mapped[str] = mapped_column(String(255), nullable=False)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    image_version: Mapped[str] = mapped_column(String(255), nullable=False)
    worker_generation: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(24), nullable=False)
    chat_session_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=True))
    cpu_request_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    cpu_limit_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_request_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_limit_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    provider_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    termination_requested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    terminal_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    accrued_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    terminal_reason: Mapped[Optional[str]] = mapped_column(String(64))
    reconciliation_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="local"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "origin IN ('blank_pool','direct','qualification','reconciled_orphan')",
            name="chat_sandbox_compute_origin_check",
        ),
        CheckConstraint(
            "accrued_microusd >= 0 AND reserved_microusd >= 0",
            name="chat_sandbox_compute_cost_check",
        ),
        Index(
            "idx_chat_sandbox_compute_cycle_live",
            "environment",
            "billing_cycle",
            "terminal_at",
        ),
    )


class ChatSandboxBudgetState(Base):
    """One durable, worker-shared sandbox spend circuit per billing cycle."""

    __tablename__ = "chat_sandbox_budget_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    warning_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    application_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    environment_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workspace_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    estimated_accrued_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    provider_floor_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    outstanding_reservation_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="armed"
    )
    trip_reason: Mapped[Optional[str]] = mapped_column(String(64))
    tripped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_metered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_reconciled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    last_reconciliation_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    reconciliation_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="unavailable"
    )
    policy_attestation: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment", "billing_cycle", name="uq_chat_sandbox_budget_cycle"
        ),
        CheckConstraint(
            "circuit_state IN ('armed','warning','tripped')",
            name="chat_sandbox_budget_state_check",
        ),
    )


class ChatSandboxCircuitEvent(Base):
    """Content-free immutable circuit transition and alert-delivery record."""

    __tablename__ = "chat_sandbox_circuit_events"
    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sandbox_budget_states.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, server_default="{}"
    )
    delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    next_delivery_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    fallback_delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    fallback_delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    fallback_next_delivery_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    fallback_delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        Index(
            "idx_chat_sandbox_circuit_events_recent", "budget_state_id", "created_at"
        ),
    )


class ChatTitleBudgetState(Base):
    """Environment-isolated monthly circuit for server-funded chat titles."""

    __tablename__ = "chat_title_budget_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    warning_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    application_cap_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    spent_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="armed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment", "billing_cycle", name="uq_chat_title_budget_cycle"
        ),
        CheckConstraint(
            "spent_microusd >= 0 AND reserved_microusd >= 0 "
            "AND circuit_state IN ('armed','warning','tripped')",
            name="chat_title_budget_state_check",
        ),
    )


class ChatTitleProviderCall(Base):
    """Idempotent reservation and settlement for one title-generation attempt."""

    __tablename__ = "chat_title_provider_calls"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_title_budget_states.id"), nullable=False
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(BigInteger)
    input_tokens: Mapped[Optional[int]] = mapped_column(BigInteger)
    output_tokens: Mapped[Optional[int]] = mapped_column(BigInteger)
    provider_generation_id: Mapped[Optional[str]] = mapped_column(Text)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved','dispatched','settled','released')",
            name="chat_title_provider_calls_state_check",
        ),
        CheckConstraint(
            "reserved_microusd >= 0 AND "
            "(actual_microusd IS NULL OR actual_microusd >= 0) AND "
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0)",
            name="chat_title_provider_calls_nonnegative_check",
        ),
        Index(
            "idx_chat_title_calls_cycle",
            "environment",
            "billing_cycle",
            "state",
        ),
    )


class ChatTitleBudgetEvent(Base):
    """Content-free title-circuit transition and alert-delivery record."""

    __tablename__ = "chat_title_budget_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_title_budget_states.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, server_default="{}"
    )
    delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    fallback_delivery_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "budget_state_id", "event_type", name="uq_chat_title_budget_event"
        ),
        Index("idx_chat_title_budget_events_delivery", "delivery_state", "created_at"),
    )


class ChatTurnLatency(Base):
    """Content-free latency telemetry for one admitted staging chat turn."""

    __tablename__ = "chat_turn_latency"

    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    traffic_class: Mapped[str] = mapped_column(String(24), nullable=False)
    execution_backend: Mapped[str] = mapped_column(String(24), nullable=False)
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="claude"
    )
    pi_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_semantic_event_class: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True
    )
    acquisition_outcome: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="pending"
    )
    model_route: Mapped[str] = mapped_column(String(255), nullable=False)
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sandbox_image_version: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    worker_contract_version: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    pwc_cli_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    system_prompt_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    qualification_run_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    qualification_scenario: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    sandbox_cpu_request: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 3), nullable=True
    )
    sandbox_memory_request_mib: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    estimated_active_cost_usd: Mapped[Optional[float]] = mapped_column(
        Numeric(14, 8), nullable=True
    )

    acquisition_started_ms: Mapped[Optional[int]] = mapped_column(Integer)
    pool_lookup_completed_ms: Mapped[Optional[int]] = mapped_column(Integer)
    modal_sandbox_created_ms: Mapped[Optional[int]] = mapped_column(Integer)
    worker_control_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    session_assignment_completed_ms: Mapped[Optional[int]] = mapped_column(Integer)
    broker_capability_installed_ms: Mapped[Optional[int]] = mapped_column(Integer)
    sdk_query_dispatched_ms: Mapped[Optional[int]] = mapped_column(Integer)
    provider_gateway_received_ms: Mapped[Optional[int]] = mapped_column(Integer)
    control_connection_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_spawn_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_startup_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    session_bind_restore_ms: Mapped[Optional[int]] = mapped_column(Integer)
    resource_loading_ms: Mapped[Optional[int]] = mapped_column(Integer)
    agent_session_ready_ms: Mapped[Optional[int]] = mapped_column(Integer)
    upstream_response_headers_ms: Mapped[Optional[int]] = mapped_column(Integer)
    upstream_first_body_byte_ms: Mapped[Optional[int]] = mapped_column(Integer)
    first_worker_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    first_application_sse_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    first_semantic_event_ms: Mapped[Optional[int]] = mapped_column(Integer)
    pool_miss_reason: Mapped[Optional[str]] = mapped_column(String(32))
    session_reuse_cohort: Mapped[Optional[str]] = mapped_column(String(32))
    total_ms: Mapped[Optional[int]] = mapped_column(Integer)

    browser_stream_start_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_visible_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_reasoning_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_tool_call_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_first_answer_delta_ms: Mapped[Optional[int]] = mapped_column(Integer)
    browser_terminal_classification: Mapped[Optional[str]] = mapped_column(
        String(24), nullable=True
    )
    terminal_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="running"
    )
    admitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "traffic_class IN ('new_chat','followup')",
            name="chat_turn_latency_traffic_class_check",
        ),
        CheckConstraint(
            "execution_backend IN ('local_mcp','modal_cli')",
            name="chat_turn_latency_backend_check",
        ),
        CheckConstraint(
            "agent_harness IN ('claude','pi')",
            name="chat_turn_latency_agent_harness_check",
        ),
        CheckConstraint(
            "first_semantic_event_class IS NULL OR "
            "first_semantic_event_class IN ('reasoning','tool','answer')",
            name="chat_turn_latency_semantic_event_check",
        ),
        CheckConstraint(
            "acquisition_outcome IN "
            "('pending','created','reused_session','pool_hit','pool_miss')",
            name="chat_turn_latency_acquisition_check",
        ),
        CheckConstraint(
            "terminal_status IN ('running','complete','stopped','error','interrupted')",
            name="chat_turn_latency_terminal_check",
        ),
        CheckConstraint(
            "browser_terminal_classification IS NULL OR "
            "browser_terminal_classification IN "
            "('complete','stopped','error','network_error','aborted')",
            name="chat_turn_latency_browser_terminal_check",
        ),
        CheckConstraint(
            "qualification_scenario IS NULL OR qualification_scenario IN "
            "('focused_latency','reliability','clean_cancel','forced_failure')",
            name="chat_turn_latency_qualification_scenario_check",
        ),
        Index("idx_chat_turn_latency_admitted", "admitted_at", "turn_id"),
        Index("idx_chat_turn_latency_session", "chat_session_id"),
    )


class ChatTurnCapability(Base):
    """Short-lived authorization and encrypted provider credential."""

    __tablename__ = "chat_turn_capabilities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_harness: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="claude"
    )
    sdk_session_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    owner_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    provider_credential_revision: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    provider_error_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    provider_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    gateway_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    catalog_search_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    web_search_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    web_search_failed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    hf_catalog_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    hf_recursive_list_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "agent_harness IN ('claude','pi')",
            name="chat_turn_capabilities_agent_harness_check",
        ),
        CheckConstraint(
            "provider_mode IS NULL OR provider_mode IN "
            "('huggingface','openrouter_funded','openrouter_byok')",
            name="chat_turn_capabilities_provider_mode_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','high','max')",
            name="chat_turn_capabilities_reasoning_effort_check",
        ),
        Index(
            "idx_chat_turn_capabilities_scope",
            "chat_session_id",
            "turn_id",
            "expires_at",
        ),
    )


class ChatWebSearchBudgetState(Base):
    """UTC-month Exa request budget and fail-closed circuit state."""

    __tablename__ = "chat_web_search_budget_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_cycle: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    warning_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    hard_limit_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    provider_cost_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    last_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_result_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    circuit_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="armed"
    )
    trip_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_provider_error_class: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment", "billing_cycle", name="uq_chat_web_search_budget_cycle"
        ),
        CheckConstraint(
            "circuit_state IN ('armed','warning','cooldown','tripped')",
            name="chat_web_search_budget_circuit_check",
        ),
        CheckConstraint(
            "call_count >= 0 AND success_count >= 0 AND failure_count >= 0 AND "
            "provider_cost_microusd >= 0 AND warning_calls > 0 AND "
            "hard_limit_calls >= warning_calls",
            name="chat_web_search_budget_counts_check",
        ),
    )


class ChatWebSearchCircuitEvent(Base):
    """Content-free operator event for the web-search circuit."""

    __tablename__ = "chat_web_search_circuit_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    budget_state_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_web_search_budget_states.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    error_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        Index("idx_chat_web_search_events_recent", "budget_state_id", "created_at"),
    )


class ChatWebSearchOwnerUsage(Base):
    """Opaque concentration telemetry; never a user-visible allowance."""

    __tablename__ = "chat_web_search_owner_usage"

    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    billing_cycle: Mapped[date] = mapped_column(Date, primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatOpenRouterCredential(Base):
    """Write-only, owner-scoped encrypted OpenRouter inference credential."""

    __tablename__ = "chat_openrouter_credentials"

    hf_user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fallback_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    credential_revision: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatOpenRouterMonthlyUsage(Base):
    """Authoritative funded OpenRouter usage for one HF subject and UTC month."""

    __tablename__ = "chat_openrouter_monthly_usage"

    hf_user_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    limit_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    spent_microusd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    unknown_cost_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "limit_microusd > 0 AND reserved_microusd >= 0 AND "
            "spent_microusd >= 0 AND unknown_cost_calls >= 0",
            name="chat_openrouter_monthly_usage_nonnegative_check",
        ),
    )


class ChatOpenRouterProviderCall(Base):
    """Idempotent funded-provider reservation and trusted settlement ledger."""

    __tablename__ = "chat_openrouter_provider_calls"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    turn_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    call_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    hf_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    month_start: Mapped[date] = mapped_column(Date, nullable=False)
    model_route: Mapped[str] = mapped_column(String(255), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="high"
    )
    upstream_provider: Mapped[Optional[str]] = mapped_column(String(128))
    routing_policy: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="throughput"
    )
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cache_read_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cache_creation_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    provider_ttft_ms: Mapped[Optional[int]] = mapped_column(Integer)
    fallback_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    request_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    system_token_bucket: Mapped[Optional[int]] = mapped_column(Integer)
    tool_token_bucket: Mapped[Optional[int]] = mapped_column(Integer)
    conversation_token_bucket: Mapped[Optional[int]] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    reserved_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_microusd: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    generation_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "state IN ('reserved','dispatched','settled','released','cost_unknown')",
            name="chat_openrouter_provider_calls_state_check",
        ),
        CheckConstraint(
            "reasoning_effort IN ('low','high','max')",
            name="chat_openrouter_provider_calls_reasoning_effort_check",
        ),
        CheckConstraint(
            "reserved_microusd >= 0 AND "
            "(actual_microusd IS NULL OR actual_microusd >= 0)",
            name="chat_openrouter_provider_calls_nonnegative_check",
        ),
        UniqueConstraint(
            "turn_id", "call_sequence", name="uq_chat_openrouter_turn_call"
        ),
        Index(
            "idx_chat_openrouter_calls_owner_month",
            "hf_user_id",
            "month_start",
        ),
        Index("idx_chat_openrouter_calls_state_updated", "state", "updated_at"),
    )


class ChatOpenRouterCredentialAudit(Base):
    """Bounded non-secret credential lifecycle audit event."""

    __tablename__ = "chat_openrouter_credential_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "action IN ('connected','replaced','fallback_enabled',"
            "'fallback_disabled','disconnected','invalidated','account_deleted')",
            name="chat_openrouter_credential_audit_action_check",
        ),
        Index("idx_chat_openrouter_credential_audit_created", "created_at"),
    )


class ChatSDKTranscriptEntry(Base):
    __tablename__ = "chat_sdk_transcript_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_key: Mapped[str] = mapped_column(Text, nullable=False)
    sdk_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    subpath: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    entry_uuid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry: Mapped[dict] = mapped_column(JSONB, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        Index(
            "idx_chat_sdk_entries_load",
            "project_key",
            "sdk_session_id",
            "subpath",
            "id",
        ),
        Index(
            "idx_chat_sdk_entries_uuid",
            "project_key",
            "sdk_session_id",
            "subpath",
            "entry_uuid",
            unique=True,
            postgresql_where=text("entry_uuid IS NOT NULL"),
        ),
    )


class ChatSDKSessionSummary(Base):
    __tablename__ = "chat_sdk_session_summaries"

    project_key: Mapped[str] = mapped_column(Text, primary_key=True)
    sdk_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    mtime: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ChatPiSession(Base):
    """Server-owned index for one opaque native Pi JSONL session."""

    __tablename__ = "chat_pi_sessions"

    agent_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    current_leaf_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    byte_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    format_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "entry_count >= 0 AND byte_size >= 0",
            name="chat_pi_sessions_nonnegative_check",
        ),
        CheckConstraint(
            "format_version = 1", name="chat_pi_sessions_format_version_check"
        ),
    )


class ChatPiTranscriptEntry(Base):
    """One ordered, otherwise opaque Pi session record."""

    __tablename__ = "chat_pi_transcript_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_pi_sessions.agent_session_id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_entry_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entry: Mapped[dict] = mapped_column(JSONB, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "ordinal >= 0 AND byte_size >= 2 AND byte_size <= 1048576",
            name="chat_pi_transcript_entries_bounds_check",
        ),
        UniqueConstraint(
            "agent_session_id",
            "ordinal",
            name="uq_chat_pi_transcript_entries_ordinal",
        ),
        Index(
            "idx_chat_pi_transcript_entries_entry_id",
            "agent_session_id",
            "entry_id",
            unique=True,
            postgresql_where=text("entry_id IS NOT NULL"),
        ),
    )


class ChatPiPreparedFork(Base):
    """Inactive native Pi branch awaiting transactional edit activation."""

    __tablename__ = "chat_pi_prepared_forks"

    fork_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_session_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False)
    boundary_entry_id: Mapped[str] = mapped_column(Text, nullable=False)
    entries: Mapped[list] = mapped_column(JSONB, nullable=False)
    entry_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "entry_count >= 1 AND byte_size >= 2 AND format_version = 1",
            name="chat_pi_prepared_forks_bounds_check",
        ),
        Index("idx_chat_pi_prepared_forks_chat", "chat_session_id"),
    )


class ChatHarnessAssignmentAudit(Base):
    """Content-free audit of protected harness overrides and cutover assignment."""

    __tablename__ = "chat_harness_assignment_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    agent_harness: Mapped[str] = mapped_column(String(16), nullable=False)
    assignment_source: Mapped[str] = mapped_column(String(24), nullable=False)
    operator_subject_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    app_release_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "agent_harness IN ('claude','pi')",
            name="chat_harness_assignment_audit_harness_check",
        ),
        CheckConstraint(
            "assignment_source IN ('default','cutover','admin_override')",
            name="chat_harness_assignment_audit_source_check",
        ),
    )


class UserPreference(Base):
    """Per-HF-user account preferences.

    Keyed on the lowercased HF username carried in the ``pwc_session`` JWT (see
    ``backend.routers.auth``). Written exclusively through the
    ``/api/v1/me/preferences`` endpoints which require the session cookie.
    """

    __tablename__ = "user_preferences"

    hf_username: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False
    )
    # When True, the user hides closed-source model rows (Evaluation.is_open is
    # False) on benchmark leaderboards and paper evaluation tables.
    hide_closed_source_evals: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<UserPreference(hf_username='{self.hf_username}', "
            f"hide_closed_source_evals={self.hide_closed_source_evals})>"
        )


class StagingAccessRequest(Base):
    """Verified Hugging Face accounts requesting contributor access."""

    __tablename__ = "staging_access_requests"

    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    hf_username: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="staging_access_requests_status_check",
        ),
        CheckConstraint(
            "email IS NULL OR email_verified",
            name="staging_access_requests_verified_email_check",
        ),
        Index("idx_staging_access_requests_status_created", "status", "created_at"),
    )


class PendingPaperEdit(Base):
    """Edit submissions from non-admin Hugging Face users.

    Each row records a proposed change to one of the paper-page edit surfaces
    (tasks, methods, evaluation results, GitHub repositories, project pages),
    or an unscoped taxonomy suggestion submitted from a directory page.
    Admin direct edits bypass this table and continue to mutate live data
    through the existing admin endpoints. Approval of a pending row replays
    ``proposed_payload`` through the same backend mutation services.

    ``is_author`` is true when the submitting HF username matched a linked
    author of the paper at submit time. It is informational today and used to
    surface author-originated edits in review; a future change can use it to
    auto-approve without going through admin review.
    """

    __tablename__ = "pending_paper_edits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    paper_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=True,
    )
    hf_username: Mapped[str] = mapped_column(String(255), nullable=False)
    hf_subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_author: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    edit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    proposed_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    current_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    applied_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result_entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    result_entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    catalog_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_mutation_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    conflict_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_by_kind: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reviewed_by_hf_subject: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    review_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    review_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    review_evidence: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "edit_type IN ('tasks', 'methods', 'evaluations', 'repositories', 'project_pages', 'source_url', 'hf_artifacts', 'organizations', 'new_task', 'new_method', 'new_benchmark', 'new_metric', 'new_conference', 'new_external_paper')",
            name="pending_paper_edits_edit_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="pending_paper_edits_status_check",
        ),
        CheckConstraint(
            "reviewed_by_kind IS NULL OR reviewed_by_kind IN ('human', 'codex')",
            name="pending_paper_edits_reviewed_by_kind_check",
        ),
        Index(
            "idx_pending_paper_edits_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "idx_pending_paper_edits_paper_edit_type",
            "paper_id",
            "edit_type",
        ),
        Index("idx_pending_paper_edits_hf_username", "hf_username"),
        Index("idx_pending_paper_edits_hf_subject", "hf_subject", "created_at"),
        Index("idx_pending_paper_edits_source_ip", "source_ip", "created_at"),
        Index(
            "uq_pending_paper_edits_subject_idempotency",
            "hf_subject",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "idx_pending_paper_edits_author_pending",
            "is_author",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PendingPaperEdit(id={self.id}, paper_id={self.paper_id}, "
            f"hf_username='{self.hf_username}', edit_type='{self.edit_type}', "
            f"status='{self.status}')>"
        )


class UserProfile(Base):
    """Stable Hugging Face identity and its current public username."""

    __tablename__ = "user_profiles"

    hf_subject: Mapped[str] = mapped_column(String(255), primary_key=True)
    current_username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    is_submission_suspended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    suspension_reason: Mapped[Optional[str]] = mapped_column(Text)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suspended_by_hf_subject: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserProfileAlias(Base):
    __tablename__ = "user_profile_aliases"

    alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    hf_subject: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("user_profiles.hf_subject", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("idx_user_profile_aliases_subject", "hf_subject"),)
