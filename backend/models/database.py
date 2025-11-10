"""
SQLAlchemy database models.

These models represent the database schema and provide ORM functionality
for interacting with the PostgreSQL database.
"""

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Integer,
    BigInteger,
    String,
    Text,
    Date,
    DateTime,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

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

    # ArXiv information with versioning support
    arxiv_id: Mapped[str] = mapped_column(String(50), nullable=False)
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
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="paper"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("arxiv_id", "version", name="uq_paper_arxiv_version"),
        Index("idx_papers_arxiv_id", "arxiv_id"),
        Index("idx_papers_date_published", "date_published"),
        Index("idx_papers_conference", "conference"),
        Index("idx_papers_title_search", "title"),  # For text search
        Index("idx_papers_latest_version", "is_latest_version"),
        Index("idx_papers_citation_count", "citation_count"),
        Index("idx_papers_semantic_scholar_id", "semantic_scholar_id"),
        Index("idx_papers_primary_category", "primary_category"),
        Index("idx_papers_urls_extracted", "urls_extracted"),
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
    Research areas (Computer Vision, NLP, etc.).
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
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    code_snippet_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    image_credit: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
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
    papers: Mapped[List[Paper]] = relationship(
        "Paper", secondary="paper_methods", back_populates="methods"
    )

    def __repr__(self) -> str:
        return f"<Method(id={self.id}, name='{self.name}')>"


class Dataset(Base):
    """
    Benchmark datasets.
    """

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
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
    tasks: Mapped[List["Task"]] = relationship(
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
    methodology: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)  # JSONB field
    uses_additional_data: Mapped[bool] = mapped_column(Boolean, default=False)
    best_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    best_metric: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    evaluated_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    external_source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

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
    )

    def __repr__(self) -> str:
        return f"<Evaluation(id={self.id}, paper_id={self.paper_id}, task_id={self.task_id}, dataset_id={self.dataset_id})>"


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

    # Indexes
    __table_args__ = (
        Index("idx_paper_tasks_paper_id", "paper_id"),
        Index("idx_paper_tasks_task_id", "task_id"),
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


class TaskDataset(Base):
    """Junction table for tasks and datasets (many-to-many relationship)."""

    __tablename__ = "task_datasets"

    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("datasets.id", ondelete="CASCADE"), primary_key=True
    )

    # Indexes
    __table_args__ = (
        Index("idx_task_datasets_task_id", "task_id"),
        Index("idx_task_datasets_dataset_id", "dataset_id"),
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
