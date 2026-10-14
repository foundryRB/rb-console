# Foundry Console

> The **optional**, published pane onto the Foundry: watch any delivery end-to-end, and (when you
> want to) drive it. It sits **on top of** tools that never know it exists. **Never load-bearing;
> always derived state.**

The Foundry is "the one factory that builds, ships, runs, and watches software." It runs the
**Delivery Line** (five phases, four gates) on a **Ground**. The Console is the surface that *watches*
the Line and *federates* driving it into one place. It is itself just another app the Foundry
ships.

**The whole model lives in [`docs/`](docs/src/content/docs/index.md).** Start there. In short:

- **Optional & non-central.** Every phase, gate, and tool is fully doable without the Console: by
  hand with Claude + the delivery skills, or by the headless one-shot path. Delete the Console and no
  delivery notices. ([principles](docs/src/content/docs/principles.md))
- **Derived delivery state.** The set of deliveries *is* the set of Git repos with a `.delivery/`;
  progress is derived from committed records. The persistent archive retains run evidence and command receipts. ([delivery](docs/src/content/docs/modules/delivery.mdx))
- **Deterministic core; agents at the edges.** The orchestrator is code: it reads `.delivery/`,
  checks gates, and compiles the line into an Argo Workflow its **own single-namespace executor** runs;
  it never *is* the worker. Each step runs a worker pod, an agent chosen per run that self-validates and
  exits non-zero on failure, and it is the only thing that runs a skill. ([execution](docs/src/content/docs/modules/execution.mdx))
- **Published, from any PC.** Your machine is just a driver: a browser. The playbook, tools,
  workers, and state all live on the Ground. ([driving it](docs/src/content/docs/operations/publish.md))
- **Three worker credentials, none in git.** A per-run model credential (which model the worker thinks
  with, cited by `credential_ref`), plus the machine-user git identity assigned to that phase (no shared
  or default one) and per-door MCP access (Basic auth, one credential per door) held as Console-side
  runtime settings, editable live and persisted to ConfigMaps + Secrets.
  ([settings](docs/src/content/docs/modules/settings.mdx))

## Run with Docker

```
docker compose -f devops/docker-compose.yml up --build
```

Serves the static web client and its same-origin `/api` proxy on http://localhost:8000. The backend binds loopback within the shared container network. The
Console serves no `/mcp` - it only orchestrates what the operator could do manually, and no
model pushes its buttons. Delivery workspaces persist in the data volume. `.env.example`
documents install facts and operator admission. Local commands require an explicit `FC_LOCAL_OPERATOR` and loopback access.

## Develop without Docker

Backend (hexagonal FastAPI, port 8000):

```
python -m venv .venv
.venv\Scripts\activate            # POSIX: source .venv/bin/activate
pip install -e ".[test]"
python -m orchestrator.adapters.inbound.http.run    # http://127.0.0.1:8000
```

Frontend (Vite dev server, proxies `/api` to the backend):

```
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Test, audit, and the read-only CLI:

```
python -m pytest                  # backend unit + integration
csd-intent .                      # validate intent.yaml + coverage
python -m orchestrator status <repo>
```

## Layout

| Directory | Responsibility |
| --- | --- |
| `orchestrator/domain/` | Delivery rules and normalized records |
| `orchestrator/application/` | Capability use cases and their ports |
| `orchestrator/adapters/` | HTTP, repository, executor and persistence boundaries |
| `frontend/src/` | Generated Models, ViewModels and Atomic Views |
| `devops/` | Web, API and worker images, plus the pinned playbook bundle |
| `k8s/` | Helm deployment assembly |
| `docs/` | Published documentation |
| `tests/` | Backend behavior and architecture checks |

## Contracts and checks

The backend publishes typed feature APIs. The browser generates its Models from the committed OpenAPI seed and separates state, actions and presentation selectors in its ViewModels. Views render the backend's lifecycle and command projections.

```bash
python tools/export_openapi.py
cd frontend
npm run models:generate
npm run lint
npm run build
npm run e2e
```

Observation runs independently of commands. Metadata pages read snapshots with freshness and coverage; explicitly selected content uses bounded readers. Commands check trusted authority and fresh evidence, then record durable dispatch intent before an external write. An unknown result remains visible across restarts and cannot be replayed automatically.

The default lifecycle, deterministic helpers and worker skills are imported from one playbook revision. See [the pin contract](devops/vendor/README.md) and [the delivery module](docs/src/content/docs/modules/delivery.mdx).

## Commits

Every commit follows the platform's commit convention: a Conventional Commit
subject and no co-author trailer. CI derives the version from the type and
blocks release otherwise. The convention is documented on the platform
portal's GitOps delivery page, under "Commit convention"; the committed
`.pre-commit-config.yaml` checks it locally once installed (`pre-commit install`).
