"""The Phase 2 GMGN surface: reads plus a gateway that cannot trade."""

from __future__ import annotations

from integrations.gmgn.client import GMGNClient
from integrations.gmgn.discovery import GMGNDiscoveryService
from integrations.gmgn.execution import GMGNExecutionGateway
from integrations.gmgn.market_data import GMGNMarketData
from integrations.gmgn.token_service import GMGNTokenService
from integrations.gmgn.wallet import GMGNWalletService


class GMGNReadOnly:
    """Group the read services. The execution gateway has no HTTP client."""

    def __init__(self, client: GMGNClient) -> None:
        self.client = client
        self.market = GMGNMarketData(client)
        self.tokens = GMGNTokenService(client)
        self.discovery = GMGNDiscoveryService(client)
        self.wallet = GMGNWalletService(client)
        self.execution = GMGNExecutionGateway()
