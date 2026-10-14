"""The console reads the contract the platform scaffolds.

Two repositories parse `devops/promotion.yaml`: platform-studio writes and
validates it, the console reads it to render the promotion mode. They are
separate parsers by design (the console keeps no yaml dependency for one small
document), which makes their agreement the thing worth pinning. These fixtures
are the shapes platform-studio ships and documents; a change on that side that
this suite cannot read is a cross-repo drift, and this is where it surfaces.
"""
from orchestrator.application.promotion import parse_contract

# Byte-for-byte the file platform-studio's scaffold writes into every new app
# repo (studio.domain.services.promotion_contract.render_promotion_contract).
SCAFFOLDED = """\
# The app's promotion contract: where proven releases move beyond the entry
# environment. Each target carries its door (how the write is submitted),
# terms (what is written, and what deployed means) and acceptance (what
# proven-there means), written out in full; nothing is resolved by an engine
# at run time. Credentials are named here and held by the platform, never
# stored in any repository.
#
# targets:
#   - name: example-prod          # an environment of an install we run
#     kind: environment
#     install: example
#     environment: prod           # in that install's declared list; never its entry
#     door: commit                # to this repo's deploy-example branch
#     terms: version              # image tags + chart pin; deployed when it serves them
#     acceptance: probe           # or: none (closes at deployed), or suite
#   - name: example-qa            # a suite verdict is READ where it is published
#     kind: environment
#     install: example
#     environment: qa
#     door: commit
#     terms: version
#     acceptance: suite           # the app's own integrated suite
#     suite: https://ci.example/api/sit/latest
#     suite_pass: '"result":"passed"'   # a 200 is transport, not a pass
#   - name: partner               # another organization's repository
#     kind: repository
#     repo: their-org/their-repo
#     branch: main
#     credential: partner-pair    # a named secret the platform holds
#     door: pull-request          # theirs to review; the merge lands it
#     terms: source
#     acceptance: none            # or: probe: https://their-hostname.example
targets: []
"""


def test_the_scaffolded_contract_declares_nothing_and_is_not_malformed() -> None:
    # Every new app repo ships this file. The pane must read it as "declares no
    # targets", never as a malformed contract, or every fresh app shows an error.
    targets, problem = parse_contract(SCAFFOLDED)
    assert targets == []
    assert problem == ""


def test_the_commented_example_shape_parses_once_uncommented() -> None:
    # The scaffold teaches the shape in its comments; a hand that uncomments it
    # must get exactly what the comments promised.
    uncommented = "\n".join(
        [
            "targets:",
            "  - name: example-prod",
            "    kind: environment",
            "    install: example",
            "    environment: prod",
            "    door: commit",
            "    terms: version",
            "    acceptance: probe",
            "  - name: partner",
            "    kind: repository",
            "    repo: their-org/their-repo",
            "    branch: main",
            "    credential: partner-pair",
            "    door: pull-request",
            "    terms: source",
            "    acceptance: none",
        ]
    )
    targets, problem = parse_contract(uncommented)
    assert problem == ""
    assert [t.name for t in targets] == ["example-prod", "partner"]
    first, second = targets
    assert (first.door, first.terms, first.acceptance) == ("commit", "version", "probe")
    assert (first.install, first.environment) == ("example", "prod")
    assert (second.door, second.terms, second.acceptance) == (
        "pull-request",
        "source",
        "none",
    )
    assert (second.repo, second.branch) == ("their-org/their-repo", "main")


def test_the_mapping_form_of_acceptance_carries_its_url() -> None:
    # platform-studio validates `acceptance: {probe: <url>}`; the console must
    # read the same file and come out with the probe and its URL.
    targets, problem = parse_contract(
        "\n".join(
            [
                "targets:",
                "  - name: partner",
                "    kind: repository",
                "    repo: their-org/their-repo",
                "    branch: main",
                "    credential: partner-pair",
                "    acceptance:",
                "      probe: https://their-hostname.example",
            ]
        )
    )
    assert problem == ""
    (target,) = targets
    assert target.acceptance == "probe"
    assert target.probe_url == "https://their-hostname.example"


def test_a_target_missing_its_kind_is_reported_not_skipped() -> None:
    targets, problem = parse_contract("targets:\n  - name: half-written\n")
    assert targets == []
    assert "missing name or kind" in problem


def test_a_suite_acceptance_carries_its_coordinate_and_its_pass_rule() -> None:
    # A suite is declared as WHERE ITS VERDICT IS PUBLISHED and what passing
    # looks like in that answer, never as how to run one: who executes a suite
    # is outside the contract, because a destination we can write to may be on
    # a network we have no path into (REF-Promotion section 3).
    targets, problem = parse_contract(
        "\n".join(
            [
                "targets:",
                "  - name: example-qa",
                "    kind: environment",
                "    install: example",
                "    environment: qa",
                "    door: commit",
                "    terms: version",
                "    acceptance: suite",
                "    suite: https://ci.example/api/sit/latest",
                "    suite_pass: '\"result\":\"passed\"'",
            ]
        )
    )
    assert problem == ""
    (target,) = targets
    assert target.acceptance == "suite"
    assert target.suite_url == "https://ci.example/api/sit/latest"
    assert target.suite_pass == '"result":"passed"'
    # A suite target is a target like any other; nothing about the contract's
    # shape changes because the declared signal happens to be a suite.
    assert (target.door, target.terms) == ("commit", "version")
