"""The vendored playbook pin is checkable, not merely documented.

Two ways a pin drifts, and they need different mechanisms because the playbook repo is
private and the shared CI carries no cross-repo credential (issue #33):

* the vendored copy is edited in place - offline, free, and asserted here on every push;
* upstream moves and the pin does not - needs the playbook, so it lives in
  ``devops/vendor/check_pin_drift.py``, run by an operator on their own credential.

This file owns the first and asserts that the second exists and is wired.

The manifest carries several SOURCES, each a playbook skill folder with its own local
destination, because the two kinds of vendored file want different homes: the delivery
helpers are RUN as scripts and are baked into the images, so they sit beside the
Dockerfiles; the inbox sweep is IMPORTED in process, so it ships inside the orchestrator
package. One manifest and one refresh script still cover both - a pin split across two
homes is two things to forget.
"""
import base64
import hashlib
import importlib.util
import io
import json
import re
import sys
import tarfile
import urllib.error
from pathlib import Path

from pytest_intent import intent

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "devops" / "vendor"


@intent("INT-FC-R112")
def test_the_vendored_files_still_match_their_recorded_pin():
    manifest = json.loads((VENDOR / "PINNED.json").read_text(encoding="utf-8"))

    # The manifest is the SINGLE home for the pin: repo, commit, and a hash per file under
    # each source. A second copy of the commit elsewhere is a second thing to forget.
    assert re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+", manifest["repo"]), manifest["repo"]
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["ref"]), manifest["ref"]
    sources = manifest["sources"]
    assert set(sources) == {
        "galaxies/foundry/skills/deliver-engagement",
        "galaxies/foundry/skills/maintenance-inbox",
        "galaxies/foundry/skills/promote",
    }
    assert set(sources["galaxies/foundry/skills/deliver-engagement"]["files"]) == {
        "establish_scratch.py",
        "reach_gate.py",
        "stamp_gate.py",
        "lifecycle.json",
        "artifact-handlers.json",
    }
    # The sweep's fixtures are pinned WITH it, not separately: a corpus one commit ahead of
    # the derivation it pins is a corpus that reports a green it did not earn.
    promote = sources["galaxies/foundry/skills/promote"]["files"]
    # Fixtures ONLY - no code, and the absence is the contract. The console derives promotion
    # positions in Python and the desk derives them in TypeScript, so nothing implementation
    # -shaped is available to both; the corpus is what is shared instead, and a day someone
    # vendors a .py from this skill is a day one of those derivations quietly became the other
    # one's dependency.
    assert all(name.startswith("fixtures/") for name in promote), promote
    assert "fixtures/door-shut-outranks-every-other-rule.json" in promote

    inbox = sources["galaxies/foundry/skills/maintenance-inbox"]["files"]
    assert "sweep.py" in inbox
    # Every case upstream holds, by NAME. A count alone is what let a hand-typed refresh
    # list drop `urgency-order` while the suite still reported green over the eight that
    # remained - a corpus missing the case that pins the attention order is a corpus that
    # cannot catch a queue in the wrong order, which is most of what the queue IS.
    cases = {f[len("fixtures/"):-len(".json")] for f in inbox if f.startswith("fixtures/") and f.endswith(".json")}
    assert cases >= {
        "urgency-order",
        "fold-run-over-ticket",
        "fold-review-maps-to-ticket",
        "fold-pr-into-issue",
        "issue-stages",
        "hidden-and-archived",
        "unlinked-pr-keeps-its-row",
        "unchecked-is-not-healthy",
        "empty-queue",
    }, f"the vendored corpus is missing cases: {cases}"

    # The bytes on disk ARE the pin. A hand-edit of a vendored file is a re-implementation
    # wearing a pin's clothes (REF-Delivery anti-pattern 30); the README forbade it in
    # prose, which is what let it stay unenforced.
    for source in sources.values():
        for name, recorded in source["files"].items():
            actual = hashlib.sha256((ROOT / source["into"] / name).read_bytes()).hexdigest()
            assert actual == recorded, (
                f"{source['into']}/{name} does not match its recorded pin. Do not hand-edit "
                f"a vendored file - refresh it: devops/vendor/update-vendored-helpers.sh"
            )

    bundle = manifest["runtime_bundle"]
    archive_path = VENDOR / bundle["file"]
    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == bundle["sha256"]
    with tarfile.open(archive_path) as archive:
        assert archive.extractfile("REVISION").read().decode().strip() == manifest["ref"]
        assert len(archive.getmembers()) == bundle["files"]
        for path, source in sources.items():
            for name in source["files"]:
                assert archive.extractfile(f"{path}/{name}").read() == (ROOT / source["into"] / name).read_bytes()

    # A BAKED source's files are copied into the worker image, so a pin this test guards is
    # a pin the pod actually runs (issue #2 - the record helper was absent from every
    # delivery pod). A source that is not baked is imported in process instead, and must
    # NOT appear in a Dockerfile: a second copy at /opt/foundry is a second thing to bump.
    worker_df = (ROOT / "devops" / "worker.Dockerfile").read_text(encoding="utf-8")
    for source in sources.values():
        for name in source["files"]:
            copied = f"COPY {source['into']}/{name} /opt/foundry/{name}" in worker_df
            assert copied is bool(source["baked"]), (
                f"{source['into']}/{name} is {'baked' if source['baked'] else 'imported'} "
                f"but the worker Dockerfile says otherwise"
            )

    # The upstream question - has the playbook moved past the pin? - is asked by an
    # OPERATOR on their own credential, the read-only twin of update-vendored-helpers.sh
    # beside it, which already reaches the playbook the same way.
    drift = (VENDOR / "check_pin_drift.py").read_text(encoding="utf-8")
    assert "PINNED.json" in drift  # it reads the same single home
    assert "return 2" in drift     # a credential problem is its own outcome, not "in sync"
    assert "update-vendored-helpers.sh" in drift  # a drift report carries its own fix
    assert "urllib" in drift and "subprocess" not in drift  # stdlib, runs from any Python

    # And the refresh script is the only writer of the manifest, from the bytes it just
    # wrote - so the recorded hashes can never describe a different file than the one on
    # disk, which is the failure this whole test would otherwise only half-catch.
    refresh = (VENDOR / "update-vendored-helpers.sh").read_text(encoding="utf-8")
    assert "PINNED.json" in refresh
    assert "hashlib.sha256" in refresh

    for name, body in (("check_pin_drift.py", drift), ("update-vendored-helpers.sh", refresh)):
        assert manifest["repo"] not in body, f"{name} names the source repository; read it from PINNED.json"


