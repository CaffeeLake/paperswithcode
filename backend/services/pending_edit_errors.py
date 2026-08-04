"""Domain errors shared by pending-edit submission components."""


class PendingEditError(Exception):
    """Raised for validation problems with pending edit submissions or reviews."""


class PendingEditNotFoundError(PendingEditError):
    """Raised when a pending edit row cannot be found."""


class PendingEditAlreadyReviewedError(PendingEditError):
    """Raised when an admin tries to approve or reject a non-pending row."""


class PendingEditConflictError(PendingEditError):
    """Raised when canonical state changed after a submission was created."""


class SubmissionRateLimitError(PendingEditError):
    def __init__(self, message: str, *, retry_after: int = 3600):
        super().__init__(message)
        self.retry_after = retry_after


class SubmissionSuspendedError(PendingEditError):
    """Raised when a suspended profile attempts to submit an edit."""
