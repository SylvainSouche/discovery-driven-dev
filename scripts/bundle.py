#!/usr/bin/env python3
"""
bundle.py — export project-model/ to somewhere a sandbox reset can't reach.

Called automatically by model.py after every mutating command (new, link,
status, amend, supersede) — regenerate() calls bundle() unconditionally, so
this runs on every single write with no agent judgment involved. It can also
be run standalone.

Two copies are written, and they are NOT equivalent:

  - <root's parent>/project-model-backup.tar.gz — convenient, but lives
    inside the same sandbox as project-model/ itself. A full sandbox reset
    (the exact failure this exists to catch) destroys this copy too. Its
    value is for ordinary re-upload/handoff, not reset protection.

  - /mnt/user-data/outputs/project-model-backup.tar.gz — written only if
    that directory exists. This is the copy that actually matters: on
    Claude's code-execution environment, outputs/ is conventionally backed
    by storage outside the ephemeral compute sandbox, so it can survive a
    reset that wipes everything else. On any other environment (a real
    filesystem, Claude Code, Cowork) the directory simply won't exist and
    this half is a silent no-op — project-model/ already lives outside the
    sandbox there, via the connected folder, and needs no rescuing.

The archive contains project-model/ as-is, plus MANIFEST.json: schema
version, skill version, object/edge counts, and a checksum-of-checksums
(sha256 over every object's own stamped checksum, sorted) so a human can
tell at a glance, without re-verifying every file, whether two bundles
represent the same state.
"""
import datetime
import hashlib
import json
import re
import shutil
import sys
import tarfile
from pathlib import Path

SCHEMA_VERSION = 2
BACKUP_NAME = "project-model-backup.tar.gz"
OUTPUTS_DIR = Path("/mnt/user-data/outputs")


def manifest_checksum(root):
    sums = []
    for p in sorted(root.glob("*/*.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^checksum:\s*(\S+)", text, re.M)
        if m:
            sums.append(m.group(1))
    return hashlib.sha256("|".join(sums).encode()).hexdigest()[:16]


def bundle(root, skill_version="?"):
    root = Path(root)
    objs = list(root.glob("*/*.md"))
    edges = 0
    for p in objs:
        text = p.read_text(encoding="utf-8", errors="ignore")
        edges += len(re.findall(r"^rel_[a-z_]+:", text, re.M))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "skill_version": skill_version,
        "objects": len(objs),
        "edges": edges,
        "manifest_checksum": manifest_checksum(root),
        "bundled_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    written = []
    targets = [root.parent / BACKUP_NAME]
    if OUTPUTS_DIR.is_dir():
        targets.append(OUTPUTS_DIR / BACKUP_NAME)

    for target in targets:
        try:
            with tarfile.open(target, "w:gz") as tf:
                tf.add(root, arcname=root.name)
                manifest_bytes = json.dumps(manifest, indent=2).encode()
                info = tarfile.TarInfo(name=f"{root.name}/MANIFEST.json")
                info.size = len(manifest_bytes)
                info.mtime = int(datetime.datetime.now().timestamp())
                import io
                tf.addfile(info, io.BytesIO(manifest_bytes))
            written.append(target)
        except OSError:
            # A best-effort export must never break the write path it rides
            # on. If a target isn't writable, skip it silently -- the write
            # to project-model/ itself already succeeded before bundle() was
            # ever called.
            continue

    return written, manifest


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("project-model")
    written, manifest = bundle(root)
    for w in written:
        print(f"wrote {w}")
    print(json.dumps(manifest, indent=2))