def _check_against(monkeypatch, capsys, tree: dict[str, bytes]) -> tuple[int, str]:
    """Run check_pin_drift.py offline against a playbook holding exactly ``tree``
    (playbook path -> bytes): its one network call is replaced by a reader of the tree."""
    spec = importlib.util.spec_from_file_location("check_pin_drift", VENDOR / "check_pin_drift.py")
    drift = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drift)
    repo = json.loads((VENDOR / "PINNED.json").read_text(encoding="utf-8"))["repo"]

    def get(path: str, token: str):
        if path.startswith(f"/repos/{repo}/commits/"):
            return {"sha": "f" * 40}
        wanted = path.removeprefix(f"/repos/{repo}/contents/").split("?", 1)[0]
        if wanted in tree:
            return {"content": base64.b64encode(tree[wanted]).decode("ascii")}
        children: dict[str, str] = {}
        for held in tree:
            if held.startswith(f"{wanted}/"):
                name, _, rest = held[len(wanted) + 1:].partition("/")
                children[name] = "dir" if rest else "file"
        if not children:
            raise urllib.error.HTTPError(path, 404, "Not Found", None, io.BytesIO())
        return [{"name": name, "type": kind} for name, kind in children.items()]

    monkeypatch.setattr(drift, "_get", get)
    monkeypatch.setattr(sys, "argv", ["check_pin_drift.py"])
    monkeypatch.setenv("GH_TOKEN", "offline")
    code = drift.main()
    return code, capsys.readouterr().err


