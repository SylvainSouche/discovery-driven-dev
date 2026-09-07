#!/usr/bin/env python3
"""
trace.py — read the model without loading all of it.

Reading every object in a mature model costs roughly 57,000 tokens for 176
objects and 69,000 for 249. That is the whole session budget spent before any
work starts, so this tool exists to answer questions from the index and
targeted lookups instead.

It also computes inverse relationships. Nothing stores `decides` or
`refined_by`; they are derived here from the forward edges. The rade-bmake
pilot stored both directions and they disagreed — 82 against 69 — which is
what storing an inverse buys you.

Subcommands:
    show     one object, with its edges in both directions
    walk     follow edges from an object, N levels deep
    find     search titles, aliases and bodies (this is the cheap default)
    orphans  objects nothing points at and that point at nothing
    open     unresolved observations and unconfirmed requirements
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import RELATIONSHIPS, INVERSE_LABELS, INACTIVE_STATUSES, TYPES
from model import load, resolve


def inverse_index(objs):
    """dst -> inverse_label -> [src]. Computed, never stored."""
    inv = defaultdict(lambda: defaultdict(list))
    for src, o in objs.items():
        for key, targets in o["rels"].items():
            for dst in targets:
                inv[dst][INVERSE_LABELS.get(key, key + "_by")].append(src)
    return inv


def label(objs, oid):
    o = objs.get(oid)
    if not o:
        return f"{oid} (MISSING)"
    a = o["fm"].get("alias")
    return (f"{o['fm'].get('type','?').upper()} {oid}" + (f" [{a}]" if a else "") +
            f" ({o['fm'].get('status','?')})")


def cmd_show(objs, a):
    oid = resolve(objs, a.id)
    o = objs[oid]
    inv = inverse_index(objs)
    print(label(objs, oid))
    print(f"  {o['title']}")
    print(f"  origin: {o['fm'].get('origin', '-')}")
    if o["fm"].get("facets"):
        print(f"  facets: {o['fm']['facets']}")
    if o["rels"]:
        print("\n  outgoing (stored):")
        for k in sorted(o["rels"]):
            for t in o["rels"][k]:
                print(f"    --{k}--> {label(objs, t)}")
    if inv[oid]:
        print("\n  incoming (computed):")
        for k in sorted(inv[oid]):
            for s in inv[oid][k]:
                print(f"    <--{k}-- {label(objs, s)}")
    if a.body:
        print("\n" + o["body"].strip())


def cmd_walk(objs, a):
    oid = resolve(objs, a.id)
    inv = inverse_index(objs)
    seen = set()

    def rec(n, d, prefix):
        if n in seen or d > a.depth:
            return
        seen.add(n)
        print(f"{prefix}{label(objs, n)} — {objs[n]['title'][:70]}")
        edges = []
        for k, ts in sorted(objs[n]["rels"].items()):
            edges += [(f"--{k}-->", t) for t in ts]
        if a.both:
            for k, ss in sorted(inv[n].items()):
                edges += [(f"<--{k}--", s) for s in ss]
        for arrow, t in edges:
            if t in objs:
                print(f"{prefix}  {arrow}")
                rec(t, d + 1, prefix + "    ")

    rec(oid, 0, "")


def cmd_find(objs, a):
    pat = re.compile(a.query, re.I)
    for oid, o in sorted(objs.items(), key=lambda kv: kv[1]["fm"].get("type", "")):
        hay = " ".join([o["title"], o["fm"].get("alias", ""),
                        o["body"] if a.deep else ""])
        if pat.search(hay):
            print(f"{label(objs, oid)}\n    {o['title'][:100]}")


def cmd_orphans(objs, a):
    inv = inverse_index(objs)
    for oid, o in sorted(objs.items()):
        if o["fm"].get("status") in INACTIVE_STATUSES:
            continue
        if not o["rels"] and not inv[oid]:
            print(f"{label(objs, oid)} — {o['title'][:70]}")


def cmd_open(objs, a):
    """The outstanding-work agenda.

    Both pilots kept hand-maintained "still genuinely open" lists in prose —
    four items in one document, six in another — and both drifted out of step
    with the model. Every one of those items was already representable as an
    object; nothing surfaced them together, so a prose list got written instead.

    This is that list, derived rather than maintained."""
    inv = inverse_index(objs)

    def act(i):
        return objs[i]["fm"].get("status") not in INACTIVE_STATUSES

    groups = [
        ("Unresolved observations — noticed, not yet dealt with",
         [i for i, o in objs.items()
          if o["fm"].get("type") == "obs" and act(i)
          and not inv[i].get("resolved_by")]),
        ("Open candidates — options raised, no decision made",
         [i for i, o in objs.items()
          if o["fm"].get("type") == "cand" and o["fm"].get("status") == "open"]),
        ("AI proposals awaiting a decision — not requirements until accepted",
         [i for i, o in objs.items()
          if o["fm"].get("type") == "ai" and o["fm"].get("status") == "proposed"]),
        ("Planned but unrun validation",
         [i for i, o in objs.items()
          if o["fm"].get("type") == "test"
          and o["fm"].get("status") in ("proposed", "skipped")]),
        ("Failing tests",
         [i for i, o in objs.items()
          if o["fm"].get("type") == "test" and o["fm"].get("status") == "failing"]),
        ("Assumptions never verified",
         [i for i, o in objs.items()
          if o["fm"].get("type") == "asm" and o["fm"].get("status") == "assumed"]),
        ("Proposed, never confirmed",
         [i for i, o in objs.items()
          if o["fm"].get("type") in ("req", "nreq", "uc")
          and o["fm"].get("status") == "proposed"]),
        ("Deferred — parked deliberately",
         [i for i, o in objs.items()
          if o["fm"].get("status") == "deferred"]),
        ("Confirmed with no decision behind them",
         [i for i, o in objs.items()
          if o["fm"].get("type") in ("req", "nreq")
          and o["fm"].get("status") == "confirmed"
          and not o["rels"].get("decided_by")]),
        ("Implementations gone stale",
         [i for i, o in objs.items()
          if o["fm"].get("type") == "impl" and o["fm"].get("status") == "stale"]),
    ]

    total = 0
    for title, group in groups:
        if not group:
            continue
        total += len(group)
        print(f"\n{title} ({len(group)})")
        for i in sorted(group)[:a.limit]:
            print(f"  {label(objs, i)}\n      {objs[i]['title'][:70]}")
        if len(group) > a.limit:
            print(f"  ... and {len(group) - a.limit} more")
    if not total:
        print("Nothing outstanding.")
    else:
        print(f"\n{total} items outstanding. This list is derived from object "
              f"status — do not keep a second copy of it in prose.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("project-model"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show"); s.add_argument("id"); s.add_argument("--body", action="store_true")
    w = sub.add_parser("walk"); w.add_argument("id")
    w.add_argument("--depth", type=int, default=2); w.add_argument("--both", action="store_true")
    f = sub.add_parser("find"); f.add_argument("query"); f.add_argument("--deep", action="store_true")
    sub.add_parser("orphans")
    o = sub.add_parser("open"); o.add_argument("--limit", type=int, default=10)

    a = ap.parse_args()
    objs = load(a.root)
    if not objs:
        raise SystemExit(f"No objects under {a.root}")
    {"show": cmd_show, "walk": cmd_walk, "find": cmd_find,
     "orphans": cmd_orphans, "open": cmd_open}[a.cmd](objs, a)


if __name__ == "__main__":
    main()
