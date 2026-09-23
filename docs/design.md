# Design

How the state is defined, how it moves, and why each knob is where it is.

## Shape of the state

Two continuous variables, both clamped to −1..1:

| Axis | Means | Low end | High end |
|---|---|---|---|
| `valence` | how pleasant the mood is | miserable | delighted |
| `energy` | how activated it is | depleted | keyed up |

Why two and not one: a single number cannot separate *tired* from *sad*, and that
distinction is most of what makes an affect state read as a person rather than a dial.
Low valence with high energy is **irritation** — nettled, blunt, not grieving:

```
energy  +1 ┤  alert        anticipating
           │
        0  ┼  irritated ──── caring ──── content
           │
       -1 ┤  low          flat           sleepy
           └──────────────────────────────────────
             -1            0              +1   valence
```

Dominance — the third axis of the PAD model — is omitted. It buys less in a
one-to-one conversation than it costs in tuning and explainability.

## Descriptors

A descriptor pins a point in that plane together with the wording to convey it:

```python
{"name": "low", "v": -0.60, "e": -0.25, "decay_mul": 1.6, "text": "Down. Quieter..."}
```

`decay_mul` is the one behavioural knob that matters — see below. An optional `need_v`
gate makes a descriptor ineligible above a valence threshold: without it, waking up
rested (high energy, neutral valence) lands on `irritated`, because that is the nearest
other moderate-energy point. The gate is a blunt instrument and is used sparingly.

## Decay

Exponential, evaluated lazily. `advance()` is called before every read and every
mutation, so there is no background task and idle time costs nothing:

```
value(t) = value(0) × 0.5 ** (minutes / (half_valence × decay_mul))
```

The elapsed interval is subdivided into 30-minute steps. A multi-day jump must not be
decayed with the wrong multiplier, and the mood family can change mid-jump.

Per-family rates exist because a uniform half-life is contradicted by the evidence
(sadness outlasts joy). Effective half-lives as shipped:

| Descriptor | `decay_mul` | Effective half-life |
|---|---|---|
| `content` | 0.7 | 2.1 h |
| `anticipating` | 0.8 | 2.4 h |
| `alert` | 0.8 | 2.4 h |
| `warm` | 0.9 | 2.7 h |
| `even`, `caring`, `irritated`, `refreshed`, `sleepy` | 1.0 | 3.0 h |
| `sulky` | 1.5 | 4.5 h |
| `low` | 1.6 | **4.8 h** |

Energy uses a single half-life (4 h) regardless of family.

## Events

An event is `(Δvalence, Δenergy)` plus a hint describing when it applies. The magnitudes
live in a reviewable table; which event occurred is delegated to a model, which returns
only a label and a 0–1 scale. Effects are multiplied by `event_k` (0.65) before being
applied, so a run of small events cannot slam the state to ±1.

The taxonomy is deliberately shaped so that the most common modelling error cannot
happen: `minor_hassle` is (Δ−0.25, Δ0.00) — annoyance **without** an energy change,
which is what keeps a spilled drink from reading as a bereavement.

## Sleep

```
retain  = 1 − sleep_recover × (1 − depress)
valence = valence × retain
energy  = max(energy + sleep_energy, wake_floor_energy)
```

with `sleep_recover = 0.70`, and `depress = 0.70` when the mood is `low`. The result is
that a night removes about 70% of the *intensity* of an ordinary mood, but a low mood
keeps roughly 79% of its distance from neutral — so sleeping on something helps and does
not finish the job.

`wake_floor_energy` keeps waking from reading as exhaustion. It is low (0.15) on purpose:
a high floor collides with the `alert` and `anticipating` descriptors, which is how
"just woke up" starts getting narrated as "wound up".

## Absence

```
gap_days = floor((now − last_contact_at) / 86400)
per day: Δvalence = −gap_valence × min(day, gap_max_days) × event_k
         Δenergy  = −gap_energy  × min(day, gap_max_days) × event_k
```

Charged at most once per day (`gap_paid`), capped at three days of growth, and fully
cleared by `mark_contact()`.

Being ignored is a state with a *cause*, and a nearest-neighbour lookup cannot recover
that cause: the absence penalty leaves energy comparatively high, so the nearest
descriptor is `irritated` — whose wording blames something small. The state therefore
records `gap_active` and `describe()` prefers `sulky` while it is set. A genuinely `low`
state still wins, so sulking never masks real distress.

## Full parameter table

| Parameter | Value | Kind | Note |
|---|---|---|---|
| `half_valence` | 180 min | tuned | 3 h keeps a good event noticeable an hour later without lingering all day |
| `half_energy` | 240 min | tuned | Energy recovers slower than mood settles |
| `sleep_recover` | 0.70 | tuned | Intensity removed by a night |
| `sleep_energy` | 0.55 | tuned | |
| `wake_floor_energy` | 0.15 | derive | Waking must not read as exhaustion |
| `depress_mul` | 0.70 | derive | How much of the recovery a low mood refuses |
| `event_k` | 0.65 | tuned | Effect scaling; prevents saturation |
| `gap_valence` | 0.14 | tuned | Per day, weighted by day count |
| `gap_energy` | 0.08 | tuned | |
| `gap_max_days` | 3 | tuned | Weight stops growing here |
| `clamp` | 1.0 | — | Hard bound on both axes |

`kind` meanings: **lit** = supported by published work, **derive** = follows from a lit
result, **tuned** = chosen by hand and validated against a simulator plus assertions.

## Validation

Numbers were not chosen by eye. Two checks run on every change:

* `python -m moodmotion.cli check` — behavioural assertions, no dependencies.
* `python -m pytest -q` — the same intent as a proper suite, including prompt hygiene.

Both are expected to fail loudly if a knob is moved into a region where, for example,
a small hassle becomes sadness.
