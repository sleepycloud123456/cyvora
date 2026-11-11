"""ORM models imported for Alembic metadata discovery."""

from database.models.application import ApplicationMetadata
from database.models.base import Base
from database.models.radar import (
    AuditEvent,
    IndicatorSignal,
    LiquiditySnapshot,
    RadarCycle,
    SecurityAssessmentRow,
    SmartMoneyEvent,
    Token,
    TokenAnalysis,
    TokenCandle,
    TokenObservation,
    WatchlistItem,
    WhaleEvent,
)
from database.models.shield import (
    ShieldCampaign,
    ShieldControl,
    ShieldDaily,
    ShieldDecision,
    ShieldEmergency,
    ShieldNoticeRow,
    ShieldStop,
)
from database.models.simulation import (
    SimulationAssumption,
    SimulationBar,
    SimulationDataset,
    SimulationMember,
    SimulationRun,
    SimulationSignalRow,
)
from database.models.trading import (
    TradingInstrument,
    TradingOrder,
    TradingOrderEvent,
    TradingPosition,
    TradingReconciliation,
    TradingStrategy,
)

__all__ = [
    "ApplicationMetadata",
    "AuditEvent",
    "Base",
    "IndicatorSignal",
    "LiquiditySnapshot",
    "RadarCycle",
    "SecurityAssessmentRow",
    "ShieldCampaign",
    "ShieldControl",
    "ShieldDaily",
    "ShieldDecision",
    "ShieldEmergency",
    "ShieldNoticeRow",
    "ShieldStop",
    "SimulationAssumption",
    "SimulationBar",
    "SimulationDataset",
    "SimulationMember",
    "SimulationRun",
    "SimulationSignalRow",
    "SmartMoneyEvent",
    "Token",
    "TokenAnalysis",
    "TokenCandle",
    "TokenObservation",
    "TradingInstrument",
    "TradingOrder",
    "TradingOrderEvent",
    "TradingPosition",
    "TradingReconciliation",
    "TradingStrategy",
    "WatchlistItem",
    "WhaleEvent",
]
