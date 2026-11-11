# Roadmap

Phase 7 is the current code. Later phases are listed so the boundary stays visible. Do not start one because its heading exists.

| Phase | Objective | State |
|---|---|---|
| 1 | Development environment and foundation | Merged. PostgreSQL 17 is installed and revision `0001_application_metadata` is applied. |
| 2 | GMGN read-only integration | Implemented. See `PROJECT_STATUS.md` and `docs/integrations/GMGN_API_RESEARCH.md`. |
| 3 | Radar and token intelligence | Implemented. Read-only. See `PROJECT_STATUS.md` and `docs/intelligence/SCORING.md`. |
| 4 | Core trading infrastructure, including a Nautilus proof of concept | Implemented. Paper only. See `docs/trading/NAUTILUS_MAPPING.md`. |
| 5 | Shield risk engine | Implemented. Paper decisions only. See `docs/trading/SHIELD.md`. |
| 6 | Backtesting and paper trading | Implemented. Simulation only. See `docs/trading/SIMULATION.md`. |
| 7 | Full CYVORA Terminal | Implemented. Paper pages only. See `docs/terminal/TERMINAL.md`. |
| 8 | Long-running local operations and a cloud design | Not started. No cloud deploy. |
| 9 | Security review and live-trading readiness | Not started. Live trading stays off without a separate authorization. |

Phase 7 is the completed terminal. It reads stored paper, radar, Shield, and simulation rows. A profile and a local analyst cannot approve an order. Phase 8 has not started.
