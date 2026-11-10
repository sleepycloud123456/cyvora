"""GMGN failures. Messages name the route and the error code, not a secret."""

from __future__ import annotations

from domain.exceptions import CyvoraError


class GMGNError(CyvoraError):
    """Base type for GMGN integration failures."""


class GMGNNotConfigured(GMGNError):
    """A GMGN call was requested without an API key."""


class GMGNExecutionBlocked(GMGNError):
    """The caller asked for a trade, a signature, or a route this phase refuses."""


class GMGNAuthorizationRequired(GMGNError):
    """The official route exists, but it requires a private key CYVORA will not load."""


class GMGNValidationError(GMGNError):
    """The caller supplied a chain, address, or parameter the documented API rejects."""


class GMGNTransportError(GMGNError):
    """The HTTP call did not produce a JSON envelope."""

    def __init__(self, method: str, path: str, reason: str) -> None:
        self.method = method
        self.path = path
        super().__init__(f"{method} {path} could not reach GMGN ({reason}).")


class GMGNResponseError(GMGNError):
    """The envelope or the documented object shape could not be read."""

    def __init__(self, route: str, detail: str) -> None:
        self.route = route
        super().__init__(f"{route} response could not be read ({detail}).")


class GMGNApiError(GMGNError):
    """GMGN returned an envelope whose code was not 0."""

    def __init__(
        self,
        method: str,
        path: str,
        *,
        http_status: int,
        api_code: object,
        api_error: str | None,
        reset_at: int | None,
    ) -> None:
        self.method = method
        self.path = path
        self.http_status = http_status
        self.api_code = api_code
        self.api_error = api_error
        self.reset_at = reset_at
        error_name = api_error or "unknown"
        message = f"{method} {path} failed: HTTP {http_status} code={api_code} error={error_name}."
        if reset_at is not None:
            message = (
                f"{message} Do not send another GMGN request until unix {reset_at}. "
                "Further requests during the cooldown can extend the ban."
            )
        super().__init__(message)


class GMGNRateLimitError(GMGNApiError):
    """The plan bucket or a ban window rejected the call."""


class GMGNPlanError(GMGNApiError):
    """The route weight is above the key's plan. Retrying will not succeed."""
