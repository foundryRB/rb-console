#!/usr/bin/env bash
# Refresh the vendored playbook pins (the playbook repo is private, so this uses the
# caller's authenticated gh). Byte-identical imports of the true files, never a hand-port
# (REF-Delivery anti-pattern 30); PINNED.json records the pinned commit.
#
# Every source is read at one immutable ref. Delivery helpers, the effective definition
# and its artifact catalog share that pin, together with the inbox sweep and its fixtures.
#
# Fixture folders are discovered at that ref. Each destination holds exactly the files
# present in its source folder.
#
# This is the ONLY writer of PINNED.json. The manifest it emits is what makes the pin
# checkable: tests/test_vendor_pin.py re-hashes the files against it offline on every
# push, and check_pin_drift.py re-fetches upstream against it (issue #33).
#
# PLAYBOOK_CLONE bootstraps a pin whose commit is not yet on the remote: it reads the bytes
# from a local playbook checkout and takes the ref from its git. The recorded SHA is the
# commit's real one either way, so such a pin becomes checkable the moment that commit is
# pushed - and check_pin_drift.py is what says whether it has been.
#
#   devops/vendor/update-vendored-helpers.sh [ref]
#   PLAYBOOK_CLONE=../playbook devops/vendor/update-vendored-helpers.sh
#   PLAYBOOK_REPO=<owner/name> devops/vendor/update-vendored-helpers.sh [ref]
set -euo pipefail

ref="${1:-main}"
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "${here}/../.." && pwd)"
clone="${PLAYBOOK_CLONE:-}"

# The sources, one line each: <skill path>|<destination, repo-relative>|<entry>,<entry>,...
# An entry is a file, or a folder written with its trailing slash, which stands for every
# file that folder holds at the ref.
#
# The delivery helpers are RUN as scripts, baked into the images at /opt/foundry, so they
# sit here beside the Dockerfiles that copy them. The inbox sweep is IMPORTED in process by
# the orchestrator, so it ships as part of that package instead - a library, not a helper
# the entrypoint shells.
sources=(
  "galaxies/foundry/skills/deliver-engagement|devops/vendor|establish_scratch.py,reach_gate.py,stamp_gate.py,lifecycle.json,artifact-handlers.json"
  "galaxies/foundry/skills/maintenance-inbox|orchestrator/vendor|sweep.py,fixtures/,fixtures/verdict/"
  # The promotion corpus verifies each consumer's own promotion derivation.
  "galaxies/foundry/skills/promote|orchestrator/vendor/promote|fixtures/"
)

# Execute each interpreter candidate before writing files. A PATH entry can be an alias
# that resolves without providing a working interpreter.
py=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "no working python on PATH (tried python3, python, py); PINNED.json cannot be written" >&2
  exit 1
fi

# sys.stdout.write, not print: a Windows Python ends lines in CRLF and $(...) keeps the CR.
repo="${PLAYBOOK_REPO:-}"
if [ -z "$repo" ] && [ -f "${here}/PINNED.json" ]; then
  repo=$("$py" -c 'import json, sys; sys.stdout.write(json.load(open(sys.argv[1], encoding="utf-8")).get("repo", ""))' "${here}/PINNED.json")
fi
if [ -z "$repo" ]; then
  echo "PINNED.json names no source repository; set PLAYBOOK_REPO=<owner/name> for a first pin" >&2
  exit 1
fi

# Resolve the ONE commit every read below is made at, before any read is made. A branch can
# move between two reads, and a listing taken at one commit with its files fetched at the
# next pins a tree the playbook never held.
if [ -n "$clone" ]; then
  sha=$(git -C "$clone" rev-parse HEAD)
else
  sha=$(gh api "repos/${repo}/commits/${ref}" --jq '.sha')
fi
today=$(date +%F)

# What a playbook folder holds at that commit, one `<kind><TAB><name>` line per entry.
listing() {
  if [ -n "$clone" ]; then
    git -C "$clone" ls-tree --format='%(objecttype)%x09%(path)' "${sha}:$1"
  else
    gh api "repos/${repo}/contents/$1?ref=${sha}" --jq '.[] | "\(.type)\t\(.name)"'
  fi
}

