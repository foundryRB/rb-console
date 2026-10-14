"""FleetChat over consumed application contracts."""
from __future__ import annotations

from orchestrator.application.ports.inbound.projections.fleet import FleetPort
from orchestrator.application.ports.inbound.projections.studios import StudiosPort
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.driver_agent import DriverAgent
from orchestrator.application.services.definitions import REF_DELIVERY_DIGEST
from orchestrator.domain.model.command_context import CommandContext


class FleetChat:

    def __init__(self, *, config: ConfigStore | None, driver: DriverAgent | None, cap_fleet: FleetPort, cap_studios: StudiosPort) -> None:
        self.config = config
        self.driver = driver
        self.cap_fleet = cap_fleet
        self.cap_studios = cap_studios

    def execute(self, message: str, history=None, *, viewer: CommandContext | None = None) -> dict:
        """One turn with the HOME co-pilot: the Console-wide driver agent - the operator's
        own endpoint pick in Settings (any Anthropic-compatible base_url + key: the deepseek
        slot) - reasoning over the whole floor: every project's delivery state, onboarding,
        live status, and the studios' health. It advises and names the exact next act in the
        console; it executes nothing - the operator stays the one who presses. Degrades to a
        not-configured hint until the driver credential exists (never fabricates a reply).
        The floor is the viewer's: a team member's turn is grounded in its teams' projects."""
        if self.driver is None or self.config is None:
            return {'reply': None, 'configured': False, 'model': None}
        d = self.config.get_setting('driver')
        credential = self.config.get_secret('driver')
        if not credential:
            return {'reply': None, 'configured': False, 'model': None}
        floor = [f"- {it.name}: delivery={it.delivery_status or 'none'}" + (f' (phase: {it.delivery_phase})' if it.delivery_phase else '') + f", onboarded={('yes' if it.onboarded else 'no')}, live={it.live or 'no'}" for it in self.cap_fleet.execute(include_hidden=False, viewer=viewer)[:60]]
        studios = [f"- {s.studio}: {('reachable' if s.reachable else 'UNREACHABLE')}" for s in self.cap_studios.execute()]
        system = '\n'.join(["You are the Foundry Console's home co-pilot, advising the operator over their whole floor.", REF_DELIVERY_DIGEST, 'The floor (every project):', *floor, 'The studios:', *studios, "The console's acts, all operator-pressed: open a project's cockpit; Drive (compile the remaining line to the executor); Drive from a chosen phase (adopting upstream studio work); sign an awaiting gate; re-open a signed phase; pause/resume a live app; start a new delivery (New delivery, with the customer's verbatim request).", 'Advise concisely, with ASCII punctuation only (no em-dashes), and point at the exact next act and where it lives. You never execute anything yourself: you are toolless by design, so never attempt a tool call and never claim you ran anything.'])
        messages = list(history or []) + [{'role': 'user', 'content': message}]
        reply = self.driver.chat(system, messages, credential=credential, model=d.get('model', ''), base_url=d.get('base_url', ''))
        return {'reply': reply, 'configured': True, 'model': d.get('model') or d.get('agent') or 'driver'}
