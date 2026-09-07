# Implementation linkage

Load this when connecting code to the model, or tracking what has been built.

## Why this exists

A pilot's `README.md` states that its API header tags every declaration with
the requirement IDs it implements. The header repeats the claim in its own
comment. It contains 37 function declarations, 9 type definitions, and **zero
requirement IDs**.

Nobody noticed for weeks, because nothing checked. Meanwhile the same project's
manual cites 124 IDs and its specification cites 384 — the discipline held
perfectly in prose and evaporated the moment the artifact was code.

That is the failure mode here: not drift between two records that both exist,
but an artifact that *claims* traceability and has none. No instruction
prevents it. A two-line grep catches it immediately.

## How code links to the model

Two halves, deliberately indirect.

**In the code**, a marker carrying a canonical id:

```c
/* @impl 9730-6a92-f9b5-487a */
```

```make
# @impl 9730-6a92-f9b5-487a
```

Syntax-agnostic, so one grep works everywhere.

**In the model**, an IMPL object recording what that code realizes and why.

The indirection earns its keep. If the comment named the requirement directly,
every change in traceability — one block turning out to satisfy a second
requirement, a requirement being superseded — would mean editing source files
to record a modelling fact. With the mapping in the model, source changes only
when code changes.

### The marker carries the id, never the alias

Aliases are renamable by design. Source comments are the most expensive place
in a project to have to rename anything. Ugly in the source; correct forever.

### IMPL objects store no file paths

Locations are derived by grepping at run time. Files can move, functions can be
renamed, code can be split across translation units, and nothing in the model
goes stale — because the model never claimed to know where anything was.

This removes an entire class of drift by not recording the thing that rots.

## Where implementation attaches

To **leaves of the refinement DAG** — requirements nothing refines further, so
the most specific claims the model makes. `model.py leaves`.

Attaching to a root instead is a smell: it usually means the requirement is
still too broad to implement, and the refinement that would make it concrete
hasn't been written.

## The three checks

```bash
python3 scripts/check_impl.py --src . --ext .c,.h
```

| Check | Meaning | Reliable? |
|---|---|---|
| **orphan** | Marker in the code, no such object | yes |
| **dangling** | IMPL asserts something the source doesn't contain | yes |
| **uncovered** | Confirmed leaf with no implementation | yes |

**Dangling is the one that quietly lies to you** — the model keeps asserting
something is implemented after the code was refactored away.

**Semantic drift** — marker and object both present, code no longer doing what
the object says — is not mechanically detectable, and this system does not
pretend otherwise. The honest mitigation is a review queue, not a guarantee.

## When implementation contradicts the model

This is the loop that matters, and it runs in both directions.

A pilot's empirical validation pass found three assumptions wrong: two
build-system variables were inert without machinery the project doesn't have,
a library toggle didn't exist natively at all, and a path variable wasn't a
native concept. Each finding invalidated a confirmed requirement.

What should happen:

1. `model.py new --type obs` — record what was actually found.
2. `model.py new --type dec --relates resolves:<obs>` — decide what to do.
3. New or superseding REQ, with `decided_by` pointing at that DEC.

What actually happened: the requirements were promoted to `confirmed` with no
DEC behind them at all. `trace.py open` finds four such objects in that pilot.
Implementation feedback is not permission to skip the decision.

## Working with them

```bash
model.py new --type impl --alias impl-incl-promotion \
  --title "INCL= header promotion in mk.lib.mk" \
  --origin "written during phase 1" \
  --relates implements:incl-macro-promotes-generated-headers-req

model.py status --id impl-incl-promotion --to verified
```

Statuses: `asserted` (claimed), `verified` (checks pass), `stale` (code moved
on), `superseded`.
