"""Security categories from a GMGN token security payload.

UNKNOWN is not safe. A missing honeypot flag does not become false.
``burn_status`` is recorded and is never treated as proof that liquidity is locked.
The integer ``honeypot`` field seen on 2026-11-11 is stored as unverified: Phase 2
did not establish what 0 or 1 means, separate from ``is_honeypot``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.radar import SecurityCategory
from integrations.gmgn.models import TokenInfo, TokenSecurity
from intelligence.numbers import explicit_bool, score, show

_HALF = Decimal("0.5")
_TAX_FRACTION = Decimal("0.10")


@dataclass(frozen=True, slots=True)
class SecurityAssessment:
    """One security result. ``score`` is ``None`` only when the payload is missing."""

    category: SecurityCategory
    score: Decimal | None
    evidence: tuple[tuple[str, str], ...]
    missing: tuple[str, ...]
    warnings: tuple[str, ...]


def assess_security(
    security: TokenSecurity | None,
    info: TokenInfo | None = None,
) -> SecurityAssessment:
    """Classify one token from the fields CYVORA already parses."""

    if security is None:
        return SecurityAssessment(
            category=SecurityCategory.UNKNOWN,
            score=None,
            evidence=(),
            missing=("token_security",),
            warnings=(
                "The security payload was not retrieved. Missing security data is not safe.",
            ),
        )

    evidence: list[tuple[str, str]] = []
    missing: list[str] = []
    warnings: list[str] = []
    honeypot = explicit_bool(security.is_honeypot)
    evidence.append(("is_honeypot", show(security.is_honeypot)))
    extra = security.model_extra or {}
    if "honeypot" in extra:
        evidence.append(("honeypot_field_unverified", show(extra["honeypot"])))
        warnings.append(
            "GMGN returned a honeypot field whose meaning was not verified. "
            "It does not approve or reject the token by itself."
        )
    if honeypot is True:
        warnings.append("GMGN reported the token as a honeypot.")
        return SecurityAssessment(
            category=SecurityCategory.REJECTED,
            score=score(Decimal(0)),
            evidence=tuple(evidence),
            missing=tuple(missing),
            warnings=tuple(warnings),
        )

    mint = security.renounced_mint
    freeze = security.renounced_freeze_account
    points = _baseline(mint, freeze, honeypot)
    _apply_flags(security, info, points_box := [points], evidence, missing, warnings)
    points = score(points_box[0])
    category = _category(security, honeypot, mint, freeze, points, missing)
    if category == "UNKNOWN":
        warnings.append(
            "A critical security field is missing. That does not mean the token is safe."
        )
    if category == "HIGH_RISK":
        warnings.append("Security is high risk. This is not an entry.")
    return SecurityAssessment(
        category=category,
        score=points,
        evidence=tuple(evidence),
        missing=tuple(missing),
        warnings=tuple(warnings),
    )


def _baseline(mint: bool | None, freeze: bool | None, honeypot: bool | None) -> Decimal:
    if mint is True and freeze is True and honeypot is False:
        return Decimal(85)
    if mint is True and freeze is True:
        return Decimal(70)
    return Decimal(55)


def _apply_flags(
    security: TokenSecurity,
    info: TokenInfo | None,
    points_box: list[Decimal],
    evidence: list[tuple[str, str]],
    missing: list[str],
    warnings: list[str],
) -> None:
    if security.renounced_mint is None:
        missing.append("renounced_mint")
    elif security.renounced_mint is False:
        points_box[0] -= Decimal(25)
        warnings.append("Mint authority is not renounced.")
    if security.renounced_freeze_account is None:
        missing.append("renounced_freeze_account")
    elif security.renounced_freeze_account is False:
        points_box[0] -= Decimal(20)
        warnings.append("Freeze authority is not renounced.")
    if security.is_honeypot is None or security.is_honeypot == "":
        missing.append("is_honeypot")
        warnings.append("is_honeypot was not explicit. That is not evidence the token can be sold.")

    if security.is_wash_trading is None:
        missing.append("is_wash_trading")
    elif security.is_wash_trading is True:
        points_box[0] -= Decimal(30)
        warnings.append("GMGN reported wash trading.")

    if security.rug_ratio is None:
        missing.append("rug_ratio")
    else:
        evidence.append(("rug_ratio", show(security.rug_ratio)))
        if security.rug_ratio > _HALF:
            points_box[0] -= Decimal(20)
            warnings.append(
                "rug_ratio is above 0.5. That cutoff is CYVORA's. GMGN did not document the scale."
            )

    if security.sniper_count is None:
        missing.append("sniper_count")
    elif security.sniper_count > 0:
        points_box[0] -= min(Decimal(15), Decimal(security.sniper_count))
        warnings.append(f"Sniper count is {security.sniper_count}.")

    top_10 = security.top_10_holder_rate
    if top_10 is None and info is not None and info.stat is not None:
        top_10 = info.stat.top_10_holder_rate
    if top_10 is None:
        missing.append("top_10_holder_rate")
    else:
        evidence.append(("top_10_holder_rate", show(top_10)))
        if top_10 > _HALF:
            points_box[0] -= Decimal(15)
            warnings.append("The top-10 holder rate is above 0.5.")

    creator_rate = security.creator_balance_rate
    if creator_rate is None and info is not None and info.stat is not None:
        creator_rate = info.stat.creator_hold_rate
    if creator_rate is None:
        missing.append("creator_hold_rate")
    else:
        evidence.append(("creator_hold_rate", show(creator_rate)))
        if creator_rate > Decimal("0.2"):
            points_box[0] -= Decimal(10)
            warnings.append("Creator holdings are above 0.2 of the recorded rate.")

    for name in ("buy_tax", "sell_tax"):
        tax = getattr(security, name)
        if tax is None:
            missing.append(name)
            continue
        evidence.append((name, show(tax)))
        if tax > Decimal(10) or tax > _TAX_FRACTION:
            points_box[0] -= Decimal(15)
            warnings.append(
                f"{name} is above 0.10. CYVORA penalizes that whether the figure is a "
                "fraction or a percent, because the scale was not documented."
            )

    if security.burn_status is None:
        missing.append("burn_status")
        warnings.append("No burn status was returned. Liquidity is not treated as locked.")
    else:
        evidence.append(("burn_status", security.burn_status))
        warnings.append(
            "burn_status is a GMGN report. CYVORA does not treat it as verified locked liquidity."
        )


def _category(
    security: TokenSecurity,
    honeypot: bool | None,
    mint: bool | None,
    freeze: bool | None,
    points: Decimal,
    missing: list[str],
) -> SecurityCategory:
    dangerous = (
        mint is False
        or freeze is False
        or security.is_wash_trading is True
        or (security.rug_ratio is not None and security.rug_ratio > _HALF)
        or points < 40
    )
    if dangerous:
        return SecurityCategory.HIGH_RISK
    if mint is None and freeze is None and honeypot is None:
        return SecurityCategory.UNKNOWN
    approved = (
        mint is True
        and freeze is True
        and honeypot is False
        and security.is_wash_trading is False
        and security.buy_tax is not None
        and security.sell_tax is not None
        and security.buy_tax <= _TAX_FRACTION
        and security.sell_tax <= _TAX_FRACTION
        and security.rug_ratio is not None
        and security.rug_ratio <= _HALF
        and security.sniper_count == 0
        and "top_10_holder_rate" not in missing
        and "creator_hold_rate" not in missing
        and points >= 70
    )
    if approved:
        return SecurityCategory.APPROVED_FOR_FURTHER_ANALYSIS
    return SecurityCategory.CAUTION
