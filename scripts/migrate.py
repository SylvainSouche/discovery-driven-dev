#!/usr/bin/env python3
"""
migrate.py — bring a project-model up to the current schema version.

Dry-run by default. Nothing is written without --apply.

Neither pilot project recorded a schema version, so legacy models are
FINGERPRINTED rather than read from a marker. After migration every object
carries schema_version, and no future run has to guess again.

Rules this obeys, in order of importance:

  1. ADDITIVE ONLY. Bodies, titles, ids and creation dates are never touched.
     Only frontmatter shape and vocabulary change.
  2. IDS ARE IMMUTABLE. An 8-hex legacy id stays 8-hex forever. Rewriting ids
     would break every reference in every document the project ever produced.
  3. NOTHING IS SILENTLY DROPPED. Any edge that cannot be mapped halts the
     run and is reported. There is no "best effort" mode.

Usage:
    python3 migrate.py --root path/to/project-model            # dry run
    python3 migrate.py --root path/to/project-model --apply
    python3 migrate.py --root path/to/project-model --report out.md
"""
import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import (SCHEMA_VERSION, TYPES, STATUSES, DEFAULT_STATUS,
                    RELATIONSHIP_KEYS, INACTIVE_STATUSES)
import reconcile as rec

# ---------------------------------------------------------------------------
# Legacy vocabulary mapping
# ---------------------------------------------------------------------------
# Each entry is (new_key, invert). invert=True means the legacy edge pointed
# forward in time, so it gets rewritten onto the OTHER object.

REL_MAP = {
    # --- already correct ---
    "decided_by":        ("decided_by", False),
    "refines":           ("refines", False),
    "informed_by":       ("informed_by", False),
    "supersedes":        ("supersedes", False),
    "resolves":          ("resolves", False),
    "raised_by":         ("raised_by", False),

    # --- stored inverses: flip onto the other object ---
    "decides":           ("decided_by", True),
    "superseded_by":     ("supersedes", True),
    "produced":          ("decided_by", True),
    "raises":            ("raised_by", True),
    "resolved_by":       ("resolves", True),
    "finalizes":         ("decided_by", True),
    "confirms":          ("decided_by", True),
    "corrected_by":      ("supersedes", True),
    "deferred":          ("decided_by", True),
    "rejects":           ("decided_by", True),

    # --- synonyms of decided_by ---
    "finalized_by":      ("decided_by", False),
    "deferred_by":       ("decided_by", False),

    # --- supersession under other names ---
    "corrects":          ("supersedes", False),
    "reverts":           ("supersedes", False),
    "restores":          ("supersedes", False),
    "revises_partial":   ("supersedes", False),

    # --- the untyped escape hatch, and near-misses ---
    "related":           ("informed_by", False),
    "deferred_from":     ("informed_by", False),
    "reopens":           ("informed_by", False),
    "addresses":         ("resolves", False),
    "resolves_partial":  ("resolves", False),

    # --- one edge doing two jobs; handled specially below ---
    "raised_and_deferred": ("raised_by", True),
}

# Some legacy keys mean different things depending on what they point at.
# `derived_from` is 142/142 -> DEC in the FSM pilot, so it is decided_by there,
# but the same word would mean something else pointing at a UC. `addresses` and
# `resolves` are only legal against an OBS; anything else degrades to
# informed_by rather than being forced into an invalid edge.
REL_MAP_BY_TARGET = {
    "derived_from":     {"dec": ("decided_by", False), "uc": ("motivated_by", False),
                         "*": ("informed_by", False)},
    "addresses":        {"obs": ("resolves", False), "uc": ("motivated_by", False),
                         "*": ("informed_by", False)},
    "resolves":         {"obs": ("resolves", False), "*": ("informed_by", False)},
    "resolves_partial": {"obs": ("resolves", False), "*": ("informed_by", False)},
    "resolved_by":      {"*": ("resolves", True)},
}


def map_edge(legacy_key, dst_type):
    """Return (new_key, invert) for one legacy edge, or None if unmappable."""
    if legacy_key in REL_MAP_BY_TARGET:
        table = REL_MAP_BY_TARGET[legacy_key]
        return table.get(dst_type, table["*"])
    return REL_MAP.get(legacy_key)


def _legal(key, h_type, o_type):
    from schema import RELATIONSHIPS
    src_ok, dst_ok, _ = RELATIONSHIPS[key]
    return ((src_ok == "*" or h_type in src_ok.split("|")) and
            (dst_ok == "*" or o_type in dst_ok.split("|")))


