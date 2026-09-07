#!/usr/bin/env python3
"""
check_impl.py — reconcile IMPL objects against markers in the source tree.

The FSM pilot's api/fsm.h states that every declaration is tagged with the
requirement ID it implements. It has 37 declarations, 9 type definitions, and
zero IDs. Nobody noticed, because nothing checked. That is the failure this
script exists to make impossible.

MARKER FORMAT
    @impl <canonical-id>

Syntax-agnostic on purpose, so one grep works across C, headers, Makefiles,
shell and anything else:

    /* @impl 9730-6a92-f9b5-487a */
    # @impl 9730-6a92-f9b5-487a

The marker carries the CANONICAL ID, never the alias. Aliases are renamable by
design, and source comments are the most expensive place in a project to have
to rename anything.

IMPL objects store no file paths. Locations are derived by grepping at run
time, so code can move, split or be renamed without the model going stale —
the model never claimed to know where anything was.

THREE CHECKS
    orphan     a marker in the code whose id matches no object
    dangling   an IMPL object whose id appears nowhere in the source
    uncovered  a refinement-DAG leaf with no IMPL claiming it

The first two are mechanical and reliable. Semantic drift — marker and object
both present, code no longer doing what the object says — is not detectable
here and this script does not pretend otherwise.
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import INACTIVE_STATUSES
from model import load

MARKER = re.compile(r"@impl\s+([0-9a-f][0-9a-f-]{6,})")
SKIP_DIRS = {".git", "node_modules", "build", "dist", "__pycache__",
             "project-model", ".venv", "venv"}


def scan(src_root, exts):
    """id -> [(path, lineno)]. Text files only; binaries skipped silently."""
    found = defaultdict(list)
    for p in src_root.rglob("*"):
        if not p.is_file() or any(d in p.parts for d in SKIP_DIRS):
            continue
        if exts and p.suffix not in exts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in MARKER.finditer(line):
                found[m.group(1)].append((p.relative_to(src_root), n))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("project-model"))
    ap.add_argument("--src", type=Path, default=Path("."),
                    help="source tree to scan (default: cwd)")
    ap.add_argument("--ext", default="",
                    help="comma-separated extensions to limit the scan, e.g. .c,.h")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any leaf is uncovered, not just on hard errors")
    a = ap.parse_args()

    objs = load(a.root)
    exts = {e if e.startswith(".") else "." + e
            for e in a.ext.split(",") if e.strip()}
    markers = scan(a.src, exts)

    impls = {i: o for i, o in objs.items() if o["fm"].get("type") == "impl"}

    # An IMPL is "present" if its own id appears in the source, or if any id it
    # claims to implement does. Both spellings are legitimate: mark the code
    # with the IMPL id when several requirements converge on one block, or with
    # the requirement id when it is one-to-one.
    orphan = {i: locs for i, locs in markers.items() if i not in objs}

    dangling = []
    for i, o in impls.items():
        if o["fm"].get("status") in INACTIVE_STATUSES:
            continue
        claimed = o["rels"].get("implements", [])
        if i not in markers and not any(c in markers for c in claimed):
            dangling.append((i, o["title"], claimed))

    refined = {t for o in objs.values() for t in o["rels"].get("refines", [])}
    covered = set()
    for i, o in impls.items():
        covered.update(o["rels"].get("implements", []))
    covered.update(markers)
    leaves = [(i, o) for i, o in objs.items()
              if o["fm"].get("type") in ("req", "nreq")
              and i not in refined
              and o["fm"].get("status") == "confirmed"]
    uncovered = [(i, o) for i, o in leaves if i not in covered]

    print(f"source: {a.src}  ·  markers found: {sum(len(v) for v in markers.values())} "
          f"across {len(markers)} ids")
    print(f"model:  {len(impls)} IMPL objects  ·  {len(leaves)} confirmed leaves\n")

    if orphan:
        print(f"ORPHAN MARKERS ({len(orphan)}) — in the code, not in the model")
        for i, locs in list(orphan.items())[:15]:
            where = ", ".join(f"{p}:{n}" for p, n in locs[:3])
            print(f"  {i}  {where}")
        print()

    if dangling:
        print(f"DANGLING IMPL ({len(dangling)}) — asserted in the model, absent from the code")
        for i, t, claimed in dangling[:15]:
            print(f"  {i}  {t[:60]}")
            print(f"      claims: {', '.join(claimed) or '(nothing)'}")
        print()

    if uncovered:
        print(f"UNCOVERED LEAVES ({len(uncovered)}) — confirmed, most-specific, no implementation")
        for i, o in uncovered[:15]:
            alias = o["fm"].get("alias", "")
            print(f"  {i}  [{alias}]  {o['title'][:60]}")
        if len(uncovered) > 15:
            print(f"  ... and {len(uncovered) - 15} more")
        print()

    if not (orphan or dangling or uncovered):
        print("OK — every marker resolves, every assertion is present, every leaf covered.")
        return 0
    return 1 if (orphan or dangling or (a.strict and uncovered)) else 0


if __name__ == "__main__":
    sys.exit(main())
