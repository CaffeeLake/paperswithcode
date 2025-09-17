"""
Configuration management for the FastAPI backend.
"""

import os
from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Server configuration
    host: str = Field(default="0.0.0.0", description="Host to bind the server")
    port: int = Field(default=8000, description="Port to bind the server")
    environment: str = Field(default="development", description="Environment (development, staging, production)")
    log_level: str = Field(default="INFO", description="Log level")
    
    # Database configuration
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_name: str = Field(default="paperswithcode", description="Database name")
    db_user: str = Field(default="nielsrogge", description="Database user")
    db_password: str = Field(default="", description="Database password")
    
    # CORS configuration
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins"
    )
    
    # API configuration
    default_page_size: int = Field(default=50, description="Default page size for paginated responses")
    max_page_size: int = Field(default=500, description="Maximum page size for paginated responses")
    
    # ArXiv configuration
    arxiv_base_url: str = Field(default="https://arxiv.org", description="ArXiv base URL")
    
    # Application URLs
    app_domain: str = Field(default="paperswithcode.ai", description="Application domain for URL generation")
    
    class Config:
        env_file = ".env"
        env_prefix = "PWC_"
    
    @property
    def database_url(self) -> str:
        """Get the database URL."""
        password_part = f":{self.db_password}" if self.db_password else ""
        return f"postgresql://{self.db_user}{password_part}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() == "development"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
