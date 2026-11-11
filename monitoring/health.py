"""Foundation health checks."""

from __future__ import annotations

import asyncio
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config.settings import APP_NAME, APP_VERSION, PHASE, Settings
from database.connection import check_database
from domain.status import ComponentStatus, StatusSnapshot
from operations.status import operation_components

logger = logging.getLogger("cyvora.health")


def overall_status(snapshot: StatusSnapshot) -> str:
    """Return ok unless a configured database could not be reached."""

    if snapshot.database.state == "unreachable":
        return "degraded"
    return "ok"


def collect_status(settings: Settings, *, probe_backend: bool) -> StatusSnapshot:
    """Collect foundation status.

    When ``probe_backend`` is false, the caller is the API process itself.
    The desktop sets it true and calls the loopback health endpoint.
    """

    database = check_database(settings)
    workers, market_data, queue, websocket = operation_components(settings)
    if probe_backend:
        backend = probe_backend_http(settings)
    else:
        backend = ComponentStatus(
            state="running",
            detail="This CYVORA API process is serving the health response.",
        )
    return StatusSnapshot(
        app_name=APP_NAME,
        version=APP_VERSION,
        phase=PHASE,
        environment=settings.environment,
        execution_mode=settings.execution_mode.value,
        live_trading_enabled=False,
        application=ComponentStatus(
            state="running",
            detail=f"{APP_NAME} {APP_VERSION} phase {PHASE}",
        ),
        database=database,
        backend=backend,
        gmgn=gmgn_configuration_status(settings),
        workers=workers,
        market_data=market_data,
        queue=queue,
        websocket=websocket,
    )


def gmgn_configuration_status(settings: Settings) -> ComponentStatus:
    """Report whether a GMGN key is configured. This does not call GMGN."""

    if settings.gmgn_api_key is None:
        return ComponentStatus(
            state="not_configured",
            detail="GMGN_API_KEY is not set. GMGN has not been contacted.",
        )
    return ComponentStatus(
        state="configured",
        detail=(
            "A GMGN API key is set. This health check does not call GMGN, "
            "so no market data was requested."
        ),
    )


def probe_backend_http(settings: Settings, timeout: float = 1.5) -> ComponentStatus:
    """Call the local health endpoint. Response bodies are not copied into the result."""

    url = f"http://{settings.api_host}:{settings.api_port}/health"
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
    except HTTPError as exc:
        status_code = int(exc.code)
    except TimeoutError:
        return ComponentStatus(state="offline", detail="The health request timed out.")
    except (URLError, OSError):
        return ComponentStatus(
            state="offline",
            detail="The CYVORA API is not accepting connections on the configured loopback port.",
        )
    if status_code == 200:
        return ComponentStatus(
            state="running",
            detail="The health endpoint responded with HTTP 200.",
        )
    if status_code == 503:
        return ComponentStatus(
            state="degraded",
            detail="The health endpoint responded with HTTP 503.",
        )
    return ComponentStatus(
        state="degraded",
        detail=f"The health endpoint responded with HTTP {status_code}.",
    )


async def probe_tcp(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return whether a TCP connection to a loopback port can be opened."""

    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (TimeoutError, OSError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        return True
    return True


def log_startup(settings: Settings) -> None:
    """Log a startup line that omits the database URL."""

    logger.info(
        "startup app=%s version=%s phase=%s environment=%s mode=%s "
        "host=%s port=%s database=%s gmgn=%s",
        APP_NAME,
        APP_VERSION,
        PHASE,
        settings.environment,
        settings.execution_mode.value,
        settings.api_host,
        settings.api_port,
        "configured" if settings.database_url else "not_configured",
        "configured" if settings.gmgn_api_key is not None else "not_configured",
    )
