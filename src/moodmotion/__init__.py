"""moodmotion — continuous mood state for conversational agents.

Most "emotional" chat agents pick a tone per message. This one keeps a *state*: two
variables that persist, decay on their own schedule, are dented by what the other
person says, recover over a night's sleep, and notice when nobody has been around.

The point is not to perform feeling. It is that the same message, arriving in
different states, should produce different replies — because that is how people work.

Quick start::

    from moodmotion import Mood, apply_judged, judge_blocking, mood_block

    mood = Mood.load("mood.db")          # survives restarts; time-decays on load
    said = "I finally had a proper meal today."

    judged = judge_blocking(said)        # needs a model; degrades to keywords if down
    apply_judged(mood, judged, said)
    mood.mark_contact()                  # they showed up
    mood.save()

    system_prompt += mood_block(mood)    # <- this is what changes the reply
    print(mood.snapshot())               # <- numbers, for logs only

No model configured? Everything except :func:`judge` still works — feed
:meth:`Mood.apply` directly, or run ``python -m moodmotion.cli demo``.

Where things live:

* :class:`~moodmotion.engine.Mood` — the state itself
* :func:`~moodmotion.judge.judge` — classify an incoming message into an event
* :func:`~moodmotion.prompt.mood_block` — render the state into prompt text
* :mod:`~moodmotion.taxonomy` — the event table (edit this, not the prompt)

Two deliberate omissions, so the surface stays honest about what it can do:

* **No sentiment analysis of the assistant's own reply.** The state must move because
  of what happened, not because of what was said back.
* **No autonomous messaging.** Deciding to message someone unprompted is a product and
  consent question, not a modelling one.
"""

from .descriptors import DEFAULT_DESCRIPTORS, NEUTRAL, Descriptor
from .engine import PARAMS, Mood
from .judge import apply_judged, build_prompt, judge, judge_blocking, parse_response
from .prompt import mood_block, render_block
from .taxonomy import DEFAULT_KINDS, EventKind, by_name, guess_fallback

__version__ = "0.1.0"

__all__ = [
    # state
    "Mood", "PARAMS",
    # events
    "EventKind", "DEFAULT_KINDS", "by_name", "guess_fallback",
    # judging
    "judge", "judge_blocking", "apply_judged", "build_prompt", "parse_response",
    # prompt
    "mood_block", "render_block",
    # descriptors
    "Descriptor", "DEFAULT_DESCRIPTORS", "NEUTRAL",
    "__version__",
]
