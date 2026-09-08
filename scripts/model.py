#!/usr/bin/env python3
"""
model.py — the ONLY sanctioned way to write to project-model/.

Every write goes through here. That is not a style preference: across two pilot
projects, 436 objects were hand-written while a perfectly good generator sat
unused beside them, and the result was 24 relationship keys, 10 free-text
statuses, and 163 objects with no recorded origin. The script was never the
problem; the fact that it was optional was.

Frontmatter is machine territory and carries a checksum. Bodies are prose and
are yours to edit freely — the checksum deliberately does not cover them.

Subcommands:
    new      create an object
    link     add a relationship between two existing objects
    status   change an object's status
    amend    change a labeling field (alias/origin/facets/certainty) in
             place, logging a terse, checksummed "date: reason" entry
    index    regenerate index.md, alias_table.json and model.json
    check    verify the model (see also: --strict)
    leaves   list refinement-DAG leaves (the spec-grade requirements)

Examples:
    python3 model.py new --type req --alias saved-search \\
        --title "The system shall support saved searches" \\
        --origin "user statement, 2026-08-29"

    python3 model.py link --from saved-search --key decided_by --to search-dec
    python3 model.py status --id saved-search --to confirmed
    python3 model.py check --strict
"""
import argparse
import datetime
from collections import defaultdict
import hashlib
import json
import re
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import schema
from schema import (SCHEMA_VERSION, TYPES, STATUSES, DEFAULT_STATUS,
                    INACTIVE_STATUSES, RELATIONSHIPS, RELATIONSHIP_KEYS,
                    INVERSE_LABELS, CERTAINTIES)

SKILL_VERSION = "2.5.0"          # bumped on any skill change
# 2.5.0 — new `amend` subcommand: change alias/origin/facets/certainty on an
#         existing object without supersession. Every amendment appends a
#         terse "date: reason" entry to `amended`, checksummed independently
#         of the object's own checksum (SUMMED, and therefore every existing
#         object's checksum, is untouched -- no migration needed). id stays
#         permanent, type requires supersede, status keeps its own command.
# 2.4.0 — check --strict gained a citation/edge-parity rule: if a body cites
#         another object by TYPE-alias, a matching edge must exist. Also
#         fixes this very constant, which had been stuck at 2.1.0 through
#         the 2.2.0 and 2.3.0 releases -- every object written in between
#         was silently stamped generator: model.py/2.1.0 regardless of the
#         version actually running. SCHEMA_VERSION unchanged either time:
#         no object format change, so no migration.
# 2.1.0 — supersession made explicitly total; `supersede` subcommand
#         added for the absorb and split cases. SCHEMA_VERSION is
#         unchanged: no object format change, so no migration.
GENERATOR = f"model.py/{SKILL_VERSION}"
HOST_ID_PATH = Path.home() / ".cache" / "discovery-driven-dev" / "host_id"

# Frontmatter keys that participate in the checksum, in canonical order.
# `checksum` and `generator` are excluded (one is the output, the other is
# metadata about it).
SUMMED = ["schema_version", "id", "alias", "type", "status", "origin",
          "created", "certainty", "facets"]

# Matches the TYPE-alias shorthand the skill itself writes in prose, e.g.
# "REQ-foo-bar" or "DEC-search-dec". Used by check's citation/edge-parity
# rule below -- not by resolve(), which already handles this more generally.
CITATION_RE = re.compile(
    r"\b(?:REQ|NREQ|DEC|OBS|CON|IMPL|TEST|CAND|AI|ASM|UC)-"
    r"([a-z][a-z0-9-]*[a-z0-9])\b")


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------
def host_id():
    if HOST_ID_PATH.exists():
        v = HOST_ID_PATH.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-f]{4}", v):
            return v
    HOST_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    v = secrets.token_hex(2)
    HOST_ID_PATH.write_text(v, encoding="utf-8")
    return v


def object_files(root):
    if not root.exists():
        return []
    return sorted(p for p in root.glob("*/*.md")
                  if p.parent.name in TYPES)


