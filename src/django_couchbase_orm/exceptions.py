class DjangoCbError(Exception):
    """Base exception for all django-couchbase-orm errors."""


class ValidationError(DjangoCbError):
    """Raised when field or document validation fails.

    Can hold a single message string or a dict mapping field names to error messages.
    """

    def __init__(self, message=None, errors=None):
        if errors is not None:
            self.errors = errors
            self.message = str(errors)
        elif isinstance(message, dict):
            self.errors = message
            self.message = str(message)
        else:
            self.errors = {}
            self.message = message or "Validation error"
        super().__init__(self.message)


class DocumentDoesNotExist(DjangoCbError):
    """Raised when a requested document is not found."""


class MultipleDocumentsReturned(DjangoCbError):
    """Raised when a single document was expected but multiple were found."""


class ConnectionError(DjangoCbError):
    """Raised when a connection to Couchbase cannot be established."""


class OperationError(DjangoCbError):
    """Raised when a Couchbase operation fails."""


class ConcurrentModificationError(OperationError):
    """Raised when an optimistic-locking save fails because the stored CAS
    no longer matches the in-memory CAS — another writer modified the
    document between read and write. Retry by reloading the document."""
