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

A THIRD, optional export: if <root>/.backup-remote.json exists (created
once, deliberately, by the agent asking the user -- never assumed), every
call also pushes project-model/ to a dedicated branch on a real git remote.
This is the one export with actual version history, not just a
latest-state snapshot. It never touches the current branch or working
tree: a temporary git worktree checks out (or creates) the backup branch
in isolation, gets a fresh copy of project-model/, commits, and pushes --
so auto-backup noise never lands in the project's real history, and a
bundle failure here follows the same rule as the tar export: it must
never break the write it rides on.
"""
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SCHEMA_VERSION = 2
BACKUP_NAME = "project-model-backup.tar.gz"
BACKUP_CONFIG_NAME = ".backup-remote.json"
OUTPUTS_DIR = Path("/mnt/user-data/outputs")


def manifest_checksum(root):
    sums = []
    for p in sorted(root.glob("*/*.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^checksum:\s*(\S+)", text, re.M)
        if m:
            sums.append(m.group(1))
    return hashlib.sha256("|".join(sums).encode()).hexdigest()[:16]


def find_git_root(start):
    p = Path(start).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _run(args, cwd, timeout=30):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def git_backup(root, manifest):
    """Best-effort. Returns a short status string; never raises past this
    function, since a broken remote or a network hiccup must never turn a
    successful object write into a failed one."""
    config_path = root / BACKUP_CONFIG_NAME
    if not config_path.exists():
        return "not configured"

    try:
        config = json.loads(config_path.read_text())
        remote = config.get("remote", "origin")
        branch = config["branch"]
    except (json.JSONDecodeError, KeyError):
        return "invalid .backup-remote.json"

    repo_root = find_git_root(root)
    if repo_root is None:
        return "no git repository found"

    worktree = Path(tempfile.mkdtemp(prefix="bundle-backup-wt-"))
    try:
        worktree.rmdir()  # git worktree add requires the target not exist
        fetched = _run(["git", "fetch", "-q", remote, branch], cwd=repo_root).returncode == 0
        if fetched:
            r = _run(["git", "worktree", "add", "-q", "--detach", str(worktree),
                     f"{remote}/{branch}"], cwd=repo_root)
            if r.returncode != 0:
                return f"worktree add failed: {r.stderr.strip()[:200]}"
            r = _run(["git", "checkout", "-q", "-B", branch], cwd=worktree)
            if r.returncode != 0:
                return f"checkout failed: {r.stderr.strip()[:200]}"
        else:
            # No ref given: worktree add checks out HEAD, which brings in
            # whatever the caller's own current branch has (e.g. README.md)
            # -- --orphan then keeps those working-tree files staged as
            # "new", and git rm refuses to remove a staged-new file without
            # -f, treating it as "changes you'd lose". Force it: an orphan
            # backup branch is supposed to start from nothing.
            r = _run(["git", "worktree", "add", "-q", "--detach", str(worktree)], cwd=repo_root)
            if r.returncode != 0:
                return f"worktree add failed: {r.stderr.strip()[:200]}"
            r = _run(["git", "checkout", "-q", "--orphan", branch], cwd=worktree)
            if r.returncode != 0:
                return f"orphan checkout failed: {r.stderr.strip()[:200]}"
            r = _run(["git", "rm", "-rqf", "--ignore-unmatch", "."], cwd=worktree)
            if r.returncode != 0:
                return f"clearing orphan worktree failed: {r.stderr.strip()[:200]}"

        dest = worktree / root.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(root, dest, ignore=shutil.ignore_patterns("__pycache__"))

        _run(["git", "add", "-A"], cwd=worktree)
        status = _run(["git", "status", "--porcelain"], cwd=worktree)
        if not status.stdout.strip():
            return "no change since last backup"

        msg = f"auto-backup: {manifest['objects']} objects, {manifest['edges']} edges"
        commit = _run(["git", "commit", "-q", "-m", msg], cwd=worktree)
        if commit.returncode != 0:
            return f"commit failed: {commit.stderr.strip()[:200]}"

        push = _run(["git", "push", "-q", remote, f"HEAD:{branch}"], cwd=worktree, timeout=60)
        if push.returncode != 0:
            return f"push failed: {push.stderr.strip()[:200]}"
        return f"pushed to {remote}/{branch}"
    except Exception as e:
        return f"error: {e}"
    finally:
        _run(["git", "worktree", "remove", "--force", str(worktree)], cwd=repo_root)


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

    # Run the git backup first so its outcome can actually be embedded in
    # the manifest that goes into the tar below, rather than only living in
    # this function's return value.
    try:
        manifest["git_backup"] = git_backup(root, manifest)
    except Exception as e:
        manifest["git_backup"] = f"error: {e}"

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