# Expand every folder entry into the files it holds, before a single byte is written. A
# folder holding a folder, or holding nothing, stops the run here: skipping the one drops a
# nested corpus in silence, and pinning the other is a corpus of no cases, which every suite
# that globs it reports as green.
pinned=()
mirrors=()
for source in "${sources[@]}"; do
  IFS='|' read -r skill into list <<<"$source"
  IFS=',' read -ra entries <<<"$list"
  names=()
  for entry in "${entries[@]}"; do
    if [[ "$entry" != */ ]]; then
      names+=("$entry")
      continue
    fi
    held=$(listing "${skill}/${entry%/}")
    found=()
    while IFS=$'\t' read -r kind name; do
      [ -n "$name" ] || continue
      if [ "$kind" != "blob" ] && [ "$kind" != "file" ]; then
        # A nested folder named as its own entry is vendored by that entry.
        case ",${list}," in *",${entry}${name}/,"*) continue ;; esac
        echo "${skill}/${entry}${name} is a ${kind}, not a file; name it as its own entry" >&2
        exit 1
      fi
      found+=("$name")
    done <<<"$held"
    if [ "${#found[@]}" -eq 0 ]; then
      echo "${skill}/${entry} holds no files at ${sha}; an empty corpus is not a pin" >&2
      exit 1
    fi
    for name in "${found[@]}"; do
      names+=("${entry}${name}")
    done
    mirrors+=("${into}/${entry}|$(IFS=','; echo "${found[*]}")")
  done
  pinned+=("${skill}|${into}|$(IFS=','; echo "${names[*]}")")
done

count=0
for source in "${pinned[@]}"; do
  IFS='|' read -r skill into files <<<"$source"
  IFS=',' read -ra names <<<"$files"
  for name in "${names[@]}"; do
    mkdir -p "$(dirname "${root}/${into}/${name}")"
    if [ -n "$clone" ]; then
      # Read committed bytes directly; checkout newline translation must not affect pins.
      git -C "$clone" show "${sha}:${skill}/${name}" > "${root}/${into}/${name}"
    else
      gh api "repos/${repo}/contents/${skill}/${name}?ref=${sha}" --jq '.content' | base64 -d > "${root}/${into}/${name}"
    fi
    echo "vendored ${skill}/${name} -> ${into}/${name}"
    count=$((count + 1))
  done
done

# Remove destination files absent from the pinned source folder.
for mirror in "${mirrors[@]}"; do
  IFS='|' read -r folder held <<<"$mirror"
  for path in "${root}/${folder}"*; do
    [ -f "$path" ] || continue
    case ",${held}," in
      *",${path##*/},"*) ;;
      *)
        rm -- "$path"
        echo "removed ${folder}${path##*/} (the playbook holds no such file at ${sha})"
        ;;
    esac
  done
done

# Rewrite the manifest from the bytes just written, so the recorded hashes can never
# describe a different file than the one on disk.
REPO="$repo" SHA="$sha" TODAY="$today" ROOT="$root" "$py" - "${pinned[@]}" <<'PY'
import hashlib, json, os, sys

root = os.environ["ROOT"]
#: A source is BAKED when its files are copied into an image and run there as scripts; the
#: pin test asserts exactly those appear in the Dockerfiles, and exactly the others do not.
baked = {"devops/vendor"}
sources = {}
for spec in sys.argv[1:]:
    skill, into, files = spec.split("|")
    sources[skill] = {
        "into": into,
        "baked": into in baked,
        "files": {
            name: hashlib.sha256(open(os.path.join(root, into, name), "rb").read()).hexdigest()
            for name in files.split(",")
        },
    }

manifest = {
    "_comment": (
        "The single home for the vendored playbook pin. update-vendored-helpers.sh writes "
        "this file; check_pin_drift.py and tests/test_vendor_pin.py read it. Never "
        "hand-edit either this or the vendored files - a hand-edit is a re-implementation "
        "wearing a pin's clothes (REF-Delivery anti-pattern 30)."
    ),
    "repo": os.environ["REPO"],
    "ref": os.environ["SHA"],
    "pinned_on": os.environ["TODAY"],
    "sources": sources,
}
with open(os.path.join(root, "devops", "vendor", "PINNED.json"), "w", encoding="utf-8", newline="\n") as fh:
    json.dump(manifest, fh, indent=2)
    fh.write("\n")
PY
"$py" "${here}/bundle_playbook.py" "${here}/PINNED.json" --clone "$clone"
"$py" "${root}/scripts/generate_lifecycle.py"
echo "${count} files pinned at ${sha} (PINNED.json rewritten)"
