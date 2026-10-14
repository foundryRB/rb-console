#!/usr/bin/env bash
# One phase of a delivery, run headless by the executor. Every input comes from the
# environment the compiler set, plus the phase prompt as $1. The worker exits 0 only
# when the phase's record is present and non-empty (the domain's completeness contract:
# resolver.derive_from_records treats a committed record as the phase being done); any
# failure exits non-zero so the executor retries it (and, past its budget, parks the
# phase in a degraded stop).
#
# The shape is fixed: clone, mount the scratch worktree, point the agent at the owner
# MCP doors, run the per-run agent, self-validate the record, push the scratch ref. The
# exact agent flags and MCP URL scheme are tuned against a live run; adjust here, not in
# the deterministic engine.
set -euo pipefail

# The step's output (issue #181), a file the executor reads back onto the Workflow object as
# the worker template's `refusal` output parameter, so it outlives the pod:
#   FC_REFUSAL_FILE - the last refusal line a stopping step printed (stop_line below). The
#     cockpit names it beside a failed run, instead of a bare exit code or nothing.
# The path is the compiler's (worker_template.py names the same one); overridable for the suite.
FC_REFUSAL_FILE="${FC_REFUSAL_FILE:-/tmp/fc-refusal}"
rm -f "$FC_REFUSAL_FILE" 2>/dev/null || true
# Say why the step stops, on stderr as always and into the refusal output. Every exit below
# that ends a step on purpose calls it; the trap names an exit nothing explained.
stop_line() {
  printf '%s\n' "$1" >&2
  printf '%s\n' "$1" > "$FC_REFUSAL_FILE" 2>/dev/null || true
}
worker_exit() {
  local code="$1"
  rm -f "${agent_raw:-}" "${agent_err:-}" "${approvals:-}" 2>/dev/null || true
  if [ "$code" -ne 0 ] && [ ! -s "$FC_REFUSAL_FILE" ]; then
    printf '%s\n' "worker: ${FC_PHASE:-the step} exited ${code} with no refusal line; the step's log has the rest" > "$FC_REFUSAL_FILE" 2>/dev/null || true
  fi
}
trap 'worker_exit $?' EXIT

export FC_PLAYBOOK_DIR="${FC_PLAYBOOK_DIR:-/opt/foundry/playbook}"
if [ -n "${FC_PLAYBOOK_REF:-}" ]; then
  if [ ! -f "$FC_PLAYBOOK_DIR/REVISION" ] || [ "$(cat "$FC_PLAYBOOK_DIR/REVISION")" != "$FC_PLAYBOOK_REF" ]; then
    stop_line "worker: the installed playbook revision does not match FC_PLAYBOOK_REF"
    exit 1
  fi
fi

# Terminal-stop exit codes the executor must NOT retry - a blind retry can neither clear a
# blocker nor shrink an oversized ticket. Kept in sync with run_policy.py's terminal exits,
# which tells Argo not to retry these codes. Every other non-zero exit is transient and retried.
#   64 - degraded stop: a record stamped status: aborted (a missing authorization, a
#        deterministic blocker the agent must not work around).
#   65 - delivery-scale stop: a resolve worker judged the ticket too big for a maintenance
#        scope and punted it to a delivery line (issue #13); see the sentinel check below.
#   66 - wrong-repo stop: a resolve worker found the ticket's fix lives in a DIFFERENT repo,
#        so no PR can open here (issue #35). 65 is about a ticket's SIZE, 66 about its LOCUS.
#   67 - session-limit stop: the agent run hit the model's own session/usage limit (issue #40).
#        Terminal because the wall is a rolling window that only the clock reopens, so retrying
#        immediately just burns the budget against a still-closed door; park and let a re-drive
#        after the reset be the answer (see step 3a). This is the MODEL's wall, kept apart from
#        the degraded 64 so the console reads which stop it was.
#   68 - stamp-refused stop: a one-shot gate's stamper refused to close the gate over a
#        passing fresh-eyes review (issue #181; step 5). The work and its review stand; what
#        refused is the closure (a studio that is down, an export it would not serve, a
#        record the stamper will not close), and re-running the whole phase meets the same
#        wall. The review is recorded and the refusal written on the record, so the line
#        reads awaiting its gate and the operator's Sign is the act that closes it.
# test_exit_contract.py asserts these five equal run_policy.py's table - the "kept in sync"
# above is a machine gate, not a promise.
DEGRADED_EXIT=64
DELIVERY_SCALE_EXIT=65
WRONG_REPO_EXIT=66
SESSION_LIMIT_EXIT=67
STAMP_REFUSED_EXIT=68

# The ticket labels the two park stops key on. A park is authorized by the DURABLE record on
# GitHub - the label the agent applied before it asked to park - so these are read here as
# well as by the pane and the resolver; test_exit_contract.py holds all three in sync.
DELIVERY_SCALE_LABEL="foundry-delivery-scale"
WRONG_REPO_LABEL="foundry-wrong-repo"

# Does this run's ticket carry $1 on GitHub? A park stop demands it: the sentinel is one
# process asking another to park, the label is the agent's recorded finding, and only the
# label survives the pod. No ticket, no gh, or an unreachable API answers no, so an
# unverifiable park degrades to the ordinary contracts below rather than parking a run that
# may have done real work.
ticket_has_label() {
  [ -n "${FC_TICKET:-}" ] || return 1
  gh issue view "$FC_TICKET" --repo "$repo_path" --json labels \
    --jq '[.labels[].name] | index("'"$1"'") != null' 2>/dev/null | grep -q true
}

PROMPT="${1:?worker prompt required}"
# FC_RECORD is deliberately NOT required: learn leaves no record (its stamp lands in the
# journal's frontmatter), so its value is empty and the validation section branches on that.
: "${FC_REPO:?FC_REPO required}" "${FC_PHASE:?}"
# A record-leaving delivery phase cannot run without its line's scratch ref: the record it
# must write lives on that ref (mounted at .delivery/ in step 1b) and the push names the
# ref explicitly. An empty FC_SCRATCH_REF here is a mis-compile - fail fast and plainly,
# before an agent burns its whole turn and dies late on a malformed refspec.
if [ -n "${FC_RECORD:-}" ] && [ -z "${FC_SCRATCH_REF:-}" ]; then
  stop_line "worker: FC_RECORD is set but FC_SCRATCH_REF is empty - a delivery phase needs its line's scratch ref (delivery/<line-id>)"
  exit 1
fi
# Maintenance and promotion execute the source approved by preflight. An absent or
# abbreviated revision cannot authorize a branch-tip fallback, including managed homes.
case "$FC_PHASE" in
  maintenance:*|promotion:*)
    if [ -z "${FC_SOURCE_REVISION:-}" ]; then
      stop_line "worker: FC_SOURCE_REVISION is required for maintenance and promotion"
      exit 1
    fi
    ;;
esac
if [ -n "${FC_SOURCE_REVISION:-}" ] && ! [[ "$FC_SOURCE_REVISION" =~ ^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$ ]]; then
  stop_line "worker: FC_SOURCE_REVISION must be a full commit SHA"
  exit 1
fi
GIT_USER="${FC_GIT_USER:-delivery-bot}"
# The commit email is the phase identity's own (a real GitHub no-reply, so commits attribute
# to and link the machine-user); it falls back to the synthetic <user>@delivery.local when the
# identity carries none. An UNASSIGNED phase has no FC_GIT_USER/FC_GIT_TOKEN at all, so GIT_USER
# is only a local commit label and the tokenless clone/push fails loudly - by design, no default
# identity ever pushes.
GIT_EMAIL="${FC_GIT_EMAIL:-${GIT_USER}@delivery.local}"

# The playbook's two delivery-record helpers, baked into this image (devops/vendor/). They
# are the only legitimate writers of a record's frontmatter and its signature in any mode
# (REF-Delivery section 1), and they live in ONE playbook skill folder that a pod running any
# other phase's skill never receives - so the image is their delivery mechanism. EXPORTED, not
# just local: the AGENT needs them too (a skill tells it to open its record and to record the
# review), and a pod with no path to reach_gate.py leaves its phases hand-authoring the
# frontmatter the REF says is never hand-authored (playbook-studio#2, INT-FC-R111). The
# compiled prompt names these same variables.
export FC_ESTABLISH_HELPER="${FC_ESTABLISH_HELPER:-/opt/foundry/establish_scratch.py}"
export FC_REACH_HELPER="${FC_REACH_HELPER:-/opt/foundry/reach_gate.py}"
export FC_STAMP_HELPER="${FC_STAMP_HELPER:-/opt/foundry/stamp_gate.py}"
# The worker's own run-figures writer (issue #115), baked beside them: after the agent's turn
# the entrypoint runs it to record what the run cost - tokens, USD, turns, the model, the span
# - into the phase record as `run_*` keys (step 4c). Not exported: the agent never runs it, the
# figures are the harness's to know, and the same path is overridable for the execution suite.
FC_RECORD_RUN_HELPER="${FC_RECORD_RUN_HELPER:-/opt/foundry/record_run.py}"
# The agent's permission-prompt tool (issue #212), baked beside them: the CLI hands it every ask
# the session raises and it allows each one (step 2). Not exported, overridable for the suite.
FC_APPROVER="${FC_APPROVER:-/opt/foundry/approver.py}"

# The workspace root. /work in the executor's pods (the worker template mounts it there, and its
# compiled prompts name /work/repo by that literal, so the default must stay /work).
# Overridable so test_entrypoint_execution.py can run this file against a temp repo.
WORK_DIR="${FC_WORK_DIR:-/work}"

# Where the agent drops a park sentinel for this script to read (steps 3b/3c). OUTSIDE the
# clone, and exported so the agent's skill can address it: the sentinel is one process
# signalling another inside one pod, and a signal that lives in a git working tree is a
# signal any `git add -A` can publish. A published sentinel is read by every later clone,
# so every later run on that repo parks before its agent has done anything (issue #49).
# Its absence is what tells a by-hand run there is no wrapper to signal - the skill then
# writes nothing, and a long-lived local clone never accumulates one.
export FC_SIGNAL_DIR="${FC_SIGNAL_DIR:-${WORK_DIR}/signals}"
mkdir -p "$FC_SIGNAL_DIR"

