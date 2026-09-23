# moodmotion

**Continuous mood state for conversational agents.** Two dimensions that persist, decay
on their own schedule, are dented by what the other person says, recover over a night's
sleep, and notice when nobody has been around.

Most "emotional" chat agents pick a tone per message. That is not a mood — it is a
label on a sentence. The point here is that **the same message, arriving in different
states, should produce different replies**, because that is how people work.

```
$ python -m moodmotion.cli demo

moodmotion — one state over ~3 days. Left bars: valence. Right bars: energy.
    clock  valence                      energy                       mood        event
----------------------------------------------------------------------------------------------------------------
 d0 00:00            |           +0.00            |           +0.00  even         baseline

-- a normal day --
 d0 00:00            |#          +0.12            |           +0.03  even         they had a really good meal
 d0 03:00            |#          +0.06            |           +0.02  even         (3h later — most of it is already gone)
 d0 03:00            |           -0.01            |           +0.02  even         they spilled water — annoyance, not sadness
 d0 05:00            |####       +0.41            |#          +0.10  caring       they say they have been thinking about her
 d0 15:00            |           +0.01            |######     +0.57  refreshed    slept — intensity drops, nothing is wiped
 d0 21:00            |           +0.00            |##         +0.20  even         a quiet day

-- then they stop showing up --
 d0 21:00            |           +0.00            |##         +0.20  even         last time they spoke
 d1 21:00           #|           -0.09            |           -0.05  even         one day of silence (1 day charged)
 d2 21:00          ##|           -0.18           #|           -0.10  even         another one (1 day charged)
```

