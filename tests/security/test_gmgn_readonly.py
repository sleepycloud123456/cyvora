"""The GMGN package cannot sign or submit a trade."""

from __future__ import annotations

from pathlib import Path

import httpx2
import pytest

from integrations.gmgn.client import GMGNClient
from integrations.gmgn.errors import GMGNExecutionBlocked
from integrations.gmgn.execution import GMGNExecutionGateway


def test_source_has_no_signature_header() -> None:
    root = Path(__file__).resolve().parents[2] / "integrations" / "gmgn"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "X-Signature" not in text
    assert "BEGIN PRIVATE KEY" not in text
    assert "def swap" not in text
    assert "def sign" not in text


def test_gateway_discards_payload_text() -> None:
    secret = "gmgn-test-key-not-real"
    with pytest.raises(GMGNExecutionBlocked) as caught:
        GMGNExecutionGateway().submit("swap", api_key=secret, private_key=secret)
    assert secret not in str(caught.value)


@pytest.mark.asyncio
async def test_client_refuses_holdings_and_quote_before_http() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("transport was called")

    client = GMGNClient("gmgn-test-key-not-real", transport=httpx2.MockTransport(handler))
    async with client:
        with pytest.raises(GMGNExecutionBlocked):
            await client.get_data("GET", "/v1/trade/quote", {"chain": "sol"})
        with pytest.raises(GMGNExecutionBlocked):
            await client.get_data("GET", "/v1/user/wallet_holdings", {"chain": "sol"})
