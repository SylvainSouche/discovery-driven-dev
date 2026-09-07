# Outstanding work, bugs, and what does not belong here

Load this when asked what is left to do, how to track a bug, or whether
something should become a task.

```bash
python3 scripts/trace.py open        # the agenda, derived from status
python3 scripts/coverage.py --list   # written down but not built or tested
```

## There is no TASK type, and no BUG type

This is deliberate, and the evidence is fairly direct.

Both pilots kept hand-maintained open lists in prose — four items in one
document, six in another — while the model sat beside them. Every single item
was already representable:

| Written in prose as | Was really |
|---|---|
| "macOS bsdmake — NOT TESTED" | a TEST at status `proposed` |
| "`.depend` mechanics — not tested" | a TEST at status `proposed` |
| "optimization variable not identified" | an unresolved OBS |
| "static `.a` byproduct — not decided" | an open CAND |
| "CC-path table not written" | a confirmed REQ with no IMPL |

Nothing was missing from the vocabulary. What was missing was a command that
showed them together, so a prose list got written instead — and then drifted,
which is the failure this whole methodology exists to prevent.

Adding a TASK type would not have fixed that. It would have added an eleventh
place to write the same thing.

## Where a bug goes

**A defect that proves a requirement wrong is model knowledge.** Record it:

```bash
model.py new --type obs --alias o-target-vars-inert \
  --title "TARGET=/TARGET_ARCH= are inert without Makefile.inc1" \
  --origin "empirical test on bmake, 2026-08-24"
model.py new --type dec --alias d-toolchain-owns-cc \
  --title "mk.toolchain.<name>.mk maps target to concrete CC paths" \
  --origin "after o-target-vars-inert" --relates resolves:o-target-vars-inert
model.py supersede --old target-selection-uses-bmake-native-vars-req \
  --decided-by d-toolchain-owns-cc --origin "validation finding" \
  --with "..."
```

That is the loop that matters, and a pilot ran it three times: two build
variables turned out inert, a library toggle did not exist, a path variable was
not native. Each invalidated a confirmed requirement.

**A defect in code that is meant to work is not model knowledge.** "This
function returns the wrong value on empty input" is an issue for an issue
tracker. Putting it here would flood `index.md`, which is read every session —
a model of 176 durable objects plus 400 closed bugs is strictly worse to work
with, and the token cost is paid every time.

The test: **does fixing this change what the system is supposed to do?** If
yes, it is an OBS. If no, it is a ticket.

## The agenda

`trace.py open` derives ten groups from status alone:

unresolved observations · open candidates · AI proposals awaiting a decision ·
planned but unrun validation · failing tests · unverified assumptions ·
proposed but never confirmed · deferred · confirmed with no decision behind
them · stale implementations

Two of those catch discipline breaches rather than pending work. **Confirmed
with no decision behind it** means something was promoted without a DEC — a
pilot has four, all from validation findings that skipped the decision step.
**Stale implementations** means code moved on and the model still claims
otherwise.

## Never keep a second copy

If you find yourself writing "still open" into a document, stop. That list
exists already and is derived. A written copy is correct on the day it is
written and wrong shortly after, and nothing will tell you when.

Generated views may *include* the agenda — `build_view.py` regenerates, so it
cannot drift. Prose written once cannot make that promise.
