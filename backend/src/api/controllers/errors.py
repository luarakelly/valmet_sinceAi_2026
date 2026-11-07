from contextlib import contextmanager

from fastapi import HTTPException, status

from business.errors import (
    InvalidRequestError,
    NotFoundError,
    PayloadTooLargeError,
    RouteNotFoundError,
    ServiceUnavailableError,
    UnsupportedMediaTypeError,
)

_STATUS = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidRequestError: status.HTTP_400_BAD_REQUEST,
    RouteNotFoundError: status.HTTP_409_CONFLICT,
    ServiceUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    PayloadTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    UnsupportedMediaTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
}


@contextmanager
def http_errors():
    """Translate business errors raised inside the block into HTTP errors."""
    try:
        yield
    except tuple(_STATUS) as error:
        raise HTTPException(status_code=_STATUS[type(error)], detail=str(error)) from error