# The captured definition binds each record to its supported artifact handler.
lifecycle_flags=()
if [ -n "${FC_RECORD:-}" ]; then
  export FC_LIFECYCLE_SPEC="${FC_SIGNAL_DIR}/lifecycle.json"
  printf '%s\n' "${FC_LIFECYCLE_DEFINITION:?FC_LIFECYCLE_DEFINITION required for a delivery record}" > "$FC_LIFECYCLE_SPEC"
  : "${FC_ARTIFACT:?FC_ARTIFACT required for a delivery record}"
  lifecycle_flags=(--definition "$FC_LIFECYCLE_SPEC")
fi

# 1. Clone the delivery repo with this phase's git identity.
git config --global user.name "$GIT_USER"
git config --global user.email "$GIT_EMAIL"
# The PAT authenticates the clone and push. Trim any stray whitespace the seated secret may
# carry - a token stored via `echo` gains a trailing newline.
FC_GIT_TOKEN="$(printf '%s' "${FC_GIT_TOKEN:-}" | tr -d '[:space:]')"
# gh reads GH_TOKEN: export it up front for this script's own gh calls (the step-8 completeness
# check and the like). The AGENT's own gh calls - a resolve's `gh pr create`, a review's `gh pr
# review --approve` - act as THIS phase's identity through the wrapper written before the launch,
# which reads the token from its file: the agent's environment never holds it (INT-FC-R192). A
# distinct reviewer identity can approve another author's PR.
#
# THIS IS OUR CREDENTIAL AND IT REACHES OUR ORG ONLY. It is right for the ticket, which is
# always on our repo - and wrong for a pair's repository, which was never granted to it. An
# act over a home must reach their repo through $FC_PAIR_DOOR (below) and never through plain
# gh: git and API writes both use the credential assigned to their repository.
export GH_TOKEN="${FC_GIT_TOKEN:-${GH_TOKEN:-}}"
repo_path="${FC_REPO#https://github.com/}"; repo_path="${repo_path#github.com/}"; repo_path="${repo_path%.git}"

# Git reads the checkout credential over a pipe, from a 0600 file outside the clone, at call
# time: the agent runs without the token in its environment, so an environment listing cannot
# print it, while its own git still authenticates (INT-FC-R192). The helper file, clone URL,
# config and command arguments contain only the repository and helper path.
# A demo line reads its source - a repository of the same owner, FC_DEMO_OF - over git as well,
# so the helper answers for that exact repository too, and for no other.
demo_path=""
case "${FC_DEMO_OF:-}" in "${repo_path%%/*}"/?*) demo_path="${FC_DEMO_OF%.git}" ;; esac
if [ -n "${FC_GIT_TOKEN}" ]; then
  mkdir -p "${WORK_DIR}/git"
  chmod 700 "${WORK_DIR}/git"
  ( umask 077; printf '%s' "${FC_GIT_TOKEN}" > "${WORK_DIR}/git/token" )
  export FC_GIT_TOKEN_FILE="${WORK_DIR}/git/token" FC_GIT_DEMO_PATH="${demo_path}"
  cat > "${WORK_DIR}/git/credential-helper.sh" <<'OWN_HELPER'
#!/bin/sh
[ "$1" = "get" ] || exit 0
protocol= host= path=
while IFS='=' read -r key value; do
  case "$key" in
    protocol) protocol="$value" ;;
    host) host="$value" ;;
    path) path="$value" ;;
  esac
done
repo="${FC_REPO#https://github.com/}"; repo="${repo#github.com/}"; repo="${repo%.git}"
[ "$protocol" = https ] && [ "$host" = github.com ] || exit 0
demo="${FC_GIT_DEMO_PATH:-}"
case "$path" in
  "$repo"|"${repo}.git") ;;
  *) [ -n "$demo" ] && { [ "$path" = "$demo" ] || [ "$path" = "${demo}.git" ]; } || exit 0 ;;
esac
[ -r "${FC_GIT_TOKEN_FILE:-}" ] || exit 0
printf 'username=x-access-token\npassword=%s\n' "$(cat "${FC_GIT_TOKEN_FILE}")"
OWN_HELPER
  chmod 700 "${WORK_DIR}/git/credential-helper.sh"
  for scoped in "$repo_path" ${demo_path:+"$demo_path"}; do
    for suffix in "" .git; do
      git config --global "credential.https://github.com/${scoped}${suffix}.helper" "${WORK_DIR}/git/credential-helper.sh"
      git config --global "credential.https://github.com/${scoped}${suffix}.useHttpPath" true
    done
  done
  export FC_GIT_TOKEN
fi

# 0b. The PAIR credential, when this worker performs a door onto a repository the foundry does
#     NOT own (a `kind: repository` promotion target). It is a token another organization
#     granted us, and it reaches git through a CREDENTIAL HELPER scoped to its repository - never
#     through a URL, a remote, or a file.
#
#     Both helpers hand their token to git on demand over a pipe. Remotes and config carry
#     credential-free URLs, so checkout inspection and retained diagnostics keep secrets out.
FC_PAIR_TOKEN="$(printf '%s' "${FC_PAIR_TOKEN:-}" | tr -d '[:space:]')"
if [ -n "${FC_PAIR_TOKEN}" ] && [ -n "${FC_PAIR_REPO:-}" ]; then
  pair_host="${FC_PAIR_HOST:-github.com}"
  mkdir -p "${WORK_DIR}/pair"
  chmod 700 "${WORK_DIR}/pair"
  # The helper reads the token from its own 0600 file at call time, so the secret is never
  # written to this file - the file is only the protocol git speaks - and never sits in the
  # agent's environment (INT-FC-R192).
  ( umask 077; printf '%s' "${FC_PAIR_TOKEN}" > "${WORK_DIR}/pair/token" )
  export FC_PAIR_TOKEN_FILE="${WORK_DIR}/pair/token"
  cat > "${WORK_DIR}/pair/credential-helper.sh" <<'HELPER'
#!/bin/sh
# git credential helper for the pair's repository. Only `get` answers; store/erase are no-ops, so
# git never persists anything of the pair's anywhere.
[ "$1" = "get" ] || exit 0
protocol= host= path=
while IFS='=' read -r key value; do
  case "$key" in
    protocol) protocol="$value" ;;
    host) host="$value" ;;
    path) path="$value" ;;
  esac
done
[ "$protocol" = https ] && [ "$host" = "${FC_PAIR_HOST:-github.com}" ] || exit 0
case "$path" in "$FC_PAIR_REPO"|"${FC_PAIR_REPO}.git") ;; *) exit 0 ;; esac
[ -r "${FC_PAIR_TOKEN_FILE:-}" ] || exit 0
printf 'username=x-access-token
password=%s
' "$(cat "${FC_PAIR_TOKEN_FILE}")"
HELPER
  chmod 700 "${WORK_DIR}/pair/credential-helper.sh"
  # Scoped to the pair's REPOSITORY, not merely its host. Host scoping is not enough and the
  # difference matters: the common pair lives on github.com, which is our host too, so a
  # host-scoped helper would answer for our own org as well - and the day a pair's grant is
  # the only credential git can find for github.com is the day something of ours is pushed on
  # a partner's token. Git matches a credential config URL carrying a path only when the
  # request's path matches, which is exactly the narrowing wanted here.
  for suffix in "" .git; do
    git config --global "credential.https://${pair_host}/${FC_PAIR_REPO}${suffix}.helper" "${WORK_DIR}/pair/credential-helper.sh"
    git config --global "credential.https://${pair_host}/${FC_PAIR_REPO}${suffix}.useHttpPath" true
  done
  export FC_PAIR_TOKEN

  # THE DOOR, script-side (foundry-platform#167, ADR-044 section 6). Every act this worker
  # performs against a PAIR's repository goes through this one script - the entrypoint's own
  # completeness reads AND the agent's writes - so a second repo host is a one-place edit
  # here exactly as it is one port in the console. A door scattered across call sites is a
  # seam nobody can re-shape without finding every one of them.
  #
  # A SCRIPT and not a shell function, because the agent is a separate process: a function
  # defined here would be invisible to it, and an agent that cannot reach the door reaches
  # for plain `gh` instead - which is our credential, pointed at a repository nobody granted
  # us. The same failure this file refuses for git (the credential helper above), refused
  # here for the API.
  #
  # WHICH credential is the whole point. The agent's plain gh stays OURS (its wrapper reads our
  # token from its file), because a Managed act reads and comments on our ticket on our repo;
  # their repository is reached only through here, on their grant. Two coordinates, two credentials, and neither
  # substitutes for the other.
  #
  # gh speaks GitHub; GH_HOST points it at a pair on a different GitHub host, from the value
  # that has ridden the registry as FC_PAIR_HOST since #131. A host gh cannot speak fails the
  # call, and every caller treats a failed pair read as fail-open rather than as a failed act:
  # we could not look, so we do not claim the door is missing.
  #
  # NO SECOND IMPLEMENTATION UNTIL A CUSTOMER NEEDS ONE. The first non-GitHub door is written
  # for that customer, against this seam. Azure DevOps Repos is the first candidate.
  cat > "${WORK_DIR}/pair/door" <<'DOOR'
#!/bin/sh
# The door to the pair's repository: gh, on THEIR grant, against THEIR host. Read the token
# from its file at call time so the secret is never written into this file, and call the
# real gh, not the agent's wrapper, which would put OUR credential back.
exec env GH_TOKEN="$(cat "${FC_PAIR_TOKEN_FILE}")" GH_HOST="${FC_PAIR_HOST:-github.com}" "${FC_REAL_GH:-gh}" "$@"
DOOR
  chmod 700 "${WORK_DIR}/pair/door"
  export FC_PAIR_DOOR="${WORK_DIR}/pair/door"
  echo "worker: pair credential wired for ${pair_host}/${FC_PAIR_REPO} (value never printed)"
  echo "worker: the door onto ${FC_PAIR_REPO} is ${FC_PAIR_DOOR} - every act on their repo goes through it"
