# Use cases

Load this when the work touches users, journeys, functional tests, or user
documentation.

## Why this exists

In two pilot projects covering 425 objects, the use-case type fired **zero
times**. It was defined, it was correct, and nothing ever created one. Both
projects then produced the material anyway, outside the model: a user manual,
a worked `examples/` directory with a lexer and an RPN calculator, and a
validation document describing a four-module dependency chain built in correct
order every time.

So use cases were never inapplicable. They went into `doc/` and `examples/`
instead of into the model, where nothing could link to them.

## What a UC is

A concrete thing someone does, end to end, with an observable outcome.

The "someone" is often a developer. For a build system: *set up a workspace
with two parent workspaces*; *add a library module that promotes a generated
header*; *cross-compile to freebsd-amd64 with gcc*. For a DSL: *define an FSM
with a guarded transition and compile it*. These are use cases even though no
end user in a business sense appears anywhere.

Not a UC: a capability ("supports cross-compilation"), a quality ("must be
fast"), or a UI description. Those are requirements or constraints.

## One object, three faces

A use case is simultaneously:

- **a scenario** — what someone does and what should happen
- **a functional test** — the same steps, executed, with a pass criterion
- **a documentation section** — the same steps, narrated

Write it once. The TEST object that `verifies` it, and any document section
generated from it, are views of the same statement. When it changes, all three
change, because there is only one of them.

A pilot already had this and didn't notice: a validation document contains a
worked four-module chain `A ← B ← C ← D`, tested for real, plus a deliberate
cycle confirmed to fail loudly. That is a use case, its functional test, and
its documentation — recorded as prose under a positional number, `2.4`, which
is exactly the positional identifier this methodology forbids.

## Working with them

```bash
model.py new --type uc --alias add-library-module \
  --title "A developer adds a library module that promotes a generated header" \
  --origin "user walkthrough, 2026-08-29"

model.py new --type req --alias incl-macro --title "..." \
  --origin "derived from add-library-module" \
  --relates motivated_by:add-library-module

model.py new --type test --alias t-add-library-module \
  --title "Build a workspace with one promoting module; header visible to sibling" \
  --origin "written alongside add-library-module" \
  --relates verifies:add-library-module
```

`motivated_by` points from requirement to use case, never the reverse — the
requirement is the newer, more specific object.

## Working backwards from existing requirements

Most projects arrive with requirements and no use cases. Writing the use case
afterwards is legitimate and productive: it routinely reveals sibling
requirements nobody stated, because narrating a journey exposes the steps that
were assumed.

Link the existing requirements to the new UC with `motivated_by` after the
fact. There is no ordering rule saying the UC must come first.

## Watch for

**A UC that is really a requirement.** If it has no actor and no sequence, it
is a REQ.

**A UC nobody can perform.** If you cannot write the test, the use case is
underspecified — that is the test earning its keep.

**Requirements with no UC.** `trace.py open` lists these. Not every requirement
needs one; constraints and negative requirements often don't. But a confirmed
functional requirement no journey reaches is worth a question.
