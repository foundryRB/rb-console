---
title: Run the console locally
id: DOC-FC-OPS-RUN-LOCALLY
type: Guide
status: Active
updated: "2026-10-08"
summary: Run the console on a workstation, in Docker or as a backend and a web dev server, with a local operator admitted on loopback.
---

The console runs on a workstation for development: the same backend and web client, with a local
operator admitted on loopback instead of the sign-in proxy. The backend reads the install facts and
the local operator from its environment and refuses to start without `FC_ORG` and
`FC_WORKER_IMAGE`; `.env.example` documents them.

## When to use

Developing or checking a change against the real application before it is released.

## Steps

1. Copy `.env.example` to `.env` at the repository root and set `FC_ORG`, `FC_WORKER_IMAGE` and
   `FC_LOCAL_OPERATOR`.
2. To run everything in containers: `docker compose -f devops/docker-compose.yml up --build`. The
   compose service loads `.env`; the web client and its same-origin `/api` proxy serve on
   `http://localhost:8000`.
3. To run without containers, load the same variables into the shell (`set -a; . ./.env; set +a`)
   and start the backend from a virtual environment with the test extras installed
   (`pip install -e ".[test]"`): `python -m orchestrator.adapters.inbound.http.run`, which listens
   on `http://127.0.0.1:8000`.
4. Start the web client from `frontend/` with `npm install` and `npm run dev`; it serves on
   `http://localhost:5173` and proxies `/api` to the backend.
5. Run the checks: `python -m pytest` for the backend, `csd-intent .` for the intent claims, and
   `npm test` in `docs/` for the documentation.

## Verify

- `GET /api/health` answers, and `GET /api/ready` answers once the first observation tick completes.
- The cockpit loads. The Fleet board fills only where the console's settings live in a cluster
  (`FC_LIVE=1`, with a kube context whose namespace holds a git identity assigned to the console
  role); otherwise it reads held.

## Read next

- [Drive from the published console](../publish/)
- [Configuration](../../reference/configuration/)
