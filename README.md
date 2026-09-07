# discovery-driven-dev

A [Claude Skill](https://support.claude.com/en/articles/12512142) for keeping
requirements, decisions, use cases and implementation links in durable files
instead of in the conversation.

It exists to prevent two specific failures:

- **Unspecified gets in the way** — something discussed but never turned into
  an object with a state.
- **Specified gets forgotten** — a decision whose only home was the chat.

The model lives in `project-model/`, one markdown file per object, greppable
and version-controllable. Files cannot be forgotten, and unlike prose they can
be checked.

## Why it looks like this

Version 1 was a coherent design that did not survive contact. It was used on
two real projects — a BSD-make build system and an FSM DSL library in
C/POSIX — which produced 425 objects between them. Version 2 is a rewrite
driven by what those projects actually did, not by what the design intended.

Some of what the pilots revealed:

| Finding | Consequence |
|---|---|
| 436 objects hand-written while a working generator sat unused | Every write goes through one script, and frontmatter carries a checksum so hand editing is detected |
| Relationship vocabulary grew from 6 keys in one project to 24 in the other, including `raised_and_deferred` | Nine keys, fixed, rejected at write time |
| One project stored inverse edges and they disagreed — 82 `decided_by` against 69 `decides` | No inverse is ever stored; they are computed |
| 56 `refines` edges against 0 SPEC objects | The specification layer is depth in the refinement DAG, not a separate type |
| The use-case type fired **zero** times across 425 objects, while both projects wrote use-case material outside the model | Renamed to `UC`, given its own reference, and coverage reports on it |
| 163 of 249 objects carried `origin: unspecified — fill in before treating this as settled` | `--origin` is mandatory at creation |
| An API header claimed every declaration carried its requirement IDs; it had 37 declarations and zero IDs | `check_impl.py` reconciles `@impl` markers against the model |
| A generated contract marked a design point as newly invented while a confirmed requirement already said exactly that | A search step is mandatory before claiming a gap, and the negative result is recorded |

The schema has been corrected four times by evidence and zero times by
argument. That is the intended way for it to change.

## Install

Download `dist/discovery-driven-dev.zip` from a release, or build it:

```sh
./build.sh
```

Then in claude.ai: **Customize → Skills → + → Create skill**, upload the
archive, and toggle it on.

**Code execution and file creation must be enabled** in Settings →
Capabilities. Every write goes through a script, so the skill does nothing
without it. Skills are available on Free, Pro, Max, Team and Enterprise plans.

The archive is a plain zip. A `.skill` copy with identical bytes is also
produced, since some upload dialogs prefer it.

## Use

```sh
python3 scripts/model.py check                    # is the model sound?
cat project-model/index.md                        # what exists

python3 scripts/model.py new --type req --alias saved-search \
    --title "The system shall support saved searches" \
    --origin "user statement, 2026-08-29" --relates decided_by:search-dec

python3 scripts/trace.py find "saved search" --deep
python3 scripts/trace.py open                     # outstanding work
python3 scripts/coverage.py --list                # gaps by use case, test, code
python3 scripts/check_impl.py --src . --ext .c,.h # markers vs model
```

## What is in the box

The repo root **is** the skill — clone it and point a skill loader straight
at it, no subfolder to find. `build.sh` stages it into a `discovery-driven-dev/`
folder only when producing the upload archive, since that's what the format
requires.

```
./                            = discovery-driven-dev/ once installed
├── SKILL.md                 thin router, always loaded (~1,270 tokens)
├── references/              loaded on demand
│   ├── objects.md           types, the nine relationships, supersession
│   ├── uc.md                use cases, functional tests, user docs
│   ├── dev.md               @impl markers, implementation linkage
│   ├── import.md            classifying work produced elsewhere
│   ├── views.md             generated documents and API contracts
│   ├── coverage.md          what is owed coverage, and what is not
│   ├── outstanding.md       bugs, todos, and what does not belong
│   └── migration.md         conducting a schema migration
└── scripts/
    ├── schema.py            the format; the single source of truth
    ├── model.py             the only write path
    ├── trace.py             cheap reads, computed inverses
    ├── coverage.py          three coverage axes
    ├── check_impl.py        reconcile markers against the model
    ├── build_view.py        generate documents; validate generated ones
    ├── migrate.py           schema upgrade with reconciliation and rollback
    └── reconcile.py         conservation proofs and analysis documents
```

## Two version numbers

`version` is the skill. `schema_version` is the on-disk object format. A skill
release that does not change the format does not trigger a migration — 2.1.0
through 2.3.0 all run on `schema_version: 2`.

Legacy models carry no version at all, so `migrate.py` fingerprints them by ID
shape and frontmatter layout, then stamps them so nothing has to guess again.

## Migration safety

Migration is dry-run by default. On `--apply` it backs up, migrates, then
proves the result: object counts conserved, edge buckets summing to the legacy
total, every legacy pair still related in some direction, bodies compared byte
for byte, and `model.py check` run automatically. **If any of that fails it
reverts itself.** Every rollback writes an analysis document beside the model
listing what blocked, what needs deciding, and a numbered path to a second
attempt.

Verified against both pilot models: 176 and 249 objects, `Reconciliation:
PASS`, and the auto-revert confirmed with an injected fault.

## Tests

```sh
python3 tests/run_tests.py
```

19 tests covering alias uniqueness, closed vocabulary, illegal and dangling
edges, tamper detection, both supersession modes, coverage inheritance, marker
reconciliation, view citation checking, computed inverses, and model
relocatability.

## Status

Version 2 has been verified against both pilot models and has a passing test
suite, but **has not yet been used to run a project from scratch.** Its
predecessor was also coherent before it met real work. Treat the design as
evidence-shaped but not yet field-tested, and expect the schema to be corrected
by data again.

## Licence

MIT — see [LICENSE](LICENSE).
