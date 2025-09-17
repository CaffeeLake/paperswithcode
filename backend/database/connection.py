"""
SQLAlchemy database connection and session management.

This module provides SQLAlchemy integration for the FastAPI backend,
building on top of the existing psycopg2-based database utilities.
"""

from typing import Generator

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from ..config import get_settings
from ..models.database import Base


class DatabaseManager:
    """
    Database manager for SQLAlchemy integration.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._engine: Engine = None
        self._session_local: sessionmaker = None
    
    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine."""
        if self._engine is None:
            self._engine = create_engine(
                self.settings.database_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=self.settings.is_development  # Log SQL queries in development
            )
        return self._engine
    
    @property
    def session_local(self) -> sessionmaker:
        """Get the session factory."""
        if self._session_local is None:
            self._session_local = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
        return self._session_local
    
    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)
    
    def drop_tables(self):
        """Drop all database tables (use with caution!)."""
        Base.metadata.drop_all(bind=self.engine)
    
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a database session.
        
        This is a generator function that yields a SQLAlchemy session
        and ensures proper cleanup.
        """
        session = self.session_local()
        try:
            yield session
        finally:
            session.close()


# Global database manager instance
db_manager = DatabaseManager()


def get_database_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency for getting database sessions.
    
    Usage in FastAPI endpoints:
    ```python
    @app.get("/papers/")
    def get_papers(db: Session = Depends(get_database_session)):
        return db.query(Paper).all()
    ```
    """
    yield from db_manager.get_session()


def get_engine() -> Engine:
    """Get the SQLAlchemy engine."""
    return db_manager.engine


def create_tables():
    """Create all database tables."""
    db_manager.create_tables()


def drop_tables():
    """Drop all database tables."""
    db_manager.drop_tables()


# Utility functions for testing and development

def reset_database():
    """Reset the database (drop and recreate all tables)."""
    print("⚠️  Resetting database...")
    drop_tables()
    create_tables()
    print("✅ Database reset complete")


def init_database():
    """Initialize the database (create tables if they don't exist)."""
    print("🔧 Initializing database...")
    create_tables()
    print("✅ Database initialized")


if __name__ == "__main__":
    # For testing the database connection
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "init":
            init_database()
        elif command == "reset":
            reset_database()
        elif command == "test":
            print("🔍 Testing database connection...")
            try:
                engine = get_engine()
                with engine.connect() as conn:
                    result = conn.execute("SELECT 1")
                    print("✅ Database connection successful!")
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
        else:
            print("Usage: python -m backend.database.connection [init|reset|test]")
    else:
        print("Database connection module")
        print("Available commands: init, reset, test")
