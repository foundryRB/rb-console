# Pinned playbook content

`PINNED.json` records the source repository, commit and file hashes. The refresh command imports every helper and fixture from that commit and packages its runtime policy into a deterministic archive:

```bash
devops/vendor/update-vendored-helpers.sh [ref]
```

`PLAYBOOK_REPO` selects the source repository. `PLAYBOOK_CLONE` reads committed bytes from an authenticated local checkout. The refresh requires a working Python interpreter and either the checkout or authenticated GitHub CLI access.

The delivery helpers and lifecycle definition live in `devops/vendor`. The maintenance sweep and shared fixture corpora live in `orchestrator/vendor`. `scripts/generate_lifecycle.py` derives the pure domain defaults from the pinned definition and archive; `--check` verifies the generated source.

The runtime archive contains the playbook entry point, galaxies, supporting scripts and a `REVISION` file. Workers read their skills from this immutable content and verify the run's expected revision before execution. The helper copies and archive are checked against the same source hashes. The backend, web client and worker images share one release version.

Run `python -m pytest tests/test_vendor_pin.py` for offline integrity checks. An authorized operator can run `python devops/vendor/check_pin_drift.py [ref]` with `GH_TOKEN` configured to compare the individually pinned source files with the upstream commit. Builds use committed content and require no playbook credential.

Do not edit imported files. Refresh the complete pin through the command above.
