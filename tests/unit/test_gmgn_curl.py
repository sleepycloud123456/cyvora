"""The live Windows transport must not put the API key on the command line."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx2
import pytest

from integrations.gmgn.curl_transport import CurlTransport

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_gmgn_curl.py"
KEY = "gmgn-test-key-not-real"


def _request() -> httpx2.Request:
    return httpx2.Request(
        "GET",
        "https://openapi.gmgn.ai/v1/market/rank?chain=sol",
        headers={"X-APIKEY": KEY, "Accept": "application/json"},
    )


@pytest.mark.asyncio
async def test_curl_transport_keeps_the_api_key_out_of_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv_file = tmp_path / "argv.txt"
    monkeypatch.setenv("CYVORA_FAKE_CURL_ARGV", str(argv_file))
    transport = CurlTransport(sys.executable, (str(FIXTURE),))
    response = await transport.handle_async_request(_request())
    assert response.status_code == 200
    assert response.json()["code"] == 0
    argv = argv_file.read_text(encoding="utf-8").splitlines()
    assert KEY not in "\n".join(argv)
    assert "--disable" in argv
    config = Path(argv[argv.index("--config") + 1])
    assert not config.exists()


@pytest.mark.asyncio
async def test_curl_failure_does_not_echo_the_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CYVORA_FAKE_CURL_ARGV", str(tmp_path / "argv.txt"))
    monkeypatch.setenv("CYVORA_FAKE_CURL_FAIL", "1")
    transport = CurlTransport(sys.executable, (str(FIXTURE),))
    with pytest.raises(httpx2.ConnectError, match="curl exit 28") as caught:
        await transport.handle_async_request(_request())
    assert KEY not in str(caught.value)


@pytest.mark.asyncio
async def test_curl_transport_refuses_a_quoted_header_value() -> None:
    transport = CurlTransport(sys.executable, (str(FIXTURE),))
    request = httpx2.Request(
        "GET",
        "https://openapi.gmgn.ai/v1/user/info",
        headers={"X-APIKEY": 'gmgn-test-"key'},
    )
    with pytest.raises(httpx2.TransportError, match="quote or a newline") as caught:
        await transport.handle_async_request(request)
    assert "gmgn-test" not in str(caught.value)
