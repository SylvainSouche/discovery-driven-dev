# Coverage

Load this when asked what is covered, where the gaps are, or whether something
is ready.

```bash
python3 scripts/coverage.py --list
```

## Three axes

| Axis | Reads | Answers |
|---|---|---|
| **motivation** | `motivated_by` | Which requirements exist for a stated reason? |
| **verification** | `verifies` | Which use cases and leaf requirements have a functional test? |
| **realization** | `implements` | Which leaf requirements are actually built? |

Note the direction difference, since it is easy to get wrong: `motivated_by` is
written **on the requirement** pointing at the use case, so it is outgoing.
`verifies` and `implements` are written on the TEST and IMPL, so from the
requirement's side they are inbound.

## What is deliberately not owed coverage

A report that flags everything is noise, and noise gets ignored. These
exclusions are the difference between a useful report and an ignored one.

**Non-leaf requirements owe no implementation.** A requirement something else
refines is not the thing you build — its leaves are. rade-bmake has 71
confirmed requirements and 28 leaves; demanding an IMPL for each level of a
9-deep chain would flag the same code repeatedly.

**Motivation inherits down the refinement chain.** A leaf sharpening a
motivated requirement inherits its reason. Only a requirement with no use case
anywhere in its ancestry is flagged — that is a requirement nobody can say why
they want.

**Constraints, assumptions and negative requirements owe no use case or
implementation.** A constraint is imposed, not performed. "We will not do X" is
satisfied by absent code, which cannot carry a marker.

**Anything not `confirmed` is excluded.** Proposed and deferred work is not yet
owed coverage. That is what status is for — do not chase gaps in things nobody
has committed to.

## Reading the result

**Low motivation** means requirements exist that nobody can justify. Either
write the use case — which routinely reveals sibling requirements nobody
stated — or question whether the requirement belongs.

**Low verification** means nothing proves the system does what it claims. On
the use-case axis this is severe: a use case you cannot test is underspecified,
and that is the test earning its keep before it is ever run.

**Low realization** is expected early and alarming late. Read it alongside
`check_impl.py`, which catches the opposite failure: implementations asserting
requirements the code no longer contains.

**Use cases nothing derives from** are listed separately, because that is a
different failure — a journey was written and then no requirement followed. It
usually means the use case was descriptive rather than decisive.

## Coverage is not correctness

Every axis measures whether a *link exists*, not whether it is true. An IMPL
can point at a requirement whose code was refactored away; a test can verify a
use case and assert nothing. `check_impl.py` catches the first mechanically.
Nothing catches the second. Report coverage as link density, never as evidence
that the system works.
