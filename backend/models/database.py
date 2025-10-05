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

    # Hierarchical structure
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("tasks.id"), nullable=True
    )
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("areas.id"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, default=0)

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
    full_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Area assignment (methods belong to one area)
    area_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("areas.id"), nullable=True
    )

    introduced_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    code_snippet_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    collection_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    collection_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collection_parent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    collection_area: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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
    full_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hf_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

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
    evaluations: Mapped[List["Evaluation"]] = relationship(
        "Evaluation", back_populates="dataset"
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

    # Indexes
    __table_args__ = (
        Index("idx_repositories_url", "url"),
        Index("idx_repositories_stars", "num_stars"),
        Index("idx_repositories_owner", "owner"),
        Index("idx_repositories_name", "name"),
        Index("idx_repositories_source", "source"),
        Index("idx_repositories_num_stars_updated_at", "num_stars_updated_at"),
        Index("idx_repositories_created_at", "created_at"),
        Index("idx_repositories_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Repository(id={self.id}, url='{self.url}', stars={self.num_stars})>"


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