fi
# The helpers authenticate with the fixed username x-access-token. FC_GIT_USER remains
# the commit label and can carry spaces. An unassigned identity supplies no helper token.
# WHICH repository holds the code. Ordinarily it is ours (FC_REPO), and the clone below is
# the whole story. For an app whose HOME is another organization's repository - a Managed app
# (REF-Delivery section 1) - the act spans two coordinates that answer different questions,
# and FC_HOME_BRANCH is what says so (a promotion door also carries FC_PAIR_REPO and must NOT
# take either path: its clone is our own repo, and the pair is where it pushes to, not from).
#
#   A MAINTENANCE act over a home: the ticket is on OUR repo and stays there; the code is
#   cloned from THEIRS into /work/repo, and the pull request is opened there. Maintenance
#   carries no scratch, so one clone is the whole workspace.
#
#   A DELIVERY phase over a home (foundry-platform#135): the line's scratch lives on OUR repo
#   exactly as every other line's does - an orphan delivery/<line-id> ref mounted at
#   .delivery/ inside OUR clone (step 1b below) - so /work/repo stays ours, and the home is
#   cloned BESIDE it at /work/home for the code. Two clones, because the scratch and the code
#   have parted company: mounting our records inside their tree is the "never scaffold the
#   foundry into their repository" rule broken by plumbing rather than by intent.
if [ -n "${FC_HOME_BRANCH:-}" ] && [ -n "${FC_PAIR_REPO:-}" ]; then
  pair_host="${FC_PAIR_HOST:-github.com}"
  # No token in the URL: the credential helper wired above answers for this exact repository,
  # so the pair's grant never lands in .git/config of a tree we then push from.
  if [ -n "${FC_RECORD:-}" ] || [ -n "${FC_SCRATCH_REF:-}" ]; then
    echo "worker: home is ${FC_PAIR_REPO} - cloning ours for the scratch and theirs beside it for the code"
    git clone "https://github.com/${repo_path}.git" "${WORK_DIR}/repo"
    git clone --branch "${FC_HOME_BRANCH}" "https://${pair_host}/${FC_PAIR_REPO}.git" "${WORK_DIR}/home"
    # Exported so the skills and the agent can address the code by name rather than by a
    # path they would otherwise have to be told in prose alone.
    export FC_HOME_DIR="${WORK_DIR}/home"
  else
    echo "worker: home is ${FC_PAIR_REPO} (${FC_REPO} holds the ticket) - cloning theirs for the code"
    git clone --branch "${FC_HOME_BRANCH}" "https://${pair_host}/${FC_PAIR_REPO}.git" "${WORK_DIR}/repo"
  fi
else
  git clone "https://github.com/${repo_path}.git" "${WORK_DIR}/repo"
fi
cd "${WORK_DIR}/repo"

# Keep the clone's branch name for direct maintenance commits and ordinary pushes.
# Reset only this local checkout to the exact approved commit, never a newer branch tip.
DEFAULT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ -n "${FC_SOURCE_REVISION:-}" ]; then
  if ! git fetch --no-tags origin "$FC_SOURCE_REVISION"; then
    stop_line "worker: the approved source revision is unavailable"
    exit 1
  fi
  approved_sha=$(git rev-parse --verify 'FETCH_HEAD^{commit}')
  if [ "$approved_sha" != "${FC_SOURCE_REVISION,,}" ]; then
    stop_line "worker: fetched source does not match the approved revision"
    exit 1
  fi
  git checkout -B "$DEFAULT_BRANCH" "$approved_sha"
fi
# Completeness compares the agent's commits with this approved starting point.
BASE_SHA=$(git rev-parse HEAD)

# 1b. Mount the delivery scratch. The scratch lives on the line's own orphan ref - the
#     delivery/<line-id> branch the compiler resolved into FC_SCRATCH_REF - with records at
#     the branch root, never on the default branch (decision 0003). Fetch that ref into a
#     local branch of the same name and mount it at .delivery/ as a linked worktree: every
#     hardcoded .delivery/ path below (the skills', the helpers', this script's) then reads
#     and writes the scratch exactly as the on-disk contract says, while the main tree stays
#     on the default branch, which git-ignores the mount point. Scratch commits happen INSIDE
#     the mount (`git -C .delivery`) and push the ref by explicit refspec - from the main
#     tree, `git add .delivery/` would stage a gitlink, not files, and a bare `git push`
#     would target the default branch the scratch never rides. A maintenance worker carries
#     no scratch and no FC_SCRATCH_REF, so it skips the mount.
if [ -n "${FC_SCRATCH_REF:-}" ]; then
  git fetch origin "refs/heads/${FC_SCRATCH_REF}:refs/heads/${FC_SCRATCH_REF}"
  git worktree add .delivery "$FC_SCRATCH_REF"
fi

# 2. Point the agent at the owner MCP doors (playbook-studio for the skill, plus the
#    phase's tool), authenticated with the shared MCP token.
mcp='{"mcpServers":{}}'
IFS=',' read -ra doors <<< "${FC_MCP_ENDPOINTS:-}"
for d in "${doors[@]}"; do
  [ -z "$d" ] && continue
  e=$(printf '%s' "$d" | tr '[:lower:]-' '[:upper:]_' | tr -cd 'A-Z0-9_')
  user_var="FC_MCP_${e}_USER"; pass_var="FC_MCP_${e}_PASS"
  user="${!user_var:-}"; pass="${!pass_var:-}"
  hdr=""
  if [ -n "$user" ] || [ -n "$pass" ]; then
    hdr=$(printf '%s:%s' "$user" "$pass" | base64 -w0)  # per-door Basic auth, not a shared token
  fi
  mcp=$(jq --arg n "$d" --arg u "https://${d}.${FC_DOMAIN:?FC_DOMAIN required (the ground domain for studio MCP URLs; no fallback, or a second install silently targets the first)}/mcp" --arg h "$hdr" \
    '.mcpServers[$n] = ({"type":"http","url":$u} + (if $h=="" then {} else {"headers":{"Authorization":("Basic "+$h)}} end))' <<<"$mcp")
done
# The approver beside the doors (issue #212). A key whose organisation policy turns bypass off
# runs the session in another mode, where every ask is refused with nobody to answer it; the
# CLI hands each ask to this server instead (--permission-prompt-tool, step 3), and it allows
# each one, writing its answers outside the clone for the log after the turn. The policy's deny
# rules refuse before an ask exists, so they never reach it.
approvals="${WORK_DIR}/approvals.jsonl"
: > "$approvals"
mcp=$(jq --arg a "$FC_APPROVER" --arg f "$approvals" \
  '.mcpServers.approver = {"type":"stdio","command":"python3","args":[$a,$f]}' <<<"$mcp")
# The config carries the studios' Authorization headers, so it lives OUTSIDE the clone
# (beside it, under WORK_DIR) and reaches the agent by explicit path: at the clone root it
# is one broad `git add` away from the default branch, and `.mcp.json` there is the CLI's
# committable project config, a filename a team checks in on purpose (playbook#189).
printf '%s' "$mcp" > "${WORK_DIR}/mcp.json"

# 3. Run the per-run agent for this phase. The credential is the secret; the provider,
#    model, and base_url pick the model. claude uses its own auth; an OpenAI-compatible
#    endpoint is reached through an Anthropic-style gateway base_url. The exact gateway
#    compatibility is tuned against a live run.
#
#    --dangerously-skip-permissions (not --permission-mode acceptEdits): the worker is a
#    fully-autonomous, headless (-p) agent in an isolated pod; it must call MCP tools and
#    Bash without a human to approve them. acceptEdits auto-approves file edits only, so a
#    headless run stalls at its first MCP tool call ("approve the MCP tool permissions") and
#    exits without writing its record. Skipping permissions is the sanctioned headless mode.
#    Where a key's organisation policy turns that mode off, --permission-prompt-tool hands
#    every ask to the approver (step 2), which allows it; where the mode holds, nothing asks.
#    WHO runs this step (issue #62): the playbook catalog agent the console bound to it, named
#    in FC_AGENT and announced here so the pod log says who did the work. When the console
#    could read the catalog, the agent's posture and character ride too and are honoured:
#    FC_AGENT_PROMPT is the paragraph the agent runs under, appended to the system prompt
#    verbatim (the corpus's own words, never restated here); FC_AGENT_WRITES=false denies the
#    editing tools, the same denylist the playbook's installer renders for a read-only agent
#    (writes is "may it change the artifacts it works on", so a Reviewer posting a verdict
#    through gh still can). FC_AGENT_PERMISSION is carried as information: every mode that
#    stops to ask would hang a pod with nobody to answer, so the headless skip stays and the
#    posture's mode is what the log records. Catalog roles are pinned locally with the worker.
agent_flags=()
if [ -n "${FC_AGENT:-}" ]; then
  echo "worker: ${FC_PHASE} runs as ${FC_AGENT} (${FC_AGENT_TITLE:-$FC_AGENT})${FC_AGENT_PERMISSION:+, posture ${FC_AGENT_PERMISSION}}${FC_AGENT_WRITES:+, writes ${FC_AGENT_WRITES}}"
  if [ -n "${FC_AGENT_PROMPT:-}" ]; then
    agent_flags+=(--append-system-prompt "$FC_AGENT_PROMPT")
  fi
  if [ "${FC_AGENT_WRITES:-}" = "false" ]; then
    agent_flags+=(--disallowedTools "Edit,Write,MultiEdit,NotebookEdit")
  fi
else
  echo "worker: ${FC_PHASE} runs unnamed (no catalog agent bound)"
