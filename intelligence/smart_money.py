"""Smart-money observations from GMGN tag counts.

This does not call ``/v1/user/smartmoney``. That route is in the official
client and was not wrapped, because its response shape was not verified.
A tag count is not a copy instruction. Individual purchases are unknown
unless a later verified feed provides them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from integrations.gmgn.models import TokenInfo, TokenParticipant
from intelligence.numbers import as_decimal, score


@dataclass(frozen=True, slots=True)
class SmartMoneyObservation:
    """Tag counts for one token."""

    status: str
    score: Decimal | None
    smart_wallets: int | None
    renowned_wallets: int | None
    sniper_wallets: int | None
    rat_trader_wallets: int | None
    source: str
    warnings: tuple[str, ...]


def observe_smart_money(
    info: TokenInfo | None,
    *,
    rank_smart_count: Decimal | None = None,
    traders: tuple[TokenParticipant, ...] | None = None,
) -> SmartMoneyObservation:
    """Score explicit tag counts. A missing object is not zero wallets."""

    tags = None if info is None else info.wallet_tags_stat
    warnings: list[str] = [
        "Smart-money purchases were not read. No verified purchase feed is called.",
    ]
    if tags is None and rank_smart_count is None:
        return SmartMoneyObservation(
            status="missing",
            score=None,
            smart_wallets=None,
            renowned_wallets=None,
            sniper_wallets=None,
            rat_trader_wallets=None,
            source="not_returned",
            warnings=tuple(warnings + ["wallet_tags_stat was not in the token payload."]),
        )

    smart = None if tags is None else tags.smart_wallets
    renowned = None if tags is None else tags.renowned_wallets
    snipers = None if tags is None else tags.sniper_wallets
    rats = None if tags is None else tags.rat_trader_wallets
    source = "token_info.wallet_tags_stat"
    if smart is None and rank_smart_count is not None:
        smart = int(rank_smart_count)
        source = "rank.smart_degen_count"
    elif (
        smart is not None
        and rank_smart_count is not None
        and abs(Decimal(smart) - rank_smart_count)
        > max(Decimal(1), Decimal(smart) * Decimal("0.5"))
    ):
        warnings.append(
            "The rank smart-wallet count disagrees with wallet_tags_stat. "
            "The token-info count is used."
        )

    points = Decimal(40)
    if smart is not None:
        points += min(Decimal(40), Decimal(smart) * Decimal(8))
    if renowned is not None:
        points += min(Decimal(20), Decimal(renowned) * Decimal(4))
    if snipers is not None and smart is not None and snipers > smart and snipers > 0:
        points -= Decimal(15)
        warnings.append("Sniper wallets outnumber the smart-wallet tag.")
    if rats is not None and rats > 0:
        points -= min(Decimal(10), Decimal(rats))
        warnings.append("GMGN reported rat-trader wallets.")
    if traders is not None:
        suspicious = sum(1 for row in traders if row.is_suspicious is True)
        if suspicious:
            points -= min(Decimal(10), Decimal(suspicious) * Decimal(2))
            warnings.append(f"{suspicious} top traders were marked suspicious.")
    status = "observed"
    if tags is None:
        status = "partial"
    return SmartMoneyObservation(
        status=status,
        score=score(points),
        smart_wallets=smart,
        renowned_wallets=renowned,
        sniper_wallets=snipers,
        rat_trader_wallets=rats,
        source=source,
        warnings=tuple(warnings),
    )


def rank_smart_count(extra: dict[str, object] | None) -> Decimal | None:
    """Read a rank-row count when GMGN included one. The key is an order-by field."""

    if not extra:
        return None
    for key in ("smart_degen_count", "renowned_count"):
        parsed = as_decimal(extra.get(key))
        if parsed is not None and parsed >= 0:
            return parsed
    return None
