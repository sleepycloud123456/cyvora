"""In-memory radar store for tests. It is not a stand-in for PostgreSQL."""

from __future__ import annotations

from decimal import Decimal

from intelligence.present import present_cycle
from intelligence.store import CycleSnapshot, StoredCycle, WatchRow


class MemoryRadarStore:
    """Keep cycles in process memory. Rows are not overwritten."""

    def __init__(self) -> None:
        self.cycles: list[StoredCycle] = []
        self.watches: dict[tuple[str, str], WatchRow] = {}
        self.audits: list[str] = []

    def save_cycle(self, cycle: StoredCycle) -> int:
        self.cycles.append(cycle)
        cycle_id = len(self.cycles)
        for chain, address, symbol in cycle.watch_suggestions:
            key = (chain, address)
            current = self.watches.get(key)
            if current is not None and current.active:
                self.audits.append(f"watch_suggestion_skipped {chain} {address}")
                continue
            self.watches[key] = WatchRow(
                chain=chain,
                address=address,
                symbol=symbol,
                note=(
                    "Radar suggested this token because the documented score "
                    "threshold was met. This is not an entry."
                ),
                source="radar_suggestion",
                active=True,
            )
            self.audits.append(f"watch_suggested {chain} {address}")
        self.audits.append(f"cycle_saved {cycle.status}")
        return cycle_id

    def latest_snapshot(self) -> CycleSnapshot | None:
        if not self.cycles:
            return None
        cycle_id = len(self.cycles)
        watches = tuple(self.watches.values())
        return present_cycle(cycle_id, self.cycles[-1], watches)

    def latest_liquidity(self, chain: str, address: str) -> Decimal | None:
        for cycle in reversed(self.cycles):
            for row in cycle.analyses:
                if row.chain == chain and row.address == address and row.liquidity is not None:
                    return row.liquidity
        return None

    def add_watch(
        self,
        chain: str,
        address: str,
        symbol: str | None,
        note: str,
        source: str,
    ) -> WatchRow:
        row = WatchRow(
            chain=chain,
            address=address,
            symbol=symbol,
            note=note[:500],
            source=source,
            active=True,
        )
        self.watches[(chain, address)] = row
        self.audits.append(f"watch_added {chain} {address}")
        return row

    def deactivate_watch(self, chain: str, address: str) -> bool:
        current = self.watches.get((chain, address))
        if current is None or not current.active:
            return False
        self.watches[(chain, address)] = WatchRow(
            chain=current.chain,
            address=current.address,
            symbol=current.symbol,
            note=current.note,
            source=current.source,
            active=False,
        )
        self.audits.append(f"watch_removed {chain} {address}")
        return True

    def list_watches(self) -> tuple[WatchRow, ...]:
        return tuple(self.watches.values())
