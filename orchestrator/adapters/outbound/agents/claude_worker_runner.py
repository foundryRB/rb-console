"""WorkerRunner over the Claude agent runtime. Executing a launch plan spawns the
worker: the single model step in the drive path. Building the invocation is
deterministic and tested; the actual spawn is guarded behind FC_DRIVE_LIVE and a
credential, so a run never fires without an explicit opt-in. FC_DRIVE_LIVE gates the
drive (spawning), separate from FC_LIVE which gates the in-cluster stores.
"""
from __future__ import annotations

import os
import subprocess

from orchestrator.domain.model.worker_launch import WorkerLaunch


def build_invocation(plan: WorkerLaunch) -> list[str]:
    """The deterministic command that spawns the worker for a launch plan: `claude`
    headless with the plan's prompt. The credential and MCP endpoints are supplied
    through the environment the runner sets, never on the command line.
    """
    return ["claude", "-p", plan.prompt]


class ClaudeWorkerRunner:
    def launch(self, plan: WorkerLaunch) -> str:
        argv = build_invocation(plan)
        if os.environ.get("FC_DRIVE_LIVE") != "1" or not plan.credential_ref:
            # Not opted in, or no credential: return a dry-run handle, spawn nothing.
            return f"dry-run:{plan.phase}:{plan.skill}"
        env = dict(os.environ)
        env["CLAUDE_CODE_OAUTH_TOKEN"] = plan.credential_ref
        proc = subprocess.Popen(argv, cwd=plan.repo, env=env)
        return f"live:{proc.pid}"
