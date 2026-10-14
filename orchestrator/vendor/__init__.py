"""Byte-identical pins of playbook files this package IMPORTS.

`devops/vendor/` holds the helpers the images bake and RUN as scripts; these are the ones
the orchestrator loads in process, so they ship with the package rather than beside the
Dockerfiles. One manifest covers both (`devops/vendor/PINNED.json`) and one script writes
it, because a pin split across two homes is two things to forget.

Never edit a file here. Refresh it: `devops/vendor/update-vendored-helpers.sh`.
"""
