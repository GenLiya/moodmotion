"""Turn a mood into prompt text.

This is the half that actually changes behaviour. A mood that only picks a voice or a
colour is decoration; a mood that reaches the prompt changes what gets said.

Three rules are enforced here rather than left to the caller's discipline:

1. **No numbers.** The block states a feeling and a band, never a value. A model told
   "valence = 0.42" will eventually announce it, and a person does not have a mood
   number.
2. **Mood biases wording, not beliefs.** The wording nudges length, warmth and
   willingness to start a topic. It never licenses a factual conclusion ("you were
   gone, so you don't care"). This mirrors mood-congruent *processing* without letting
   the state rewrite the relationship.
3. **Combination states are named explicitly.** Low valence with high energy is
   irritation, not sadness; low valence with low energy is not "tiredness" either.
   Models collapse these by default, and the collapse is audible.
"""

from __future__ import annotations

from .engine import Mood

HEADER = "# Your current state (internal — never state a number or name a 'mood value')"

#: Extra wording per combination, keyed by (valence sign, energy sign) predicates.
_COMBOS = [
    (lambda v, e: v < -0.3 and e > 0.2,
     "What you feel is *annoyance*, **not** sadness — do not write it as grief."),
    (lambda v, e: v < -0.3 and e < -0.3,
     "You are both low and depleted — but do **not** volunteer this; answer if asked."),
    (lambda v, e: v > 0.3 and e < -0.3,
     "Your mood is fine, your body is tired — do not call this sadness, and do not "
     "pretend to be energetic either."),
]

_INTENSITY = {
    "faint": "Barely there. Do not perform it.",
    "moderate": "Moderate: sentence length, word choice and willingness to elaborate "
                "are all affected.",
    "strong": "Strong: it clearly affects how much you say and whether you open a topic.",
}


_NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight",
                 "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen"]


def _word(n: int) -> str:
    """Spell small numbers out: a prompt with digits in it invites digits back."""
    return _NUMBER_WORDS[n] if 0 <= n < len(_NUMBER_WORDS) else f"{n}"


def mood_block(mood: Mood, *, gap_days: int | None = None, header: bool = True) -> str:
    """Render the mood as a system-prompt fragment.

    Args:
        mood: The state to render.
        gap_days: Override the absence count. Defaults to ``mood.gap_days()``.
        header: Include the leading header line.

    Returns:
        Markdown-ish text, ready to append to a system prompt. Empty string is never
        returned — being 'even' is itself information for the model.
    """
    d = mood.describe()
    days = mood.gap_days() if gap_days is None else gap_days
    parts: list[str] = []
    if header:
        parts.append(HEADER)
    parts.append(f"Your mood: **{d['name']}**. {d['text']}")
    parts.append(_INTENSITY[d["intensity"]])

    for test, wording in _COMBOS:
        if test(d["valence"], d["energy"]):
            parts.append(wording)

    if days >= 1:
        parts.append("")
        parts.append(f"# They have not been in touch for {_word(days)} day(s)")
        if days == 1:
            parts.append("They were absent yesterday and it has been on your mind. One "
                         "light remark is allowed — not an accusation. 'I thought you'd "
                         "come by', not 'where were you'.")
        else:
            parts.append(f"{_word(days).capitalize()} days. You would like not to mind, "
                         "and it shows. One half-joking line, then let it go.")
        parts.append("Bounds: this is *caring*, not *blaming*. No coldness, no pursuing "
                     "it, no interrogation. The moment they explain, accept it.")

    parts.append("")
    parts.append("Never state a number, and never claim to have a 'mood value'. Describe "
                 "the feeling in words instead — say you are a bit flat today, not that "
                 "some score has dropped.")
    return "\n".join(parts)


def render_block(mood: Mood, **kwargs) -> str:
    """Alias for :func:`mood_block`, kept for readability at call sites."""
    return mood_block(mood, **kwargs)
