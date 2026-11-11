"""Health response models."""

from __future__ import annotations

from pydantic import BaseModel

from domain.status import ComponentStatus, StatusSnapshot
from monitoring.health import overall_status


class ComponentStatusModel(BaseModel):
    state: str
    detail: str

    @classmethod
    def from_status(cls, status: ComponentStatus) -> ComponentStatusModel:
        return cls(state=status.state, detail=status.detail)


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str
    phase: str
    environment: str
    execution_mode: str
    live_trading_enabled: bool
    application: ComponentStatusModel
    database: ComponentStatusModel
    backend: ComponentStatusModel
    gmgn: ComponentStatusModel
    workers: ComponentStatusModel
    market_data: ComponentStatusModel
    queue: ComponentStatusModel
    websocket: ComponentStatusModel

    @classmethod
    def from_snapshot(cls, snapshot: StatusSnapshot) -> HealthResponse:
        return cls(
            status=overall_status(snapshot),
            app_name=snapshot.app_name,
            version=snapshot.version,
            phase=snapshot.phase,
            environment=snapshot.environment,
            execution_mode=snapshot.execution_mode,
            live_trading_enabled=snapshot.live_trading_enabled,
            application=ComponentStatusModel.from_status(snapshot.application),
            database=ComponentStatusModel.from_status(snapshot.database),
            backend=ComponentStatusModel.from_status(snapshot.backend),
            gmgn=ComponentStatusModel.from_status(snapshot.gmgn),
            workers=ComponentStatusModel.from_status(snapshot.workers),
            market_data=ComponentStatusModel.from_status(snapshot.market_data),
            queue=ComponentStatusModel.from_status(snapshot.queue),
            websocket=ComponentStatusModel.from_status(snapshot.websocket),
        )
