# PostgreSQL Setup Guide for PapersWithCode

## Table of Contents
1. [Installation](#installation)
2. [Basic PostgreSQL Concepts](#basic-postgresql-concepts)
3. [Getting Started](#getting-started)
4. [Database Design for PapersWithCode](#database-design-for-paperswithcode)
5. [Python Integration](#python-integration)
6. [Docker Setup (Recommended)](#docker-setup-recommended)
7. [Common Operations](#common-operations)
8. [Best Practices](#best-practices)

## Installation

### Option 1: Docker (Recommended for Development)
```bash
# Create a docker-compose.yml file (we'll do this later)
docker-compose up -d postgres
```

### Option 2: Local Installation

#### macOS (using Homebrew)
```bash
brew install postgresql
brew services start postgresql
```

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Windows
Download and install from: https://www.postgresql.org/download/windows/

## Basic PostgreSQL Concepts

### Key Terms
- **Database**: A collection of related tables
- **Table**: Structured data storage (rows and columns)
- **Schema**: A namespace that contains tables, views, functions
- **Primary Key**: Unique identifier for each row
- **Foreign Key**: Reference to a primary key in another table
- **Index**: Data structure that improves query performance

### Data Types (Most Common)
- `INTEGER` / `BIGINT`: Whole numbers
- `VARCHAR(n)`: Variable-length text (up to n characters)
- `TEXT`: Unlimited text
- `TIMESTAMP`: Date and time
- `BOOLEAN`: True/false
- `JSONB`: JSON data (PostgreSQL specific, very useful for our use case)

## Getting Started

### 1. Connect to PostgreSQL

#### Using psql (command line tool)
```bash
# Connect to default database
psql postgres

# Connect to specific database
psql -d paperswithcode -U your_username
```

#### Basic psql Commands
```sql
\l                 -- List all databases
\c database_name   -- Connect to a database
\dt                -- List tables in current database
\d table_name      -- Describe table structure
\q                 -- Quit psql
```

### 2. Create Your First Database
```sql
-- Create database for our project
CREATE DATABASE paperswithcode;

-- Connect to it
\c paperswithcode;

-- Create a simple test table
CREATE TABLE test_papers (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert some test data
INSERT INTO test_papers (title) VALUES ('My First Paper');
INSERT INTO test_papers (title) VALUES ('Another Great Paper');

-- Query the data
SELECT * FROM test_papers;
```

## Database Design for PapersWithCode

Based on your PLAN.md, here's the schema design:

### Core Tables Schema

```sql
-- Authors table
CREATE TABLE authors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Papers table
CREATE TABLE papers (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT,
    arxiv_id VARCHAR(50),
    url VARCHAR(500),
    conference VARCHAR(200),
    year INTEGER,
    proceeding VARCHAR(200),
    date_published DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tasks table (hierarchical structure)
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    parent_id INTEGER REFERENCES tasks(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Methods table
CREATE TABLE methods (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Datasets table
CREATE TABLE datasets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Repositories table
CREATE TABLE repositories (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER REFERENCES papers(id),
    url VARCHAR(500) NOT NULL,
    framework VARCHAR(100),
    stars INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Evaluations table (benchmark results)
CREATE TABLE evaluations (
    id SERIAL PRIMARY KEY,
    paper_id INTEGER REFERENCES papers(id),
    task_id INTEGER REFERENCES tasks(id),
    dataset_id INTEGER REFERENCES datasets(id),
    metrics JSONB, -- Store flexible metric data
    model_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Junction tables for many-to-many relationships
CREATE TABLE paper_authors (
    paper_id INTEGER REFERENCES papers(id),
    author_id INTEGER REFERENCES authors(id),
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE paper_tasks (
    paper_id INTEGER REFERENCES papers(id),
    task_id INTEGER REFERENCES tasks(id),
    PRIMARY KEY (paper_id, task_id)
);

CREATE TABLE paper_methods (
    paper_id INTEGER REFERENCES papers(id),
    method_id INTEGER REFERENCES methods(id),
    PRIMARY KEY (paper_id, method_id)
);

CREATE TABLE paper_datasets (
    paper_id INTEGER REFERENCES papers(id),
    dataset_id INTEGER REFERENCES datasets(id),
    PRIMARY KEY (paper_id, dataset_id)
);
```

### Create Indexes for Performance
```sql
-- Indexes for common queries
CREATE INDEX idx_papers_title ON papers USING gin(to_tsvector('english', title));
CREATE INDEX idx_papers_abstract ON papers USING gin(to_tsvector('english', abstract));
CREATE INDEX idx_papers_year ON papers(year);
CREATE INDEX idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_tasks_parent_id ON tasks(parent_id);
CREATE INDEX idx_evaluations_paper_task ON evaluations(paper_id, task_id);
```

## Python Integration

### 1. Install Required Packages
```bash
pip install psycopg2-binary sqlalchemy alembic python-dotenv
```

### 2. Database Connection Setup

Create `.env` file:
```env
DATABASE_URL=postgresql://username:password@localhost:5432/paperswithcode
```

Basic connection example:
```python
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Create engine
engine = create_engine(os.getenv("DATABASE_URL"))

# Create session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Test connection
def test_connection():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        print(result.fetchone())

if __name__ == "__main__":
    test_connection()
```

### 3. SQLAlchemy Models

Create `models.py`:
```python
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Table, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

# Junction tables
paper_authors = Table(
    'paper_authors', Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id'), primary_key=True),
    Column('author_id', Integer, ForeignKey('authors.id'), primary_key=True)
)

paper_tasks = Table(
    'paper_tasks', Base.metadata,
    Column('paper_id', Integer, ForeignKey('papers.id'), primary_key=True),
    Column('task_id', Integer, ForeignKey('tasks.id'), primary_key=True)
)

class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(Text, nullable=False)
    abstract = Column(Text)
    arxiv_id = Column(String(50))
    url = Column(String(500))
    conference = Column(String(200))
    year = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    authors = relationship("Author", secondary=paper_authors, back_populates="papers")
    tasks = relationship("Task", secondary=paper_tasks, back_populates="papers")
    repositories = relationship("Repository", back_populates="paper")
    evaluations = relationship("Evaluation", back_populates="paper")

class Author(Base):
    __tablename__ = "authors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    papers = relationship("Paper", secondary=paper_authors, back_populates="authors")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey('tasks.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Self-referential relationship for hierarchical tasks
    children = relationship("Task")
    papers = relationship("Paper", secondary=paper_tasks, back_populates="tasks")

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey('papers.id'))
    url = Column(String(500), nullable=False)
    framework = Column(String(100))
    stars = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    paper = relationship("Paper", back_populates="repositories")

class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey('papers.id'))
    task_id = Column(Integer, ForeignKey('tasks.id'))
    dataset_id = Column(Integer, ForeignKey('datasets.id'))
    metrics = Column(JSON)  # Use JSON for flexible metrics
    model_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    paper = relationship("Paper", back_populates="evaluations")
```

### 4. Create Tables with SQLAlchemy
```python
from sqlalchemy import create_engine
from models import Base
import os

engine = create_engine(os.getenv("DATABASE_URL"))

# Create all tables
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
```

### 5. Basic CRUD Operations
```python
from sqlalchemy.orm import sessionmaker
from models import Paper, Author, paper_authors

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_paper_with_author():
    db = SessionLocal()
    try:
        # Create author
        author = Author(name="John Doe")
        db.add(author)
        db.flush()  # Get the ID without committing

        # Create paper
        paper = Paper(
            title="My Amazing AI Paper",
            abstract="This paper presents a novel approach to...",
            arxiv_id="2024.12345",
            year=2024
        )

        # Link author to paper
        paper.authors.append(author)

        db.add(paper)
        db.commit()

        print(f"Created paper: {paper.title} by {author.name}")
        return paper.id

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

def get_papers_with_authors():
    db = SessionLocal()
    try:
        papers = db.query(Paper).join(Paper.authors).all()
        for paper in papers:
            authors = [author.name for author in paper.authors]
            print(f"{paper.title} - Authors: {', '.join(authors)}")
    finally:
        db.close()

if __name__ == "__main__":
    create_paper_with_author()
    get_papers_with_authors()
```

## Docker Setup (Recommended)

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: paperswithcode
      POSTGRES_USER: your_username
      POSTGRES_PASSWORD: your_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init.sql:/docker-entrypoint-initdb.d/init.sql

  pgadmin:
    image: dpage/pgadmin4
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@admin.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "8080:80"
    depends_on:
      - postgres

volumes:
  postgres_data:
```

Start the services:
```bash
docker-compose up -d
```

Access pgAdmin at `http://localhost:8080` (admin@admin.com / admin)

## Common Operations

### Data Migration Script
```python
import json
from sqlalchemy.orm import sessionmaker
from models import Paper, Author, Task

def migrate_papers_data():
    """Migrate data from papers-with-abstracts.json to PostgreSQL"""
    db = SessionLocal()

    # Load your existing JSON data
    with open('data/papers-with-abstracts.json', 'r') as f:
        papers_data = json.load(f)

    try:
        for paper_data in papers_data[:100]:  # Start with first 100 papers
            # Create paper
            paper = Paper(
                title=paper_data.get('title'),
                abstract=paper_data.get('abstract'),
                arxiv_id=paper_data.get('arxiv_id'),
                year=paper_data.get('year')
            )

            # Handle authors
            for author_name in paper_data.get('authors', []):
                # Check if author exists
                author = db.query(Author).filter(Author.name == author_name).first()
                if not author:
                    author = Author(name=author_name)
                    db.add(author)

                paper.authors.append(author)

            db.add(paper)

            if len(db.new) % 10 == 0:  # Commit every 10 papers
                db.commit()
                print(f"Processed {len(db.new)} papers...")

        db.commit()
        print("Migration completed!")

    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
    finally:
        db.close()
```

### Search and Filtering
```python
from sqlalchemy import or_, and_

def search_papers(query, year=None, limit=20):
    db = SessionLocal()
    try:
        papers_query = db.query(Paper)

        # Text search in title and abstract
        if query:
            papers_query = papers_query.filter(
                or_(
                    Paper.title.ilike(f'%{query}%'),
                    Paper.abstract.ilike(f'%{query}%')
                )
            )

        # Year filter
        if year:
            papers_query = papers_query.filter(Paper.year == year)

        papers = papers_query.limit(limit).all()

        return [
            {
                "id": paper.id,
                "title": paper.title,
                "authors": [author.name for author in paper.authors],
                "year": paper.year
            }
            for paper in papers
        ]
    finally:
        db.close()
```

## Best Practices

1. **Use Environment Variables**: Never hardcode database credentials
2. **Connection Pooling**: SQLAlchemy handles this automatically
3. **Transactions**: Use `db.commit()` and `db.rollback()` properly
4. **Indexes**: Create indexes for columns you frequently query
5. **Batch Operations**: Process large datasets in chunks
6. **Connection Management**: Always close database sessions
7. **Error Handling**: Use try/except blocks for database operations

## Next Steps

1. **Set up Docker environment** using the docker-compose.yml
2. **Create the database schema** using the SQL provided
3. **Set up Python environment** with the required packages
4. **Test basic connections** and CRUD operations
5. **Create migration scripts** for your existing JSON data
6. **Implement FastAPI endpoints** that use these database operations

This should give you a solid foundation to start working with PostgreSQL for your PapersWithCode project!