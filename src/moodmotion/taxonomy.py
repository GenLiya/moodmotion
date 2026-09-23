"""Event taxonomy: turning what the *other person said* into a mood effect.

The naive approach — scoring the assistant's own reply for emotion keywords — cannot
work: "I just had an amazing meal" contains no joy keyword if you only look at the
assistant's output, so the state never moves. The effect has to come from the
*input event*.

Two halves, deliberately separated:

* **What an event is worth** (this module) is a fixed table you control. It is data,
  so the numbers stay reviewable and tunable.
* **Which event happened and how big** is delegated to a model, because keyword rules
  cannot tell "an amazing meal" (mildly good) from "you spilled water" (mildly
  annoying) from "I've been thinking about you all day" (strongly good).

The shipped taxonomy is **an example, not a theory** — it covers the common shapes of
one-to-one conversation. Replace it for your own domain::

    from moodmotion import EventKind
    kinds = [EventKind("good_news", 0.55, 0.20, "something went well for them")]
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventKind:
    """One class of event and its intended effect.

    Args:
        name: Stable identifier. Must match what the judge returns.
        dv: Intended valence change, −1..1 (scaled by ``event_k`` when applied).
        de: Intended energy change, −1..1.
        hint: Description shown to the judge. Keep it concrete and mutually exclusive
            with the other kinds, or the judge will hedge.
    """

    name: str
    dv: float
    de: float
    hint: str = ""


#: Example taxonomy for one-to-one conversation. Notice ``minor_hassle``: a spill is
#: annoying, and importantly **not** saddening — collapsing the two is the most common
#: way these systems end up sounding wrong.
DEFAULT_KINDS: list[EventKind] = [
    EventKind("affection", +0.70, +0.15, "they express fondness, miss you, or praise you"),
    EventKind("plan", +0.80, +0.40, "you agree on something to do together later"),
    EventKind("gift", +0.85, +0.35, "they gave you something or brought you something"),
    EventKind("good_news", +0.55, +0.20, "something good happened to *them*"),
    EventKind("pleasant_time", +0.45, +0.10, "a small shared pleasure: a good meal, a nice walk"),
    EventKind("concern", -0.35, +0.10, "they are ill or in trouble — you worry, you are not sad"),
    EventKind("neglected", -0.40, -0.15, "they are cold or have been ignoring you"),
    EventKind("hurt", -0.45, -0.10, "they snapped at you or dismissed you"),
    EventKind("minor_hassle", -0.25, 0.00, "a small annoyance: something spilled, a delay"),
    EventKind("trigger", -0.20, -0.10, "a subject that makes you sombre"),
    EventKind("none", 0.00, 0.00, "ordinary talk, no event worth reacting to"),
]


def by_name(kinds: list[EventKind], name: str) -> EventKind | None:
    """Look up one kind by name."""
    for k in kinds:
        if k.name == name:
            return k
    return None


#: Cheap offline fallback. Deliberately coarse — it exists so that a failed model
#: call degrades to *something* instead of silently doing nothing. Replace the
#: markers with your own language.
FALLBACK_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    ("plan", ("see you then", "next time we", "let's do", "promise")),
    ("affection", ("miss you", "love you", "thinking about you", "proud of you")),
    ("gift", ("got you", "bought you", "brought you")),
    ("pleasant_time", ("delicious", "great meal", "had fun", "lovely", "amazing day")),
    ("good_news", ("passed", "got the job", "won", "accepted", "promotion")),
    ("concern", ("sick", "unwell", "fever", "hurt", "hospital")),
    ("neglected", ("leave me alone", "not now", "too busy")),
    ("hurt", ("shut up", "useless", "hate you")),
    ("minor_hassle", ("spilled", "dropped", "lost my", "forgot", "traffic")),
    ("trigger", ("back then", "the old days", "the war")),
]


def guess_fallback(text: str, kinds: list[EventKind]) -> tuple[str, float]:
    """Best-effort keyword guess. Returns ``(name, scale)``.

    Only used when the model call fails. Returns ``("none", 0.0)`` when nothing matches.
    """
    lowered = (text or "").lower()
    valid = {k.name for k in kinds}
    for name, markers in FALLBACK_MARKERS:
        if name in valid and any(m in lowered for m in markers):
            return name, 0.6
    return "none", 0.0
