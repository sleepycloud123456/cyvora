# Roadmap

Phase 9 is the current code. Later work stays closed until the user asks. Do not start it because a heading exists.

| Phase | Objective | State |
|---|---|---|
| 1 | Development environment and foundation | Merged. PostgreSQL 17 is installed and revision `0001_application_metadata` is applied. |
| 2 | GMGN read-only integration | Implemented. See `PROJECT_STATUS.md` and `docs/integrations/GMGN_API_RESEARCH.md`. |
| 3 | Radar and token intelligence | Implemented. Read-only. See `PROJECT_STATUS.md` and `docs/intelligence/SCORING.md`. |
| 4 | Core trading infrastructure, including a Nautilus proof of concept | Implemented. Paper only. See `docs/trading/NAUTILUS_MAPPING.md`. |
| 5 | Shield risk engine | Implemented. Paper decisions only. See `docs/trading/SHIELD.md`. |
| 6 | Backtesting and paper trading | Implemented. Simulation only. See `docs/trading/SIMULATION.md`. |
| 7 | Full CYVORA Terminal | Implemented. Paper pages only. See `docs/terminal/TERMINAL.md`. |
| 8 | Long-running local operations and a cloud design | Implemented locally. Nothing was deployed. See `docs/operations/OPERATIONS.md` and `docs/operations/CLOUD_DESIGN.md`. |
| 9 | Security review and live-trading readiness | Implemented as a closed gate. Live trading stays off without a separate authorization. See `docs/security/LIVE_READINESS.md`. |

Phase 9 reviews the controls, records the gaps, and adds a kill switch that cannot authorize a live order. A profile, a local analyst, and a completed checklist cannot approve one.