fi
# Nothing secret reaches the agent's environment, where one `env` listing would print it into
# the transcript (INT-FC-R192). The CLI keeps a subscription token from the commands it runs, so
# CLAUDE_CODE_OAUTH_TOKEN is the one credential the CLI's own environment carries.
export CLAUDE_CODE_OAUTH_TOKEN="${FC_MODEL_CREDENTIAL:-}"
if [ -n "${FC_BASE_URL:-}" ]; then
  export ANTHROPIC_BASE_URL="$FC_BASE_URL"
  # A compatible gateway may authenticate by x-api-key (the real Anthropic convention, and
  # OpenCode Zen) or by Authorization: Bearer (DeepSeek and OAuth proxies). We can't know which,
  # so supply both: the CLI's apiKeyHelper sends what it prints as both headers. It reads the
  # key from a 0600 file at call time, because ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN would
  # sit in the environment of every command the agent runs. Bearer alone 401'd ("Missing API
  # key") against Zen's x-api-key /v1/messages.
  mkdir -p "${WORK_DIR}/model"
  chmod 700 "${WORK_DIR}/model"
  ( umask 077; printf '%s' "${FC_MODEL_CREDENTIAL:-}" > "${WORK_DIR}/model/key" )
  agent_flags+=(--settings "$(printf '{"apiKeyHelper": "cat %s"}' "${WORK_DIR}/model/key")")
fi
# The agent's own gh acts as THIS phase's identity through a wrapper first on its PATH, which
# hands gh the token from its file at call time; the real gh is remembered for the wrapper and
# for the pair's door, which must never reach the wrapper.
FC_REAL_GH="$(command -v gh || true)"
export FC_REAL_GH
mkdir -p "${WORK_DIR}/bin"
cat > "${WORK_DIR}/bin/gh" <<'AGENT_GH'
#!/bin/sh
[ -n "${FC_REAL_GH:-}" ] || { echo "gh is not installed" >&2; exit 127; }
if [ -r "${FC_GIT_TOKEN_FILE:-}" ]; then
  exec env GH_TOKEN="$(cat "${FC_GIT_TOKEN_FILE}")" "${FC_REAL_GH}" "$@"
