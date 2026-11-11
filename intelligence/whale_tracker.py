"""Whale and holder-concentration observations.

GMGN's ``whale_wallets`` tag count is recorded when token info includes it.
Holder rows, when the holders route is called, supply the largest share.
Wallet activity is not called: this API key has no bound wallet, and querying
arbitrary holder addresses was not part of the verified read set. A count of
whale wallets is not treated as a buy signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from integrations.gmgn.models import TokenInfo, TokenParticipant, TokenSecurity
from intelligence.numbers import score

_NOT_A_TRADE_FEED = (
    "Whale transactions were not read. No verified public whale-trade route is "
    "on the allowlist, and wallet activity is not queried for other addresses."
)


@dataclass(frozen=True, slots=True)
class WhaleObservation:
    """Concentration for one token. A higher score is less concentrated."""

    status: str
    score: Decimal | None
    whale_wallets: int | None
    top_10_holder_rate: Decimal | None
    largest_holder_rate: Decimal | None
    holder_rows: int | None
    source: str
    warnings: tuple[str, ...]


def observe_whales(
    *,
    info: TokenInfo | None,
    security: TokenSecurity | None,
    holders: tuple[TokenParticipant, ...] | None,
) -> WhaleObservation:
    """Score distribution. Missing holder data stays missing."""

    warnings = [_NOT_A_TRADE_FEED]
    whale_wallets = None
    if info is not None and info.wallet_tags_stat is not None:
        whale_wallets = info.wallet_tags_stat.whale_wallets
    top_10 = _top_10(info, security)
    largest, holder_rows = _largest(holders)
    if top_10 is None and largest is None and whale_wallets is None and holders is None:
        return WhaleObservation(
            status="missing",
            score=None,
            whale_wallets=None,
            top_10_holder_rate=None,
            largest_holder_rate=None,
            holder_rows=None,
            source="not_returned",
            warnings=tuple(warnings + ["No holder concentration field was returned."]),
        )

    points = Decimal(70)
    if top_10 is not None:
        points = _from_top_10(top_10)
    elif largest is not None:
        points = _from_top_10(largest)
    if largest is not None and largest > Decimal("0.2"):
        points -= Decimal(15)
        warnings.append("The largest returned holder share is above 0.2.")
    if whale_wallets is not None and whale_wallets > 5:
        points -= min(Decimal(15), Decimal(whale_wallets - 5) * Decimal(3))
        warnings.append(
            "The GMGN whale-wallet count is above 5. "
            "CYVORA treats that as concentration, not demand."
        )
    status = "observed" if holders is not None or top_10 is not None else "partial"
    source = "token_info"
    if holders is not None:
        source = "token_top_holders"
    elif security is not None and security.top_10_holder_rate is not None:
        source = "token_security"
    return WhaleObservation(
        status=status,
        score=score(points),
        whale_wallets=whale_wallets,
        top_10_holder_rate=top_10,
        largest_holder_rate=largest,
        holder_rows=holder_rows,
        source=source,
        warnings=tuple(warnings),
    )


def _top_10(info: TokenInfo | None, security: TokenSecurity | None) -> Decimal | None:
    if security is not None and security.top_10_holder_rate is not None:
        return security.top_10_holder_rate
    if info is not None and info.stat is not None and info.stat.top_10_holder_rate is not None:
        return info.stat.top_10_holder_rate
    if info is not None and info.dev is not None:
        return info.dev.top_10_holder_rate
    return None


def _largest(
    holders: tuple[TokenParticipant, ...] | None,
) -> tuple[Decimal | None, int | None]:
    if holders is None:
        return None, None
    rates = [row.amount_percentage for row in holders if row.amount_percentage is not None]
    if not rates:
        return None, len(holders)
    largest = max(rates)
    if largest > 1:
        largest = largest / Decimal(100)
    return largest, len(holders)


def _from_top_10(rate: Decimal) -> Decimal:
    fraction = rate / Decimal(100) if rate > 1 else rate
    if fraction <= Decimal("0.2"):
        return Decimal(85)
    if fraction <= Decimal("0.4"):
        return Decimal(65)
    if fraction <= Decimal("0.6"):
        return Decimal(40)
    return Decimal(15)
