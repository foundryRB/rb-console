"""Server-owned action names for each mutating capability."""

from __future__ import annotations

COMMAND_ACTIONS = {
    "pause_app": "studios.pause",
    "resume_app": "studios.resume",
    "set_target_selection": "settings.target",
    "set_delivery_config": "delivery.configure",
    "set_delivery_model": "settings.delivery_model",
    "set_delivery_timeout": "settings.delivery_timeout",
    "reopen": "delivery.reopen",
    "start": "delivery.start",
    "establish": "delivery.establish",
    "close_line": "delivery.close",
    "advance": "delivery.advance",
    "drive": "delivery.drive",
    "stop_run": "runs.stop",
    "resume_run": "runs.resume",
    "sign_gate": "delivery.sign",
    "set_driver_config": "settings.driver",
    "declare_promotion_target": "promotion.declare",
    "promotion_drive": "promotion.drive",
    "maintenance_drive": "maintenance.drive",
    "maintenance_merge": "maintenance.merge",
    "maintenance_comment": "maintenance.comment",
    "maintenance_close_ticket": "maintenance.close",
    "maintenance_switch_to_delivery": "maintenance.switch_to_delivery",
    "set_git_identity": "settings.git_identity",
    "delete_git_identity": "settings.delete_git_identity",
    "set_git_roles": "settings.git_roles",
    "set_pair_credential": "settings.pair_credential",
    "delete_pair_credential": "settings.delete_pair_credential",
    "set_agent": "settings.agent",
    "delete_agent": "settings.delete_agent",
    "apply_agent_to_driver": "settings.apply_driver",
    "apply_agent_to_delivery": "settings.apply_delivery",
    "set_setting": "settings.save",
    "set_team": "settings.team",
    "delete_team": "settings.delete_team",
    "assign_project": "settings.assign_project",
}

#: The actions an admin alone holds: setting up the teams and assigning projects to them,
#: and every installation-wide setting (the home co-pilot, git identities and their roles,
#: pair credentials, the named settings), which serves every team at once.
ADMIN_ACTIONS = frozenset({
    "settings.team", "settings.delete_team", "settings.assign_project",
    "settings.driver", "settings.apply_driver", "settings.git_identity",
    "settings.delete_git_identity", "settings.git_roles", "settings.pair_credential",
    "settings.delete_pair_credential", "settings.save",
})
