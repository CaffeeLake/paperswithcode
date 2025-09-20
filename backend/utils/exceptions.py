"""
Custom exception classes for the PapersWithCode API.
"""


class PapersWithCodeAPIError(Exception):
    """Base exception for PapersWithCode API errors."""

    pass


class PaperNotFoundError(PapersWithCodeAPIError):
    """Raised when a paper is not found."""

    pass


class DatabaseError(PapersWithCodeAPIError):
    """Raised when a database operation fails."""

    pass


class ValidationError(PapersWithCodeAPIError):
    """Raised when input validation fails."""

    pass


class ArXivError(PapersWithCodeAPIError):
    """Raised when ArXiv-related operations fail."""

    pass


class ThumbnailGenerationError(PapersWithCodeAPIError):
    """Raised when thumbnail generation fails."""

    pass
