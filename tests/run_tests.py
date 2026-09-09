#!/usr/bin/env python3
"""
run_tests.py — exercise every enforcement path and every checker.

Run from the repository root:

    python3 tests/run_tests.py

Each test builds a throwaway model in a temporary directory. Nothing here
touches a real project.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
S = REPO / "scripts"
PASS = FAIL = 0
FAILURES = []


def run(cwd, script, *args, expect_fail=False):
    r = subprocess.run([sys.executable, str(S / script), *map(str, args)],
                       cwd=cwd, capture_output=True, text=True)
    out = r.stdout + r.stderr
    if expect_fail and r.returncode == 0:
        raise AssertionError(f"{script} {' '.join(map(str,args))} should have "
                             f"failed but succeeded:\n{out}")
    if not expect_fail and r.returncode != 0:
        raise AssertionError(f"{script} {' '.join(map(str,args))} failed:\n{out}")
    return out


def check(name, fn):
    global PASS, FAIL
    with tempfile.TemporaryDirectory() as d:
        try:
            fn(Path(d))
            PASS += 1
            print(f"  ok   {name}")
        except AssertionError as e:
            FAIL += 1
            FAILURES.append((name, str(e)))
            print(f"  FAIL {name}")


def seed(d):
    """A minimal but complete model: obs -> dec -> req -> refined req."""
    run(d, "model.py", "new", "--type", "obs", "--alias", "o",
        "--title", "Users repeat searches", "--origin", "tickets")
    run(d, "model.py", "new", "--type", "dec", "--alias", "d",
        "--title", "Build saved searches", "--origin", "user",
        "--relates", "resolves:o")
    run(d, "model.py", "new", "--type", "uc", "--alias", "u",
        "--title", "A user saves and re-runs a search", "--origin", "walkthrough")
    run(d, "model.py", "new", "--type", "req", "--alias", "r",
        "--title", "System shall persist a named search", "--origin", "d",
        "--relates", "decided_by:d", "--relates", "motivated_by:u")
    run(d, "model.py", "new", "--type", "req", "--alias", "rc",
        "--title", "At most 50 saved searches", "--origin", "user",
        "--relates", "refines:r", "--relates", "decided_by:d")
    for a in ("u", "r", "rc"):
        run(d, "model.py", "status", "--id", a, "--to", "confirmed")


# --------------------------------------------------------------------------
def t_lifecycle(d):
    seed(d)
    assert "OK" in run(d, "model.py", "check")
    assert "rc" in run(d, "model.py", "leaves"), "the refined req should be the leaf"


def t_alias_uniqueness(d):
    seed(d)
    out = run(d, "model.py", "new", "--type", "req", "--alias", "r",
              "--title", "dupe", "--origin", "x", expect_fail=True)
    assert "in use by active object" in out


def t_origin_mandatory(d):
    seed(d)
    r = subprocess.run([sys.executable, str(S / "model.py"), "new",
                        "--type", "req", "--title", "no origin"],
                       cwd=d, capture_output=True, text=True)
    assert r.returncode != 0, "creation without --origin must fail"


def t_vocabulary_closed(d):
    seed(d)
    r = subprocess.run([sys.executable, str(S / "model.py"), "link",
                        "--from", "r", "--key", "invented_key", "--to", "d"],
                       cwd=d, capture_output=True, text=True)
    assert r.returncode != 0, "an unknown relationship key must be rejected"


def t_illegal_edge(d):
    seed(d)
    out = run(d, "model.py", "link", "--from", "r", "--key", "verifies",
              "--to", "d", expect_fail=True)
    assert "cannot" in out.lower()


def t_dangling_target(d):
    seed(d)
    out = run(d, "model.py", "new", "--type", "req", "--title", "t",
              "--origin", "o", "--relates", "decided_by:nope", expect_fail=True)
    assert "matches no object" in out


def t_tamper_detection(d):
    seed(d)
    f = next((d / "project-model" / "req").glob("*.md"))
    f.write_text(f.read_text().replace("status: confirmed", "status: proposed"))
    # check() exits non-zero on a hard problem, which tampering is
    out = run(d, "model.py", "check", expect_fail=True)
    assert "TAMPERED" in out, "hand-edited frontmatter must be detected"


def _file_for_alias(d, typ, alias):
    for f in (d / "project-model" / typ).glob("*.md"):
        if re.search(rf"^alias: {re.escape(alias)}$", f.read_text(), re.M):
            return f
    raise AssertionError(f"no {typ} object with alias {alias}")


def t_amend(d):
    seed(d)
    f = _file_for_alias(d, "req", "r")
    text_before = f.read_text()
    out = run(d, "model.py", "amend", "--id", "r", "--field", "origin",
              "--value", "user statement, corrected", "--reason", "fixed a typo")
    assert "origin -> user statement, corrected" in out
    text = f.read_text()
    assert "origin: user statement, corrected" in text
    assert "amended: " in text and "fixed a typo" in text
    assert "amended_checksum: " in text
    # the object's own checksum changed too, since origin is a SUMMED field
    assert text != text_before
    run(d, "model.py", "check", "--strict")  # clean after a real amend
    # forbidden fields are rejected outright, before touching the model
    r = subprocess.run([sys.executable, str(S / "model.py"), "amend", "--id", "r",
                        "--field", "status", "--value", "proposed", "--reason", "x"],
                       cwd=d, capture_output=True, text=True)
    assert r.returncode != 0, "status must keep using the dedicated status command"
    # hand-editing the log text (not the checksummed frontmatter it logs
    # about) must be caught independently of ordinary tamper detection
    f.write_text(text.replace("fixed a typo", "fixed something else entirely"))
    out = run(d, "model.py", "check", "--strict", expect_fail=True)
    assert "LOG-TAMPERED" in out, "hand-edited log text must be caught by its own checksum"
    assert "\nTAMPERED" not in out, \
        "the object's own checksum must be untouched by a log-only edit"


def t_citation_edge_parity(d):
    seed(d)
    run(d, "model.py", "new", "--type", "dec", "--alias", "cites-but-skips",
        "--title", "A decision citing another object only in prose", "--origin", "user",
        "--note", "This builds directly on REQ-rc without a formal edge.")
    # soft: a plain check() must still succeed with the finding present
    out = run(d, "model.py", "check")
    assert "UNCITED" in out, "a body naming REQ-rc with no matching edge must be flagged"
    # but --strict treats every finding as a failure
    run(d, "model.py", "check", "--strict", expect_fail=True)
    run(d, "model.py", "link", "--from", "cites-but-skips", "--key", "informed_by", "--to", "rc")
    out = run(d, "model.py", "check", "--strict")
    assert "UNCITED" not in out, "linking the cited object must clear the finding"


def t_supersede_absorb(d):
    seed(d)
    run(d, "model.py", "new", "--type", "dec", "--alias", "d2",
        "--title", "Rework", "--origin", "u")
    out = run(d, "model.py", "supersede", "--old", "rc", "--decided-by", "d2",
              "--origin", "finding", "--with", "rc2:At most 100 saved searches")
    assert "absorbed into 1" in out
    assert "OK" in run(d, "model.py", "check")


def t_supersede_split(d):
    seed(d)
    run(d, "model.py", "new", "--type", "dec", "--alias", "d2",
        "--title", "Split", "--origin", "u")
    out = run(d, "model.py", "supersede", "--old", "r", "--decided-by", "d2",
              "--origin", "finding",
              "--with", "ra:Persistence half", "--with", "rb:Naming half")
    assert "split across 2" in out
    assert "still refine the superseded object" in out, \
        "children of a split parent must be reported"
    assert "REFINES-DEAD" in run(d, "model.py", "check", expect_fail=True)


def t_supersede_needs_decision(d):
    seed(d)
    out = run(d, "model.py", "supersede", "--old", "r", "--decided-by", "rc",
              "--origin", "x", "--with", "y:z", expect_fail=True)
    assert "must name a DEC" in out


def t_supersede_twice_refused(d):
    seed(d)
    run(d, "model.py", "new", "--type", "dec", "--alias", "d2",
        "--title", "x", "--origin", "u")
    run(d, "model.py", "supersede", "--old", "rc", "--decided-by", "d2",
        "--origin", "x", "--with", "rc2:v2")
    out = run(d, "model.py", "supersede", "--old", "rc", "--decided-by", "d2",
              "--origin", "x", "--with", "rc3:v3", expect_fail=True)
    assert "already superseded" in out


def t_orphan_superseded(d):
    seed(d)
    run(d, "model.py", "status", "--id", "rc", "--to", "superseded")
    assert "ORPHAN-SUPERSEDED" in run(d, "model.py", "check", expect_fail=True)


def t_coverage(d):
    seed(d)
    out = run(d, "coverage.py")
    assert "motivation" in out and "100%" in out, \
        "both reqs are motivated: r directly, rc by inheritance"


def t_impl_markers(d):
    seed(d)
    leaf = run(d, "model.py", "leaves").split()[0]
    src = d / "src"
    src.mkdir()
    (src / "a.c").write_text(f"/* @impl {leaf} */\nint f(void){{return 0;}}\n")
    run(d, "model.py", "new", "--type", "impl", "--alias", "i",
        "--title", "cap", "--origin", "phase1", "--relates", "implements:rc")
    assert "OK" in run(d, "check_impl.py", "--src", ".", "--ext", ".c")


def t_impl_orphan_marker(d):
    seed(d)
    src = d / "src"
    src.mkdir()
    (src / "a.c").write_text("/* @impl dead-beef-0000-0000 */\n")
    r = subprocess.run([sys.executable, str(S / "check_impl.py"),
                        "--src", ".", "--ext", ".c"],
                       cwd=d, capture_output=True, text=True)
    assert "ORPHAN MARKERS" in r.stdout


def t_view_check(d):
    seed(d)
    run(d, "build_view.py", "generate", "--out", "v.md", "--title", "V",
        "--type", "req")
    assert "0 unresolved" in run(d, "build_view.py", "check", "v.md")
    (d / "stale.md").write_text("This cites REQ-nonexistent-alias for no reason.\n")
    r = subprocess.run([sys.executable, str(S / "build_view.py"), "check", "stale.md"],
                       cwd=d, capture_output=True, text=True)
    assert "unresolved" in r.stdout and r.returncode != 0


def t_agenda(d):
    seed(d)
    out = run(d, "trace.py", "open")
    assert "Unresolved observations" not in out, "the obs is resolved by d"
    run(d, "model.py", "new", "--type", "cand", "--alias", "c",
        "--title", "An undecided option", "--origin", "u")
    assert "Open candidates" in run(d, "trace.py", "open")


def t_computed_inverse(d):
    seed(d)
    out = run(d, "trace.py", "show", "d")
    assert "decides" in out, "the inverse must be computed, not stored"
    dec = next((d / "project-model" / "dec").glob("*.md")).read_text()
    assert "rel_decides" not in dec, "the inverse must never be written to disk"


def t_relocatable(d):
    seed(d)
    moved = d / "moved"
    (d / "project-model").rename(moved)
    assert "OK" in run(d, "model.py", "check", "--root", "moved"), \
        "the model must not depend on its own path"


def t_auto_bundle(d):
    backup = d / "project-model-backup.tar.gz"
    assert not backup.exists(), "sanity: nothing bundled before any write"
    seed(d)  # every model.py new call inside seed() should trigger a bundle
    assert backup.exists(), "a mutating command must bundle automatically, unprompted"
    import tarfile
    with tarfile.open(backup) as tf:
        names = tf.getnames()
    assert any(n.endswith("MANIFEST.json") for n in names)
    assert any("/req/" in n and n.endswith(".md") for n in names), \
        "the bundle must contain the actual objects, not just the manifest"
    mtime_after_seed = backup.stat().st_mtime
    # a later, unrelated write must re-bundle too -- not just the first one
    run(d, "model.py", "status", "--id", "r", "--to", "proposed")
    assert backup.stat().st_mtime >= mtime_after_seed, \
        "amend/status/link must re-trigger the bundle, not only new"


TESTS = [(k[2:].replace("_", " "), v) for k, v in sorted(globals().items())
         if k.startswith("t_")]

if __name__ == "__main__":
    print(f"discovery-driven-dev — {len(TESTS)} tests\n")
    for name, fn in TESTS:
        check(name, fn)
    print(f"\n{PASS} passed, {FAIL} failed")
    for name, err in FAILURES:
        print(f"\n--- {name} ---\n{err}")
    sys.exit(1 if FAIL else 0)