def repair(key, holder, other, h_type, o_type):
    """A mapped edge may still be illegal because the legacy vocabulary used one
    word for several relations. FSM wrote `refines` on DEC objects, which is not
    the REQ-to-REQ spec-layer sense at all — a decision that refines a
    requirement is a decision that governs it, so it becomes decided_by.

    Order: accept if already legal; try the reverse direction; then try
    decided_by when a DEC is involved; finally degrade to informed_by, which is
    always legal, and record that the precision was lost.
    """
    if _legal(key, h_type, o_type):
        return key, holder, other, h_type, o_type, False
    if _legal(key, o_type, h_type):
        return key, other, holder, o_type, h_type, False
    if o_type == "dec" and _legal("decided_by", h_type, o_type):
        return "decided_by", holder, other, h_type, o_type, False
    if h_type == "dec" and _legal("decided_by", o_type, h_type):
        return "decided_by", other, holder, o_type, h_type, False
    return "informed_by", holder, other, h_type, o_type, True

# Legacy edges whose partial/qualified nature is lost by the key mapping and
# must be preserved in the body instead of silently discarded.
QUALIFIED = {
    "resolves_partial": "partially resolves",
    "revises_partial": "partially revises",
    "raised_and_deferred": "raised, and deferred at the same time",
    "deferred_from": "deferred from",
    "reopens": "reopens",
    "corrects": "corrects",
    "reverts": "reverts",
    "restores": "restores",
    "rejects": "rejects",
}

STATUS_MAP = {
    "recorded": "recorded", "confirmed": "confirmed", "proposed": "proposed",
    "superseded": "superseded", "rejected": "rejected", "deferred": "deferred",
    "accepted": "accepted", "unapproved": "proposed",
    "under discussion": "open", "captured": "proposed", "draft": "proposed",
    "assumed": "assumed", "abandoned": "rejected", "descoped": "deferred",
    "tentative - confirm before treating as settled": "proposed",
}

TYPE_MAP = {"scn": "uc", "spec": "req", "des": "req"}


def harvest_review(root):
    """Body notes recording qualifiers the vocabulary could not express."""
    items = []
    for f in sorted(root.glob("*/*.md")):
        if f.parent.name not in TYPES:
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if "## Migration notes" not in txt:
            continue
        o = parse_object(f)
        for line in txt.split("## Migration notes", 1)[1].strip().splitlines():
            if line.strip().startswith("-"):
                items.append((o["fm"].get("id", f.stem), line.strip()[2:]))
    return items


