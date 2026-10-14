"""DriverAgent: the Console-side co-pilot the operator chats with per phase. It is the
DRIVER (distinct from the per-run worker that autonomously executes a phase): a model the
Console itself calls, with the delivery's context and any files the operator referenced.

The service resolves which credential/model to use (the delivery's own, persisted by slug,
or the global Settings default) and passes them in; this adapter just runs the model. It
reads config the SAME way the worker does (devops/worker-entrypoint.sh) - every route runs
through Claude Code, no hand-rolled calls:

  * a subscription setup-token -> the Claude subscription (CLAUDE_CODE_OAUTH_TOKEN);
  * an sk-ant-api... key        -> the metered Anthropic API (ANTHROPIC_API_KEY);
  * a base_url                  -> any compatible endpoint (ANTHROPIC_BASE_URL, with the
                                   credential sent as BOTH x-api-key and Bearer so either
                                   gateway auth convention accepts it).

The default model is the cheapest Claude (Haiku).
"""
from __future__ import annotations

import json
import os
import subprocess


class HttpDriverAgent:
    def chat(
        self,
        system: str,
        messages: list[dict],
        *,
        credential: str,
        model: str = "",
        base_url: str = "",
        max_tokens: int = 1024,
        timeout: int = 180,
    ) -> str:
        if not credential:
            raise RuntimeError("no driver credential")
        model = model or "haiku"  # cheapest; Claude Code maps the alias to the latest Haiku
        # --tools "" ENFORCES the advisory contract: the co-pilot is toolless by design, and
        # merely saying so in the grounding is not enough - observed live, an ungrounded turn
        # attempted tool calls and burned its 180s budget narrating the denials. With no tools
        # offered, the whole turn spends itself on the answer.
        argv = ["claude", "-p", self._render(messages), "--append-system-prompt", system,
                "--output-format", "json", "--model", model, "--tools", ""]
        env = {**os.environ, "HOME": "/tmp", "CLAUDE_CONFIG_DIR": "/tmp/.claude"}
        # Exactly the worker's auth selection (worker-entrypoint.sh step 3).
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
            # A compatible gateway may read the credential from either header convention:
            # x-api-key (ANTHROPIC_API_KEY - the real Anthropic convention, and OpenCode Zen)
            # or Authorization: Bearer (ANTHROPIC_AUTH_TOKEN - DeepSeek and OAuth proxies). The
            # adapter can't know which, so it supplies both and the gateway ignores the header it
            # does not use. Sending only Bearer 401'd against Zen's x-api-key /v1/messages
            # ("Missing API key"), stalling the co-pilot on that endpoint.
            env["ANTHROPIC_AUTH_TOKEN"] = credential
            env["ANTHROPIC_API_KEY"] = credential
        elif credential.startswith("sk-ant-api"):
            env["ANTHROPIC_API_KEY"] = credential  # a metered API key
        else:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = credential  # a subscription setup-token

        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, cwd="/tmp", check=False)
        except subprocess.TimeoutExpired:
            # The exception's text is the command line, which carries the rendered transcript
            # and the grounding; the turn records only that the driver ran out of time.
            raise RuntimeError(f"Driver timed out after {timeout}s") from None
        if proc.returncode != 0:
            diagnostic = (proc.stderr or proc.stdout or "").lower()
            if any(marker in diagnostic for marker in self._AUTH_FAILURE_MARKERS):
                raise RuntimeError("Driver authentication failed (401/403)")
            raise RuntimeError("Driver execution failed")
        out = proc.stdout.strip()
        try:
            data = json.loads(out)
            return data.get("result") or data.get("text") or out
        except json.JSONDecodeError:
            return out

    # A credential is only ever checked for PRESENCE (is a Secret seated?), never for
    # VALIDITY, until a worker pod runs it - so a wrong/expired key first surfaces as a
    # build-ship 401, hours into a delivery (issue #30). This runs the same auth
    # selection as chat() above, as a minimal one-turn preflight with a short timeout, so
    # a pass here means a pass at build-ship.
    _AUTH_FAILURE_MARKERS = (
        "401", "403", "invalid api key", "invalid x-api-key", "invalid bearer token",
        "authentication_error", "unauthorized", "permission denied", "invalid_api_key",
    )

    def validate(self, credential: str, model: str = "", base_url: str = "") -> bool | None:
        """Exercise `credential` with a minimal 1-token turn against the resolved endpoint.
        True on a working credential, False on an explicit auth failure (401/403 - fail-
        closed on an answer), None on a transport failure or timeout (fail-open: an
        unreachable endpoint is not evidence the credential itself is wrong)."""
        if not credential:
            return False
        try:
            self.chat(
                "Reply with the single word: ok.",
                [{"role": "user", "content": "ping"}],
                credential=credential, model=model, base_url=base_url, timeout=20,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        except RuntimeError as exc:
            message = str(exc).lower()
            if any(marker in message for marker in self._AUTH_FAILURE_MARKERS):
                return False
            return None
        return True

    @staticmethod
    def _render(messages: list[dict]) -> str:
        """Fold the conversation into a single prompt (Claude Code -p is one turn)."""
        return "\n\n".join(
            f"{'User' if m.get('role') == 'user' else 'Assistant'}: {m.get('content', '')}"
            for m in messages
        )
