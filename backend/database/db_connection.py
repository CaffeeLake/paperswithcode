"""
Database connection and management utilities for PapersWithCode.
Provides a centralized way to handle PostgreSQL connections and common operations.
"""

import os
import sys
import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection


logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration management."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "paperswithcode",
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user or os.getenv('USER', 'postgres')
        self.password = password or os.getenv('POSTGRES_PASSWORD', '')
    
    @classmethod
    def from_env(cls) -> 'DatabaseConfig':
        """Create config from environment variables."""
        return cls(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            database=os.getenv('DB_NAME', 'paperswithcode'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
    
    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        return f"postgresql://{self.user}@{self.host}:{self.port}/{self.database}"


class Database:
    """
    Database connection and operations manager.
    Provides a clean interface for database operations with proper connection management.
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        self.config = config or DatabaseConfig()
        self._connection: Optional[connection] = None
    
    def connect(self) -> connection:
        """Establish database connection."""
        if self._connection and not self._connection.closed:
            return self._connection
        
        try:
            self._connection = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                cursor_factory=RealDictCursor
            )
            logger.info(f"Connected to database '{self.config.database}' as user '{self.config.user}'")
            return self._connection
        
        except psycopg2.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.info("Database connection closed")
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = self.connect()
        try:
            yield conn
        finally:
            # Don't close the connection here - let the Database instance manage it
            pass
    
    @contextmanager
    def get_cursor(self, commit: bool = True):
        """Context manager for database cursors with automatic commit/rollback."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                if commit:
                    conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database operation failed, rolled back: {e}")
                raise
            finally:
                cursor.close()
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        with self.get_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def execute_single(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        """Execute a SELECT query and return single result."""
        with self.get_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()
    
    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return affected rows."""
        with self.get_cursor(commit=True) as cursor:
            cursor.execute(query, params)
            return cursor.rowcount
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute a query multiple times with different parameters."""
        with self.get_cursor(commit=True) as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount
    
    def table_exists(self, table_name: str, schema: str = 'public') -> bool:
        """Check if a table exists."""
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            );
        """
        result = self.execute_single(query, (schema, table_name))
        return result['exists'] if result else False
    
    def get_table_info(self, table_name: str, schema: str = 'public') -> List[Dict[str, Any]]:
        """Get column information for a table."""
        query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """
        return self.execute_query(query, (schema, table_name))
    
    def get_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table."""
        query = f"SELECT COUNT(*) as count FROM {table_name};"
        result = self.execute_single(query)
        return result['count'] if result else 0
    
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.get_cursor(commit=False) as cursor:
                cursor.execute("SELECT 1;")
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


class PapersDatabase(Database):
    """
    Specialized database class for papers operations.
    Extends the base Database class with papers-specific methods.
    """
    
    def get_paper_count(self) -> int:
        """Get total number of papers."""
        return self.get_row_count('papers')
    
    def get_latest_paper_date(self):
        """Get the date of the most recent paper."""
        query = "SELECT MAX(date_published) as max_date FROM papers;"
        result = self.execute_single(query)
        return result['max_date'] if result else None
    
    def paper_exists(self, arxiv_id: str, version: str) -> bool:
        """Check if a paper version exists."""
        query = "SELECT 1 FROM papers WHERE arxiv_id = %s AND version = %s LIMIT 1;"
        result = self.execute_single(query, (arxiv_id, version))
        return result is not None
    
    def insert_paper(self, paper_data: Dict[str, Any]) -> Optional[int]:
        """Insert a new paper and return its ID."""
        query = """
            INSERT INTO papers (
                title, abstract, arxiv_id, version, is_latest_version,
                date_published, proceeding, conference, 
                conference_url_abs, conference_url_pdf,
                created_at, updated_at
            ) VALUES (
                %(title)s, %(abstract)s, %(arxiv_id)s, %(version)s, %(is_latest_version)s,
                %(date_published)s, %(proceeding)s, %(conference)s,
                %(conference_url_abs)s, %(conference_url_pdf)s,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) ON CONFLICT (arxiv_id, version) DO NOTHING
            RETURNING id;
        """
        
        try:
            with self.get_cursor(commit=True) as cursor:
                cursor.execute(query, paper_data)
                result = cursor.fetchone()
                return result['id'] if result else None
        except psycopg2.Error as e:
            logger.error(f"Error inserting paper {paper_data.get('arxiv_id', 'unknown')}: {e}")
            return None
    
    def search_papers(self, search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Full-text search in papers."""
        # Convert search term to proper tsquery format
        formatted_term = ' & '.join(search_term.split())
        
        query = """
            SELECT title, arxiv_id, version, date_published, abstract
            FROM papers 
            WHERE to_tsvector('english', title || ' ' || COALESCE(abstract, '')) 
                  @@ to_tsquery('english', %s)
            ORDER BY date_published DESC 
            LIMIT %s;
        """
        return self.execute_query(query, (formatted_term, limit))
    
    def get_papers_by_year(self, year: int) -> List[Dict[str, Any]]:
        """Get papers published in a specific year."""
        query = """
            SELECT COUNT(*) as paper_count, 
                   EXTRACT(MONTH FROM date_published) as month
            FROM papers 
            WHERE EXTRACT(YEAR FROM date_published) = %s
            GROUP BY EXTRACT(MONTH FROM date_published)
            ORDER BY month;
        """
        return self.execute_query(query, (year,))
    
    def get_version_distribution(self) -> List[Dict[str, Any]]:
        """Get distribution of paper versions."""
        query = """
            SELECT version, COUNT(*) as count,
                   ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
            FROM papers 
            GROUP BY version 
            ORDER BY count DESC;
        """
        return self.execute_query(query)


# Convenience functions for backward compatibility
def get_database(config: Optional[DatabaseConfig] = None) -> Database:
    """Get a Database instance."""
    return Database(config)


def get_papers_database(config: Optional[DatabaseConfig] = None) -> PapersDatabase:
    """Get a PapersDatabase instance."""
    return PapersDatabase(config)


# Example usage
if __name__ == "__main__":
    # Test the database connection
    db = get_papers_database()
    
    if db.test_connection():
        print("✅ Database connection successful!")
        print(f"📊 Total papers: {db.get_paper_count():,}")
        print(f"📅 Latest paper date: {db.get_latest_paper_date()}")
        
        # Test search
        results = db.search_papers("transformer attention", limit=3)
        print(f"🔍 Search results: {len(results)} papers found")
        for paper in results:
            print(f"   - {paper['title'][:60]}... ({paper['arxiv_id']})")
    else:
        print("❌ Database connection failed!")
