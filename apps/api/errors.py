"""Safe API error responses."""

from __future__ import annotations

import logging

from fastapi.responses import JSONResponse

logger = logging.getLogger("cyvora.api")


def unexpected_error_response(exc: Exception, path: str) -> JSONResponse:
    """Return a generic 500 response.

    The exception text is not logged or returned. Driver and validation
    messages can contain URLs or other configuration.
    """

    logger.error("unhandled error type=%s path=%s", type(exc).__name__, path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
