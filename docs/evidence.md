# Evidence

What is supported by published work, what follows from it, and what was simply chosen.
Read this before citing anything in this library as established.

**Access caveat, stated up front:** the sources below were read as abstracts, published
summaries, or second-hand reports of the findings — **not** as full papers. Where a
specific number circulates (for example a duration in hours), it is flagged as unverified
here rather than repeated as fact. Anyone relying on this for research should go to the
originals.

## Supported by literature

**Two dimensions describe affect.**
Russell (1980) proposed the circumplex model of affect, in which affective states are
arranged in a two-dimensional space. Mehrabian & Russell (1974) named the axes
pleasure–arousal–dominance (PAD). This library uses pleasure and arousal, and drops
dominance.

- [Circumplex model of affect (overview)](https://www.sciencedirect.com/topics/computer-science/positive-affect)
- [A recent application using PAD](https://www.sciencedirect.com/science/article/pii/S2666954425000456)

**Affect decays over time.**
In an emotion-transition study, the probability of an emotion recurring was found to
decrease over time (a negative coefficient for all but one emotion), and the same work
models this with exponential decay.

- [Thornton & Tamir, PNAS 2017 — mental models predict emotion transitions](https://www.pnas.org/doi/10.1073/pnas.1616056114)
- [Exponential decay modelling (PNAS supplement)](http://psnlab.princeton.edu/sites/default/files/Thornton-PNAS-2017_supplement.pdf)

*What this does and does not license:* the phenomenon (decay) and the functional form
(exponential) are defensible. **No specific half-life follows from this**, and none is
claimed.

**Sadness lasts longer than other emotions.**
Two experience-sampling studies measured how long emotional episodes actually persist;
sadness came out longest, with rumination proposed as the mechanism.

- [Verduyn et al. (2009), two experience-sampling studies](https://cris.maastrichtuniversity.nl/en/publications/predicting-the-duration-of-emotional-experience-two-experience-sa)
- [Plain-language summary: why sadness lasts longer](https://www.bps.org.uk/research-digest/why-sadness-lasts-longer-other-emotions)

*How it is used:* this is the sole justification for per-family `decay_mul`, with `low`
at 1.6 against `content` at 0.7. The **ratio** is a judgement call; only the **ordering**
is supported.

**Two separate fates for negative material.**
Fading affect bias describes the tendency for unpleasant events to lose their emotional
colour *faster* than pleasant ones in recall, with one study placing its onset within
12 hours and its persistence up to three months.

- [Koval et al. (2011), fading affect bias](https://onlinelibrary.wiley.com/doi/10.1002/acp.1738)

*Reconciliation, because these two findings look contradictory:* they operate on
different layers. Fading affect bias concerns the **remembered** emotion attached to an
event over weeks; Verduyn concerns the **ongoing** emotional episode over hours. A state
machine can hold both, and this one only implements the second — the first would belong
to a memory layer. **This library does not implement fading affect bias**, and does not
claim to.

**Separation produces protest, not indifference.**
In attachment theory, an unavailable attachment figure triggers hyperactivation —
proximity-seeking and expressed displeasure (protest behaviour) — whereas prolonged
non-response tends towards deactivation.

- [Attachment fundamentals — concluding commentary (Shaver & Mikulincer line of work)](https://socialinteractionlab.psych.umn.edu/sites/socialinteractionlab.psych.umn.edu/files/2021-04/2021%20Attachment%20Fundamentals%20Concluding%20Commentary.docx)

*How it is used:* it answers "why should being ignored make an agent upset rather than
neutral", and it supplied the shape of the wording — a brief complaint that seeks
reassurance. **The intensity is deliberately reduced**, because modelling the anxious
extreme produces clinginess, which is a different and worse product.

**Mood influences processing.**
Mood-congruent processing (including Bower's mood-congruent recall) describes the bias of
interpretation and recall towards the current mood.

*How it is used:* it is the justification for mood affecting *wording, length and
willingness to initiate* — and equally for the explicit limit that it must **not** alter
factual judgements about the relationship. Bias in processing is not licence for a false
belief.

## Hand-tuned, with no literature behind it

Stated plainly, because these are the numbers that decide whether the thing feels right
and none of them can be cited:

| Value | Chosen by |
|---|---|
| `half_valence = 180 min`, `half_energy = 240 min` | Iterating on a simulator until a good event was still noticeable an hour later and settled by morning |
| `sleep_recover = 0.70`, `sleep_energy = 0.55` | Same; 70% emerged as "already much better, not wiped" |
| `wake_floor_energy = 0.15` | Lowered twice after "just woke up" kept landing on high-energy descriptors |
| `depress_mul = 0.70` | Chosen so a low mood retains ~79% of its distance from neutral |
| `event_k = 0.65` | Prevents a run of small events saturating the state |
| `gap_valence = 0.14`, `gap_energy = 0.08`, `gap_max_days = 3` | `gap_valence` was cut from 0.20 after three days of silence produced −0.78 — despair, not pique |
| The event taxonomy and its magnitudes | Domain judgement |
| All descriptor coordinates | Geometry, so that the plane has no dead zones |

## Explicitly not verified

- **Exact duration figures** for emotional episodes circulate in summaries (sadness
  reported in the region of five days) — not confirmed against the source tables. Only
  the **ordering** (sadness longest) is relied upon.
- **The HoYo-adjacent** anything: irrelevant here, and deliberately absent — this library
  contains no third-party character material.
- **No claim of psychological validity.** This is an engineering model that borrows a
  small number of established results. It is not a measurement instrument, and it is not
  suitable for assessing anyone's actual mental state.
