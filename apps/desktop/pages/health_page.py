"""System health page for the foundation checks."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from apps.desktop.components.disclosure import DetailDisclosure
from apps.desktop.components.status_card import StatusCard
from config.settings import PHASE, Settings
from domain.enums import ExecutionMode
from domain.status import StatusSnapshot


class HealthPage(QWidget):
    """Shows the same verified checks as the dashboard, plus the interpreter."""

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(22)
        mode = "PAPER" if settings.execution_mode is ExecutionMode.PAPER else "READ-ONLY"
        self.summary = QLabel(
            f"Phase {PHASE}. Mode {mode}. Python {sys.version.split()[0]}. "
            "Live trading is locked. Worker, market-data, queue, and connection "
            "cards read local status. This page does not start the API or a worker, "
            "and it does not request market data."
        )
        self.summary.setObjectName("Notice")
        self.summary.setWordWrap(True)
        self.application_card = StatusCard("Application")
        self.database_card = StatusCard("Database")
        self.backend_card = StatusCard("Backend")
        self.gmgn_card = StatusCard("GMGN")
        self.workers_card = StatusCard("Workers")
        self.market_data_card = StatusCard("Market data")
        self.queue_card = StatusCard("Queue")
        self.connection_card = StatusCard("Connection")
        self.kill_switch_card = StatusCard("Kill switch")
        primary = QHBoxLayout()
        primary.setSpacing(16)
        primary.addWidget(self.database_card)
        primary.addWidget(self.backend_card)
        primary.addWidget(self.gmgn_card)
        primary.addWidget(self.kill_switch_card)
        self.reconnect = QLabel(
            "The desktop probes the loopback API again every 15 seconds. It does not start the API."
        )
        self.reconnect.setObjectName("Notice")
        self.reconnect.setWordWrap(True)
        self.freshness = QLabel("Stored radar freshness has not been read.")
        self.freshness.setObjectName("Notice")
        self.freshness.setWordWrap(True)
        secondary = QGridLayout()
        secondary.setSpacing(16)
        for index, card in enumerate(
            (
                self.application_card,
                self.workers_card,
                self.market_data_card,
                self.queue_card,
                self.connection_card,
            )
        ):
            secondary.addWidget(card, index // 3, index % 3)
        secondary_host = QWidget()
        secondary_host.setLayout(secondary)
        self.details = DetailDisclosure("Details")
        self.details.add(self.summary)
        self.details.add(secondary_host)
        self.details.add(self.reconnect)
        self.details.add(self.freshness)
        layout.addLayout(primary)
        layout.addWidget(self.details)
        layout.addStretch(1)

    def show_freshness(self, text: str) -> None:
        self.freshness.setText(text)

    def set_checking(self) -> None:
        for card in self._cards():
            card.set_status("Checking...", "A background status check is running.")

    def set_idle(self) -> None:
        for card in self._cards():
            card.set_status("Not checked", "The status probe is idle in this session.")

    def show_probe_failure(self, message: str) -> None:
        self.database_card.set_status("unknown", message)
        self.backend_card.set_status("unknown", message)
        self.gmgn_card.set_status("unknown", message)
        self.workers_card.set_status("unknown", message)
        self.market_data_card.set_status("unknown", message)
        self.kill_switch_card.set_status("unknown", message)

    def note_reconnect(self) -> None:
        self.reconnect.setText("Probing the loopback API again. This window does not start it.")

    def apply_snapshot(self, snapshot: StatusSnapshot) -> None:
        self.application_card.apply(snapshot.application)
        self.database_card.apply(snapshot.database)
        self.backend_card.apply(snapshot.backend)
        self.gmgn_card.apply(snapshot.gmgn)
        self.workers_card.apply(snapshot.workers)
        self.market_data_card.apply(snapshot.market_data)
        self.queue_card.apply(snapshot.queue)
        self.connection_card.apply(snapshot.websocket)
        self.kill_switch_card.apply(snapshot.kill_switch)
        if snapshot.backend.state == "offline":
            self.reconnect.setText(
                "The API is offline. The desktop will probe loopback again. "
                "It does not start the API."
            )
        elif snapshot.backend.state == "running":
            self.reconnect.setText(
                "The API responded. The desktop will keep probing loopback. "
                "It does not start the API."
            )

    def _cards(self) -> tuple[StatusCard, ...]:
        return (
            self.application_card,
            self.database_card,
            self.backend_card,
            self.gmgn_card,
            self.workers_card,
            self.market_data_card,
            self.queue_card,
            self.connection_card,
            self.kill_switch_card,
        )
