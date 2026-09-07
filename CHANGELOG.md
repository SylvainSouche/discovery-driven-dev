# Changelog

Two version numbers, deliberately. `version` is the skill; `schema_version` is
the on-disk object format. A skill change that does not alter the format does
not trigger a migration.

## 2.3.0 — schema_version 2

- `trace.py open` became the full outstanding-work agenda: ten groups derived
  from status, including discipline breaches (confirmed with no decision
  behind it, stale implementations).
- `references/outstanding.md`: no TASK or BUG type, and the boundary for where
  a defect belongs. Both pilots kept hand-maintained "still open" lists in
  prose while every item was already representable as an object.

## 2.2.0 — schema_version 2

- `coverage.py`: motivation, verification and realization axes, with explicit
  rules for what is *not* owed coverage.
- Motivation inherits down the refinement chain, so a leaf sharpening a
  motivated requirement is not flagged separately.

## 2.1.0 — schema_version 2

- `model.py supersede`: supersession is total. Absorb into one replacement, or
  split across several. Requires a DEC; sets the old object superseded;
  follows supersession when inheriting refinement parents.
- New checks: `refines-dead`, `live-superseded`, `orphan-superseded`. These
  found 14 pre-existing defects across the two pilot projects.

## 2.0.0 — schema_version 2

Rebuilt after two real projects (a BSD-make build system, an FSM DSL library)
produced 425 objects between them.

**Removed**
- `SPEC` and `DES` types. The specification layer is depth in the refinement
  DAG: 56 `refines` edges against 0 SPEC objects across both pilots.
- Stored inverse relationships. One pilot stored both directions and they
  disagreed — 82 `decided_by` against 69 `decides`.
- The frontmatter layout from the documentation, which was the affordance that
  let 436 objects be hand-written and look correct.

**Added**
- `model.py` as the single write path, with schema-backed rejection, alias
  uniqueness, and a frontmatter checksum that detects hand editing.
- `IMPL` and `TEST` types; `@impl <id>` markers reconciled by `check_impl.py`.
- `migrate.py` with fingerprinting, reconciliation, automatic verification and
  self-reverting rollback; every rollback writes an analysis document.
- Mandatory `--origin`. It was optional in v1 and 163 of one pilot's 249
  objects carried a placeholder.
- Lazy-loaded references. `SKILL.md` went from ~4,345 to ~1,270 tokens.

**Changed**
- `SCN` renamed to `UC`. The type fired zero times across 425 objects while
  both projects produced use-case material outside the model.
- Relationship vocabulary fixed at nine keys and enforced at write time. The
  pilots used 6 and 24 respectively.

## 1.x — unversioned

Never carried a version number in its objects, which is why v2's migration
fingerprints legacy models rather than reading a marker.
