"""Windows GMGN transport that uses the operating-system curl.

On 2026-11-11, ``httpx2`` from this PC received a Cloudflare HTML 403
(``Sorry, you have been blocked``) for ``https://openapi.gmgn.ai``. The same
read, sent with ``C:\\Windows\\System32\\curl.exe`` over IPv4, received
HTTP 200 JSON. The API key is written only to a temporary curl config file,
which is removed before this function returns. It is not placed on the
command line.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx2

_SKIPPED_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "cookie"})


class CurlTransport(httpx2.AsyncBaseTransport):
    """Perform one GMGN request with curl and return an httpx response."""

    def __init__(self, executable: str, leading_args: tuple[str, ...] = ()) -> None:
        self._executable = executable
        self._leading_args = leading_args

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        return await asyncio.to_thread(self._perform, request)

    def _perform(self, request: httpx2.Request) -> httpx2.Response:
        if not Path(self._executable).is_file():
            raise httpx2.ConnectError("The GMGN curl executable is not available.")
        timeout = _timeout_seconds(request)
        with tempfile.TemporaryDirectory(prefix="cyvora-gmgn-") as directory:
            root = Path(directory)
            config_path = root / "request.cfg"
            body_path = root / "body.bin"
            header_path = root / "headers.txt"
            config_path.write_text(
                _config(request, body_path, header_path, timeout),
                encoding="utf-8",
            )
            try:
                completed = subprocess.run(
                    [
                        self._executable,
                        *self._leading_args,
                        "--disable",
                        "--config",
                        str(config_path),
                    ],
                    check=False,
                    capture_output=True,
                    timeout=timeout + 2,
                )
            except subprocess.TimeoutExpired as exc:
                raise httpx2.ConnectError("curl timed out") from exc
            content = body_path.read_bytes() if body_path.is_file() else b""
            raw_headers = header_path.read_bytes() if header_path.is_file() else b""
        if completed.returncode != 0:
            raise httpx2.ConnectError(f"curl exit {completed.returncode}")
        status, headers = _parse_status(raw_headers)
        return httpx2.Response(status, headers=headers, content=content, request=request)


def default_gmgn_transport() -> httpx2.AsyncBaseTransport:
    """Use the system curl on Windows. Other platforms stay on httpx2."""

    if sys.platform == "win32":
        executable = windows_system_curl()
        if executable is not None:
            return CurlTransport(executable)
    return httpx2.AsyncHTTPTransport(local_address="0.0.0.0")


def windows_system_curl() -> str | None:
    root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    candidate = Path(root) / "System32" / "curl.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _timeout_seconds(request: httpx2.Request) -> float:
    raw = request.extensions.get("timeout")
    if not isinstance(raw, dict):
        return 10.0
    numbers = [
        float(item)
        for item in (raw.get("connect"), raw.get("read"), raw.get("write"))
        if isinstance(item, int | float) and item > 0
    ]
    return max(numbers) if numbers else 10.0


def _config(
    request: httpx2.Request,
    body_path: Path,
    header_path: Path,
    timeout: float,
) -> str:
    lines = [
        "ipv4",
        "compressed",
        "silent",
        "show-error",
        "globoff",
        "max-redirs = 0",
        'noproxy = "*"',
        f"max-time = {int(timeout) if timeout >= 1 else 1}",
        f"connect-timeout = {min(5, int(timeout) if timeout >= 1 else 1)}",
        f"url = {_quote(str(request.url))}",
        f"request = {_quote(request.method)}",
        f"output = {_quote(body_path.as_posix())}",
        f"dump-header = {_quote(header_path.as_posix())}",
    ]
    content = request.content
    if content:
        request_body = body_path.with_name("request-body.bin")
        request_body.write_bytes(content)
        lines.append(f"data-binary = {_quote('@' + request_body.as_posix())}")
    for name, value in request.headers.items():
        if name.lower() in _SKIPPED_HEADERS or name.lower() == "content-encoding":
            continue
        lines.append(f"header = {_quote(f'{name}: {value}')}")
    return "\n".join(lines) + "\n"


def _quote(value: str) -> str:
    if any(character in value for character in ('"', "\n", "\r")):
        raise httpx2.TransportError("Refusing a curl value that contains a quote or a newline.")
    return '"' + value + '"'


def _parse_status(raw: bytes) -> tuple[int, list[tuple[str, str]]]:
    status = 0
    headers: list[tuple[str, str]] = []
    for line in raw.split(b"\r\n"):
        if line.startswith(b"HTTP/"):
            parts = line.decode("iso-8859-1").split()
            if len(parts) < 2 or not parts[1].isdigit():
                continue
            status = int(parts[1])
            headers = []
            continue
        if b":" not in line:
            continue
        name, value = line.decode("iso-8859-1").split(":", 1)
        if name.lower() in {"content-encoding", "content-length", "transfer-encoding"}:
            continue
        headers.append((name.strip(), value.strip()))
    if status == 0:
        raise httpx2.ConnectError("curl returned no HTTP status")
    return status, headers
