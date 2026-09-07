#!/usr/bin/env python3
"""
coverage.py — what is covered, by what, and what is legitimately not.

Three axes:

    motivation     REQ  <- UC     which requirements serve a stated use case
    verification   UC/REQ <- TEST which are exercised by a functional test
    realization    REQ  <- IMPL   which are actually built

A coverage report that flags everything is noise, and noise gets ignored — so
this is opinionated about what does NOT need covering:

  * **Non-leaf requirements** need no IMPL. A requirement that something else
    refines is not the thing you build; its leaves are. Demanding an IMPL for
    every level of a 9-deep chain would flag the same code nine times.
  * **Constraints and assumptions** need no UC. They are imposed or believed,
    not performed.
  * **Negative requirements** need no UC or IMPL. "We will not do X" is
    satisfied by the absence of code, which cannot carry a marker.
  * **Anything not `confirmed`** is excluded. Proposed and deferred work is not
    yet owed coverage; that is what status is for.

What remains is what genuinely should be covered, so a non-empty report means
something.
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model import load
from schema import INACTIVE_STATUSES


def analyse(objs):
    refined = {t for o in objs.values() for t in o["rels"].get("refines", [])}

    inbound = defaultdict(lambda: defaultdict(list))
    for src, o in objs.items():
        for key in ("motivated_by", "verifies", "implements"):
            for dst in o["rels"].get(key, []):
                inbound[dst][key].append(src)

    def active(i):
        return objs[i]["fm"].get("status") not in INACTIVE_STATUSES

    def motivated(i, seen=None):
        """A requirement is motivated if it, or anything it refines, names a use
        case. `motivated_by` is written ON the requirement pointing AT the use
        case, so it is an outgoing edge — unlike `implements` and `verifies`,
        which are written on the IMPL or TEST and so are found inbound.

        Motivation flows DOWN the refinement chain: a leaf that sharpens a
        requirement inherits the reason that requirement exists. Demanding a
        separate use case at every level of a 9-deep chain would flag the same
        journey nine times."""
        seen = seen or set()
        if i in seen:
            return False
        seen.add(i)
        if any(u in objs and active(u) for u in objs[i]["rels"].get("motivated_by", [])):
            return True
        return any(motivated(p, seen) for p in objs[i]["rels"].get("refines", [])
                   if p in objs)

    reqs = [i for i, o in objs.items()
            if o["fm"].get("type") == "req" and o["fm"].get("status") == "confirmed"]
    ucs = [i for i, o in objs.items()
           if o["fm"].get("type") == "uc" and o["fm"].get("status") == "confirmed"]
    leaves = [i for i in reqs if i not in refined]

    rows = {
        "motivation": {
            "owed": reqs,
            "covered": [i for i in reqs if motivated(i)],
            "what": "confirmed requirements traceable to a use case",
        },
        "verification": {
            "owed": ucs + leaves,
            "covered": [i for i in ucs + leaves
                        if any(active(s) for s in inbound[i]["verifies"])],
            "what": "confirmed use cases and leaf requirements with a test",
        },
        "realization": {
            "owed": leaves,
            "covered": [i for i in leaves
                        if any(active(s) for s in inbound[i]["implements"])],
            "what": "confirmed leaf requirements with an implementation",
        },
    }

    # A use case nothing derives from is a different failure: it was written
    # and then nothing came of it.
    barren = [i for i in ucs
              if not any(active(s) for s in inbound[i]["motivated_by"])]
    # inbound[uc]["motivated_by"] is right here: the edge is written on the
    # requirement and points at the use case, so the use case sees it inbound.
    return rows, barren, inbound, refined


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("project-model"))
    ap.add_argument("--axis", default="", help="motivation|verification|realization")
    ap.add_argument("--list", action="store_true", help="list the uncovered objects")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--strict", action="store_true", help="exit non-zero if any gap")
    a = ap.parse_args()

    objs = load(a.root)
    if not objs:
        raise SystemExit(f"No objects under {a.root}")
    rows, barren, inbound, refined = analyse(objs)

    print(f"{len(objs)} objects\n")
    print(f"{'axis':<14}{'covered':>9}{'owed':>7}{'':>4}what")
    print("-" * 72)
    gap = False
    for name, r in rows.items():
        if a.axis and name != a.axis:
            continue
        n, d = len(r["covered"]), len(r["owed"])
        pct = f"{100 * n // d}%" if d else "n/a"
        if n < d:
            gap = True
        print(f"{name:<14}{n:>9}{d:>7}{pct:>6}  {r['what']}")

    if a.list:
        for name, r in rows.items():
            if a.axis and name != a.axis:
                continue
            missing = [i for i in r["owed"] if i not in set(r["covered"])]
            if not missing:
                continue
            print(f"\nNot covered — {name} ({len(missing)})")
            for i in missing[:a.limit]:
                o = objs[i]
                alias = o["fm"].get("alias", "")
                print(f"  {i}  [{alias}]  {o['title'][:62]}")
            if len(missing) > a.limit:
                print(f"  ... and {len(missing) - a.limit} more")

    if barren:
        print(f"\nUse cases nothing derives from ({len(barren)}) — written, then "
              f"no requirement followed")
        for i in barren[:a.limit]:
            print(f"  {i}  [{objs[i]['fm'].get('alias','')}]  {objs[i]['title'][:62]}")

    excluded = sum(1 for i, o in objs.items()
                   if o["fm"].get("type") in ("con", "nreq", "asm")
                   or o["fm"].get("status") != "confirmed")
    print(f"\n{excluded} objects excluded from coverage: not confirmed, or a "
          f"constraint, assumption or negative requirement.")
    return 1 if (a.strict and gap) else 0


if __name__ == "__main__":
    sys.exit(main())
