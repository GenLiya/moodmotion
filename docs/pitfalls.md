# Pitfalls

Things that went wrong while building this, in the order they were found. Each one is
here because it is the sort of failure that survives a green test suite.

## 1. The state that kept working and never moved

**Symptom.** Chat behaved perfectly. Replies looked right. The mood simply never changed
— `valence` sat at 0.0 through conversations that should obviously have moved it.

**Cause.** The classification prompt is a `str.format` template containing a placeholder
written as `{ kinds }` — with spaces. Python's format spec does not allow that, so the
call raised `KeyError: ' kinds '`. The call sat inside a `try/except` whose job was to
keep the conversation alive if the model failed, and it did exactly that: it swallowed the
exception every single turn.

```
[mood] settlement failed (reply unaffected): ' kinds '
```

A log line existed. Nobody was reading it, because nothing was obviously broken.

**Fix.** Correct the placeholder — and, more importantly, understand what made it
invisible. **A safety net that catches everything must emit an observable signal, or it
converts a loud failure into a silent one.** The classifier now returns an explicit
`ok: False` rather than only logging, so callers can assert on it, and the fallback path
degrades the sensitivity of the state instead of freezing it.

## 2. Sentiment sampled from the wrong side of the conversation

**Symptom.** "I just had an amazing meal" left the state untouched.

**Cause.** The original implementation scored the **assistant's own reply** for emotion
keywords. That sentence contains no joy keyword on the assistant's side, and even with a
perfectly worded reply, judging your own output tells you nothing about what happened to
you.

**Fix.** Move the effect to the *input*: classify what the other person said into an
event class, then apply that class's table entry. Keep the magnitudes in a reviewable
table rather than letting the model invent them.

**Lesson.** When a state does not respond to input, check whether it is being computed
from the output. This is easy to miss because the wiring *looks* connected.

## 3. A missing region in the plane, misread as a missing mood

**Symptom.** Two days of silence produced a state whose descriptor was `irritated`,
described as "nettled by something small". The wording was wrong at the source: an empty
inbox is not a small annoyance.

**Cause, part one — geometry.** The silence penalty lowers valence while leaving energy
comparatively high. In the (valence, energy) plane that point is genuinely nearest to the
moderate-energy negative descriptor, which happened to be `irritated`. Nothing was
mathematically broken.

**Cause, part two — the deeper error.** Nearest-neighbour lookup recovers *where* the
state is but not *why*. Two states can sit at nearly the same coordinates for entirely
different reasons, and the wording has to name the reason.

**Fix.** Record the cause (`gap_active`) and let `describe()` prefer the descriptor that
matches it — while keeping a genuinely `low` state dominant, so sulking never masks real
distress. Two false starts were tried and abandoned first: nudging the descriptor
coordinates (the distances nearly tie, so this is fragile and arbitrary) and lowering the
penalty (which changes the emotional content to fix a labelling bug).

**Lesson.** Fix the attribution, not the coordinates. If you find yourself tuning
geometry to make a label come out right, you probably want provenance instead.

## 4. Units multiplied twice, quietly turning hours into days

**Symptom.** A scripted three-day demo reported sixty days of silence; the clock ran away
and every derived figure was wrong. Nothing raised.

**Cause.** Two unit systems meet at this boundary. The engine's `advance`/`sleep`/
`settle_absence` take a wall-clock timestamp in **seconds**; the demo tracked elapsed time
in **minutes**. A helper named `MIN = 60.0` was then used to convert minutes to
timestamps — scaling by 60 a second time.

**Fix.** One `at()` helper doing the single `minutes × 60` conversion, and a comment
naming the trap. **Lesson.** When both minutes and seconds are in play, keep exactly one
conversion site. A constant named for its *meaning* rather than its value (`MIN` could
read as "one minute" or "seconds per minute") is how the mistake survives review.

## 5. The prompt that leaked numbers via a negative example

**Symptom.** A test asserting "the rendered prompt contains no digits" failed — on the
prompt's own warning: *"…is right; 'my valence is 0.3' is not."*

**Cause.** The prohibition was written as a counter-example containing the very thing it
prohibited. Small models copy the *shape* of an example regardless of the surrounding
instruction.

**Fix.** Remove the numeric example, and spell small counts out as words ("two days").
Guarded by a test across several states.

**Lesson.** "Never do X" plus a sample of X is not a prohibition, it is a demonstration.

## 6. Publishing a repo with a hardcoded API key

Not a bug in this library, but the reason it exists as a separate repository.

A secret scanner runs automatically on public repositories and, for recognised providers,
notifies them so the credential can be revoked. Pushing a key is not a private mistake —
it is disclosure. Rotate the key first, start a **fresh** repository rather than publishing
an existing working tree (history included), and scan the whole tree before the first push.

The original project this library was extracted from is a personal one containing
third-party character material and cloned voice assets. **None of that is here**; the
descriptors shipped in this package are neutral placeholders, and the persona work stays
private. Separating the generic mechanism from the licensed material was the point.
