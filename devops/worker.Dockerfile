# syntax=docker/dockerfile:1
# The worker executes one phase with the pinned playbook bundle and its canonical
# delivery helpers. Node 22 runs the headless Claude runtime; Debian bookworm
# supplies the deterministic Python gates, Git tooling and browser libraries.
FROM node:22-bookworm-slim
# Skills run their own Python gates and the intent CLI. GitHub CLI handles repository
# acts; each delivery installs its own application dependencies. Assert the agent CLI
# can execute on this Node runtime while building the image. The floor is what moves the CLI:
# the CLI must know every model the console offers, and while the install line below is
# unchanged a cached layer keeps whatever CLI it first resolved.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates jq curl python3 python3-pip \
 && install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends gh \
 && pip install --no-cache-dir --break-system-packages "csd-intent>=0.6.0,<0.7" "PyYAML>=6" \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g "@anthropic-ai/claude-code@>=2.1.293" \
 && claude --version
# Install browser system libraries at build time because workers run without root.
# Each delivery installs the browser binary pinned by its own test dependencies.
RUN npx --yes playwright@1.61.1 install-deps chromium \
 && rm -rf /var/lib/apt/lists/*
# The immutable playbook bundle, canonical lifecycle and gate helpers share the
# vendored revision. Workers use local skills and verify REVISION before cloning.
COPY devops/vendor/playbook.tar.gz /opt/foundry/playbook.tar.gz
COPY devops/vendor/lifecycle.json /opt/foundry/lifecycle.json
COPY devops/vendor/artifact-handlers.json /opt/foundry/artifact-handlers.json
RUN mkdir -p /opt/foundry/playbook \
 && tar -xzf /opt/foundry/playbook.tar.gz -C /opt/foundry/playbook \
 && rm /opt/foundry/playbook.tar.gz
COPY devops/vendor/establish_scratch.py /opt/foundry/establish_scratch.py
COPY devops/vendor/reach_gate.py /opt/foundry/reach_gate.py
COPY devops/vendor/stamp_gate.py /opt/foundry/stamp_gate.py
# The worker's own run-figures writer (issue #115): reads the agent stream's result event and
# records the run's tokens, cost, model and span into the phase record as `run_*` keys. The
# entrypoint's, not the playbook's, so it lives beside the entrypoint and carries no pin.
COPY devops/record_run.py /opt/foundry/record_run.py
# The agent's permission-prompt tool (issue #212): allows every ask the harness raises, so a key
# whose organisation policy turns bypass off still runs headless. The entrypoint's, beside it.
COPY devops/approver.py /opt/foundry/approver.py
COPY orchestrator/adapters/outbound/records/yaml_record_parser.py /opt/foundry/orchestrator/adapters/outbound/records/yaml_record_parser.py
COPY orchestrator/domain/model/frontmatter.py /opt/foundry/orchestrator/domain/model/frontmatter.py
COPY orchestrator/domain/model/record_status.py /opt/foundry/orchestrator/domain/model/record_status.py
COPY orchestrator/domain/model/delivery_record.py /opt/foundry/orchestrator/domain/model/delivery_record.py
COPY devops/worker-entrypoint.sh /usr/local/bin/worker-entrypoint.sh
RUN chmod +x /usr/local/bin/worker-entrypoint.sh
# Run as a non-root user: Claude Code refuses --dangerously-skip-permissions under
# root/sudo, and the worker is a headless autonomous agent that needs that flag. The
# node image already ships a `node` user (uid 1000) with a home dir; own /work with it
# (its clone + scratch) so the agent has a writable tree and HOME for its own state.
RUN mkdir -p /work && chown -R node:node /work
USER node
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/worker-entrypoint.sh"]
