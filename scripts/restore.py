#!/usr/bin/env python3
"""
restore.py — the counterpart to bundle.py. A backup mechanism nobody has
tested restoring from is not actually a backup mechanism.

    python3 restore.py                          # auto-detect a source
    python3 restore.py --from path/to/backup.tar.gz
    python3 restore.py --from path/to/some/dir   # an already-extracted bundle
    python3 restore.py --force                   # overwrite an existing project-model/

Auto-detection order, when --from is not given: /mnt/user-data/outputs/
project-model-backup.tar.gz (the copy that actually survives a sandbox
reset), then the sibling project-model-backup.tar.gz next to --root.

Never writes into --root directly. Extracts to a temp directory first, shows
what's about to be restored (object/edge counts, when it was bundled) before
touching anything, and refuses to overwrite an existing non-empty --root
unless --force is given -- and even then, the existing directory is moved
aside (project-model.pre-restore-<timestamp>/, never deleted) rather than
overwritten in place, the same additive-only discipline migrate.py already
uses for its own backups.

After restoring, runs the same checks model.py check --strict runs, and
reports the result plainly. A restore that leaves the model incoherent is
not a successful restore.
"""
import argparse
import datetime
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import model as model_mod

OUTPUTS_DIR = Path("/mnt/user-data/outputs")
BACKUP_NAME = "project-model-backup.tar.gz"


def find_source(root):
    candidates = [OUTPUTS_DIR / BACKUP_NAME, root.parent / BACKUP_NAME]
    for c in candidates:
        if c.is_file():
            return c
    return None


def extract_to_temp(source):
    tmp = Path(tempfile.mkdtemp(prefix="restore-"))
    if source.is_dir():
        # already-extracted bundle, or a bare copy of project-model/ itself
        inner = source if (source / "index.md").exists() else next(
            (p for p in source.iterdir() if p.is_dir() and (p / "index.md").exists()), source)
        shutil.copytree(inner, tmp / "project-model")
    else:
        with tarfile.open(source) as tf:
            tf.extractall(tmp)
        # bundle.py's tar has one top-level dir named after --root (usually
        # "project-model"); find it rather than assuming the exact name.
        members = [p for p in tmp.iterdir() if p.is_dir()]
        if len(members) == 1:
            members[0].rename(tmp / "project-model")
        elif not (tmp / "project-model").exists():
            raise SystemExit(f"Could not find an extracted model directory in {source}")
    return tmp / "project-model"


def read_manifest(extracted):
    mf = extracted / "MANIFEST.json"
    if mf.exists():
        return json.loads(mf.read_text())
    return None


def restore(root, source=None, force=False):
    root = Path(root)
    if source is None:
        source = find_source(root)
        if source is None:
            raise SystemExit(
                "No backup found. Looked in "
                f"{OUTPUTS_DIR / BACKUP_NAME} and {root.parent / BACKUP_NAME}. "
                "Pass --from explicitly if the backup is somewhere else "
                "(e.g. a file you re-uploaded after a reset).")
    else:
        source = Path(source)
        if not source.exists():
            raise SystemExit(f"{source} does not exist.")

    extracted = extract_to_temp(source)
    manifest = read_manifest(extracted)

    print(f"Source: {source}")
    if manifest:
        print(f"  bundled_at: {manifest.get('bundled_at', '?')}")
        print(f"  objects: {manifest.get('objects', '?')}  edges: {manifest.get('edges', '?')}")
        print(f"  schema_version: {manifest.get('schema_version', '?')}  "
              f"skill_version: {manifest.get('skill_version', '?')}")
    else:
        print("  (no MANIFEST.json in this bundle -- older or hand-made archive)")

    if root.exists() and any(root.iterdir()):
        existing_count = len(list(root.glob("*/*.md")))
        if not force:
            raise SystemExit(
                f"\n{root} already exists and is not empty ({existing_count} object "
                f"files). Refusing to overwrite -- the local copy may be newer than "
                f"this backup. Compare the counts above against what's already there, "
                f"then re-run with --force if you're sure. --force moves the existing "
                f"directory aside (project-model.pre-restore-<timestamp>/), it never "
                f"deletes it.")
        aside = root.parent / f"project-model.pre-restore-{datetime.date.today().isoformat()}"
        n = 1
        while aside.exists():
            n += 1
            aside = root.parent / f"project-model.pre-restore-{datetime.date.today().isoformat()}-{n}"
        root.rename(aside)
        print(f"\nMoved existing {root} aside to {aside} (not deleted).")

    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(extracted), str(root))
    shutil.rmtree(extracted.parent, ignore_errors=True)
    print(f"Restored to {root}.")

    print("\nRunning check --strict on the restored model...")
    a = argparse.Namespace(strict=True, limit=10)
    rc = model_mod.cmd_check(root, a)
    if rc != 0:
        print("\nRestore completed, but the restored model is NOT clean. "
              "See the problems above before trusting it.")
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("project-model"))
    ap.add_argument("--from", dest="source", default=None,
                    help="a .tar.gz bundle, or an already-extracted directory")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing --root (moved aside, not deleted)")
    a = ap.parse_args()
    sys.exit(restore(a.root, a.source, a.force))


if __name__ == "__main__":
    main()