def parse_object(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    _, fm_raw, body = text.split("---", 2)
    fm, rels = {}, defaultdict(list)
    for line in fm_raw.strip().splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "relationships":                       # nested-map form
            inner = v.strip("{} ")
            for part in re.findall(r"(\w+):\s*(\[[^\]]*\]|[^,}]+)", inner):
                key, val = part[0], part[1].strip()
                targets = ([x.strip() for x in val.strip("[]").split(",")]
                           if val.startswith("[") else [val])
                rels[key].extend(t for t in targets if t)
        elif k.startswith("rel_"):                     # flat form
            rels[k[4:]].extend(x.strip() for x in v.strip("[]").split(",") if x.strip())
        else:
            fm[k] = v
    return {"path": path, "fm": fm, "rels": dict(rels), "body": body,
            "type": path.parent.name}


def bare_id(ref):
    """DEC-952b1d4e -> 952b1d4e ; REQ-6f38-6a88-1836-0f69 -> 6f38-6a88-1836-0f69"""
    return re.sub(r"^[A-Z]+-", "", ref.strip())


def fingerprint(objs):
    ids = [o["fm"].get("id", "") for o in objs]
    has_facets = any("facets" in o["fm"] for o in objs)
    has_version = any("schema_version" in o["fm"] for o in objs)
    if has_version:
        return "v2"
    short = sum(1 for i in ids if re.fullmatch(r"[0-9a-f]{8}", i))
    long_ = sum(1 for i in ids if re.fullmatch(r"[0-9a-f-]{19}", i))
    if short > long_:
        return "legacy-flat8" + ("+facets" if has_facets else "")
    return "legacy-grouped16" + ("+facets" if has_facets else "")


def migrate(root, apply=False, report_path=None):
    files = sorted(p for p in root.glob("*/*.md") if p.parent.name != "views")
    objs = [o for o in (parse_object(p) for p in files) if o]
    if not objs:
        raise SystemExit(f"No objects found under {root}")

    fp = fingerprint(objs)
    if fp == "v2":
        print(f"{root}: already at schema_version {SCHEMA_VERSION}. Nothing to do.")
        return

    by_id = {}
    for o in objs:
        oid = o["fm"].get("id") or o["path"].stem
        o["fm"]["id"] = oid
        by_id[oid] = o

    # ---- pass 1: build the new edge set, inverting where needed -----------
    new_edges = defaultdict(lambda: defaultdict(set))   # id -> key -> {targets}
    notes = defaultdict(list)                           # id -> [prose notes]
    unmapped, dangling, degrades = [], [], []

    for o in objs:
        src = o["fm"]["id"]
        for legacy_key, targets in o["rels"].items():
            if legacy_key not in REL_MAP and legacy_key not in REL_MAP_BY_TARGET:
                unmapped.append((src, legacy_key, targets))
                continue
            for raw in targets:
                dst = bare_id(raw)
                if dst not in by_id:
                    dangling.append((src, legacy_key, raw))
                    continue
                dst_type = TYPE_MAP.get(by_id[dst]["type"], by_id[dst]["type"])
                src_type = TYPE_MAP.get(o["type"], o["type"])
                new_key, invert = map_edge(legacy_key, dst_type)

                holder, other = (dst, src) if invert else (src, dst)
                h_type, o_type = ((dst_type, src_type) if invert
                                  else (src_type, dst_type))
                new_key, holder, other, h_type, o_type, degraded = repair(
                    new_key, holder, other, h_type, o_type)

                new_edges[holder][new_key].add(other)
                if degraded:
                    degrades.append((holder, legacy_key, new_key, other))
                    notes[holder].append(
                        f"Legacy edge `{legacy_key}` -> `{other}` had no exact "
                        f"v{SCHEMA_VERSION} equivalent for a {h_type}/{o_type} pair; "
                        f"recorded as the weaker `{new_key}` rather than dropped."
                    )
                if legacy_key in QUALIFIED:
                    notes[holder].append(
                        f"Migrated from legacy edge `{legacy_key}` "
                        f"({QUALIFIED[legacy_key]} {other}); the qualifier is not "
                        f"expressible in the v{SCHEMA_VERSION} vocabulary and is "
                        f"recorded here instead."
                    )

    if unmapped:
        print("HALT — unmapped relationship keys. Nothing written.\n")
        for src, key, tg in unmapped[:20]:
            print(f"  {src}: {key} -> {tg}")
        raise SystemExit(f"{len(unmapped)} unmapped edges. Add them to REL_MAP explicitly.")

    # ---- pass 2: statuses and types --------------------------------------
    stat_changes, type_changes, bad_status = [], [], []
    for o in objs:
        t = TYPE_MAP.get(o["type"], o["type"])
        if t != o["type"]:
            type_changes.append((o["fm"]["id"], o["type"], t))
        o["new_type"] = t
        old = o["fm"].get("status", "")
        new = STATUS_MAP.get(old, old)
        if new not in STATUSES.get(t, []):
            bad_status.append((o["fm"]["id"], t, old))
            new = DEFAULT_STATUS[t]
        if new != old:
            stat_changes.append((o["fm"]["id"], old, new))
        o["new_status"] = new

    # ---- pass 3: validate every produced edge against schema constraints ---
    from schema import RELATIONSHIPS
    invalid = []
    for src, keys in new_edges.items():
        st = TYPE_MAP.get(by_id[src]["type"], by_id[src]["type"])
        for key, targets in keys.items():
            src_ok, dst_ok, _ = RELATIONSHIPS[key]
            for dst in targets:
                dt = TYPE_MAP.get(by_id[dst]["type"], by_id[dst]["type"])
                if (src_ok != "*" and st not in src_ok.split("|")) or \
                   (dst_ok != "*" and dt not in dst_ok.split("|")):
                    invalid.append((src, st, key, dst, dt))
    if invalid:
        print("HALT — edges that violate the v2 vocabulary constraints. Nothing written.\n")
        for s, st, k, d, dt in invalid[:25]:
            print(f"  {st}:{s} --{k}--> {dt}:{d}   (allowed: "
                  f"{RELATIONSHIPS[k][0]} -> {RELATIONSHIPS[k][1]})")
        raise SystemExit(f"{len(invalid)} invalid edges. Fix the mapping, not the schema.")

    # ---- report -----------------------------------------------------------
    edge_in = sum(len(v) for o in objs for v in o["rels"].values())
    edge_out = sum(len(t) for d in new_edges.values() for t in d.values())
    lines = [
        f"# Migration report — {root}", "",
        f"Detected schema: **{fp}** -> v{SCHEMA_VERSION}", "",
        f"- objects: {len(objs)}",
        f"- legacy edges read: {edge_in}",
        f"- v{SCHEMA_VERSION} edges written: {edge_out}  "
        f"({edge_in - edge_out} collapsed as stored inverses or duplicates)",
        f"- legacy relationship keys: {len(set(k for o in objs for k in o['rels']))} -> "
        f"{len(set(k for d in new_edges.values() for k in d))}",
        f"- status changes: {len(stat_changes)}",
        f"- type renames: {len(type_changes)}",
        f"- dangling targets dropped: {len(dangling)}",
        f"- edges degraded to informed_by (precision lost, noted in body): {len(degrades)}",
        f"- qualifier notes preserved in bodies: {sum(len(v) for v in notes.values())}",
        "",
    ]
    if degrades:
        lines += ["## Degraded edges", ""]
        lines += [f"- `{h}`: legacy `{lk}` -> `{nk}` (target `{o}`)" for h, lk, nk, o in degrades[:40]] + [""]
    if dangling:
        lines += ["## Dangling targets (pointed at nothing, dropped)", ""]
        lines += [f"- `{s}` had `{k} -> {t}`" for s, k, t in dangling[:40]] + [""]
    if bad_status:
        lines += ["## Statuses reset to type default (no valid mapping)", ""]
        lines += [f"- `{i}` ({t}): `{s}`" for i, t, s in bad_status] + [""]
    if type_changes:
        lines += ["## Type renames", ""]
        lines += [f"- `{i}`: {a} -> {b}" for i, a, b in type_changes] + [""]
    report = "\n".join(lines)
    print(report)
    if report_path:
        Path(report_path).write_text(report, encoding="utf-8")

    if not apply:
        print("Dry run. Re-run with --apply to write. A pre-migration copy is made first.")
        return

    # ---- write ------------------------------------------------------------
    pre_snapshot = {o["fm"]["id"]: o for o in objs}
    backup = root.parent / f"{root.name}.pre-v{SCHEMA_VERSION}"
    if backup.exists():
        # After a deliberate rollback the backup and the model are identical, so
        # retrying is safe. Any other case means an earlier migration is still
        # unreviewed, and clobbering its backup would destroy the only way back.
        import filecmp
        cmp = filecmp.dircmp(str(root), str(backup))
        identical = not (cmp.left_only or cmp.right_only or cmp.diff_files)
        if not identical:
            raise SystemExit(
                f"{backup} exists and differs from the current model.\n"
                f"An earlier migration has not been reviewed. Roll it back "
                f"(--rollback) or move the backup aside before retrying.")
        print(f"Reusing existing backup at {backup} (identical to current model).")
    else:
        shutil.copytree(root, backup)

    for o in objs:
        oid = o["fm"]["id"]
        fm = ["---", f"schema_version: {SCHEMA_VERSION}", f"id: {oid}"]
        if o["fm"].get("alias"):
            fm.append(f"alias: {o['fm']['alias']}")
        fm += [f"type: {o['new_type']}", f"status: {o['new_status']}"]
        origin = o["fm"].get("origin", "")
        if origin and not origin.startswith("unspecified"):
            fm.append(f"origin: {origin}")
        else:
            fm.append("origin: unrecorded (pre-v2, not captured at creation)")
        if o["fm"].get("created"):
            fm.append(f"created: {o['fm']['created']}")
        if o["fm"].get("facets"):
            fm.append(f"facets: {o['fm']['facets']}")
        if o["fm"].get("certainty"):
            fm.append(f"certainty: {o['fm']['certainty']}")
        for key in sorted(new_edges.get(oid, {})):
            fm.append(f"rel_{key}: [{', '.join(sorted(new_edges[oid][key]))}]")
        import hashlib
        SUMMED = ["schema_version", "id", "alias", "type", "status", "origin",
                  "created", "certainty", "facets"]
        flat = {}
        for line in fm[1:]:
            k, v = line.split(":", 1)
            flat[k.strip()] = v.strip()
        parts = [f"{k}={flat.get(k, '')}" for k in SUMMED]
        parts += [f"rel_{k}={','.join(sorted(new_edges.get(oid, {}).get(k, [])))}"
                  for k in sorted(new_edges.get(oid, {}))]
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]
        fm.append(f"generator: migrate.py/v{SCHEMA_VERSION}")
        fm.append(f"checksum: {digest}")
        fm.append("---")

        body = o["body"]
        if notes[oid]:
            body = body.rstrip() + "\n\n## Migration notes\n\n" + \
                   "\n".join(f"- {n}" for n in notes[oid]) + "\n"

        dest = root / o["new_type"] / f"{oid}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("\n".join(fm) + body.rstrip() + "\n", encoding="utf-8")
        if dest != o["path"]:
            o["path"].unlink()

    for stale in root.glob("*/"):
        if stale.is_dir() and stale.name not in TYPES and stale.name != "views":
            if not any(stale.iterdir()):
                stale.rmdir()

    # Regenerate through model.py so there is exactly one index generator.
    import model
    model.regenerate(root)

    # ---- verification: reconcile, then validate, then roll back on failure --
    post = {}
    for p2 in sorted(root.glob("*/*.md")):
        if p2.parent.name not in TYPES:
            continue
        o2 = parse_object(p2)
        if o2:
            post[o2["fm"].get("id", p2.stem)] = o2

    ok, lines = rec.reconcile(pre_snapshot, post, new_edges, degrades, dangling)
    verdict = "\n".join(lines)
    print("\n" + verdict)
    if report_path:
        Path(report_path).write_text(report + "\n" + verdict + "\n", encoding="utf-8")

    check_ok = True
    try:
        import argparse as _ap
        ns = _ap.Namespace(strict=False, limit=5)
        check_ok = (model.cmd_check(root, ns) == 0)
    except SystemExit:
        check_ok = False

    if not (ok and check_ok):
        print("\nVerification FAILED — writing analysis, then rolling back.")
        cause = ("reconciliation failed" if not ok
                 else "post-migration validation (model.py check) failed")
        ap_ = rec.write_analysis(
            root, backup, cause, "", report, lines,
            unmapped, degrades, dangling, bad_status, harvest_review(root))
        rec.rollback(root, backup)
        print(f"\nAnalysis written to {ap_}")
        raise SystemExit("Migration reverted. The model is exactly as it was. "
                         "Read the analysis, resolve the listed tasks, then retry.")

    print(f"\nApplied and verified. Pre-migration copy at {backup}")
    print(f"To undo:  python3 migrate.py --root {root} --rollback")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", default=None)
    ap.add_argument("--review", action="store_true",
                    help="list objects carrying migration notes — the review queue")
    ap.add_argument("--reason", default="",
                    help="why you are rolling back; recorded in the analysis")
    ap.add_argument("--rollback", action="store_true",
                    help="restore the pre-migration copy and discard the migration")
    a = ap.parse_args()
    if a.review:
        n = 0
        for f in sorted(a.root.glob("*/*.md")):
            if f.parent.name not in TYPES:
                continue
            txt = f.read_text(encoding="utf-8")
            if "## Migration notes" not in txt:
                continue
            n += 1
            o = parse_object(f)
            alias = o["fm"].get("alias", "")
            title = next((l[2:] for l in o["body"].splitlines()
                          if l.startswith("# ")), "")
            print(f"\n{o['fm'].get('type','?').upper()} {o['fm']['id']}"
                  + (f" [{alias}]" if alias else ""))
            print(f"  {title[:90]}")
            for line in txt.split("## Migration notes", 1)[1].strip().splitlines():
                if line.strip().startswith("-"):
                    print(f"  {line.strip()}")
        print(f"\n{n} objects need semantic review. The tool proved nothing was "
              f"lost; it cannot prove the mapping preserved your meaning.")
    elif a.rollback:
        backup = a.root.parent / f"{a.root.name}.pre-v{SCHEMA_VERSION}"
        review = harvest_review(a.root) if a.root.exists() else []
        prior = ""
        for cand in (Path("migration.md"), a.root.parent / "migration.md"):
            if cand.exists():
                prior = cand.read_text(encoding="utf-8")
                break
        ap_ = rec.write_analysis(
            a.root, backup, "requested by the user after review",
            a.reason, prior or "(no migration report was kept)", [],
            [], [], [], [], review)
        rec.rollback(a.root, backup)
        print(f"Analysis written to {ap_}")
        print("The model is back on the previous schema; this skill cannot "
              "write to it until a migration succeeds.")
    else:
        migrate(a.root, a.apply, a.report)
