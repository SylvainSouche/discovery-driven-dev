# Running a migration

Load this when `model.py check` reports a `schema_version` mismatch, or when
the skill version has moved ahead of a model.

## Read the report. Do not re-derive it.

`migrate.py` proves conservation mechanically: object counts, edge accounting
that must sum, every legacy pair still having a relation, bodies compared byte
for byte, and `model.py check` run automatically afterwards. If any of that
fails it reverts itself before you see it.

So there is nothing useful to add by reading objects and forming an impression.
An impression is weaker evidence than the proof already in the report, and
narrating one over the top of a verified result is how a checked thing becomes
an unchecked thing. **Quote the report's verdict; do not recompute it.**

What genuinely needs a human is the one thing the tool says outright it cannot
do: whether the mapping preserved the *meaning*.

## The sequence

**1. Dry run, always first.**

```bash
python3 scripts/migrate.py --root project-model
```

Nothing is written. Read the counts, the degraded edges, the status resets and
any type renames. If it halts on an unmapped relationship key, stop — that key
needs a deliberate mapping decision, not a workaround.

**2. Apply.**

```bash
python3 scripts/migrate.py --root project-model --apply --report migration.md
```

This backs up to `project-model.pre-v<N>` first, migrates, reconciles,
validates, and reverts itself if anything fails.

**3. Report the verdict plainly.** Objects before and after, the edge
accounting line, and `Reconciliation: PASS` or `FAIL`. If FAIL, the model has
already been restored — say so, and say what failed.

**4. Work the review queue.**

```bash
python3 scripts/migrate.py --root project-model --review
```

## What the review queue is

Legacy vocabularies carried qualifiers the fixed nine keys cannot express. The
migration preserved each one as a note in the object's body rather than
dropping it, and this queue lists them.

Real examples from a pilot:

- `raised_and_deferred` — one edge doing two jobs. It became `raised_by`, and
  the deferral is now only prose. Should that object's **status** be `deferred`?
- `resolves_partial` — the observation is not fully closed. Is it still open?
- `rejects` — an AI proposal a decision turned down. Is its status `rejected`?
- `deferred_from` — became `informed_by`, which is weaker and directionally
  vaguer.

Each is a question about status, not about edges. The edges are proven correct;
the statuses may now understate or overstate how settled something is.

**Batch these.** Twenty-three items in one pilot, four in the other. Present
them grouped by the kind of question, not one at a time, and propose the status
change you think is right so the user is confirming rather than deciding from
scratch. Interrogating item by item is how a review gets abandoned.

## Assessing risk honestly

Risk is proportional to the review queue and the degraded-edge count, both of
which are in the report. Do not editorialise beyond them.

| Signal | Means |
|---|---|
| `Reconciliation: PASS`, no notes | Nothing to review. Say so and move on. |
| Notes present | Statuses may need adjusting. Bounded, mechanical work. |
| Degraded edges | A relation survived in weaker form. Read each one. |
| `origin: unrecorded (pre-v2)` | **Unrecoverable.** Not a migration defect — that provenance was never captured. Do not offer to reconstruct it; do not let anyone guess it later. |

## Every rollback produces an analysis

Whether the tool reverted itself or the user asked for it, rollback writes
`<model>-migration-analysis-NN.md` **beside** the model — never inside it,
because the restore replaces the model directory wholesale and would destroy
anything written within. It is written before the restore, since the evidence
only exists in the migrated state.

It records what was attempted, the reconciliation result, blocking issues
(unmapped keys, dangling targets), issues needing a decision (degraded edges,
reset statuses, qualifier notes), and a numbered task list for making a second
attempt possible. Files are numbered, so a second failed attempt never
overwrites the record of the first.

Pass `--reason` on a deliberate rollback; it goes into the document, and it is
usually the most useful line in it.

After the user has worked the task list, they request a new attempt. The
sequence is dry run, apply, reconcile — the same as the first time.

## Rollback is a real state, not a neutral undo

```bash
python3 scripts/migrate.py --root project-model --rollback \
    --reason "deferral state was lost; deferred_from needs to be a real key"
```

This restores the pre-migration copy exactly. It copies before deleting, so a
crash mid-rollback leaves both copies and never neither.

But afterwards the model is back on the old schema, and **the current skill
cannot write to it** — `model.py` will reject it and `trace.py` will not read
its relationships. Rollback is correct when the migration was wrong. It is not
a way to defer the decision. Say this before doing it, not after.

Propose rollback when reconciliation failed and was not auto-reverted, when the
review queue reveals the mapping genuinely changed meaning, or when the user
asks. Not merely because the queue is long.

## The backup

Never deleted automatically, by design. A second migration refuses to run while
a *differing* backup exists, because that means an earlier migration was never
reviewed and clobbering its backup would destroy the only way back. After a
rollback the backup and model are identical, so retrying is allowed.

Only propose deleting it once the review queue is worked and the user has said
the model is right:

```bash
rm -rf project-model.pre-v<N>
```

Ask before running that, every time, and name the directory in full. It is the
only irreversible command in this skill.
