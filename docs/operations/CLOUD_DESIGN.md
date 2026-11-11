# Cloud design

Date: 2026-11-11. Nothing in this document was deployed. No cloud account, container registry, VPS, or managed database was created. The monthly spend remains €0. See `docs/operations/COST_ESTIMATE.md`.

## Process split

The local processes already have separate entry points, which is the split a later host would keep:

| Process | Entry | Stays |
|---|---|---|
| CYVORA Terminal | `cyvora-desktop` | On the Windows PC. It is the control panel. |
| CYVORA API | `cyvora-api` | Loopback today. A remote API needs a new authentication and bind review. |
| Supervisor | `cyvora-supervisor` | One tick by default. A long run is an explicit `--ticks 0`. |
| PostgreSQL | Local 17 | The system of record. A managed server is a separate decision. |

The supervisor calls the same recovery, paper book, and radar cycle the API uses. Moving it later does not require a second trading implementation. It still cannot submit a live order.

## What a later host would have to change

These stay rejected in the current settings, on purpose:

- `CYVORA_ENVIRONMENT` other than `local`.
- An API host other than `127.0.0.1`, `localhost`, or `::1`.
- `LIVE`, `LIVE_LOCKED`, and `LIVE_AUTHORIZED`.
- `GMGN_PRIVATE_KEY`. It is not loaded.

A cloud worker would also need a decision for secret storage, backup location, who can reach the API, and how the desktop authenticates to a non-loopback address. The desktop's 15-second probe is a loopback health check. It is not a remote session.

## Prepared files

`deploy/cloud/Dockerfile` is a design image. It does not copy `.env`. `deploy/cloud/.dockerignore` excludes `.env`, logs, backups, diagnostics, and secrets. `deploy/cloud/docker-compose.yml` puts the API behind the `manual` profile and sets `network_mode: none`, so `docker compose up` starts nothing. The compose file does not contain a database URL or a token.

Phase 8 did not run `docker build` or `docker compose`. Docker Desktop is not required on this PC.

`deploy/windows/cyvora-supervisor.xml` is a disabled task template. `scripts/register_supervisor_task.ps1` does not register it unless `-ConfirmInstall` is passed. That flag was not used.

## Cost

A small VPS and a managed database can fit inside the €20–50 planning band, and both add exposure the local PC does not have. They are not selected. GMGN stays on the free bucket. No RPC provider was added.

## Not in this phase

- No image was published.
- No host was opened on a public address.
- No live trading path was added.
- Phase 9 security review and live-trading readiness were not started.
