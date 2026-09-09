---
name: discovery-driven-dev
version: 2.6.0
schema_version: 2
license: MIT
description: Keep requirements, decisions, use cases and implementation links in durable files instead of in the conversation. Use when specifying, designing, or building software across more than one session — or whenever a project has a project-model/ directory.
---

# Discovery-driven development

Two failures this exists to prevent:

- **Unspecified gets in the way** — something discussed but never turned into an object with a state.
- **Specified gets forgotten** — a decision whose only home was the conversation.

The fix is that the model lives in files, not in context. Files cannot be forgotten, and they can be checked.

## The one rule

**Never write to `project-model/` by hand. Ever.**

Every create, link and status change goes through `scripts/model.py`. This is
not a style preference. Two pilot projects produced 436 hand-written objects
while a working generator sat unused beside them; the result was 24 ad-hoc
relationship keys, ten free-text statuses, and 163 objects with no recorded
provenance. The script was never the problem — its being optional was.

If a script is missing or won't run, **stop and say so**. Do not reconstruct
its behaviour by writing YAML that looks right. `model.py check` detects
hand-written objects by checksum, so improvised writes will be found.

Object bodies are prose and are free to edit. Frontmatter is machine territory.

A label needing to change — a project renamed, a typo in `origin`, a facet
reassigned — is not a decision and does not need supersession. Use
`model.py amend`, not a text editor: it logs a brief, independently
checksummed "what changed and why" note, so the fix is real without a DEC
asserting nothing new about the world.

This whole skill assumes `project-model/` is durable. That's only true if the
filesystem underneath it is — a bare claude.ai web-chat sandbox has no
persistence contract, and can reset without warning. Every write already
triggers `bundle.py` unconditionally, exporting a copy to
`/mnt/user-data/outputs/` when that path exists, which is the one that
actually survives a sandbox reset. Nothing to do here — it's automatic — but
know that it's *why* a `project-model-backup.tar.gz` will appear on disk, and
don't rely on that sibling copy alone: it shares the same sandbox as
everything else and won't survive a full reset by itself.

## Orientation, every session

```bash
python3 scripts/model.py check          # is the model sound?
cat project-model/index.md              # what exists (never scan the directory)
```

Reading every object costs ~57k tokens at 176 objects. Read `index.md`, then
`trace.py find` or `show` for specifics. Opening an object file is a deliberate
act, not a reflex.

## Before asserting anything is new

Search first. Claiming a gap that already exists as an object is the most
damaging error this system can make, and it has happened: an API contract in a
pilot marked a design point as newly invented while a requirement stating the
same thing sat three aliases away in the same paragraph.

```bash
python3 scripts/trace.py find "<terms>" --deep
```

Record what you searched for. "I looked and found nothing" can be audited;
"I didn't recall anything" cannot.

## Core mechanic

Objects are typed, immutably identified, and related by a **fixed nine-key
vocabulary**. Every edge is written on the newer object and points backward in
time. Inverses are never stored — they are computed. See
`references/objects.md`.

**Supersession is total; refinement never invalidates.** Refining leaves the
parent true, so it cannot be used to correct a partly-wrong statement. Replace
it instead — absorbed into one object, or split across several. See
`references/objects.md`.

**Nothing becomes `confirmed` except through a DEC.** Observations, candidates
and AI proposals are not requirements. An AI proposal is never a requirement
until a decision records acceptance.

The **specification layer is depth in the refinement DAG**, not a separate
type. A REQ that `refines` another is more precise than it. The leaves are the
spec-grade statements, and they are where implementation attaches:
`model.py leaves`.

## Load a reference when the work turns to it

| Situation | Read |
|---|---|
| Any object or relationship question | `references/objects.md` |
| Users, journeys, functional tests, user docs | `references/uc.md` |
| "What's covered?", gaps, readiness | `references/coverage.md` |
| "What's left?", bugs, todos | `references/outstanding.md` |
| Linking code to the model, tracking what's built | `references/dev.md` |
| Reviewing code or a contract written elsewhere | `references/import.md` |
| Producing a document or an API contract from the model | `references/views.md` |
| `check` reports a schema_version mismatch | `references/migration.md` |

## Tools

| Command | Does |
|---|---|
| `model.py new\|link\|status` | the only write path |
| `model.py amend` | relabel alias/origin/facets/certainty in place — not a decision, so no supersession |
| `model.py supersede` | replace an object — absorb into one, or split across several |
| `model.py check --strict` | validity, tamper detection, dangling edges, cycles |
| `bundle.py` | runs automatically after every write — exports outside the sandbox, no attention needed |
| `model.py leaves` | most-specific requirements |
| `trace.py find\|show\|walk\|orphans` | cheap reads, computed inverses |
| `trace.py open` | the outstanding-work agenda, derived from status |
| `coverage.py --list` | what is covered by use cases, tests and code — and what isn't |
| `check_impl.py` | reconcile `@impl` markers against the model |
| `migrate.py` | schema upgrade: dry-run, reconcile, auto-revert on failure |
| `migrate.py --review` | items whose meaning needs human confirmation |
| `migrate.py --rollback` | restore the pre-migration model |
| `build_view.py generate\|check` | produce documents; validate ones already produced |

## Session boundary

In chat the container is discarded between sessions; in Cowork it persists.
Both are first-class. Bundle the model before a session ends, restore it at the
start, and never assume the previous session's files are still there.
