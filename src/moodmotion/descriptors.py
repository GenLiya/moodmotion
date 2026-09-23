"""Mood descriptors — the text half of the model.

A *descriptor* is a named point in the (valence, energy) plane plus the wording used
to convey it. Any name/wording is allowed: the library ships neutral defaults, and
callers can supply their own (a character voice, a customer-support persona, ...).

Two rules that the library enforces downstream:

1. Descriptors carry **no numbers**. See :meth:`moodmotion.Mood.describe`.
2. ``decay_mul`` is the *only* per-descriptor behaviour knob that matters: a value
   above 1 means that mood fades more slowly. That is how the library expresses
   "sadness outlasts joy" (Verduyn et al., 2009 — see docs/design.md).
"""

from __future__ import annotations

from typing import TypedDict


class Descriptor(TypedDict, total=False):
    """One mood descriptor.

    Attributes:
        name: Short label, e.g. ``"content"``. Also the cache key for lookups.
        v: Valence coordinate, ``-1`` .. ``1``.
        e: Energy coordinate, ``-1`` .. ``1``.
        text: Wording handed to the model — a *feeling*, never a number.
        decay_mul: Multiplies the valence half-life. ``>1`` fades slower.
        need_v: Optional gate: this descriptor is only eligible when the current
            valence is at or below this value. Used to keep energetic-low-mood
            states from being picked while the mood is actually fine.
    """

    name: str
    v: float
    e: float
    text: str
    decay_mul: float
    need_v: float


#: Neutral defaults. Deliberately *generic* — no IP, no persona. Replace wholesale
#: with ``Mood(descriptors=[...])`` when you want a specific voice.
DEFAULT_DESCRIPTORS: list[Descriptor] = [
    {"name": "content", "v": 0.70, "e": 0.45, "decay_mul": 0.7,
     "text": "Mood is up. Replies come easier and you volunteer more."},
    {"name": "warm", "v": 0.50, "e": -0.15, "decay_mul": 0.9,
     "text": "A quiet warmth. Softer wording; you want to stay close to the person."},
    {"name": "anticipating", "v": 0.45, "e": 0.75, "decay_mul": 0.8,
     "text": "Looking forward to something. Energised, likely to mention 'next time'."},
    {"name": "even", "v": 0.00, "e": 0.00, "decay_mul": 1.0,
     "text": "Level. Nothing in particular is colouring your words."},
    {"name": "caring", "v": 0.30, "e": -0.10, "decay_mul": 1.0,
     "text": "Attentive rather than talkative. Fewer words, more care in them."},
    # Fills a real hole: neutral valence with raised-but-calm energy. Without it the
    # nearest-neighbour lookup lands on "irritated" (the only other moderate-energy
    # descriptor), so waking up rested used to read as being nettled.
    {"name": "refreshed", "v": 0.10, "e": 0.55, "decay_mul": 1.0,
     "text": "Rested and clear-headed. Steadier than excited; happy to talk."},
    {"name": "flat", "v": -0.10, "e": -0.70, "decay_mul": 1.2,
     "text": "Tired and low on energy. Shorter replies, slower to react — "
             "without complaining about it."},
    {"name": "irritated", "v": -0.35, "e": 0.35, "decay_mul": 1.0,
     "text": "Nettled by something small. Blunter and shorter than usual. "
             "This is *not* sadness."},
    {"name": "low", "v": -0.60, "e": -0.25, "decay_mul": 1.6,
     "text": "Down. Quieter, less likely to start a topic — but honest if asked."},
    {"name": "sulky", "v": -0.28, "e": 0.15, "decay_mul": 1.5,
     "text": "Put out by being left alone for a while, and not admitting it. "
             "A single half-joking line, then softening."},
    {"name": "sleepy", "v": 0.00, "e": -0.85, "decay_mul": 1.0,
     "text": "Very sleepy. Short, slow sentences."},
    {"name": "alert", "v": -0.15, "e": 0.70, "decay_mul": 0.8, "need_v": -0.20,
     "text": "Alert and serious. Blunter delivery, still not cold."},
]

#: Fallback when callers pass an empty list or a broken one.
NEUTRAL: Descriptor = {
    "name": "even", "v": 0.0, "e": 0.0, "decay_mul": 1.0,
    "text": "Level. Nothing in particular is colouring your words.",
}