def read(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    _, fm_raw, body = text.split("---", 2)
    fm, rels = {}, {}
    for line in fm_raw.strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k.startswith("rel_"):
            rels[k[4:]] = [x.strip() for x in v.strip("[]").split(",") if x.strip()]
        else:
            fm[k] = v
    title = ""
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return {"path": path, "fm": fm, "rels": rels, "body": body, "title": title}


def checksum(fm, rels):
    """Covers frontmatter only. Editing prose never invalidates it; editing
    structure by hand always does."""
    parts = [f"{k}={fm.get(k, '')}" for k in SUMMED]
    parts += [f"rel_{k}={','.join(sorted(v))}" for k, v in sorted(rels.items())]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def write(root, fm, rels, body):
    fm = dict(fm)
    fm["schema_version"] = str(SCHEMA_VERSION)
    fm["generator"] = GENERATOR
    fm["checksum"] = checksum(fm, rels)
    lines = ["---"]
    for k in SUMMED:
        if fm.get(k):
            lines.append(f"{k}: {fm[k]}")
    for k in sorted(rels):
        if rels[k]:
            lines.append(f"rel_{k}: [{', '.join(sorted(set(rels[k])))}]")
    # amended/amended_checksum sit outside SUMMED on purpose (see log_checksum):
    # they carry their own, independent checksum rather than folding into the
    # object's main one, so adding this pair never invalidates every existing
    # object's checksum the moment amend ships.
    if fm.get("amended"):
        lines.append(f"amended: {fm['amended']}")
        lines.append(f"amended_checksum: {fm['amended_checksum']}")
    lines += [f"generator: {fm['generator']}", f"checksum: {fm['checksum']}", "---"]
    path = root / fm["type"] / f"{fm['id']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + body.rstrip() + "\n", encoding="utf-8")
    return path


def load(root):
    objs = {}
    for p in object_files(root):
        o = read(p)
        if o and o["fm"].get("id"):
            objs[o["fm"]["id"]] = o
    return objs


def resolve(objs, ref):
    """Accept an id, an alias, or a typed reference like REQ-<id>; always
    return the canonical id.

    The shipped v1 script returned the ALIAS here and wrote it into the edge,
    which silently defeated the whole point of separating renamable aliases
    from immutable ids. Edges store ids. Always.

    Exact matches are tried BEFORE any prefix stripping: an alias such as
    `search-dec` otherwise looks like a typed reference whose id starts with a
    hex character, and gets mangled into `dec`."""
    ref = ref.strip()
    if ref in objs:
        return ref
    hits = [i for i, o in objs.items() if o["fm"].get("alias") == ref]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise SystemExit(f"'{ref}' matches {len(hits)} objects. Use the id.")
    m = re.match(r"^[A-Za-z]{2,4}-(.+)$", ref)
    if m and m.group(1) != ref:
        stripped = m.group(1)
        if stripped in objs or any(o["fm"].get("alias") == stripped
                                   for o in objs.values()):
            return resolve(objs, stripped)
    raise SystemExit(
        f"'{ref}' matches no object id or alias. Check index.md — an edge "
        f"cannot point at nothing.")


# --------------------------------------------------------------------------
# generated artefacts
# --------------------------------------------------------------------------
def regenerate(root):
    objs = load(root)
    rows = sorted(((o["fm"].get("type", "?"), i, o["fm"].get("alias", ""),
                    o["fm"].get("status", "?"), o["title"]) for i, o in objs.items()))
    # No path column: type/id.md is fully determined, and the v1 index spent
    # 2,800 tokens repeating an absolute path that also broke on relocation.
    lines = ["# Project model index", "",
             f"schema_version {SCHEMA_VERSION} · {len(rows)} objects · "
             f"regenerated {datetime.date.today().isoformat()}", "",
             "Generated by model.py. Do not hand-edit. Read or grep this before "
             "opening any object file; paths are `project-model/<type>/<id>.md`.",
             "", "| type | id | alias | status | title |", "|---|---|---|---|---|"]
    lines += [f"| {t} | {i} | {a} | {s} | {ti} |" for t, i, a, s, ti in rows]
    (root / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    table = {o["fm"]["alias"]: {"id": i, "type": o["fm"].get("type"),
                                "status": o["fm"].get("status"),
                                "active": o["fm"].get("status") not in INACTIVE_STATUSES}
             for i, o in objs.items() if o["fm"].get("alias")}
    (root / "alias_table.json").write_text(
        json.dumps(table, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    (root / "model.json").write_text(json.dumps({
        "schema_version": SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "objects": len(objs),
        "edges": sum(len(v) for o in objs.values() for v in o["rels"].values()),
        "last_write": datetime.datetime.now().isoformat(timespec="seconds"),
    }, indent=2) + "\n", encoding="utf-8")
    return objs


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------
def cmd_new(root, a):
    schema.check_type(a.type)
    objs = load(root)
    if a.alias:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", a.alias):
            raise SystemExit("Alias must be lowercase letters, digits and hyphens.")
        for i, o in objs.items():
            if o["fm"].get("alias") == a.alias and \
               o["fm"].get("status") not in INACTIVE_STATUSES:
                raise SystemExit(
                    f"Alias '{a.alias}' is in use by active object {i}. "
                    f"Pick another, or supersede that object first.")
    status = a.status or DEFAULT_STATUS[a.type]
    schema.check_status(a.type, status)
    if a.type == "asm" and a.certainty and a.certainty not in CERTAINTIES:
        raise SystemExit(f"certainty must be one of {', '.join(CERTAINTIES)}")

    rels = {}
    for pair in a.relates:
        if ":" not in pair:
            raise SystemExit(f"--relates '{pair}' must be KEY:TARGET")
        key, target = pair.split(":", 1)
        tid = resolve(objs, target)
        schema.check_relationship(key.strip(), a.type, objs[tid]["fm"].get("type"))
        rels.setdefault(key.strip(), []).append(tid)

    existing = set(objs)
    while True:
        ts = f"{int(time.time()):08x}"
        oid = f"{host_id()}-{ts[:4]}-{ts[4:]}-{secrets.token_hex(2)}"
        if oid not in existing:
            break

    if not a.origin:
        raise SystemExit(
            "--origin is required. Two thirds of the FSM pilot's objects carry "
            "an 'unspecified' placeholder because it was optional; that "
            "information is unrecoverable. Say where this came from.")

    body = f"\n\n# {a.title}\n\n"
    if a.type == "ai":
        body += ("> AI proposal — introduced by Claude, not the user. Not a "
                 "requirement until a DEC records acceptance.\n\n")
    body += (a.note or "<!-- rationale, detail, alternatives considered -->") + "\n"

    fm = {"id": oid, "alias": a.alias, "type": a.type, "status": status,
          "origin": a.origin, "created": datetime.date.today().isoformat(),
          "certainty": a.certainty if a.type == "asm" else "",
          "facets": f"[{', '.join(f.strip() for f in a.facets.split(',') if f.strip())}]"
                    if a.facets else ""}
    path = write(root, fm, rels, body)
    regenerate(root)
    print(f"{a.type.upper()} {oid}" + (f" [{a.alias}]" if a.alias else "") +
          f" status={status}\n{path}")


def cmd_link(root, a):
    objs = load(root)
    src, dst = resolve(objs, a.frm), resolve(objs, a.to)
    if src == dst:
        raise SystemExit("An object cannot relate to itself.")
    s, d = objs[src], objs[dst]
    schema.check_relationship(a.key, s["fm"]["type"], d["fm"]["type"])
    if a.key in INVERSE_LABELS.values():
        raise SystemExit(
            f"'{a.key}' is a computed inverse and is never stored. "
            f"Write the opposite key on the other object instead.")
    rels = dict(s["rels"])
    rels.setdefault(a.key, [])
    if dst in rels[a.key]:
        print("Already linked; nothing to do.")
        return
    rels[a.key].append(dst)
    write(root, s["fm"], rels, s["body"])
    regenerate(root)
    print(f"{src} --{a.key}--> {dst}")


def cmd_status(root, a):
    objs = load(root)
    oid = resolve(objs, a.id)
    o = objs[oid]
    schema.check_status(o["fm"]["type"], a.to)
    o["fm"]["status"] = a.to
    write(root, o["fm"], o["rels"], o["body"])
    regenerate(root)
    print(f"{oid}: status -> {a.to}")


AMENDABLE_FIELDS = {"alias", "origin", "facets", "certainty"}


def log_checksum(text):
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def cmd_amend(root, a):
    """Change a labeling field in place — alias, origin, facets, certainty.
    Deliberately excludes id (permanent identity; every edge stores it),
    type (would require moving the file to a different directory — a
    reclassification, not a label fix), status (already has its own
    validated command), and created/schema_version (system-managed).

    Every amendment appends a terse, undated-before entry to `amended`
    ("YYYY-MM-DD: reason", nothing else — no before-value, since that's
    what would make this supersession-by-stealth) and stamps a checksum
    over that log text alone, independent of the object's own checksum.
    Editing the log without going through here is caught by check the
    same way editing anything else by hand is."""
    if a.field not in AMENDABLE_FIELDS:
        raise SystemExit(
            f"--field must be one of {', '.join(sorted(AMENDABLE_FIELDS))}. "
            f"id is permanent, type needs supersede (it's a reclassification, "
            f"not a label), status has its own command.")
    objs = load(root)
    oid = resolve(objs, a.id)
    o = objs[oid]
    fm = dict(o["fm"])

    if a.field == "alias":
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", a.value):
            raise SystemExit("Alias must be lowercase letters, digits and hyphens.")
        for j, other in objs.items():
            if j != oid and other["fm"].get("alias") == a.value and \
               other["fm"].get("status") not in INACTIVE_STATUSES:
                raise SystemExit(f"Alias '{a.value}' is in use by active object {j}.")
        new_value = a.value
    elif a.field == "certainty":
        if fm.get("type") == "asm" and a.value and a.value not in CERTAINTIES:
            raise SystemExit(f"certainty must be one of {', '.join(CERTAINTIES)}")
        new_value = a.value
    elif a.field == "facets":
        new_value = f"[{', '.join(f.strip() for f in a.value.split(',') if f.strip())}]"
    else:
        new_value = a.value

    fm[a.field] = new_value
    entry = f"{datetime.date.today().isoformat()}: {a.reason}"
    fm["amended"] = f"{fm['amended']}; {entry}" if fm.get("amended") else entry
    fm["amended_checksum"] = log_checksum(fm["amended"])

    write(root, fm, o["rels"], o["body"])
    regenerate(root)
    print(f"{oid}: {a.field} -> {new_value}\n  logged: {entry}")


def cmd_leaves(root, a):
    """Leaves of the refinement DAG are the most specific requirements in the
    model. They are what a SPEC object would have been, and they are where IMPL
    markers attach."""
    objs = load(root)
    refined = {t for o in objs.values() for t in o["rels"].get("refines", [])}
    for i, o in sorted(objs.items(), key=lambda kv: kv[1]["title"]):
        if o["fm"].get("type") not in ("req", "nreq"):
            continue
        if i in refined or o["fm"].get("status") in INACTIVE_STATUSES:
            continue
        depth = 0
        cur = o
        seen = set()
        while cur["rels"].get("refines"):
            nxt = cur["rels"]["refines"][0]
            if nxt in seen or nxt not in objs:
                break
            seen.add(nxt)
            cur = objs[nxt]
            depth += 1
        print(f"{i}  d{depth}  [{o['fm'].get('alias','-')}]  {o['title']}")


def cmd_supersede(root, a):
    """Supersession is TOTAL. An object is either still true or it is replaced.

    Refinement cannot do this job: refining leaves the parent confirmed and
    true, so if half of it is wrong, the wrong half stays cited. When part of a
    statement is invalidated there are exactly two correct moves:

      absorb  one replacement carries forward what was kept and states what
              changed. Use when the two parts do not stand alone.

      split   two or more replacements, each superseding the original. One
              carries what changed, another what was kept. Use when each part
              is a coherent statement on its own.

    Both are expressed the same way: every replacement writes `supersedes` at
    the original, and the original becomes `superseded`."""
    objs = load(root)
    old_id = resolve(objs, a.old)
    old = objs[old_id]
    if old["fm"].get("status") == "superseded":
        raise SystemExit(f"{old_id} is already superseded. Supersede its "
                         f"replacement instead.")
    dec_id = resolve(objs, a.decided_by)
    if objs[dec_id]["fm"].get("type") != "dec":
        raise SystemExit(f"--decided-by must name a DEC; {dec_id} is a "
                         f"{objs[dec_id]['fm'].get('type')}. Supersession "
                         f"without a recorded decision is how a model loses "
                         f"track of why something changed.")
    if not a.with_:
        raise SystemExit("Give at least one --with 'alias:title'.")

    otype = a.type or old["fm"].get("type")
    schema.check_type(otype)

    # Inherit the old object's refinement parents — but follow supersession
    # rather than copying a dead pointer. If a parent was itself replaced by
    # exactly one object, re-point at it; if it was split, say so and let the
    # user choose, since guessing which half applies is exactly the judgment
    # this operation exists to make explicit.
    replaced_by = defaultdict(list)
    for i, o in objs.items():
        for t2 in o["rels"].get("supersedes", []):
            replaced_by[t2].append(i)
    inherited, ambiguous = [], []
    for r in old["rels"].get("refines", []):
        if r in objs and objs[r]["fm"].get("status") == "superseded":
            heirs = replaced_by.get(r, [])
            if len(heirs) == 1:
                inherited.append(heirs[0])
                print(f"note: refinement of {r} follows to its replacement {heirs[0]}")
            else:
                ambiguous.append((r, heirs))
        else:
            inherited.append(r)
    for r, heirs in ambiguous:
        print(f"note: {r} was split across {len(heirs)} objects; the new object "
              f"inherits no refinement from it. Re-point deliberately:")
        for h in heirs:
            print(f"        model.py link --from <new> --key refines --to {h}")

    created = []
    for spec in a.with_:
        if ":" not in spec:
            raise SystemExit(f"--with '{spec}' must be 'alias:title' "
                             f"(use ':title' for no alias)")
        alias, title = spec.split(":", 1)
        alias, title = alias.strip(), title.strip()
        if len(a.with_) == 1:
            note_tail = "Carries forward what remained valid and states what changed."
        else:
            note_tail = ("One of several statements replacing that object; each is "
                         "coherent on its own.")
        ns = argparse.Namespace(
            type=otype, title=title, origin=a.origin, alias=alias,
            status="", certainty="", facets=old["fm"].get("facets", "").strip("[]"),
            note=f"Supersedes {old_id} ({old['title']}).\n\n{note_tail}",
            relates=[f"supersedes:{old_id}", f"decided_by:{dec_id}"] +
                    [f"refines:{r}" for r in inherited])
        cmd_new(root, ns)
        created.append(alias or title)

    objs = load(root)
    old = objs[old_id]
    old["fm"]["status"] = "superseded"
    write(root, old["fm"], old["rels"], old["body"])
    regenerate(root)

    mode = "absorbed into" if len(a.with_) == 1 else "split across"
    print(f"\n{old_id} superseded — {mode} {len(created)} object(s).")

    # Children now refine a superseded object; they must be re-pointed.
    objs = load(root)
    orphaned = [i for i, o in objs.items()
                if old_id in o["rels"].get("refines", [])
                and o["fm"].get("status") not in INACTIVE_STATUSES]
    if orphaned:
        print(f"\n{len(orphaned)} object(s) still refine the superseded object "
              f"and must be re-pointed:")
        for i in orphaned:
            print(f"  {i} [{objs[i]['fm'].get('alias','-')}] {objs[i]['title'][:60]}")
        print("Re-point each with: model.py link --from <id> --key refines --to <new>")


def cmd_check(root, a):
    objs = load(root)
    problems = []
    for i, o in objs.items():
        fm, rels = o["fm"], o["rels"]
        if fm.get("schema_version") != str(SCHEMA_VERSION):
            problems.append((i, "schema", f"schema_version={fm.get('schema_version')} "
                                          f"(expected {SCHEMA_VERSION}) — run migrate.py"))
            continue
        if not fm.get("checksum"):
            problems.append((i, "unstamped", "no checksum — this object was written by hand"))
        elif fm["checksum"] != checksum(fm, rels):
            problems.append((i, "tampered", "checksum mismatch — frontmatter edited outside model.py"))
        if fm.get("amended") and fm.get("amended_checksum") != log_checksum(fm["amended"]):
            problems.append((i, "log-tampered",
                             "amended checksum mismatch — log edited outside model.py amend"))
        t = fm.get("type")
        if t not in TYPES:
            problems.append((i, "type", f"unknown type '{t}'"))
            continue
        if fm.get("status") not in STATUSES[t]:
            problems.append((i, "status", f"'{fm.get('status')}' invalid for {t}"))
        if not fm.get("origin") or fm["origin"].startswith(("unspecified", "unrecorded")):
            problems.append((i, "origin", "no recorded provenance"))
        if not o["title"]:
            problems.append((i, "title", "no '# Title' line"))
        for k, targets in rels.items():
            if k not in RELATIONSHIP_KEYS:
                problems.append((i, "vocab", f"'{k}' not in the vocabulary"))
                continue
            for t2 in targets:
                if t2 not in objs:
                    problems.append((i, "dangling", f"{k} -> {t2} points at nothing"))
                else:
                    src_ok, dst_ok, _ = RELATIONSHIPS[k]
                    dt = objs[t2]["fm"].get("type")
                    if (src_ok != "*" and t not in src_ok.split("|")) or \
                       (dst_ok != "*" and dt not in dst_ok.split("|")):
                        problems.append((i, "illegal", f"{t} --{k}--> {dt} not allowed"))

    # Citation/edge parity. If a body names another object by its TYPE-alias
    # form (the same shorthand the skill itself writes in prose, e.g.
    # "REQ-foo-bar"), the writer plainly knew what shaped this object --
    # only the formal edge was skipped. This never invents a relationship:
    # an object that cites nothing is untouched, and a cited object with no
    # matching edge is flagged, not auto-linked, since which key (informed_by,
    # resolves, raised_by, ...) is a judgment call the tool won't guess at.
    alias_to_id = {o["fm"]["alias"]: j for j, o in objs.items() if o["fm"].get("alias")}
    for i, o in objs.items():
        if o["fm"].get("status") in INACTIVE_STATUSES:
            continue
        own_targets = {t2 for targets in o["rels"].values() for t2 in targets}
        cited = set()
        for m in CITATION_RE.finditer(o["body"]):
            tid = alias_to_id.get(m.group(1))
            if tid and tid != i:
                cited.add(tid)
        missing = cited - own_targets
        if missing:
            names = ", ".join(sorted(objs[t2]["fm"].get("alias", t2) for t2 in missing))
            problems.append((i, "uncited", f"body names {names} but no edge records it"))

    # Supersession invariants. Supersession is total, so the model must not
    # contain a live object that something has replaced, nor a refinement
    # pointing at a replaced one.
    superseded_by = defaultdict(list)
    for i, o in objs.items():
        for t2 in o["rels"].get("supersedes", []):
            superseded_by[t2].append(i)
    for t2, srcs in superseded_by.items():
        if t2 in objs and objs[t2]["fm"].get("status") != "superseded":
            problems.append((t2, "live-superseded",
                             f"status is '{objs[t2]['fm'].get('status')}' but "
                             f"{', '.join(srcs)} supersede(s) it"))
    for i, o in objs.items():
        if o["fm"].get("status") == "superseded" and i not in superseded_by:
            problems.append((i, "orphan-superseded",
                             "marked superseded but nothing supersedes it — "
                             "what replaced it?"))
        if o["fm"].get("status") in INACTIVE_STATUSES:
            continue
        for r in o["rels"].get("refines", []):
            if r in objs and objs[r]["fm"].get("status") == "superseded":
                problems.append((i, "refines-dead",
                                 f"refines {r}, which has been superseded — "
                                 f"re-point at its replacement"))

    # Cycles in refines. A naive "already visited" check reports a false
    # positive on any diamond (two requirements refining toward a common
    # ancestor), which is legitimate structure — so track the recursion stack,
    # not merely the visited set.
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {i: WHITE for i in objs}
    cycles = []

    def visit(n, path):
        colour[n] = GREY
        for m in objs[n]["rels"].get("refines", []):
            if m not in objs:
                continue
            if colour[m] == GREY:
                cycles.append(path[path.index(m):] + [m] if m in path else [n, m])
            elif colour[m] == WHITE:
                visit(m, path + [m])
        colour[n] = BLACK

    sys.setrecursionlimit(10000)
    for i in objs:
        if colour[i] == WHITE:
            visit(i, [i])
    for c in cycles:
        problems.append((c[0], "cycle", " -> ".join(c)))

    by_kind = {}
    for i, kind, msg in problems:
        by_kind.setdefault(kind, []).append((i, msg))
    print(f"{len(objs)} objects · {sum(len(v) for o in objs.values() for v in o['rels'].values())} edges")
    if not problems:
        print("OK — no problems found.")
        return 0
    for kind in sorted(by_kind):
        items = by_kind[kind]
        print(f"\n{kind.upper()} ({len(items)})")
        for i, msg in items[:a.limit]:
            print(f"  {i}: {msg}")
        if len(items) > a.limit:
            print(f"  ... and {len(items) - a.limit} more")
    # Supersession breakages are incoherence, not untidiness: an active object
    # refining a replaced one, or a replaced object still marked live, means the
    # model asserts something it has already retracted. These must fail CI.
    hard = {"tampered", "log-tampered", "dangling", "vocab", "illegal", "cycle",
            "schema", "refines-dead", "live-superseded", "orphan-superseded"}
    return 1 if (a.strict or set(by_kind) & hard) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("project-model"),
                    help="model root (default: ./project-model)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_root(sp):
        sp.add_argument("--root", type=Path, default=None,
                        help="model root (may also be given before the subcommand)")
        return sp

    n = add_root(sub.add_parser("new"))
    n.add_argument("--type", required=True, choices=sorted(TYPES))
    n.add_argument("--title", required=True)
    n.add_argument("--origin", required=True, help="where this came from — mandatory")
    n.add_argument("--alias", default="")
    n.add_argument("--status", default="")
    n.add_argument("--certainty", default="")
    n.add_argument("--facets", default="")
    n.add_argument("--note", default="")
    n.add_argument("--relates", action="append", default=[], metavar="KEY:TARGET")

    l = add_root(sub.add_parser("link"))
    l.add_argument("--from", dest="frm", required=True)
    l.add_argument("--key", required=True, choices=sorted(RELATIONSHIP_KEYS))
    l.add_argument("--to", required=True)

    sup = add_root(sub.add_parser("supersede"))
    sup.add_argument("--old", required=True, help="object being replaced")
    sup.add_argument("--with", dest="with_", action="append", default=[],
                     metavar="ALIAS:TITLE",
                     help="a replacement; give once to absorb, twice or more to split")
    sup.add_argument("--decided-by", required=True, help="the DEC authorizing this")
    sup.add_argument("--origin", required=True)
    sup.add_argument("--type", default="", help="defaults to the old object's type")

    s = add_root(sub.add_parser("status"))
    s.add_argument("--id", required=True)
    s.add_argument("--to", required=True)

    am = add_root(sub.add_parser("amend"))
    am.add_argument("--id", required=True)
    am.add_argument("--field", required=True, choices=sorted(AMENDABLE_FIELDS))
    am.add_argument("--value", required=True)
    am.add_argument("--reason", required=True,
                    help="brief — logged verbatim, no before-value")

    add_root(sub.add_parser("index"))
    add_root(sub.add_parser("leaves"))

    c = add_root(sub.add_parser("check"))
    c.add_argument("--strict", action="store_true")
    c.add_argument("--limit", type=int, default=10)

    a = ap.parse_args()
    root = getattr(a, "root", None) or Path("project-model")
    if isinstance(root, list):
        root = root[0]
    if a.cmd == "new":
        cmd_new(root, a)
    elif a.cmd == "link":
        cmd_link(root, a)
    elif a.cmd == "supersede":
        cmd_supersede(root, a)
    elif a.cmd == "status":
        cmd_status(root, a)
    elif a.cmd == "amend":
        cmd_amend(root, a)
    elif a.cmd == "leaves":
        cmd_leaves(root, a)
    elif a.cmd == "index":
        objs = regenerate(root)
        print(f"Regenerated index for {len(objs)} objects.")
    elif a.cmd == "check":
        sys.exit(cmd_check(root, a))


if __name__ == "__main__":
    main()