@intent("INT-FC-R112")
def test_the_drift_check_sees_a_fixture_the_playbook_adds_or_drops(monkeypatch, capsys):
    """A pinned ``fixtures/`` folder is pinned WHOLE: the refresh script vendors whatever the
    playbook holds there. So the read-only check must list it too - comparing only the files
    the pin names is how a case the playbook added stayed invisible, and the check printed
    "in sync" over an inbox corpus short of two cases."""
    manifest = json.loads((VENDOR / "PINNED.json").read_text(encoding="utf-8"))
    inbox, promote = (
        "galaxies/foundry/skills/maintenance-inbox",
        "galaxies/foundry/skills/promote",
    )
    tree = {
        f"{skill}/{name}": (ROOT / source["into"] / name).read_bytes()
        for skill, source in manifest["sources"].items()
        for name in source["files"]
    }
    code, err = _check_against(monkeypatch, capsys, tree)
    assert code == 0, err

    dropped = sorted(manifest["sources"][promote]["files"])[-1]
    moved = dict(tree)
    moved[f"{inbox}/fixtures/a-case-the-pin-lacks.json"] = b"{}\n"
    moved[f"{inbox}/fixtures/nested/case.json"] = b"{}\n"
    moved[f"{inbox}/fixtures/verdict/a-case-the-pin-lacks.json"] = b"{}\n"
    del moved[f"{promote}/{dropped}"]
    code, err = _check_against(monkeypatch, capsys, moved)

    assert code == 1
    assert "orchestrator/vendor/fixtures/a-case-the-pin-lacks.json" in err
    assert "orchestrator/vendor/fixtures/nested/" in err
    assert "orchestrator/vendor/fixtures/verdict/a-case-the-pin-lacks.json" in err
    assert f"orchestrator/vendor/promote/{dropped}" in err
    assert "update-vendored-helpers.sh" in err


@intent("INT-FC-R112")
def test_the_pinned_bytes_are_held_to_lf_on_every_platform():
    """A byte-exact pin needs the checkout to hand it the bytes the repo holds.

    Git stores these LF and, with core.autocrlf on (the Windows default), translates them
    to CRLF on checkout - so every recorded hash misses on a Windows clone and the guard
    above reports drift on a tree that has none. That false alarm is worse than a silent
    one, because its own advice is to re-pin: doing so records the TRANSLATED bytes, and
    the pin then fails for CI and every other platform instead. The attributes file is
    what keeps the hashes describing the same file everywhere, so it is asserted here
    beside the pin it protects rather than left as a setting someone might tidy away.
    """
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    rules = [ln.split("#", 1)[0].split() for ln in attributes.splitlines()]
    pinned = {parts[0] for parts in rules if len(parts) > 1 and "eol=lf" in parts}
    manifest = json.loads((VENDOR / "PINNED.json").read_text(encoding="utf-8"))
    # Every destination the manifest writes into, not one remembered by name: a source
    # added without its attributes rule is a pin that misses on Windows and nowhere else.
    for source in manifest["sources"].values():
        into = source["into"]
        assert {f"{into}/*", f"{into}/**"} & pinned, (
            f"{into} holds files pinned by SHA-256, so .gitattributes must hold them to "
            f"LF - a translated checkout makes every recorded hash miss"
        )
    # The shebang is bytes too: a CRLF line ending sends the kernel looking for `bash\r`.
    assert "*.sh" in pinned, ".gitattributes must hold shell scripts to LF (the shebang)"


@intent("INT-FC-R112")
def test_no_workflow_makes_this_repo_depend_on_the_playbook():
    """The pins exist so the build is HERMETIC.

    ``devops/vendor/`` holds byte-identical copies precisely because the playbook repo is
    private and this pipeline holds no cross-repo credential; that is the property, not a
    workaround for it. A scheduled workflow that fetched the playbook to compare pins was
    added and reverted (issue #34): it needed a new cross-repo secret and made this repo's
    CI depend on another repo, which is the exact coupling the vendoring removes. Asking
    whether the pin is stale is an operator's act on their own credential
    (``check_pin_drift.py``), never a pipeline's.

    So the ABSENCE of that dependency is the claim, asserted here - a machine gate on the
    architecture rather than a comment hoping someone remembers it.
    """
    repo = json.loads((VENDOR / "PINNED.json").read_text(encoding="utf-8"))["repo"]
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        body = workflow.read_text(encoding="utf-8")
        assert repo not in body, (
            f"{workflow.name} reaches the playbook repo. The vendored pins exist so this "
            f"build is hermetic; checking them against upstream is an operator act "
            f"(devops/vendor/check_pin_drift.py), not a pipeline's (issue #34)."
        )
        assert "PLAYBOOK_READ_TOKEN" not in body, (
            f"{workflow.name} wants a cross-repo playbook credential. This pipeline holds "
            f"none by design - that is why devops/vendor/ exists (issue #34)."
        )
