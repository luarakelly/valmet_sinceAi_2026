"""Domain errors. Controllers translate them to HTTP status codes."""


class DomainError(Exception):
    """Base class for expected, user-facing failures."""


class NotFoundError(DomainError):
    """A requested asset, frame or file does not exist (HTTP 404)."""


class InvalidRequestError(DomainError):
    """The request is understood but not allowed (HTTP 400)."""


class RouteNotFoundError(DomainError):
    """No collision-free route exists to the requested target (HTTP 409)."""


class ServiceUnavailableError(DomainError):
    """An optional capability (YOLO, LLM) is not available (HTTP 503)."""


class PayloadTooLargeError(DomainError):
    """Uploaded content exceeds a limit (HTTP 413)."""


class UnsupportedMediaTypeError(DomainError):
    """Upload is not of the expected type (HTTP 415)."""