Numbers on the left are for *you*. The model never sees them — see
[Prompt hygiene](#prompt-hygiene).

## Install

No runtime dependencies — the core is stdlib only (`sqlite3`, `math`, `json`).

```bash
pip install moodmotion            # when published
# or, from a checkout:
pip install -e .
```

## Quick start

```python
from moodmotion import Mood, apply_judged, judge_blocking, mood_block

mood = Mood.load("mood.db")                     # survives restarts; decays while idle

said = "I finally had a proper meal today."
apply_judged(mood, judge_blocking(said), said)  # classify -> apply (no model? keywords)
mood.mark_contact()                             # they showed up
mood.save()

system_prompt += mood_block(mood)               # <-- this is what changes the reply
print(mood.snapshot())                          # <-- raw numbers, for logs only
```

`judge` needs a model; everything else works without one. The default client speaks the
OpenAI-compatible `/chat/completions` shape and reads `MOODMOTION_API_KEY` /
`MOODMOTION_BASE_URL` / `MOODMOTION_MODEL`. Pass your own transport if you use something
else:

```python
async def my_llm(system: str, user: str, max_tokens: int) -> str:
    return await my_client.complete(system=system, user=user, max_tokens=max_tokens)

judged = await judge(said, complete=my_llm)
```

## The three ideas that make it work

**1. The state is an event response, not a sentiment reading.**
The obvious implementation — score the assistant's own reply for emotion words — cannot
work. "I just had an amazing meal" contains no joy keyword if you look at the wrong side
of the conversation, so the state never moves. The effect has to come from *what
happened*. So a model is asked one narrow question: **which event class is this, and how
big** — chosen from a closed list in `moodmotion.taxonomy`. It never invents magnitudes;
the magnitudes are a table you can review and edit.

**2. Mood families decay at different rates.**
A uniform half-life is wrong: sadness outlasts joy (Verduyn et al., 2009, two experience
sampling studies; the mechanism they identify is rumination). So every descriptor carries
a `decay_mul`, and the effective half-life is `half_valence × decay_mul`.

**3. Sleep reduces intensity — it does not reset.**
Waking up blunts yesterday's mood without erasing it, and a low mood is allowed to refuse
part of that recovery, which is what makes "slept on it and it's still there"
reproducible rather than a free reset.

## Prompt hygiene

A mood that only selects a voice is decoration. A mood that reaches the prompt changes
behaviour. Three rules are enforced in code rather than left to your discipline:

* **The rendered block contains no digits at all.** Not as a value, not even as a
  counter-example — small models copy the shape of the example they are given. Small
  counts are spelled out ("two days"). A test asserts this across several states.
* **`describe()` returns a band** (`faint` / `moderate` / `strong`), never a figure. The
  numbers live behind `snapshot()`, explicitly documented as logs-only.
* **Mood biases wording, not beliefs.** The block nudges length, warmth and willingness
  to open a topic. It never licenses a factual conclusion about the relationship.

## Evidence vs. tuning

Every number in `moodmotion.engine.PARAMS` is labelled in the source as `lit`,
`derive` or `tuned`. The short version:

| Claim | Status |
|---|---|
| Two dimensions (valence × arousal) describe affect | **Literature.** Russell (1980) circumplex; Mehrabian & Russell (1974) PAD — dominance is dropped here as low-value for this use. |
| Affect decays over time | **Literature** (phenomenon). The *exponential* form is an engineering choice. |
| Sadness decays slower than joy | **Literature.** Verduyn et al. (2009). |
| Being ignored should read as caring-sulking, not blame | **Mechanism from attachment theory** (protest behaviour on separation). The intensity is tuned down deliberately. |
| Specific half-lives, sleep fractions, event magnitudes | **Hand-tuned**, validated against a simulator and assertions. No published constants exist for these. |

Full write-up, including what was read only as an abstract and what remains unverified:
[`docs/evidence.md`](docs/evidence.md). Parameter table and reasoning:
[`docs/design.md`](docs/design.md). Things that went wrong while building it:
[`docs/pitfalls.md`](docs/pitfalls.md).

## API

| | |
|---|---|
| `Mood.load(path, key)` / `.save(key)` | Persistent state; time-decay applied lazily on load |
| `Mood.apply(dv, de)` | Apply an event effect directly |
| `Mood.sleep(hours)` | Lower intensity; a low mood resists |
| `Mood.settle_absence()` / `.mark_contact()` / `.gap_days()` | Silence accounting |
| `Mood.describe()` | **Model-facing**: name, wording, intensity band |
| `Mood.snapshot()` | **Log-facing**: raw values, recent history |
| `moodmotion.judge(...)` / `judge_blocking(...)` | Classify an incoming message |
| `moodmotion.apply_judged(mood, judged, text)` | Apply, with keyword fallback |
| `moodmotion.mood_block(mood)` | Render the prompt fragment |
| `moodmotion.EventKind` / `DEFAULT_KINDS` | The event table — edit this, not the prompt |
| `moodmotion.DEFAULT_DESCRIPTORS` | Neutral mood wording; replace with your own |

Bring your own characters by passing descriptors:

```python
from moodmotion import Mood

mood = Mood(descriptors=[
    {"name": "bright", "v": 0.7, "e": 0.5, "decay_mul": 0.8, "text": "Bright and chatty."},
    {"name": "hollow", "v": -0.6, "e": -0.3, "decay_mul": 1.8, "text": "Hollow; slow to answer."},
])
```

Or swap the event taxonomy for your domain:

```python
from moodmotion import EventKind

kinds = [
    EventKind("compliment", +0.6, +0.1, "they praised your work"),
    EventKind("bug_report", -0.3, +0.2, "they found a bug"),
    EventKind("silence",      0.0,  0.0, "nothing notable"),
]
```

## Testing

```bash
python -m moodmotion.cli check     # behaviour assertions, no model, no pytest
python -m pytest -q                # the same ideas as a proper suite
```

The assertions target intent, not plumbing — "a spilled drink is not a bereavement",
"waking up is not exhaustion", "being ignored is not narrated as a small annoyance".
Coverage metrics never notice those.

## Limitations

* **No autonomous messaging.** Deciding to message someone unprompted is a consent and
  product question, not a modelling one. This library only shapes a reply to a message
  that already arrived.
* **One half-life family per mood, shared energy half-life.** Energy does not get
  per-family rates.
* **The shipped taxonomy is an example, not a theory.** It covers the common shapes of
  one-to-one conversation and expects to be replaced.
* **Absence is measured against one clock.** Multi-device or multi-session deployments
  need to decide what "the same relationship" means per storage key.
* No sentiment analysis of the assistant's own output, on purpose (see idea 1).

## Provenance

This is a standalone extraction of an affect model built for a personal companion agent.
**No third-party character, voice, script or game text is included** — the original
project's persona material and cloned voice assets are deliberately absent, and the
default descriptors here are neutral placeholders.

## Licence

MIT — see [`LICENSE`](LICENSE).
