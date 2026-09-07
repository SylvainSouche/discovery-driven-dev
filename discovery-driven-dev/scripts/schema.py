#!/usr/bin/env python3
"""
schema.py — the single source of truth for what a project-model object is.

Every other script imports from here. Nothing else defines a type, a status,
or a relationship key. If a value isn't in this file, writes are rejected.

This module is deliberately data-heavy and logic-light: it is meant to be
read by a human deciding whether the model's vocabulary is right, not
skimmed past on the way to the interesting code.
"""

SCHEMA_VERSION = 2

# ---------------------------------------------------------------------------
# Object types
# ---------------------------------------------------------------------------
# UC replaces the old SCN. IMPL and TEST are new (dev layer). SPEC and DES are
# gone: the evidence from two pilots is that the specification layer expresses
# itself as REQ-refines-REQ depth, not as a separate type. 55 refines edges
# against 0 SPEC objects is not a close call.

TYPES = {
    "obs":  "Observation — something noticed about the world, the code, or the discussion.",
    "cand": "Candidate — a possibility raised but not yet decided on.",
    "ai":   "AI proposal — introduced by Claude, not the user. Never a requirement until a DEC accepts it.",
    "uc":   "Use case — a concrete thing a user does, end to end. Doubles as functional-test and doc source.",
    "req":  "Requirement — something the system must do. Refines a less specific REQ to add precision.",
    "nreq": "Negative requirement — something the system must NOT do, or a rejected approach.",
    "dec":  "Decision — the only thing that can promote anything into confirmed status.",
    "asm":  "Assumption — believed true, not verified. Carries a certainty.",
    "con":  "Constraint — externally imposed, not chosen.",
    "impl": "Implementation — an assertion that code somewhere realizes specific model objects.",
    "test": "Test — a functional check that exercises a UC or REQ. Not a unit test.",
}

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------
# Fixed per type. The pilots produced 10 free-text statuses including
# "tentative - confirm before treating as settled"; that is what an
# unenforced enum degrades into.

STATUSES = {
    "obs":  ["recorded", "superseded"],
    "cand": ["open", "accepted", "deferred", "rejected", "superseded"],
    "ai":   ["proposed", "accepted", "rejected", "superseded"],
    "uc":   ["proposed", "confirmed", "deferred", "rejected", "superseded"],
    "req":  ["proposed", "confirmed", "deferred", "rejected", "superseded"],
    "nreq": ["proposed", "confirmed", "deferred", "rejected", "superseded"],
    "dec":  ["recorded", "superseded"],
    "asm":  ["assumed", "confirmed", "refuted", "superseded"],
    "con":  ["recorded", "superseded"],
    "impl": ["asserted", "verified", "stale", "superseded"],
    "test": ["proposed", "passing", "failing", "skipped", "superseded"],
}

DEFAULT_STATUS = {
    "obs": "recorded", "cand": "open", "ai": "proposed", "uc": "proposed",
    "req": "proposed", "nreq": "proposed", "dec": "recorded", "asm": "assumed",
    "con": "recorded", "impl": "asserted", "test": "proposed",
}

INACTIVE_STATUSES = {"rejected", "superseded", "refuted", "stale"}

# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------
# NINE keys, fixed and enforced. Two invariants make this enforceable:
#
#   1. Every edge is written on the NEWER object and points BACKWARD in time.
#   2. No inverse is ever stored. `decides`, `produced`, `refined_by` and
#      friends are COMPUTED from the index by trace.py.
#
# rade-bmake stored both directions and they already disagree: 82 decided_by
# against 69 decides. That is the cost of storing inverses.

RELATIONSHIPS = {
    "decided_by":   ("*",            "dec",        "The DEC that authorized this object."),
    "refines":      ("req|nreq",     "req|nreq",   "A more specific statement of a less specific one. This is the spec layer."),
    "supersedes":   ("*",            "*",          "Replaces an earlier object. Absorbs corrects/reverts/restores."),
    "informed_by":  ("*",            "*",          "Background that shaped this. The general-purpose backward edge."),
    "resolves":     ("dec|cand|ai|req|nreq", "obs",
                     "Closes an open observation. A negative requirement closes "
                     "the observation that prompted it just as a decision does — "
                     "the rade-bmake pilot had four such edges."),
    "raised_by":    ("obs",          "*",          "What surfaced this observation."),
    "motivated_by": ("req|nreq",     "uc",         "The use case this requirement serves."),
    "implements":   ("impl",         "req|nreq",   "Code realizes this requirement."),
    "verifies":     ("test",         "uc|req",     "This test exercises that object."),
}

RELATIONSHIP_KEYS = set(RELATIONSHIPS)

# Computed on read by trace.py, never written to disk.
INVERSE_LABELS = {
    "decided_by": "decides", "refines": "refined_by", "supersedes": "superseded_by",
    "informed_by": "informed", "resolves": "resolved_by", "raised_by": "raised",
    "motivated_by": "motivates", "implements": "implemented_by", "verifies": "verified_by",
}

CERTAINTIES = ["confirmed", "probable", "assumed", "speculative", "unknown"]


def check_type(t):
    if t not in TYPES:
        raise SystemExit(f"'{t}' is not an object type. Valid: {', '.join(sorted(TYPES))}")


def check_status(t, s):
    if s not in STATUSES[t]:
        raise SystemExit(
            f"'{s}' is not a valid status for {t}. Valid: {', '.join(STATUSES[t])}.\n"
            f"If this genuinely needs a new status, change schema.py and bump "
            f"SCHEMA_VERSION — do not write it as free text."
        )


def check_relationship(key, src_type, dst_type=None):
    if key not in RELATIONSHIP_KEYS:
        raise SystemExit(
            f"'{key}' is not in the relationship vocabulary.\n"
            f"Valid: {', '.join(sorted(RELATIONSHIP_KEYS))}\n"
            f"Inverses are NOT written — they are computed. If you want to say "
            f"'{key}', you probably want the opposite key on the other object."
        )
    src_ok, dst_ok, _ = RELATIONSHIPS[key]
    if src_ok != "*" and src_type not in src_ok.split("|"):
        raise SystemExit(f"'{key}' cannot be written on a {src_type} object (allowed: {src_ok}).")
    if dst_type and dst_ok != "*" and dst_type not in dst_ok.split("|"):
        raise SystemExit(f"'{key}' cannot point at a {dst_type} object (allowed: {dst_ok}).")
