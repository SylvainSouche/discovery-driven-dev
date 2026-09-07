#!/usr/bin/env python3
"""
build_view.py — generate documents from the model, and verify ones already
generated.

Hand-written derived documents rot silently. In one pilot, a superseded layout
document sat beside its five replacements with nothing marking it stale; in
another, an API header claimed per-declaration requirement tags it did not
have. Both looked authoritative. Neither was checked.

Two modes:

    generate   write a document from the model, with a provenance header
    check      re-read a generated document and validate every alias it cites

`check` is the important one. It reports aliases that no longer resolve, and —
more usefully — aliases that resolve to objects no longer `confirmed`. A
document asserting something the model has since superseded is worse than a
broken link, because it still reads as true.
"""
import argparse
import datetime
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import SCHEMA_VERSION, INACTIVE_STATUSES, TYPES
from model import load

ALIAS_CITE = re.compile(r"\b(?:REQ|NREQ|UC|DEC|OBS|CON|ASM|CAND|AI|IMPL|TEST)-"
                        r"([a-z][a-z0-9-]{3,})\b")


def header(objs, title, selected):
    counts = defaultdict(int)
    for i in selected:
        counts[objs[i]["fm"].get("type", "?")] += 1
    parts = ", ".join(f"{n} {t.upper()}" for t, n in sorted(counts.items()))
    return [
        f"# {title}", "",
        f"Generated from `project-model/` · schema_version {SCHEMA_VERSION} · "
        f"{len(objs)} objects in model",
        f"Sources: {parts or 'none'}",
        f"Generated {datetime.date.today().isoformat()}. "
        f"Regenerate rather than edit — hand edits are lost and drift silently.",
        "",
    ]


def cmd_generate(objs, a):
    sel = []
    for i, o in objs.items():
        fm = o["fm"]
        if a.type and fm.get("type") not in a.type.split(","):
            continue
        if a.facet and a.facet not in fm.get("facets", ""):
            continue
        if a.status and fm.get("status") not in a.status.split(","):
            continue
        sel.append(i)

    if a.leaves:
        refined = {t for o in objs.values() for t in o["rels"].get("refines", [])}
        sel = [i for i in sel if i not in refined]

    sel.sort(key=lambda i: (objs[i]["fm"].get("type", ""), objs[i]["title"]))
    lines = header(objs, a.title, sel)

    by_type = defaultdict(list)
    for i in sel:
        by_type[objs[i]["fm"].get("type", "?")].append(i)

    for t in sorted(by_type):
        lines += [f"## {TYPES.get(t, t).split('—')[0].strip()}s", ""]
        for i in by_type[t]:
            o = objs[i]
            alias = o["fm"].get("alias", "")
            cite = f"{t.upper()}-{alias}" if alias else f"{t.upper()}-{i}"
            lines.append(f"### {o['title']}")
            lines.append("")
            lines.append(f"`{cite}` · status **{o['fm'].get('status')}** · "
                         f"id `{i}`")
            body = o["body"].split("\n", 3)
            prose = "\n".join(l for l in body if not l.startswith("#")).strip()
            prose = re.sub(r"<!--.*?-->", "", prose, flags=re.S).strip()
            if prose:
                lines += ["", prose]
            refs = o["rels"].get("refines", [])
            if refs:
                names = ", ".join(f"`{objs[r]['fm'].get('alias') or r}`"
                                  for r in refs if r in objs)
                lines += ["", f"Refines: {names}"]
            lines.append("")

    out = Path(a.out)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out} — {len(sel)} objects, {len(lines)} lines")


def cmd_check(objs, a):
    alias_map = {o["fm"]["alias"]: i for i, o in objs.items() if o["fm"].get("alias")}
    total = missing = stale = 0
    for doc in a.docs:
        p = Path(doc)
        if not p.exists():
            print(f"{p}: not found")
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        cites = sorted(set(ALIAS_CITE.findall(text)))
        bad, inactive = [], []
        for c in cites:
            if c not in alias_map:
                bad.append(c)
            elif objs[alias_map[c]]["fm"].get("status") in INACTIVE_STATUSES:
                inactive.append((c, objs[alias_map[c]]["fm"].get("status")))
        total += len(cites)
        missing += len(bad)
        stale += len(inactive)
        flag = "OK " if not (bad or inactive) else "!! "
        print(f"{flag}{p}: {len(cites)} aliases cited, "
              f"{len(bad)} unresolved, {len(inactive)} inactive")
        for c in bad[:10]:
            print(f"     unresolved: {c}")
        for c, s in inactive[:10]:
            print(f"     {s}: {c}  (document may assert something no longer true)")
    print(f"\n{total} citations · {missing} unresolved · {stale} inactive")
    return 1 if (missing or stale) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("project-model"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--out", required=True)
    g.add_argument("--title", default="Project specification")
    g.add_argument("--type", default="", help="comma-separated types to include")
    g.add_argument("--facet", default="")
    g.add_argument("--status", default="confirmed")
    g.add_argument("--leaves", action="store_true",
                   help="only refinement-DAG leaves (the spec-grade statements)")

    c = sub.add_parser("check")
    c.add_argument("docs", nargs="+")

    a = ap.parse_args()
    objs = load(a.root)
    if not objs:
        raise SystemExit(f"No objects under {a.root}")
    sys.exit(cmd_check(objs, a) if a.cmd == "check" else (cmd_generate(objs, a) or 0))


if __name__ == "__main__":
    main()