fi
exec "${FC_REAL_GH}" "$@"
AGENT_GH
chmod 700 "${WORK_DIR}/bin/gh"
#    The worker narrates LIVE: stream-json emits each turn as it happens, and the jq
#    filter prints the agent's prose and tool calls into the pod log - plain -p buffers
#    everything until the turn ends, so a 15-minute phase shows a silent log and a
#    healthy run reads as hung. jq -R + try/catch tolerates any non-JSON
#    line; pipefail (set -o above) still fails the step on a claude error. A tool line
#    carries what the tool was asked: its description when it has one, otherwise every
#    input argument as k=v - generic on purpose, so MCP tools with their own arg names
#    (slug, path, project...) narrate too instead of printing a bare tool name. One
#    line, capped at 120 chars.
#    MCP timeouts: the default tool timeout gives up on minute-long studio calls
#    (platform-studio's conformance suite is minutes of GitHub reads), reading a
#    completing call as a dead transport and parking a whole delivery degraded on a
#    healthy studio. 10 min covers the slowest studio call; the connect timeout
#    (MCP_TIMEOUT) stays modest so a genuinely absent door still fails fast.
export MCP_TIMEOUT="${MCP_TIMEOUT:-60000}"
export MCP_TOOL_TIMEOUT="${MCP_TOOL_TIMEOUT:-600000}"
#    The raw stream-json is tee'd to a capture file (step 3a reads it back to tell a session-limit
#    failure from an ordinary one; step 4c reads its final result event for the run's figures)
#    WHILE still streaming through jq to the pod log live -
#    `stdbuf -oL tee` keeps the pass-through line-buffered so the live narration this whole block
#    fought for is not re-buffered behind the capture. stderr is captured the same way, un-redirected
#    from the log via a tee to >&2. `set +e` around the pipe keeps its failure from aborting under
#    `set -e` so 3a can branch on the agent's OWN exit (PIPESTATUS[0], read BEFORE `set -e` is
#    restored - a trailing `|| true` would reset PIPESTATUS to true's and mask it); every path below
#    re-asserts that exit. pipefail stays on but is moot here: PIPESTATUS holds each stage regardless.
# The mask every logged line passes through: the credential values this pod holds, masked
# before a line reaches the log, since a failed call or an ask can carry a command's output.
# `ask` names what a tool call acts on, for a denied and an approved call alike.
MASK="$(cat <<'JQ'
def oneline: gsub("\\s+"; " ");
def ask: if type == "object" then (.command // .file_path // .path // .url // tojson) else . end | tostring;
([$ENV | to_entries[] | select(.key | test("^(FC_GIT_TOKEN|GH_TOKEN|GITHUB_TOKEN|FC_PAIR_TOKEN|FC_MODEL_CREDENTIAL)$|^FC_MCP_.+_PASS$")) | .value | gsub("^\\s+|\\s+$"; "") | select(length >= 6)] | unique | sort_by(-length)) as $secrets
| def redact: reduce $secrets[] as $s (.; split($s) | join("***"));
# Mask the whole text first and cut it after, so no credential crosses the cut as a prefix;
# cut generously before collapsing whitespace, so a huge result costs nothing to narrate.
def brief($n): redact | .[0:($n * 2)] | oneline | .[0:$n];
JQ
)"
# The narration filter, kept beside the launch. One line per agent move, plus what a refusal
# needs to be diagnosed from the log alone (INT-FC-R193): the session's CLI version, model and
# EFFECTIVE permission mode (a headless session not in bypassPermissions puts every ask to the
# approver), each failed tool call with the tool's name, and each permission the harness denied.
NARRATE="${MASK}
$(cat <<'JQ'
def text_of: if type == "string" then . elif type == "array" then ([.[]? | .text? // empty] | join(" ")) elif . == null then "" else tojson end;
def hint: (.input // {}) | if type != "object" then tostring elif (.description? // "") != "" then (.description | tostring) else ([to_entries[] | select(.value != null and .value != "") | .key + "=" + (.value | if type == "string" then . else tojson end)] | join(" ")) end;
foreach (inputs | try fromjson catch null | select(type == "object")) as $e ({tools: {}};
  if $e.type == "assistant" then .tools += (try ([$e.message.content[]? | select(.type == "tool_use" and (.id | type) == "string") | {(.id): (.name // "tool")}] | add // {}) catch {}) else . end;
  . as $state | $e
  | try (
      if .type == "system" and .subtype == "init" then
        ("[session] claude \(.claude_code_version // "?"), model \(.model // "?"), permission mode \(.permissionMode // "?"), mcp \([.mcp_servers[]? | "\(.name):\(.status)"] | join(", ") | if . == "" then "none" else . end)"),
        (if (.permissionMode // "") != "bypassPermissions" then "[session] WARNING: permission mode \(.permissionMode // "unknown"), not bypassPermissions: the approver answers every ask" else empty end)
      elif .type == "assistant" then
        (.message.content[]? | if .type == "text" then .text elif .type == "tool_use" then ((hint | brief(120)) as $h | "[tool] " + (.name // "tool") + (if $h == "" then "" else " - " + $h end)) else empty end)
      elif .type == "user" then
        (.message.content[]? | select(.type? == "tool_result" and .is_error == true) | ((.content | text_of | brief(200)) as $t | "[tool error] " + ($state.tools[.tool_use_id // ""] // "tool") + (if $t == "" then "" else " - " + $t end)))
      elif .type == "result" then
        ((.permission_denials[]? | "[denied] " + (.tool_name // "tool") + ": " + ((.tool_input // {}) | ask | brief(200))),
         "[agent done] " + (.subtype // "result"))
      else empty end
    ) catch empty
  | strings | redact)
JQ
)"
agent_raw="$(mktemp)"; agent_err="$(mktemp)"
# Both captures go with the process, whichever exit takes it: the raw stream is read twice
# (3a's session-limit markers, 4c's result event) and the second reader sits past every
# early exit between them, so the cleanup is the EXIT trap's (worker_exit, at the top)
# rather than each path's.
agent_started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set +e
# The studios' MCP passwords are in mcp.json's headers, which the CLI reads; the agent needs none.
agent_unset=(-u FC_GIT_TOKEN -u GH_TOKEN -u GITHUB_TOKEN -u FC_PAIR_TOKEN -u FC_MODEL_CREDENTIAL
  -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN)
for name in $(compgen -e); do
  case "$name" in FC_MCP_*_PASS) agent_unset+=(-u "$name") ;; esac
done
env "${agent_unset[@]}" PATH="${WORK_DIR}/bin:${PATH}" \
  claude -p "$PROMPT" ${FC_MODEL:+--model "$FC_MODEL"} --dangerously-skip-permissions \
  --permission-prompt-tool mcp__approver__approve --mcp-config "${WORK_DIR}/mcp.json" "${agent_flags[@]}" \
  --output-format stream-json --verbose 2> >(tee "$agent_err" >&2) \
  | stdbuf -oL tee "$agent_raw" \
  | jq -nrR --unbuffered "$NARRATE"
agent_status="${PIPESTATUS[0]}"
agent_finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
set -e
# Each ask the approver answered this turn (issue #212), one line apiece, masked like the narration.
jq -nrR "${MASK}
inputs | try fromjson catch null | select(type == \"object\") | \"[approved] \" + (.tool // \"tool\") + \": \" + ((.input // {}) | ask | brief(200))" \
  < "$approvals" || true

# The run's figures into the record (issue #115). The raw stream's final `result` event
# carries what this run cost - tokens by type, USD, turns, and on recent harnesses the same
# per model - and the phase record is the durable home of a phase's figures: the `run_*`
# keys foundry-analytics reads for its ledger (spend per run, the agent-run half of every
# phase). Written by the helper, never by a shell edit (the same rule as the frontmatter
# block and the stamp). An executor retry ADDS to what a prior attempt recorded and keeps
# the attempt's whole span. The write is telemetry and never fails the run: a stream with no
# result event writes nothing and says so, and a helper failure is logged and passed over.
# Learn leaves no record, and a maintenance or promotion act carries none, so those runs say
# so and record nothing. Called at step 4c on a finished turn and at 3a on a failed one.
record_run_figures() {
  if [ -z "${FC_RECORD}" ]; then
    echo "worker: ${FC_PHASE} leaves no record; the run's figures are not recorded"
    return 0
  fi
  python3 "$FC_RECORD_RUN_HELPER" --repo . --record "$FC_RECORD" --stream "$agent_raw" \
    --run "${FC_RUN:-}" --agent "${FC_AGENT:-}" --model "${FC_MODEL:-}" \
    --started "$agent_started" --finished "$agent_finished" \
    || echo "worker: run figures not recorded in ${FC_RECORD} (record_run.py exited $?)" >&2
}
# A refused stamp's reason (issue #181): a `stamp_refused:` frontmatter key carrying the
# stamper's own refusal line, written only by this worker and only when a one-shot stamp
# refused over a passing review (step 5). It describes the closure, not the work, so like the
# run figures it lands after the review.
# JSON-quoted, which YAML reads as a double-quoted scalar, so a refusal carrying colons,
# quotes or a URL parses back verbatim. One edit both ways: with a reason it is set, with
# none it is cleared.
set_stamp_refusal() {
  python3 - ".delivery/${FC_RECORD}" "${1:-}" <<'PY'
import json, re, sys
path, reason = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().split("\n")
close = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
kept = [line for i, line in enumerate(lines) if not (0 < i < close and re.match(r"(?i)stamp_refused\s*:", line))]
if reason:
    kept.insert(next(i for i, line in enumerate(kept[1:], 1) if line.strip() == "---"), "stamp_refused: " + json.dumps(reason))
if kept != lines:
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(kept))
PY
}
# A failed turn's spend is as real as a finished one's, and the agent commits and pushes its
# record DURING its turn - so an attempt the model's limit cut off after the record landed
# would leave it on the remote carrying no figures, and the retry's add-on rule would never
# see what that attempt cost. So a failed turn records onto the record the agent had
# COMMITTED and pushes that one change. A record the agent left uncommitted stays the
# agent's, unpublished (the harness publishes an agent's uncommitted work only at a finished
# turn, step 6), and an absent record records nothing. `|| true` on the push as at step 6:
# the figures never change the exit the executor reacts to.
record_run_figures_at_the_failed_turn() {
  [ -n "${FC_RECORD}" ] && [ -f ".delivery/${FC_RECORD}" ] || return 0
  if [ -n "$(git -C .delivery status --porcelain -- "$FC_RECORD" 2>/dev/null)" ]; then
    echo "worker: ${FC_RECORD} is uncommitted at this stop; the attempt's figures are not recorded" >&2
    return 0
  fi
  record_run_figures
  if [ -n "$(git -C .delivery status --porcelain -- "$FC_RECORD" 2>/dev/null)" ]; then
    { git -C .delivery add "$FC_RECORD" \
      && git -C .delivery commit -q -m "delivery(${FC_PHASE}): run figures of an attempt cut short" \
      && git -C .delivery push origin "HEAD:refs/heads/${FC_SCRATCH_REF}"; } || true
  fi
}

# 3a. Session-limit stop (issue #40): the agent run failed AND its output names the model's own
#     session/usage limit. Terminal for the reason the whole exit table exists - a blind retry
#     cannot help - but uniquely the wall is a rolling clock window, not a permanent one: retrying
#     immediately just burns the whole attempt budget against a still-closed door and reports FAILED,
#     when the run should PARK (exit 67, which Argo does not retry) and let a re-drive after the reset
#     be the answer. The console reads 67 apart from the degraded 64 so a workflow can be built around
#     the session wall. The marker set is a best-effort bridge, not a contract (like the studio
#     refusal phrases in domain/studios.py): the model owns the exact wording, so we match the stable
#     substrings a usage/session wall prints, case-insensitively, over BOTH streams. Only a NON-ZERO
#     agent exit is inspected, so a run that merely mentioned the words in prose can never trip it.
#     No marker may depend on the word BEFORE "limit", and none on the verb that follows it: the wall
#     names whichever quota it hit, and that word is not a closed set. It has printed "session",
#     "usage", "5-hour" - and the MODEL'S OWN NAME ("You've reached your Fable 5 limit. /model to
#     switch models."), which no list of nouns can anticipate, since every model release adds one.
#     So the set carries three independent anchor families and a line need match only one: the known
#     noun phrases, the possessive frame (<verb> your ... limit, which holds whatever the quota is
#     called), and the clauses only a quota wall prints - a reset time, or the offer to switch models.
#     A per-model wall is still 67: the phase runs the model the compiler chose (FC_MODEL) and cannot
#     switch mid-flight, so the answer is the same park, with the operator free to re-drive on another
#     model instead of waiting. The asymmetry decides how wide to match: a false positive costs one
#     re-drive after the window reopens, a false negative costs the whole attempt budget and reports
#     FAILED. Widen here, and pin every wording seen in the wild as a fixture in test_exit_contract.py.
if [ "$agent_status" -ne 0 ]; then
  # Whichever stop follows, the attempt's spend lands first: its figures onto the record the
  # agent had committed, pushed as one change. The exit below is unchanged by it.
  record_run_figures_at_the_failed_turn
  if grep -qiE '(session|usage|rate) limit|[0-9]+-hour limit|(reached|hit|exceeded) your [^.]{0,40}limit|limit will reset|/model to switch models' "$agent_raw" "$agent_err" 2>/dev/null; then
    stop_line "worker: ${FC_PHASE} hit the model's session limit - session-limit stop, not retrying (exit ${SESSION_LIMIT_EXIT}); re-drive once the window resets"
    exit "$SESSION_LIMIT_EXIT"
  fi
  # Any other agent failure is an ordinary transient: exit its code so the executor retries
  # (the `set +e` above only defers the pipe's failure to here).
  stop_line "worker: ${FC_PHASE} agent exited ${agent_status} - transient, the executor will retry"
  exit "$agent_status"
fi
# The raw stream stays for step 4c (the result event's figures); the EXIT trap removes it.

# 3b. Delivery-scale sentinel: the resolve skill judged the ticket too big for a maintenance
#     scope (REF-Maintenance section 1). It has ALREADY, over gh, posted the prepared delivery
#     prompt as a marked issue comment AND labelled the ticket foundry-delivery-scale - both on
#     GitHub, so they survive this pod - then dropped this local sentinel to signal the punt.
#     Exit the delivery-scale terminal code: Argo does NOT retry it (a retry cannot shrink the
#     ticket) and parks the run, and the console reads that parked intent and offers the operator
#     "Switch to Delivery" (issue #13). Checked BEFORE the record/PR completeness contracts below,
#     which do not apply to a punt-to-delivery: it opens no PR and writes no .delivery/ record, so
#     step 8 would otherwise read "no open PR" and exit 1 (a wrong, retried transient).
#     The sentinel is read from FC_SIGNAL_DIR, outside the clone, and the ticket's own label
#     is what authorizes the park: the file says "the agent asks to park", the label says "the
#     agent recorded a punt". Both, or this is contamination rather than a punt, and a run that
#     did real work parks for a reason that never happened.
if [ -f "${FC_SIGNAL_DIR}/.foundry-delivery-scale" ] && ticket_has_label "$DELIVERY_SCALE_LABEL"; then
  stop_line "worker: ${FC_PHASE} judged delivery-scale - the prepared delivery prompt is on the ticket; delivery-scale stop, not retrying (exit ${DELIVERY_SCALE_EXIT})"
  exit "$DELIVERY_SCALE_EXIT"
fi

# 3c. Wrong-repo sentinel: the resolve skill found the ticket's fix lives in ANOTHER repo, so
#     this repo can hold no branch, no conformance run, and no PR for it (issue #35). Like 3b
#     the agent has ALREADY recorded the finding on GitHub - a comment naming the owning repo
#     and the foundry-wrong-repo label - and the sentinel carries that repo so this log names
#     it too. Exit the wrong-repo terminal code: no retry can conjure a PR for a file this
#     repo does not contain, so the run parks for the operator's transfer instead of burning
#     its whole budget on the same impossible check. Checked BEFORE step 8's completeness
#     contract, which would otherwise read "no open PR", exit 1, and retry to a red FAILED
#     (playbook-studio#8, INT-FC-R113).
if [ -f "${FC_SIGNAL_DIR}/.foundry-wrong-repo" ] && ticket_has_label "$WRONG_REPO_LABEL"; then
  owner_repo="$(head -n1 "${FC_SIGNAL_DIR}/.foundry-wrong-repo" 2>/dev/null | tr -d '[:space:]')"
  stop_line "worker: ${FC_PHASE} found #${FC_TICKET:-?}'s fix lives in ${owner_repo:-another repo}, not $(basename "$repo_path") - the ticket is labelled and commented; wrong-repo stop, not retrying (exit ${WRONG_REPO_EXIT})"
  exit "$WRONG_REPO_EXIT"
fi

# 4. Self-validate: the phase's record must exist and carry content. Presence is the
#    domain's completeness contract - resolver.derive_from_records treats a committed
#    record as the phase being done and reads the gate line (left unsigned here) apart from
#    it. Validate what the resolver reads - the record - never a second contract of our
#    own invention (INT-FC-R50).
#    Learn leaves no record (its stamp lands in the journal), so its signal is the agent's own exit.
#
#    A missing or empty record here is NOT a transient crash: reaching this line means the
#    agent's turn exited 0 (a crash dies back at step 3 under `set -o pipefail`). So the agent
#    ran to completion and chose not to write its record - a deliberate park at a blocker it
#    must not work around (e.g. an unsigned upstream gate it correctly refused to bypass, per
#    REF-Delivery). Park it degraded (the terminal sentinel the executor does NOT retry) so the
#    line stops for a human in ONE attempt, instead of blind-retrying an un-clearable wall to
#    the end of its budget.
if [ -n "${FC_RECORD}" ]; then
  rec=".delivery/${FC_RECORD:-}"
  [ -f "$rec" ] || { stop_line "worker: ${rec} not written - agent finished without its record (deliberate park); degraded stop, not retrying"; exit "$DEGRADED_EXIT"; }
  [ -s "$rec" ] || { stop_line "worker: ${rec} is empty - agent finished without a real record; degraded stop, not retrying"; exit "$DEGRADED_EXIT"; }
  # Presence is not completeness: a degraded stop writes a full record that says
  # status: aborted. Read the work-truth the agent stamped (REF-Delivery frontmatter,
  # frontmatter.py) once here - step 5 gates on it and step 7 turns it into the exit
  # code the executor reacts to. A phase record must declare a supported status.
  record_status=$(python3 "$FC_RECORD_RUN_HELPER" --record-status "$rec" || true)
fi

# 4-learn. Learn's completeness contract. Learn leaves no record, but reconcile-delivery
#    stamps a dated `learned:` into .delivery/journal.md's LEADING frontmatter when the
#    reconcile actually executed (the resolver derives the learned state from that stamp,
#    so the cockpit stops offering Drive Learn on a line whose Learn already ran). An
#    agent turn that exits 0 without the stamp parked at a wall it must not work around
#    (a pending delivery gate, a degraded build record) - the learn twin of a missing
#    record, so a degraded stop, not a retry. A journal stamped by an EARLIER learn
#    passes: a re-driven learn is an idempotent no-op, never a failure. Maintenance
#    workers also run with FC_RECORD empty, so this keys on the phase, not the gap.
if [ -z "${FC_RECORD}" ] && [ "${FC_PHASE}" = "learn" ]; then
  if ! awk 'NR==1 && $0!="---" {exit}
            NR>1 && $0=="---" {closed=1; exit}
            /^learned:[ \t]*[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/ {found=1}
            END {exit (found && closed ? 0 : 1)}' .delivery/journal.md 2>/dev/null; then
    stop_line "worker: learn ended without a dated 'learned:' in .delivery/journal.md frontmatter (deliberate park); degraded stop, not retrying"
    exit "$DEGRADED_EXIT"
  fi
fi

# 4b. Fail-safe on a self-signed gate: stamp_gate.py is the only writer of `signed:`, and at
#     this point in the script it has not run yet - so a DATED `signed:` in the phase's own
#     record is the agent hand-signing its own gate (INT-FC-R103). Left alone this fails
#     OPEN: step 5's pending-check finds nothing to do, the committed review is never verified,
#     and the phase surfaces "done - signed" with zero review. Worse, the agent commits its
#     record during its own turn, so the forged date is already authoritative on the remote
#     - were a later review to FAIL, the next phase's pre-flight would still read a closed
#     gate. Fail SAFE instead: strip the signature back to
#     `pending`, clear the self-written review date, commit the correction immediately (so
#     the forgery never outlives this attempt on the remote), and fall through to step 5,
#     which verifies the phase's review and closes the gate the legitimate way for the
#     mode. Un-signing is not
#     stamping: the stamp stays stamp_gate.py's alone (REF-Delivery anti-pattern 30); this
#     mirrors the console's own reopen_gate act, the one other legitimate un-signer.
#     A QUOTED date counts: the helpers strip quotes before reading the field, so
#     `signed: "2026-07-27"` is as much a forged signature as the bare form, and a strip
#     that missed it would hand step 4c a record its helper refuses to touch.
if [ -n "${FC_RECORD}" ] && [ -n "${FC_GATE:-}" ] && [ -f "${rec:-/nonexistent}" ] \
   && grep -qiE '^signed:[[:space:]]*["'"'"']?[0-9]{4}-[0-9]{2}-[0-9]{2}' "$rec"; then
  echo "worker: ${FC_RECORD} arrived self-signed by the agent; stripping to pending and verifying its review anyway" >&2
  python3 - "$rec" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
text = re.sub(r"""(?im)^(signed\s*:)\s*["']?\d{4}-\d{2}-\d{2}.*$""", r"\1 pending", text, count=1)
text = re.sub(r"""(?im)^(reviewed\s*:)\s*["']?\d{4}-\d{2}-\d{2}.*$""", r"\1 ", text, count=1)
open(path, "w", encoding="utf-8").write(text)
PY
  { git -C .delivery add "$FC_RECORD" && git -C .delivery commit -m "delivery(${FC_PHASE}): strip agent-signed gate to pending (worker guard)" \
    && git -C .delivery push origin "HEAD:refs/heads/${FC_SCRATCH_REF}"; } || true
fi

# (There is deliberately NO harness-side frontmatter write between the agent's turn and the
# review. The record helper (reach_gate.py, baked and exported above) is run by the AGENT,
# where its skill says to, with the provenance the compiled prompt hands it from this pod's
# environment (FC_RUN, FC_MODE, FC_CREDENTIAL_REF) - the same front door an attended session
# uses. A harness-side re-run of the helper here rewrites `run`/`mode`/`credential_ref` in
# the working tree, uncommitted, and the fresh-eyes reviewer - correctly - refuses a gate
# whose on-disk record no committed review covers (INT-FC-R111). The reviewed bytes are the
# agent's last commit; the writers after the review are the run-figures step (4c: the `run`
# and `run_*` keys, which describe the run rather than the work, so no review judges them)
# and the stamp, which IS the gate's transaction. A sloppy or hand-authored block
# fails loudly instead: 4b strips a forged signature, step 5 leaves a malformed `signed:`
# untouched, the stamper refuses bad evidence, and the reviewer reads the record itself.)

# 4c. The run's figures into the record (issue #115; the function above): AFTER the review
#     the agent committed and BEFORE any commit below, so the keys ride whichever push follows
#     - the stamp's, a failing review's evidence, an aborted record's.
record_run_figures

# 5. Gate policy: a gate only closes over the phase's PASSING fresh-eyes review, in EVERY
#    mode (REF-Delivery section 1, "How a gate closes"). The review is the PHASE'S: the
#    adversarial-review skill it ran, as a clean agent pass with no share of its own
#    context, before its record reached the gate - every round committed under
#    .delivery/reviews/ as <record-stem>-<date>-r<N>.md, FAIL rounds included. This
#    entrypoint spawns no reviewer and prompts nothing (REF-Delivery anti-pattern 40: a
#    runner-authored review prompt is a hand-restated copy of the skill that drifts from
#    its lenses, and a second review over bytes the phase's own PASS just covered is
#    duplicated cost). Its part is mechanical: LOCATE the record's newest artifact, READ
#    the verdict off it, and STAMP only over a PASS (INT-FC-R150). The STAMP is
#    deterministic and is the playbook's own stamp_gate.py, the single stamper every
#    runner executes (a hand-ported sed drifts from the helper's guards; anti-pattern 30).
#    A claimed verdict must carry its evidence: the artifact's repo-relative path is
#    passed as --review-log, which the helper re-verifies (it refuses a --review-verdict
#    without the artifact, or one whose last VERDICT token is not PASS). One-shot: a PASS
#    stamps the gate (the operator's standing pre-authorization), and a stamp the helper
#    refuses over that PASS records the review and ends the step on the stamp-refused stop
#    (68) once step 6 has pushed the record. Interactive: a PASS is
#    recorded into the record's `reviewed:` field (--review-only) and the gate suspends
#    for the human signature - the cockpit's Sign runs this same helper, which refuses
#    without that recorded review. No artifact, or a newest artifact that does not end
#    PASS, exits non-zero in both modes after pushing the scratch as it stands (the
#    committed FAIL is the retried phase's prior): the executor retries the whole phase
#    fresh, then parks it degraded once the budget is spent.
#
#    Trigger on status: gate - the status a REF-Delivery phase stamps when it reaches its gate
#    with `signed: pending` (deliver-engagement and design-session both write exactly
#    `status: gate`). `complete` is accepted too for robustness, but `gate` is the real one:
#    keyed SOLELY on `complete` the stamp never fires, every gate stays pending, and the
#    next phase's agent correctly refuses to start past an unsigned upstream gate - stalling
#    the whole one-shot line at intent+plan. The status is the trigger; the resolver treats
#    `gate` and `complete` alike (frontmatter.py), so this must too.
if [ -n "${FC_RECORD}" ] && [ -n "${FC_GATE:-}" ] \
   && { [ "${record_status:-}" = "gate" ] || [ "${record_status:-}" = "complete" ]; }; then
  if grep -qiE '^signed:[[:space:]]*pending' "$rec"; then
    # LOCATE: the record's newest review artifact, version order (r10 follows r9, a later
    # date follows an earlier one). The group's status is masked so an absent reviews/
    # folder reads as "none" rather than tripping pipefail.
    review_log=$( { [ -d .delivery/reviews ] && find .delivery/reviews -maxdepth 1 -name "${FC_RECORD%.md}-*.md"; } 2>/dev/null | sort -V | tail -n1 || true)
    if [ -z "$review_log" ]; then
      stop_line "worker: no fresh-eyes review for ${FC_RECORD} under .delivery/reviews/ - the phase reached its ${FC_GATE} gate unreviewed; failing the attempt"
      { git -C .delivery add -A && git -C .delivery commit -q -m "delivery(${FC_PHASE}): unreviewed at the ${FC_GATE} gate; scratch kept as evidence" && git -C .delivery push origin "HEAD:refs/heads/${FC_SCRATCH_REF}"; } || true
      exit 1
    fi
    # READ: the last VERDICT:(PASS|FAIL) occurrence anywhere in the artifact, not literally
    # the last line: a reviewer may wrap it in markdown emphasis (**VERDICT: PASS**) and
    # keep writing after it, and an exact-last-line parse reads that real PASS as unparsed
    # and fails a passing gate (issue #25, INT-FC-R102). The skill asks for it as the final
    # line; this only tolerates a reviewer that adds trailing prose or bold markup.
    verdict=$(grep -oiE 'VERDICT:[[:space:]]*(PASS|FAIL)' "$review_log" | tail -n1 || true)
    if [ "$(printf '%s' "$verdict" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')" != "VERDICT:PASS" ]; then
      stop_line "worker: fresh-eyes review did not pass the ${FC_GATE} gate for ${FC_PHASE} (${review_log}: ${verdict:-no verdict})"
      { git -C .delivery add -A && git -C .delivery commit -q -m "delivery(${FC_PHASE}): failing fresh-eyes review kept as evidence" && git -C .delivery push origin "HEAD:refs/heads/${FC_SCRATCH_REF}"; } || true
      exit 1
    fi
    echo "worker: ${FC_GATE} gate evidence is ${review_log} (the phase's newest fresh-eyes review, ${verdict})"
    stamp_date=$(date +%F)
    # EXPORT: a phase with a tool freezes its deliverables into the scratch at the stamp
    # (REF-Delivery section 1, "How a gate closes", step 3), read from the studio's
    # in-cluster door - the public host is a browser login - with the delivery slug as the
    # project key. Both are the compiler's (FC_TOOL_URL, FC_SLUG; INT-FC-R151), the same
    # door the cockpit's Sign hands the stamper. A phase whose gate freezes nothing carries
    # no URL and stamps export-free; a tooled gate handed none is refused by the stamper.
    tool_flags=()
    if [ -n "${FC_TOOL_URL:-}" ]; then
      tool_flags=(--tool-url "$FC_TOOL_URL" --tool-slug "${FC_SLUG:?FC_SLUG required beside FC_TOOL_URL: the delivery slug keys the export}")
    fi
    # STAMP: the artifact IS the gate's evidence. Its repo-relative path goes to the stamper
    # as --review-log, which re-reads the file's LAST VERDICT token (the same tolerant rule
    # as the grep above) and refuses a claimed verdict whose committed evidence is absent or
    # does not end PASS - the claim and the artifact are one file, so they cannot disagree.
    # The grep stays the fast-fail; the helper's read is the re-verification. Step 6's
    # in-mount commit (`git -C .delivery add -A`) carries an artifact the phase left
    # uncommitted in the same commit as the stamped record.
    #
    # A `stamp_refused:` an earlier one-shot stamp left (issue #181) belongs to that attempt
    # only: it is the worker's own field, cleared before every mode's stamp, so a line
    # re-driven after the stop (one-shot again, or switched to interactive) never shows a
    # refusal its run did not meet.
    set_stamp_refusal ""
    stamp_refusal=""
    if [ "${FC_MODE:-}" = "one-shot" ] && [ "${FC_ARTIFACT:-}" = "build" ] && [ -n "${FC_HOME_BRANCH:-}" ]; then
      # A MANAGED app's delivery gate is the home's MERGE, not this review (foundry-platform
      # #135): the app runs on no foundry, so its bar is proven-in-their-CI-and-merged, and the
      # merge is the other organization's act. One-shot's standing pre-authorization covers the
      # gates the engine can honestly close over a review; this one it cannot, so the review is
      # recorded and signed: stays pending for the operator to stamp once the pull request
      # lands. Stamping it here would call a line delivered whose change nobody has accepted.
      python3 "$FC_STAMP_HELPER" --repo . --record "$FC_RECORD" --date "$stamp_date" \
        --review-verdict pass --review-log "$review_log" --review-only "${tool_flags[@]}" "${lifecycle_flags[@]}"
      echo "worker: ${FC_GATE} review recorded (${stamp_date}, evidence ${review_log}); the gate is the home's merge, stamped by the operator when it lands - not by one-shot"
    elif [ "${FC_MODE:-}" = "one-shot" ]; then
      # The helper stamps signed:, records reviewed:, promotes status: gate to complete,
      # and appends the closure provenance NAMING THE AUTHORITY - an agent that reads a
      # bare mechanical stamp finds no authorization evidence and rightly refuses, so the
      # record must carry the why.
      #
      # A REFUSED stamp over that passing review is a wall no retry clears (issue #181): the
      # work and its review stand, and what refused is the closure - a studio that is down,
      # an export it would not serve, a door that 404s, a record the stamper will not close.
      # Re-running the whole phase meets the same wall. So the review is recorded
      # (--review-only, which exports nothing) and the stamper's own refusal line rides the
      # record as `stamp_refused:`, which step 6 pushes: the line reads awaiting this gate,
      # its next command naming the refusal. Step 7 then ends the step on the stamp-refused
      # terminal stop (68), which Argo never retries, and the run parks for the operator:
      # Sign closes the gate from the cockpit, exporting through the record's link, and a
      # drive continues the line in one-shot. A refusal the record itself causes (say, a
      # missing `delivers:`) makes Sign refuse with the same line, and the operator
      # re-drives the phase. A refusal is the stamper's to state: an exit with no
      # REFUSED/FAIL line is not one, and stays a transient.
      set +e
      stamp_out=$(python3 "$FC_STAMP_HELPER" --repo . --record "$FC_RECORD" --date "$stamp_date" \
        --review-verdict pass --review-log "$review_log" "${tool_flags[@]}" "${lifecycle_flags[@]}" \
        --by "the deterministic engine (one-shot: the operator's standing pre-authorization, REF-Delivery section 1)" 2>&1)
      stamp_status=$?
      set -e
      printf '%s\n' "$stamp_out"
      refusal=$(printf '%s\n' "$stamp_out" | grep -E '^(REFUSED|FAIL):' | tail -n1 || true)
      if [ "$stamp_status" -eq 0 ]; then
        echo "worker: ${FC_GATE} gate stamped ${stamp_date} (one-shot, review passed, stamp_gate.py; evidence ${review_log})"
      elif [ -n "$refusal" ]; then
        # A refusal that also refuses the review (the record or journal it reads is unsound)
        # leaves no gate to sign: the attempt fails, saying both.
        if ! record_out=$(python3 "$FC_STAMP_HELPER" --repo . --record "$FC_RECORD" --date "$stamp_date" \
          --review-verdict pass --review-log "$review_log" --review-only "${lifecycle_flags[@]}" 2>&1); then
          printf '%s\n' "$record_out"
          record_refusal=$(printf '%s\n' "$record_out" | grep -E '^(REFUSED|FAIL):' | tail -n1 || true)
          stop_line "worker: the ${FC_GATE} stamp refused (${refusal}) and recording its review refused too (${record_refusal:-no refusal line}); failing the attempt"
          exit 1
        fi
        printf '%s\n' "$record_out"
        set_stamp_refusal "$refusal"
        stamp_refusal="$refusal"
        echo "worker: ${FC_GATE} stamp refused (${refusal}); review recorded, signed: left pending"
      else
        stop_line "worker: the ${FC_GATE} stamp exited ${stamp_status} without a refusal line; transient, retrying"
        exit 1
      fi
    else
      # Interactive: record the review, leave signed: pending. The suspend that follows
      # is the human's gate; the cockpit's Sign fires the same helper over this record
      # WITHOUT --review-verdict, closing over the recorded reviewed: date - so the
      # committed review artifact written here is the evidence behind that date too.
      python3 "$FC_STAMP_HELPER" --repo . --record "$FC_RECORD" --date "$stamp_date" \
        --review-verdict pass --review-log "$review_log" --review-only "${tool_flags[@]}" "${lifecycle_flags[@]}"
      echo "worker: ${FC_GATE} review recorded (${stamp_date}, evidence ${review_log}); gate awaits the human signature"
    fi
  else
    # The record's gate line is not in the canonical shape (a dated signature would have
    # been stripped to pending in step 4b, so this is a malformed or empty `signed:`);
    # leave it rather than guess. An unsigned next phase holds at the gate - an honest stop.
    echo "worker: no 'signed: pending' line in ${FC_RECORD}; gate left untouched" >&2
  fi
fi

# 6. Commit and push the record - from INSIDE the scratch mount, onto the line's ref by
#    explicit refspec: the scratch never rides the default branch, and a bare `git push`
#    from the main tree would target exactly that. `|| true` on the commit tolerates an
#    agent that already committed its work; the push must land or the step fails. Learn
#    leaves no record (FC_RECORD is empty) and journals through its own in-mount commits,
#    so this block runs only for the record-leaving phases.
rm -f "${WORK_DIR}/mcp.json"
if [ -n "${FC_RECORD}" ]; then
  git -C .delivery add -A
  git -C .delivery commit -m "delivery(${FC_PHASE}): ${FC_SKILL}" || true
  git -C .delivery push origin "HEAD:refs/heads/${FC_SCRATCH_REF}"
fi
# 7. The exit code follows the record's work-truth (read in step 4), now that the record
#    is pushed. status: aborted is a DELIBERATE degraded stop - the agent hit a wall it
#    must not work around - so exit the terminal sentinel: the executor does NOT retry it
#    (a retry cannot clear the blocker) and the line parks degraded for a human to clear
#    it and re-drive. A non-complete, non-gate status (in-progress/unknown: a crash
#    mid-write or a missing status) is transient - exit 1 so the executor retries.
#    Only complete and gate advance. Learn leaves no record and keeps the
#    agent's own exit above. A one-shot gate whose stamp refused over a passing review
#    (step 5) is the stamp-refused stop: its record, review recorded and refusal written, is
#    pushed above, so the line reads awaiting that gate, and the step ends terminal so the
#    executor never re-runs the phase into the same wall.
if [ -n "${FC_RECORD}" ]; then
  case "${record_status:-}" in
    complete|gate) : ;;
    aborted)
      stop_line "worker: ${FC_PHASE} recorded status: aborted - degraded stop, not retrying (exit ${DEGRADED_EXIT})"
      exit "$DEGRADED_EXIT" ;;
    *)
      stop_line "worker: ${FC_PHASE} record status '${record_status}' is not complete - transient, retrying"
      exit 1 ;;
  esac
  if [ -n "${stamp_refusal:-}" ]; then
    stop_line "worker: the ${FC_GATE} stamp refused over a passing review (${stamp_refusal}) - stamp-refused stop, not retrying (exit ${STAMP_REFUSED_EXIT}); sign the ${FC_GATE} gate from the cockpit, then drive the line"
    exit "$STAMP_REFUSED_EXIT"
  fi
fi

# 8. Maintenance completeness contract. A maintenance worker writes no .delivery/ record, so
#    steps 4-7 (which gate on FC_RECORD) are inert for it and its ONLY prior signal is the
#    agent's exit code - on which alone a gated resolve that ends its turn BEFORE opening
#    the PR reads as a Succeeded run that shipped nothing. Validate the act's real artifact
#    on GitHub here:
#      - resolve, gated/one-shot: an OPEN PR whose branch carries the ticket AND whose title or
#        body references #n (the one shared rule, INT-FC-R84; "Stop when the PR is open");
#      - resolve, direct: a NEW ticket-referencing commit on the default branch since clone;
#      - review: a posted review carrying a VERDICT line on the target PR;
#      - reconcile-docs: report-only, no artifact - the agent's exit stays the signal.
#    A missing artifact exits 1 so the executor RETRIES and, past its budget, the run FAILS
#    honestly instead of showing done. It fails OPEN on an API error (an unreachable gh reads
#    unknown, never a false failure) - the same fail-closed-on-answer / fail-open-on-error
#    rule the positions derivation uses for checks.
case "${FC_PHASE:-}" in
  maintenance:*)
    export GH_TOKEN="${FC_GIT_TOKEN:-${GH_TOKEN:-}}"
    act="${FC_PHASE#maintenance:}"
    # WHERE the pull request is. For an ordinary app it is our own repo; for an app whose home
    # is another organization's, the ticket is ours and the PR is THEIRS - so the artifact is
    # looked for over there, on their credential, because ours cannot see it and asking with
    # ours would answer for a PR that was never opened.
    #
    # WHICH READER performs it follows from that, and is decided ONCE here rather than at
    # each call: our own repo is read with plain gh on our token, and a pair's goes through
    # the door (#167), which is what knows the pair's host as well as its credential.
    pr_repo="$repo_path"
    pr_read="gh"
    if [ -n "${FC_HOME_BRANCH:-}" ] && [ -n "${FC_PAIR_REPO:-}" ]; then
      pr_repo="$FC_PAIR_REPO"
      pr_read="$FC_PAIR_DOOR"
    fi
    tkt="${FC_TICKET:-}"
    # The CEREMONY (gated/one-shot/direct), NOT FC_MODE - a maintenance worker's RunMode is
    # always interactive, so the direct-vs-PR decision must read FC_MAINT_MODE.
    cer="${FC_MAINT_MODE:-gated}"
    if [ "$act" = "resolve" ] && [ -n "$tkt" ]; then
      if [ "$cer" = "direct" ]; then
        git fetch -q origin "$DEFAULT_BRANCH" 2>/dev/null || true
        if git log -E -n1 --grep "#${tkt}([^0-9]|\$)" "${BASE_SHA}..origin/${DEFAULT_BRANCH}" 2>/dev/null | grep -q .; then
          echo "worker: resolve #${tkt} landed a ticket-referencing commit on ${DEFAULT_BRANCH} (direct)"
        else
          stop_line "worker: resolve #${tkt} (direct) left NO ticket-referencing commit on ${DEFAULT_BRANCH} - failing so a green run never ships nothing"
          exit 1
        fi
      elif prs=$("$pr_read" pr list --repo "$pr_repo" --state open --json number,headRefName,title,body 2>/dev/null); then
        # The one shared rule (INT-FC-R84): branch carries the ticket AND the title or body
        # references #n - so a coincidental branch (a release/7-rc) never counts, and this
        # agrees with the strip and the judge about "the PR for #n".
        if prn=$(printf '%s' "$prs" | jq -r --arg t "$tkt" \
            'first(.[] | select((.headRefName | test("(^|/)"+$t+"-")) and (((.title // "")+"\n"+(.body // "")) | test("#"+$t+"([^0-9]|$)"))) | .number) // empty' \
            2>/dev/null) && [ -n "$prn" ]; then
          echo "worker: resolve #${tkt} has an open PR (${cer}): #${prn} on ${pr_repo}"
          # A Managed app's PR is on a home we do not own, and the console's loop reads OUR
          # repo - so the link is RECORDED on our ticket rather than re-derived cross-repo:
          # a marked comment naming the home PR (foundry-platform#136). Done HERE, by the
          # entrypoint, because the entrypoint is what just proved the PR exists; an agent
          # asked to remember it is a pointer that is sometimes missing. Idempotent: a
          # re-drive that found the same PR leaves no duplicate.
          if [ "$pr_repo" != "$repo_path" ]; then
            # The pointer's URL is the GITHUB door's shape, and it is parsed by
            # orchestrator/application/door.py - keep the two in step. The host is already
            # free (FC_PAIR_HOST); what is GitHub-shaped is the /pull/<n> path, so a second
            # door writes its own and teaches that parser its alternation.
            marker="<!-- foundry:home-pr https://${FC_PAIR_HOST:-github.com}/${pr_repo}/pull/${prn} -->"
            if ! gh issue view "$tkt" --repo "$repo_path" --comments --json comments \
                 --jq '.comments[].body' 2>/dev/null | grep -qF "$marker"; then
              gh issue comment "$tkt" --repo "$repo_path" --body "$(printf '%s\n\nResolved in %s#%s, theirs to review and merge.' "$marker" "$pr_repo" "$prn")" >/dev/null 2>&1 \
                && echo "worker: recorded the home PR on #${tkt}" \
                || echo "worker: could not record the home PR on #${tkt} (gh/API unreachable) - the loop will not see it until it is recorded" >&2
            fi
          fi
        else
          stop_line "worker: resolve #${tkt} left NO open PR (${cer}) - failing so a green run never ships nothing"
          exit 1
        fi
      else
        echo "worker: could not list PRs to verify resolve #${tkt} (gh/API unreachable) - skipping completeness (fail-open)" >&2
      fi
    elif [ "$act" = "review" ] && [ -n "$tkt" ]; then
      # Resolve the PR under review. A one-shot resolve's review step gets the TICKET number,
      # so find the open PR whose branch/body carries it (the same rule as resolve); a
      # standalone review gets the PR number directly, so if no PR carries $tkt as a ticket,
      # $tkt IS the PR number. Then confirm that PR received a review with a VERDICT line:
      # any of review-pr's three endings. UNRECORDED is a completed review that records no
      # verdict (its identity is the PR's author or the merger), so the act is done.
      prn=""
      if prs=$("$pr_read" pr list --repo "$pr_repo" --state open --json number,headRefName,title,body 2>/dev/null); then
        prn=$(printf '%s' "$prs" | jq -r --arg t "$tkt" \
          'first(.[] | select((.headRefName | test("(^|/)"+$t+"-")) and (((.title // "")+"\n"+(.body // "")) | test("#"+$t+"([^0-9]|$)"))) | .number) // empty')
      fi
      [ -z "$prn" ] && prn="$tkt"  # standalone review: $tkt is already the PR number
      if rv=$("$pr_read" pr view "$prn" --repo "$pr_repo" --json reviews 2>/dev/null); then
        if printf '%s' "$rv" | jq -e '[.reviews[]? | select((.body // "") | test("VERDICT:[[:space:]]*(PASS|FAIL|UNRECORDED)"; "i"))] | length > 0' >/dev/null 2>&1; then
          echo "worker: review posted a VERDICT on PR #${prn}"
        else
          stop_line "worker: review posted NO VERDICT on PR #${prn} - failing (not done)"
          exit 1
        fi
      else
        echo "worker: could not read PR #${prn} to verify the review (gh/API unreachable) - skipping (fail-open)" >&2
      fi
    fi
    ;;
  promotion:*)
    # A promotion's artifact is the DOOR, and a door either exists on a remote or does not.
    # The same never-ships-nothing rule a maintenance act is held to: an agent that ended its
    # turn before pushing leaves a run reading Succeeded over a promotion that never happened,
    # and promotion is the one line whose entire job is moving proof rather than hope.
    tgt="${FC_PROMOTE_TARGET:-}"
    rel="${FC_RELEASE:-}"
    rel="${rel#v}"
    if [ -n "${FC_PAIR_REPO:-}" ]; then
      # A pair's door: the promote/<release> pull request must be open on THEIR repository,
      # read on THEIR credential - ours cannot see it, and asking with ours would answer for
      # a door that was never opened.
      if prs=$("$FC_PAIR_DOOR" pr list --repo "$FC_PAIR_REPO" --state open                  --json headRefName -L 60 2>/dev/null); then
        if printf '%s' "$prs" | jq -e --arg r "$rel"             '[.[] | select(.headRefName | test("^promote/v?" + $r + "$"))] | length > 0' >/dev/null 2>&1; then
          echo "worker: promotion ${tgt} opened promote/${rel} on ${FC_PAIR_REPO}"
        else
          stop_line "worker: promotion ${tgt} left NO open promote/${rel} on ${FC_PAIR_REPO} - failing so a green run never ships nothing"
          exit 1
        fi
      else
        echo "worker: could not list ${FC_PAIR_REPO} PRs to verify the door (gh/API unreachable, or the pair credential does not reach it) - skipping completeness (fail-open)" >&2
      fi
    elif [ -n "$rel" ]; then
      # An environment door: the write landed on this app's own deploy branch, so it is read
      # on our own credential. The branches are fetched fresh - the agent pushed after the
      # clone, so every local ref is stale by construction.
      if git fetch -q origin "+refs/heads/deploy-*:refs/remotes/origin/deploy-*" 2>/dev/null; then
        if git for-each-ref --format='%(refname)' 'refs/remotes/origin/deploy-*'              | xargs -r -I{} git grep -lE "^[[:space:]]*(tag|version):[[:space:]]*[\"']?v?${rel}[\"']?[[:space:]]*$" {} 2>/dev/null              | grep -q .; then
          echo "worker: promotion ${tgt} landed ${rel} on a deploy branch"
        else
          stop_line "worker: promotion ${tgt} left NO ${rel} pin on any deploy branch - failing so a green run never ships nothing"
          exit 1
        fi
      else
        echo "worker: could not fetch the deploy branches to verify the door - skipping completeness (fail-open)" >&2
      fi
    fi
    ;;
esac

echo "worker: ${FC_PHASE} complete"
