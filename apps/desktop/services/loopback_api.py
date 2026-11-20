"""Call the loopback API. Redirects are refused and the token is not logged."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from config.settings import Settings
from domain.exceptions import TradingValidationError

_MAX_BODY = 8_000_000
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def loopback_url(settings: Settings, path: str) -> str:
    """Build an HTTP URL on the configured loopback host."""

    host = settings.api_host
    if host not in _LOOPBACK:
        raise TradingValidationError("The API host is not loopback. The request was not sent.")
    if not path.startswith("/") or path.startswith("//"):
        raise TradingValidationError("The API path is invalid.")
    shown = "[::1]" if host == "::1" else host
    return f"http://{shown}:{settings.api_port}{path}"


def request_json(
    settings: Settings,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> object:
    """Send one JSON request. A missing token or a redirect sends nothing useful onward."""

    if settings.api_token is None:
        raise TradingValidationError(
            "The local API token is not configured. The request was not sent."
        )
    url = loopback_url(settings, path)
    payload = None if body is None else json.dumps(body).encode("utf-8")
    if payload is not None and len(payload) > _MAX_BODY:
        raise TradingValidationError("The request is larger than the local import limit.")
    request = urllib.request.Request(url, data=payload, method=method)
    request.add_header("Accept", "application/json")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", "Bearer " + settings.api_token.get_secret_value())
    opener = urllib.request.build_opener(_RefuseRedirect())
    try:
        with opener.open(request, timeout=60) as response:
            raw = response.read(_MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        raise TradingValidationError(_safe_detail(exc.read(4096))) from None
    except urllib.error.URLError:
        raise TradingValidationError(
            "The local API is not running. No order was submitted and no file was stored."
        ) from None
    except TradingValidationError:
        raise
    if len(raw) > _MAX_BODY:
        raise TradingValidationError("The local API response was too large.")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TradingValidationError("The local API response was not JSON.") from exc


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """Stop a redirect so the local token is not sent to another host."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        raise TradingValidationError("The local API redirected the request. It was not followed.")


def _safe_detail(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    detail = parsed.get("detail") if isinstance(parsed, dict) else None
    if not isinstance(detail, str):
        return "The local API rejected the request."
    cleaned = " ".join(detail.split())
    if "://" in cleaned or len(cleaned) > 240:
        return "The local API rejected the request."
    return cleaned
