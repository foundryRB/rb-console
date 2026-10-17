# syntax=docker/dockerfile:1

# Claude Code CLI on its Node runtime, so the co-pilot can drive the operator's Claude
# subscription headlessly (CLAUDE_CODE_OAUTH_TOKEN) the same sanctioned way the worker does.
FROM node:22-bookworm-slim AS claude
# The floor is set by the models, not a preference: the CLI must know every model the console
# offers, and while the install line below is unchanged a cached layer keeps whatever CLI it
# first resolved. A bare install on a Node 20 base once silently resolved to 2.1.197 (the last
# release whose engines still admitted 18/20), so the install is asserted by running it: a
# future engines bump fails the build here instead of shipping a runtime the base cannot execute.
RUN npm install -g "@anthropic-ai/claude-code@>=2.1.293" \
 && claude --version

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    FC_HOST=127.0.0.1 \
    FC_PORT=8000
COPY pyproject.toml ./
COPY orchestrator ./orchestrator
RUN pip install --no-cache-dir .
# kubectl: the in-cluster config and credential stores shell out to it, reading the
# pod ServiceAccount token via the in-cluster config automatically.
ARG TARGETARCH
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL "https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/${TARGETARCH}/kubectl" -o /usr/local/bin/kubectl \
 && chmod +x /usr/local/bin/kubectl \
 && rm -rf /var/lib/apt/lists/*
# The playbook's gate stamper, for the cockpit's Sign: write_gate runs THIS file over
# the fetched record instead of stamping frontmatter itself (REF-Delivery section 1,
# anti-pattern 30), so a console-signed gate is byte-identical to one closed by hand.
# Baked from the vendored pin (devops/vendor/, see its README: the playbook repo is
# private, a raw fetch 404s in a credential-less build). FC_STAMP_HELPER overrides
# the path locally.
COPY devops/vendor/stamp_gate.py /opt/foundry/stamp_gate.py
COPY devops/vendor/lifecycle.json /opt/foundry/lifecycle.json
COPY devops/vendor/artifact-handlers.json /opt/foundry/artifact-handlers.json
# Its sibling the record helper, for the cockpit's Re-open: un-signing a gate re-opens
# the record for work, and the frontmatter block that says so is this helper's to write.
# Running it is what demotes `status:` and clears the previous attempt's `reviewed:` /
# `finished:` / `attests:`, so no later stamp can close the new attempt's gate over the
# old attempt's review (#77). FC_REACH_HELPER overrides the path locally.
COPY devops/vendor/reach_gate.py /opt/foundry/reach_gate.py
# The scratch helper too: the console's own establish act writes the skeleton and
# the customer request over the API, and it takes those bytes from the helper
# rather than keeping a second copy of them here.
COPY devops/vendor/establish_scratch.py /opt/foundry/establish_scratch.py
# The Claude Code CLI + its Node runtime, for the subscription-backed co-pilot chat.
# node lands in /usr/local/bin and the package under /usr/local/lib/node_modules; the
# relative `claude` symlink resolves once both are copied. python/kubectl are untouched.
COPY --from=claude /usr/local/bin/ /usr/local/bin/
COPY --from=claude /usr/local/lib/node_modules/ /usr/local/lib/node_modules/
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()" || exit 1
CMD ["python", "-m", "orchestrator.adapters.inbound.http.run"]
