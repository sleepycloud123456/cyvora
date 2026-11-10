"""One read-only GMGN smoke call.

Prints response shapes. It does not print the API key, wallet addresses, or
balances. Exit 0 when GMGN_API_KEY is unset, or when at least one documented
read succeeds.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable

from config.settings import get_settings
from integrations.gmgn.client import client_from_settings
from integrations.gmgn.errors import GMGNError
from integrations.gmgn.models import Retrieved, TokenInfo, TokenSecurity
from integrations.gmgn.read_only import GMGNReadOnly
from integrations.gmgn.report import assert_report_is_safe, describe, public_scalar
from monitoring.logging import configure_logging
from monitoring.redaction import redact_text, secret_values

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
_SYMBOL = frozenset({"symbol", "name", "chain"})
_SECURITY = frozenset(
    {
        "renounced_mint",
        "renounced_freeze_account",
        "is_honeypot",
        "burn_status",
        "sniper_count",
        "open_source",
    }
)


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    configure_logging(settings)
    if settings.gmgn_api_key is None:
        print("GMGN_SMOKE_SKIP reason=GMGN_API_KEY_not_set")
        return 0
    secret = settings.gmgn_api_key.get_secret_value()
    try:
        report = asyncio.run(_run(secret))
    except Exception as exc:
        print(
            "GMGN_SMOKE_FAIL "
            f"error_type={type(exc).__name__} "
            f"detail={redact_text(str(exc), secret_values(settings)).replace(chr(10), ' ')[:300]}"
        )
        return 1
    for value in secret_values(settings):
        try:
            assert_report_is_safe(report, value)
        except GMGNError:
            print("GMGN_SMOKE_FAIL reason=report_contained_secret")
            return 1
    print(report)
    return 0 if report.startswith("GMGN_SMOKE_OK") else 1


async def _run(secret: str) -> str:
    lines: list[str] = []
    successes = 0
    stopped = False
    client = client_from_settings(get_settings())
    api = GMGNReadOnly(client)

    async def step[T](name: str, awaitable: Awaitable[T]) -> T | None:
        nonlocal successes, stopped
        if stopped:
            lines.append(f"{name}_skipped=earlier_failure")
            return None
        try:
            result = await awaitable
        except GMGNError as exc:
            lines.append(f"{name}_error={type(exc).__name__}")
            detail = redact_text(str(exc), (secret,)).replace("\n", " ")
            lines.append(f"{name}_detail={detail}")
            if client.connection.state in {"unauthorized", "rate_limited"}:
                stopped = True
            return None
        successes += 1
        return result

    async with client:
        trending = await step("trending", api.market.trending("sol", "1h", limit=3))
        address: str | None = None
        if trending is not None:
            lines.append(f"trending_count={len(trending.payload)}")
            symbols = [
                shown
                for token in trending.payload
                if (shown := public_scalar("symbol", token.symbol, allow=_SYMBOL, secret=secret))
            ]
            lines.append("trending_symbols=" + ",".join(symbols))
            if trending.payload:
                lines.append(
                    "trending_shape="
                    + json.dumps(describe(trending.payload[0].model_dump()), sort_keys=True)
                )
            for token in trending.payload:
                if token.address:
                    address = token.address
                    lines.append("token_address_source=trending")
                    break
        if address is None and not stopped:
            address = USDC
            lines.append("token_address_source=documented_usdc_fallback")
        if address is not None:
            info = await step("token_info", api.tokens.info("sol", address))
            _note_model(lines, "token_info", info, secret)
            security = await step("token_security", api.tokens.security("sol", address))
            _note_security(lines, security, secret)
            pool = await step("token_pool", api.tokens.pool("sol", address))
            _note_model(lines, "pool", pool, secret)
            now = int(time.time())
            candles = await step(
                "kline",
                api.market.candles(
                    "sol",
                    address,
                    "1h",
                    from_unix=now - 6 * 3600,
                    to_unix=now,
                ),
            )
            if candles is not None:
                lines.append(f"kline_count={len(candles.payload)}")
                if candles.payload:
                    lines.append(
                        "kline_shape="
                        + json.dumps(describe(candles.payload[0].model_dump()), sort_keys=True)
                    )
        launches = await step("new_launches", api.discovery.new_launches("sol", limit=3))
        if launches is not None:
            lines.append(f"new_launch_count={len(launches.payload)}")
            if launches.payload:
                lines.append(
                    "new_launch_shape="
                    + json.dumps(describe(launches.payload[0].model_dump()), sort_keys=True)
                )
        account = await step("bound_account", api.wallet.bound_account())
        if account is not None:
            lines.append(
                "bound_account_shape=" + json.dumps(describe(account.payload), sort_keys=True)
            )
        state = client.connection
        lines.append(
            "connection="
            f"state={state.state} success_count={state.success_count} "
            f"failure_count={state.failure_count} last_http_status={state.last_http_status} "
            f"last_path={state.last_path}"
        )
    prefix = "GMGN_SMOKE_OK" if successes else "GMGN_SMOKE_FAIL"
    return prefix + "\n" + "\n".join(lines)


def _note_model(lines: list[str], name: str, result: Retrieved[object] | None, secret: str) -> None:
    if result is None:
        return
    payload = result.payload
    if isinstance(payload, TokenInfo):
        symbol = public_scalar("symbol", payload.symbol, allow=_SYMBOL, secret=secret) or ""
        lines.append(f"{name}_symbol={symbol}")
    if isinstance(payload, TokenInfo | TokenSecurity):
        lines.append(f"{name}_shape=" + json.dumps(describe(payload.model_dump()), sort_keys=True))
        return
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        lines.append(f"{name}_shape=" + json.dumps(describe(model_dump()), sort_keys=True))


def _note_security(lines: list[str], result: Retrieved[TokenSecurity] | None, secret: str) -> None:
    if result is None:
        return
    flags: list[str] = []
    for key in sorted(_SECURITY):
        shown = public_scalar(key, getattr(result.payload, key), allow=_SECURITY, secret=secret)
        if shown is not None:
            flags.append(f"{key}={shown}")
    lines.append("security_flags=" + ",".join(flags))
    lines.append(
        "security_shape=" + json.dumps(describe(result.payload.model_dump()), sort_keys=True)
    )


if __name__ == "__main__":
    raise SystemExit(main())
