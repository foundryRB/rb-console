"""Establish a delivery on a repo: mint the line's `delivery/<line-id>` scratch branch,
mount it at `.delivery/`, and capture the customer's verbatim request. The
deterministic writer of the scratch, so no agent and no runner hand-rolls it
(REF-Delivery section 1, anti-pattern 30).

The delivery scratch lives on one orphan branch per line, `delivery/<line-id>`, where
the line id is the line's establish date (REF-Delivery section 1). The records sit at
the branch root, the branch shares no history with the default branch, and in a
working checkout it mounts at `.delivery/` as a linked git worktree, so every reader
and writer sees `<repo>/.delivery/<record>` whatever ref carries the bytes. The
default branch git-ignores `.delivery/`: the ignore hides the mount point, never the
records, which are committed on their own ref.

Exactly one `delivery/*` ref may exist per repo, and this helper is the namespace's
only minter, so the singleton binds here: it refuses to mint while any `delivery/*`
ref exists, local or remote-tracking - the single existing line is remounted and
resumed, never re-minted - and it surfaces two distinct lines as an anomaly, never a
state to silently pick from.

Scope is the scratch and nothing else. Creating or adopting the repo itself is a
separate act with a separate blast radius (a remote, a credential, a platform contract),
so a runner that needs it does that first and hands the checkout here.

Idempotent: an existing skeleton or request is never overwritten, so adopting a repo
that is already a delivery keeps the request it was opened with. Re-running changes
nothing and says so.

Stdlib only. Usage:

    # open a line on a checkout, capturing the ask that entered it
    python establish_scratch.py --repo <repo-root> --request "<the customer's words>"

    # the same, reading the ask from a file (preserves newlines exactly)
    python establish_scratch.py --repo <repo-root> --request-file ask.txt

    # write the files but skip their commits (the branch mint and mount still happen)
    python establish_scratch.py --repo <repo-root> --no-commit
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

SCRATCH = ".delivery"

_LINE_ID = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SKELETON = (
    "# Delivery scratch\n\nCommitted on this line's own `delivery/<line-id>` branch and "
    "mounted at `.delivery/` per REF-Delivery. Progress is derived from which phase "
    "records exist here. Phase: pre-scope.\n"
)

_ESTABLISH_SUBJECT = "delivery: establish line {line_id}"
_IGNORE_SUBJECT = "delivery: ignore the scratch mount point"
_SKELETON_SUBJECT = "delivery: register (initialise .delivery/ scratch)"
_REQUEST_SUBJECT = "delivery: capture the customer request"


def request_doc(request: str) -> str:
    """The customer's verbatim request, the ground truth the Scope phase reads
    (REF-Delivery section 2). Not a phase record, so its presence advances nothing."""
    return (
        "# Customer request\n\nThe verbatim ask that enters the Scope phase "
        "(REF-Delivery section 2); ground truth for what was asked.\n\n---\n\n"
        + request.strip()
        + "\n"
    )


def _git(
    tree: Path, args: list[str], *, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(tree), *args],
        capture_output=True,
        text=True,
        check=False,
        input=input_text,
    )


def _commit(tree: Path, name: str, subject: str) -> None:
    """Commit one file under its own subject, scoped to its pathspec on the add AND
    the commit, so nothing else the caller staged is swept along. `delivery:` is the
    deterministic-write type, which cuts no release."""
    _git(tree, ["add", "--", name])
    done = _git(tree, ["commit", "-q", "-m", subject, "--", name])
    if done.returncode != 0 and "nothing to commit" not in (done.stdout + done.stderr):
        print(f"NOTE: commit refused: {(done.stderr or done.stdout).strip()}", file=sys.stderr)


def _scan_delivery_refs(repo: Path) -> tuple[dict[str, str | None], list[str]]:
    """Every occupant of the delivery ref namespace, local and remote-tracking.

    Returns (lines, anomalies): `lines` maps each line's branch name
    (`delivery/<line-id>`) to the remote-tracking ref to create it from when no local
    branch exists (else None); `anomalies` are refs that squat the namespace without
    naming a line (a flat `delivery` ref, which cannot coexist with `delivery/<x>`).
    """
    refs = _git(repo, ["for-each-ref", "--format=%(refname)"]).stdout.splitlines()
    lines: dict[str, str | None] = {}
    local: set[str] = set()
    anomalies: list[str] = []
    for ref in refs:
        if ref.startswith("refs/heads/"):
            name = ref[len("refs/heads/") :]
            if name == "delivery":
                anomalies.append(ref)
            elif name.startswith("delivery/"):
                local.add(name)
                lines.setdefault(name, None)
        elif ref.startswith("refs/remotes/"):
            rest = ref[len("refs/remotes/") :]
            _, _, name = rest.partition("/")
            if name == "delivery":
                anomalies.append(ref)
            elif name.startswith("delivery/"):
                lines.setdefault(name, ref)
    for name in local:
        lines[name] = None
    return lines, anomalies


def _mint(repo: Path, line_id: str) -> str | None:
    """Create the line's orphan branch: a parentless root commit over the empty tree,
    sharing no history with the default branch. Returns the branch name, or None."""
    branch = f"delivery/{line_id}"
    tree = _git(repo, ["mktree"], input_text="")
    if tree.returncode != 0:
        print(f"ERROR: cannot mint the scratch branch: {tree.stderr.strip()}", file=sys.stderr)
        return None
    root = _git(
        repo,
        ["commit-tree", tree.stdout.strip(), "-m", _ESTABLISH_SUBJECT.format(line_id=line_id)],
    )
    if root.returncode != 0:
        print(f"ERROR: cannot mint the scratch branch: {root.stderr.strip()}", file=sys.stderr)
        return None
    made = _git(repo, ["branch", branch, root.stdout.strip()])
    if made.returncode != 0:
        print(f"ERROR: cannot mint the scratch branch: {made.stderr.strip()}", file=sys.stderr)
        return None
    return branch


def _mount(repo: Path, branch: str, remote_src: str | None) -> bool:
    """Mount the line's branch at `<repo>/.delivery` as a linked worktree, creating
    the local branch from its remote-tracking ref when only that side exists."""
    _git(repo, ["worktree", "prune"])
    if remote_src is not None:
        made = _git(repo, ["branch", "--track", branch, remote_src])
        if made.returncode != 0:
            # A remote-tracking ref with no configured remote behind it cannot seed
            # tracking; the branch still materialises, and `push -u` sets upstream.
            made = _git(repo, ["branch", branch, remote_src])
        if made.returncode != 0:
            print(f"ERROR: cannot mount the scratch: {made.stderr.strip()}", file=sys.stderr)
            return False
    added = _git(repo, ["worktree", "add", str(repo / SCRATCH), branch])
    if added.returncode != 0:
        print(
            f"ERROR: cannot mount the scratch worktree: "
            f"{(added.stderr or added.stdout).strip()}",
            file=sys.stderr,
        )
        return False
    return True


def _ensure_ignore(repo: Path, *, no_commit: bool) -> bool:
    """The default branch ignores `.delivery/`: the mount point, never the records,
    which are committed on the line's own ref."""
    path = repo / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if any(line.strip().lstrip("/").rstrip("/") == SCRATCH for line in text.splitlines()):
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + f"{SCRATCH}/\n", encoding="utf-8")
    if not no_commit:
        _commit(repo, ".gitignore", _IGNORE_SUBJECT)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Repo root the delivery is established on")
    parser.add_argument("--request", help="The customer's verbatim ask")
    parser.add_argument(
        "--request-file", help="Read the verbatim ask from a file (wins over --request)"
    )
    parser.add_argument(
        "--line-id",
        help="The line id for the branch name, YYYY-MM-DD (defaults to today: the line "
        "id is the line's establish date, REF-Delivery section 1)",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Skip the record and ignore commits; the line's branch and its worktree "
        "mount are still established",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the line's ref after committing (push -u origin delivery/<line-id>)",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"ERROR: no such repo root: {repo}", file=sys.stderr)
        return 2
    if _git(repo, ["rev-parse", "--git-dir"]).returncode != 0:
        print(f"ERROR: not a git checkout: {repo}", file=sys.stderr)
        return 2

    request = args.request or ""
    if args.request_file:
        try:
            request = Path(args.request_file).read_text(encoding="utf-8")
        except OSError as err:
            print(f"ERROR: cannot read --request-file: {err}", file=sys.stderr)
            return 2

    lines, anomalies = _scan_delivery_refs(repo)
    if anomalies:
        print(
            f"REFUSED: refs squat the delivery namespace without naming a line "
            f"({', '.join(anomalies)}); resolve them by hand before establishing.",
            file=sys.stderr,
        )
        return 1
    if len(lines) > 1:
        print(
            f"REFUSED: more than one delivery/* ref exists ({', '.join(sorted(lines))}). "
            f"Exactly one line lives on a repo (REF-Delivery section 1); this is an "
            f"anomaly to surface, never a state to pick from.",
            file=sys.stderr,
        )
        return 1

    written: list[str] = []
    mint_id: str | None = None
    if lines:
        # The singleton invariant: a live line is resumed, never re-minted.
        ((branch, remote_src),) = lines.items()
    else:
        mint_id = args.line_id or date.today().isoformat()
        if not _LINE_ID.match(mint_id):
            print(f"ERROR: --line-id must be YYYY-MM-DD, got: {mint_id}", file=sys.stderr)
            return 2
        branch, remote_src = f"delivery/{mint_id}", None

    # Every refusal runs BEFORE the mint, so a refused establish leaves no
    # delivery/* ref behind for discovery to read as an open line.
    scratch = repo / SCRATCH
    mounted = False
    if scratch.exists():
        head = _git(scratch, ["symbolic-ref", "--short", "HEAD"]).stdout.strip()
        if not (scratch / ".git").is_file() or head != branch:
            print(
                f"REFUSED: {SCRATCH}/ exists but is not the line's worktree mount on "
                f"{branch} (a loose scratch directory, or a mount on the wrong ref); the "
                f"scratch has exactly one shape (REF-Delivery section 1) - resolve it "
                f"by hand.",
                file=sys.stderr,
            )
            return 1
        mounted = True

    if mint_id is not None:
        if _mint(repo, mint_id) is None:
            return 1
        written.append("line")

    if not mounted:
        if not _mount(repo, branch, remote_src):
            if mint_id is not None:
                # A failed mount right after a fresh mint must not strand the ref.
                _git(repo, ["branch", "-D", branch])
            return 1
        written.append("mount")

    if _ensure_ignore(repo, no_commit=args.no_commit):
        written.append("ignore")

    marker = scratch / "README.md"
    if not marker.exists():
        marker.write_text(SKELETON, encoding="utf-8")
        written.append("skeleton")
        if not args.no_commit:
            _commit(scratch, "README.md", _SKELETON_SUBJECT)

    ask = scratch / "request.md"
    if request.strip() and not ask.exists():
        ask.write_text(request_doc(request), encoding="utf-8")
        written.append("request")
        if not args.no_commit:
            _commit(scratch, "request.md", _REQUEST_SUBJECT)

    if args.push and not args.no_commit:
        pushed = _git(scratch, ["push", "-u", "origin", branch])
        if pushed.returncode != 0:
            # A scratch that cannot reach the remote is work lost the moment the
            # session ends (REF-Delivery section 1), so this is stated, never swallowed.
            print(
                f"ERROR: the scratch is committed but not pushed: "
                f"{(pushed.stderr or pushed.stdout).strip()}",
                file=sys.stderr,
            )
            return 1

    state = "+".join(written) if written else "already a delivery"
    print(f"{repo.name}: {state} ({branch})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
