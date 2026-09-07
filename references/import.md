# Importing work done elsewhere

Load this when reviewing code, a contract, or a specification produced outside
the model — by another tool, another model, or an earlier phase of the project.

## The operation

Something exists that the model didn't produce. Establish what it says, how it
relates to what's recorded, and what should be added — without laundering
implementation accidents into recorded intent.

## The safety property

**Import never creates a REQ.**

The model's core discipline is that nothing becomes a requirement except
through a DEC. An importer that promoted observed behaviour straight into
requirements would turn accidents into recorded intent, permanently, with a
provenance field claiming it came from the user.

So import emits **OBS** objects describing what the artifact does. Promotion to
requirement goes through the normal decision path, with the user in it.

## Classification

For each behaviour found:

**Covered and consistent** — the model already says this. Emit an `implements`
edge if it's code; otherwise say nothing. Batch these silently.

**Covered but contradicts** — artifact and model disagree. Surface it. Either
the code is wrong or the requirement was, and only a DEC can say which. Never
resolve it by editing the requirement.

**Not covered** — splits three ways, and the split is the actual work:
- a deliberate feature nobody wrote down → OBS, then propose a DEC
- an implementation detail legitimately below the requirement line → note and
  move on; not everything deserves an object
- an accident → OBS, flagged as such

## Search before claiming anything is new

This is mandatory, and it is the step most likely to be skipped.

A pilot's API contract marked a design point as newly invented — *modelled as
void\* for one shared accessor family rather than duplicating it per kind* —
while a confirmed requirement saying exactly that, alias
`field-accessors-shared-voidptr-family`, already existed. The same paragraph
correctly cited three other aliases, so the model was in hand at that moment.
Nothing grepped for the fourth.

That is worse than a missed link. If you are measuring specification quality by
counting where an implementer had to invent something, false positives corrupt
the measurement.

```bash
python3 scripts/trace.py find "<terms>" --deep
```

Record the negative result in the OBS body. "Searched for X, Y, Z; nothing
matched" can be audited later. Unrecorded recall cannot.

## Attention budget

An 84KB specification or a 14KB header contains hundreds of assertions. If
import interrogates every one, it will be abandoned within ten minutes.

Batch the clean matches and report them as a count. Spend the user's attention
only on contradictions and genuine gaps. A run that surfaces eight items from a
40-declaration header is useful; one that surfaces two hundred is noise.

## The reverse direction

The same pass answers the other question free: what does the model require that
nothing implements?

```bash
python3 scripts/check_impl.py --src . --strict
```

## Benchmarking multiple implementations

When one contract is handed to several independent implementers, divergence
tells you about the implementer. **Systematic divergence at the same point
across independent implementers tells you the specification was
underdetermined there** — which is a finding about the model, and belongs in it
as an OBS against the requirement in question.
