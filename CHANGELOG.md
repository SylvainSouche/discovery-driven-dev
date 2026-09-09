# Changelog

Two version numbers, deliberately. `version` is the skill; `schema_version` is
the on-disk object format. A skill change that does not alter the format does
not trigger a migration.

## 2.6.0 — schema_version 2

- New `scripts/bundle.py`, called automatically and unconditionally at the
  end of `regenerate()` — after every `new`/`link`/`status`/`amend`/
  `supersede`, with no agent judgment involved. The whole premise of this
  skill is that project-model/ is durable; that's only true if the
  filesystem underneath it is. A claude.ai web-chat sandbox has no
  persistence contract, and a design chat's sandbox reset proved it: 16
  objects existed only inside it and were gone the moment it reset, because
  nothing had exported a copy first.
- Writes two copies, and they are not equivalent. `project-model-backup.
  tar.gz` next to `project-model/` is convenient but shares its sandbox —
  a full reset destroys this copy too. The one that actually matters is a
  second copy in `/mnt/user-data/outputs/`, written only if that directory
  exists: on Claude's code-execution environment that path is
  conventionally backed by storage outside the ephemeral compute sandbox,
  so it can survive exactly the failure that already happened once. On any
  other environment (a real filesystem, Claude Code, Cowork with a
  connected folder) the directory won't exist and this half is a silent
  no-op — project-model/ already lives outside the sandbox there and needs
  no rescuing.
- A best-effort export must never break the write it rides on: `bundle()`
  catches a failed target internally, and `regenerate()`'s call site
  catches everything else too, so a bundling bug can never turn into a
  failed `model.py new`.
- Each bundle carries `MANIFEST.json`: schema/skill version, object/edge
  counts, and a checksum-of-checksums (sha256 over every object's own
  stamped checksum) so two bundles' states can be compared at a glance
  without re-verifying every file.

## 2.5.0 — schema_version 2

- New `amend` subcommand: `model.py amend --id X --field alias|origin|facets|
  certainty --value V --reason "..."` changes a labeling field on an
  existing object in place, without supersession. Prompted by a real case:
  a project got renamed, and the old name was baked into several objects'
  `origin` fields — hand-editing would be flagged tampered, and superseding
  each one just to fix a name would require a DEC per object to authorize a
  change that asserts nothing new about the world.
- Every amendment appends a terse `"YYYY-MM-DD: reason"` entry to a new
  `amended` field — no before-value, just what changed and why, briefly.
  That field carries its own checksum (`amended_checksum`), independent of
  the object's existing one: hand-editing the log is now caught by `check`
  (`LOG-TAMPERED`) exactly as hand-editing anything else already was.
- Deliberately excludes `id` (permanent — every edge stores it), `type`
  (would require moving the file to a different directory; a
  reclassification, not a label fix), and `status` (already has its own
  validated command).
- `amended`/`amended_checksum` sit outside `SUMMED` on purpose: adding them
  to the object's own checksum formula would have invalidated every
  existing object's checksum the moment this shipped, forcing a schema
  migration for a feature that doesn't touch the object format. Two
  independent checksums instead of one migration.

## 2.4.0 — schema_version 2

- `check --strict` gained a citation/edge-parity rule: if an object's body
  names another object by its `TYPE-alias` shorthand (e.g. `REQ-foo-bar`),
  a matching edge must exist somewhere in its own frontmatter. Found by
  auditing a 306-object field model: 0% of REQs were unlinked, but 89% of
  DECs and 68% of OBSs cited prior context in prose with no edge recording
  it — reachable by a human reading the file, invisible to `trace.py`
  walking the graph. Deliberately narrow: an object that cites nothing is
  untouched, and the check flags the gap rather than guessing which key
  (`informed_by`, `resolves`, `raised_by`, ...) to write.
- Fixed `model.py`'s own `SKILL_VERSION` constant, which had been stuck at
  `2.1.0` through the 2.2.0 and 2.3.0 releases. Every object written by
  those two versions was stamped `generator: model.py/2.1.0` regardless of
  what actually wrote it — a small, ironic instance of the exact drift this
  skill exists to catch, found while auditing a downstream model rather
  than by anything in this repo's own test suite.

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
