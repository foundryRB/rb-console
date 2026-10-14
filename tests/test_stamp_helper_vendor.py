"""The vendored gate stamper (devops/vendor/stamp_gate.py) behaves as the contract says.

The vendor is a byte-identical pin of the playbook's stamp_gate.py, the single writer
of a gate's `signed:` field (REF-Delivery section 1). These tests exercise the pin
itself, so a corrupted or accidentally-edited vendor fails CI here rather than inside
an image at a live gate.
"""
import subprocess
import sys
from pathlib import Path

from pytest_intent import intent

_HELPER = Path(__file__).resolve().parents[1] / "devops" / "vendor" / "stamp_gate.py"

_RECORD = """---
phase: design
skill: design-session
status: gate
gate: design
signed: pending
reviewed:{reviewed}
run: r1
attempt: 1
mode: interactive
started: 2026-07-16T00:00:00Z
finished:
credential_ref: x
---

Prototype: none - the tool-less design path; nothing external for the gate to freeze.

# Design record with the word pending in prose.
"""


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HELPER), "--repo", str(repo), "--record", "design.md", *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def _write(tmp_path: Path, reviewed: str) -> Path:
    scratch = tmp_path / ".delivery"
    scratch.mkdir()
    # The stamper refuses to close a gate while the journal is absent (REF-Delivery
    # section 1, anti-pattern 38); a real scratch always carries one by the time a gate
    # closes, and GithubStore.write_gate seeds it into the scratch it synthesizes.
    (scratch / "journal.md").write_text("# Journal\n\nno lessons this phase\n", encoding="utf-8")
    record = scratch / "design.md"
    record.write_text(_RECORD.format(reviewed=reviewed), encoding="utf-8")
    return record


@intent("INT-FC-R52")
def test_vendored_stamper_refuses_without_review_evidence(tmp_path):
    record = _write(tmp_path, "")
    result = _run(tmp_path, "--date", "2026-07-16", "--by", "the operator (console Sign)")
    assert result.returncode == 1
    assert "no review evidence" in result.stdout
    assert "signed: pending" in record.read_text(encoding="utf-8")  # untouched


@intent("INT-FC-R52")
def test_vendored_stamper_stamps_over_recorded_review_and_promotes(tmp_path):
    record = _write(tmp_path, " 2026-07-16")
    result = _run(tmp_path, "--date", "2026-07-16", "--by", "the operator (console Sign)")
    assert result.returncode == 0, result.stdout
    text = record.read_text(encoding="utf-8")
    assert "signed: 2026-07-16" in text
    assert "status: complete" in text  # gate -> complete promotion
    assert "the word pending in prose" in text  # loose 'pending' in the body untouched
    # a closed gate is never re-stamped, even when the caller brings fresh evidence
    again = _run(
        tmp_path, "--date", "2026-07-17", "--review-verdict", "pass",
        "--review-log", _review_log(tmp_path, "VERDICT: PASS\n", "design-2026-07-17.md"),
    )
    assert again.returncode == 1 and "already signed" in again.stdout


def _review_log(tmp_path: Path, text: str, name: str = "design-2026-07-16.md") -> str:
    """Write a review artifact at the conventional path; return it repo-relative."""
    reviews = tmp_path / ".delivery" / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / name).write_text(text, encoding="utf-8")
    return f".delivery/reviews/{name}"


@intent("INT-FC-R104")
def test_vendored_stamper_refuses_a_claimed_verdict_without_its_artifact(tmp_path):
    # --review-verdict is a claim; --review-log is its committed evidence. A claim
    # without the artifact (or with a path that does not exist) refuses and writes nothing.
    record = _write(tmp_path, "")
    result = _run(tmp_path, "--date", "2026-07-16", "--review-verdict", "pass")
    assert result.returncode == 1 and "--review-log" in result.stdout
    assert "signed: pending" in record.read_text(encoding="utf-8")  # untouched
    missing = _run(
        tmp_path, "--date", "2026-07-16", "--review-verdict", "pass",
        "--review-log", ".delivery/reviews/design-2026-07-16.md",
    )
    assert missing.returncode == 1 and "not found" in missing.stdout
    assert "signed: pending" in record.read_text(encoding="utf-8")


@intent("INT-FC-R104")
def test_vendored_stamper_reads_the_artifacts_last_verdict_token(tmp_path):
    # The helper re-verifies the artifact itself: its LAST VERDICT token decides,
    # case-insensitively and through markdown wrapping (the INT-FC-R102 parse rule) -
    # so a log that ends FAIL refuses even under a claimed pass, and a passing log
    # stamps with the artifact named in the record's provenance line.
    record = _write(tmp_path, "")
    failing = _review_log(tmp_path, "**VERDICT: PASS** was premature; on re-read:\n\nVERDICT: FAIL\n")
    result = _run(tmp_path, "--date", "2026-07-16", "--review-verdict", "pass", "--review-log", failing)
    assert result.returncode == 1 and "VERDICT: FAIL" in result.stdout
    assert "signed: pending" in record.read_text(encoding="utf-8")  # a FAIL never signs
    passing = _review_log(tmp_path, "Findings: none of substance.\n\n**verdict: pass**\n")
    result = _run(tmp_path, "--date", "2026-07-16", "--review-verdict", "pass", "--review-log", passing)
    assert result.returncode == 0, result.stdout
    text = record.read_text(encoding="utf-8")
    assert "signed: 2026-07-16" in text and "status: complete" in text
    assert ".delivery/reviews/design-2026-07-16.md" in text  # provenance names the evidence
