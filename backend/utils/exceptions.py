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


class ThumbnailGenerationError(PapersWithCodeAPIError):
    """Raised when thumbnail generation fails."""

    pass


class ThumbnailUnavailableError(ThumbnailGenerationError):
    """Raised when the source confirms that no thumbnail can be generated."""

    pass
