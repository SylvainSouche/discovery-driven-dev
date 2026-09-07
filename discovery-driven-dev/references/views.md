# Generated documents and contracts

Load this when producing anything from the model: a specification document, a
user manual, an API contract, a report.

## Why this exists

Views drift, silently, and both pilots demonstrate it.

One project's output directory contains `05-directory-layout.md` and
`10-directory-layout.md`. The first shares 63 lines with the second and has 118
lines nobody else has. It was superseded by a five-document split and **nothing
in it says so**. Objects cannot be silently orphaned; views can, and that one
was.

The same project's overview announces *two deliberate divergences* and then
lists four.

A second project's API header claims every declaration carries its requirement
IDs. It carries none.

All three are the same failure: hand-written derived artifacts, asserting a
relationship to the model that nothing verifies.

## Views are generated, not transcribed

If a document is written by reading objects and typing prose, it is a fork of
the model that begins rotting immediately. Generate it, and regenerate it.

Every generated view carries a header naming what it came from:

```
Generated from project-model/ · schema_version 2 · 176 objects
Sources: 32 confirmed REQ, 6 DEC, 3 CON
Generated 2026-08-29. Regenerate rather than edit.
```

## Citing aliases is fine; unchecked aliases are not

Documents should cite aliases — `REQ-prereqs-mandatory-even-empty-req` is
readable and `6f38-6a8a-f6ee-940d` is not. But aliases are renamable by design,
so a document full of them is a document full of links nothing validates.

`build_view.py --check` re-reads every alias cited in a generated document and
reports any that no longer resolve, or that resolve to an object no longer
`confirmed`. That second case is the interesting one: a document asserting
something the model has since superseded is worse than a broken link, because
it still reads as true.

## Contracts handed to an external implementer

A frozen API surface, generated so someone else can build against it, is a view
with two extra obligations.

**Tag every declaration with the requirement ids behind it.** Not as
decoration: when the implementer produces something surprising, the first
question is which requirement they were working from. An untagged contract
cannot answer it.

**Every gap becomes an object, not a comment.** Generating a contract forces
decisions the model left open — parameter order, struct layout, how an abstract
notion is concretely represented. In a pilot, eight such decisions were marked
`[fixed here]` in source comments. One of them was not a gap at all; a
confirmed requirement already said exactly that. The rest were real, and they
are still sitting in a header instead of in the model.

Each gap becomes an **AI** object — introduced by Claude, unapproved, never a
requirement until a DEC accepts it. Then the contract is traceable and the
list of gaps is itself a measurement of specification completeness.

**Search before recording a gap.** See `import.md`. A false gap corrupts that
measurement in the flattering direction.

## Statuses matter in generated documents

If a document presents something as settled, the underlying object must be
`confirmed`. A pilot's overview presents four negative requirements as
*rejected outright, not deferred* — while all four sit at `proposed` in the
model. The document asserts a settledness nobody ever recorded.

Generate from status. Do not narrate it.
