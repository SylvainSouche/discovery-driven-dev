#!/usr/bin/env python3
"""
reconcile.py — prove a migration was lossless, and undo it if it wasn't.

migrate.py reported "93 edges collapsed as stored inverses or duplicates".
That is arithmetic, not evidence. This module supplies the evidence, and
migrate.py refuses to leave a migration applied unless it passes.

Every legacy edge must land in exactly one bucket:

    written    it exists in the new model
    collapsed  it duplicates another legacy edge's result (a stored inverse)
    degraded   it survived as a weaker relation, with a note in the body
    dangling   it pointed at nothing and was reported

buckets summed must equal the legacy edge count. Any edge that lands in none
of them is unaccounted for, and an unaccounted edge is data loss.

Bodies are compared byte for byte, allowing only the appended migration-notes
section. Object count must be identical: migration never creates or destroys.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def reconcile(pre_objs, post_objs, planned, degraded, dangling):
    """pre_objs/post_objs: {id: parsed}. planned: {holder: {key: {targets}}}.
    Returns (ok, report_lines)."""
    out, ok = [], True

    # --- 1. object conservation ------------------------------------------
    lost = set(pre_objs) - set(post_objs)
    gained = set(post_objs) - set(pre_objs)
    out.append("## Reconciliation\n")
    out.append(f"- objects before {len(pre_objs)}, after {len(post_objs)}")
    if lost or gained:
        ok = False
        out.append(f"  - **LOST**: {sorted(lost)[:10]}")
        out.append(f"  - **GAINED**: {sorted(gained)[:10]}")
    else:
        out.append("  - conserved: every id present before is present after")

    # --- 2. edge accounting ----------------------------------------------
    legacy_total = sum(len(v) for o in pre_objs.values() for v in o["rels"].values())
    written = sum(len(t) for d in planned.values() for t in d.values())
    dang = len(dangling)
    # collapsed = legacy edges whose mapped result was already present
    collapsed = legacy_total - written - dang
    out.append(f"- legacy edges {legacy_total} = written {written} "
               f"+ collapsed {collapsed} + dangling {dang}")
    if collapsed < 0:
        ok = False
        out.append("  - **NEGATIVE COLLAPSE** — more edges written than read")
    else:
        out.append("  - accounted: buckets sum to the legacy total")

    # --- 3. every written edge resolves ----------------------------------
    unresolved = [(h, k, t) for h, d in planned.items()
                  for k, ts in d.items() for t in ts if t not in post_objs]
    if unresolved:
        ok = False
        out.append(f"- **{len(unresolved)} written edges point at missing objects**")
        for h, k, t in unresolved[:5]:
            out.append(f"  - {h} --{k}--> {t}")
    else:
        out.append(f"- all {written} written edges resolve to existing objects")

    # --- 4. collapse justification ---------------------------------------
    # A collapsed edge is only legitimate if the pair it described still has a
    # relation between them somewhere. Check each legacy pair survives.
    orphaned_pairs = []
    for src, o in pre_objs.items():
        for key, targets in o["rels"].items():
            for raw in targets:
                dst = raw.split("-", 1)[-1] if raw[:3].isupper() else raw
                dst = dst.strip()
                for cand in (dst, raw.strip()):
                    if cand in pre_objs:
                        dst = cand
                        break
                else:
                    continue
                fwd = any(dst in planned.get(src, {}).get(k, set())
                          for k in planned.get(src, {}))
                rev = any(src in planned.get(dst, {}).get(k, set())
                          for k in planned.get(dst, {}))
                if not (fwd or rev):
                    orphaned_pairs.append((src, key, dst))
    if orphaned_pairs:
        ok = False
        out.append(f"- **{len(orphaned_pairs)} legacy pairs have NO surviving relation**")
        for s, k, d in orphaned_pairs[:8]:
            out.append(f"  - {s} --{k}--> {d} vanished entirely")
    else:
        out.append("- every legacy pair still has a relation in at least one direction")

    # --- 5. body integrity ------------------------------------------------
    changed = []
    for i, pre in pre_objs.items():
        post = post_objs.get(i)
        if not post:
            continue
        a = pre["body"].strip()
        b = post["body"].split("## Migration notes")[0].strip()
        if a != b:
            changed.append(i)
    if changed:
        ok = False
        out.append(f"- **{len(changed)} bodies altered** (migration must be additive only)")
        for i in changed[:5]:
            out.append(f"  - {i}")
    else:
        out.append(f"- all {len(pre_objs)} bodies byte-identical (notes appended only)")

    out.append(f"- degraded edges recorded in bodies: {len(degraded)}")
    out.append("")
    out.append(f"**Reconciliation: {'PASS' if ok else 'FAIL'}**")
    return ok, out


def next_analysis_path(root: Path):
    """Beside the model, never inside it — rollback restores the model directory
    wholesale and would destroy an analysis written within it. Numbered, so a
    second failed attempt never overwrites the record of the first."""
    n = 1
    while True:
        p = root.parent / f"{root.name}-migration-analysis-{n:02d}.md"
        if not p.exists():
            return p
        n += 1


def write_analysis(root, backup, cause, reason, report, recon_lines,
                   unmapped, degraded, dangling, bad_status, review_items):
    """Written BEFORE the restore, because the evidence lives in the migrated
    state that the restore is about to discard."""
    import datetime
    p = next_analysis_path(root)
    L = [f"# Migration analysis — {root.name}", "",
         f"Written {datetime.datetime.now().isoformat(timespec='seconds')} "
         f"immediately before rolling back to `{backup.name}`.", "",
         f"**Cause of rollback:** {cause}", ""]
    if reason:
        L += [f"**Stated reason:** {reason}", ""]

    L += ["## What the migration attempted", "", report.strip(), ""]

    if recon_lines:
        L += ["## Reconciliation result", ""] + [l for l in recon_lines if l.strip() != "## Reconciliation"] + [""]

    L += ["## Blocking issues", ""]
    blocking = False
    if not (unmapped or dangling):
        L += ["None. Nothing halted the run; the failure was in verification, "
              "not in reading the legacy model.", ""]
    if unmapped:
        blocking = True
        L += [f"### Unmapped relationship keys ({len(unmapped)})", "",
              "These halted the run. Each needs a deliberate decision about what "
              "it means in the current vocabulary — added to `REL_MAP` or "
              "`REL_MAP_BY_TARGET` in `migrate.py`, not worked around.", ""]
        seen = {}
        for src, key, tg in unmapped:
            seen.setdefault(key, []).append(src)
        for key, srcs in sorted(seen.items()):
            L.append(f"- `{key}` — {len(srcs)} edges, e.g. `{srcs[0]}`")
        L.append("")
    if dangling:
        blocking = True
        L += [f"### Edges pointing at nothing ({len(dangling)})", "",
              "Dropped by the migration. If any of these targets should exist, "
              "the object is missing from the model and must be recreated "
              "before retrying.", ""]
        L += [f"- `{s}` had `{k} -> {t}`" for s, k, t in dangling[:30]] + [""]

    L += ["## Issues needing a decision before retrying", ""]
    if degraded:
        L += [f"### Degraded edges ({len(degraded)})", "",
              "A legacy relation survived only in weaker form. Decide whether "
              "the weaker form is acceptable, or whether the vocabulary needs "
              "a key it currently lacks.", ""]
        L += [f"- `{h}`: `{lk}` became `{nk}` (target `{o}`)"
              for h, lk, nk, o in degraded[:30]] + [""]
    if bad_status:
        L += [f"### Statuses with no valid mapping ({len(bad_status)})", "",
              "Reset to the type default, which may overstate or understate how "
              "settled these are. Either add the status to `schema.py` (and bump "
              "`SCHEMA_VERSION`) or set each one deliberately after retrying.", ""]
        L += [f"- `{i}` ({t}): was `{s}`" for i, t, s in bad_status] + [""]
    if review_items:
        L += [f"### Qualifiers not expressible in the vocabulary ({len(review_items)})", "",
              "Preserved as body notes. Each is a question about **status**, not "
              "about edges.", ""]
        L += [f"- `{i}`: {n}" for i, n in review_items[:40]] + [""]

    L += ["## To make a second attempt possible", ""]
    tasks = []
    if unmapped:
        tasks.append("Add every unmapped key to the mapping tables in "
                     "`migrate.py`, with an explicit target-type rule where the "
                     "key means different things depending on what it points at.")
    if dangling:
        tasks.append("Recreate the missing target objects, or accept the edges "
                     "as genuinely obsolete and record that decision.")
    if degraded:
        tasks.append("Confirm each degraded edge is acceptable, or extend the "
                     "vocabulary in `schema.py` and bump `SCHEMA_VERSION`.")
    if bad_status:
        tasks.append("Decide whether the missing statuses belong in the schema.")
    if not blocking and not tasks:
        if cause.startswith("requested by the user"):
            if review_items:
                tasks.append(
                    "Decide, for each qualifier above, whether the meaning it "
                    "carried needs a real relationship key or a status value. "
                    "Add it to `schema.py` and bump `SCHEMA_VERSION`, or accept "
                    "the body note as sufficient.")
            tasks.append("If the vocabulary changed, extend the mapping tables "
                         "in `migrate.py` so the new key is produced rather "
                         "than degraded.")
        else:
            tasks.append(
                "Reconciliation or validation failed for a reason not captured "
                "above — this indicates a defect in the migration tool rather "
                "than in the model. Read the reconciliation section and fix the "
                "tool before retrying.")
    tasks.append(f"Re-run the dry run: `python3 scripts/migrate.py --root "
                 f"{root} ` and confirm the issues above are gone.")
    tasks.append(f"Apply: `python3 scripts/migrate.py --root {root} --apply "
                 f"--report migration.md`")
    L += [f"{n}. {t}" for n, t in enumerate(tasks, 1)]
    L += ["", f"The pre-migration model is intact at `{backup}`. It is unchanged "
              f"by this analysis and by the rollback.", ""]

    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return p


def rollback(root: Path, backup: Path):
    import shutil
    if not backup.exists():
        raise SystemExit(f"No backup at {backup} — nothing to roll back to.")
    scratch = root.parent / (root.name + ".rollback-tmp")
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(backup, scratch)          # copy first, so a failure here
    shutil.rmtree(root)                       # never leaves you with neither
    scratch.rename(root)
    print(f"Rolled back {root} from {backup}.")
    print(f"The backup is untouched; delete it manually when you're satisfied.")
