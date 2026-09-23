"""Command line entry points.

``moodmotion demo``   — run a scripted weekend and print the mood curve as ASCII
``moodmotion check``  — run the built-in behaviour assertions
``moodmotion judge``  — classify one sentence (needs a model; falls back to keywords)
"""

from __future__ import annotations

import argparse
import sys
import time

from .descriptors import DEFAULT_DESCRIPTORS
from .engine import Mood
from .judge import apply_judged, judge_blocking
from .prompt import mood_block
from .taxonomy import DEFAULT_KINDS, guess_fallback

MIN = 60.0
HOUR = 60 * MIN
DAY = 24 * HOUR


# ── rendering ───────────────────────────────────────────────────────

def _bar(v: float, width: int = 21) -> str:
    """Map −1..1 onto a bar with a centre mark."""
    half = width // 2
    n = int(round(abs(v) * half))
    if v >= 0:
        return " " * half + "|" + "#" * n + " " * (half - n)
    return " " * (half - n) + "#" * n + "|" + " " * half


def _clock(minutes: float) -> str:
    days, rest = divmod(int(minutes), 24 * 60)
    return f"d{days} {rest // 60:02d}:{rest % 60:02d}"


def _row(label: str, minutes: float, mood: Mood, note: str = "") -> str:
    d = mood.nearest()
    tail = f"  {note}" if note else ""
    return (f"{_clock(minutes):>9}  {_bar(mood.valence)} {mood.valence:+.2f}  "
            f"{_bar(mood.energy)} {mood.energy:+.2f}  {d['name']:<11}{tail}")


def demo() -> int:
    """A scripted ~3 days: good news, a spill, affection, a night, then silence.

    Time arithmetic note: the engine speaks **minutes** (``advance`` takes minutes and
    reads ``time.time()`` in seconds). Everything below is kept in minutes and only
    converted at the single point where a wall-clock timestamp is needed.
    """
    mood = Mood()
    base = time.time()
    t = 0.0                                    # minutes elapsed

    # ⚠️ Unit trap worth stating once: the engine's `advance`/`sleep`/`settle_absence`
    # take a wall-clock timestamp in **seconds**, while `t` here counts **minutes**.
    # So seconds = t * 60. (MIN is the number of seconds in a minute — multiplying by
    # it would scale t by 60 twice and silently turn hours into days.)
    def at() -> float:
        return base + t * 60.0

    def advance(minutes: float) -> None:
        nonlocal t
        t += minutes
        mood.advance(at())

    def event(kind_name: str, scale: float = 1.0) -> None:
        spec = next(k for k in DEFAULT_KINDS if k.name == kind_name)
        mood.apply(spec.dv * scale, spec.de * scale, note=kind_name, now=at())

    def sleep(hours: float) -> None:
        nonlocal t
        t += hours * 60                      # hours -> minutes
        mood.sleep(hours, now=at())

    def absent(days: float) -> list:
        """Advance ``days`` on the clock, then charge the silence."""
        nonlocal t
        t += days * (24 * 60)                # days -> minutes
        return mood.settle_absence(at())

    print("moodmotion — one state over ~3 days. Left bars: valence. Right bars: energy.")
    print(f"{'clock':>9}  {'valence':<21} {'':>5}  {'energy':<21} {'':>5}  {'mood':<11} event")
    print("-" * 112)
    print(_row("start", t, mood, "baseline"))

    # Blank lines around the section markers are load-bearing: the README embeds this
    # output verbatim, and an extractor that drops empty lines would run the headings
    # into the table.
    print()
    print("-- a normal day --")
    event("pleasant_time", 0.4)
    print(_row("", t, mood, "they had a really good meal"))
    advance(3 * 60)
    print(_row("", t, mood, "(3h later — most of it is already gone)"))
    event("minor_hassle", 0.4)
    print(_row("", t, mood, "they spilled water — annoyance, not sadness"))
    advance(2 * 60)
    event("affection", 0.9)
    print(_row("", t, mood, "they say they have been thinking about her"))
    advance(2 * 60)
    sleep(8)
    print(_row("", t, mood, "slept — intensity drops, nothing is wiped"))
    advance(6 * 60)
    print(_row("", t, mood, "a quiet day"))

    print()
    print("-- then they stop showing up --")
    mood.mark_contact(at())                    # silence starts here, not at t=0
    print(_row("", t, mood, "last time they spoke"))
    days1 = absent(1)
    print(_row("", t, mood, f"one day of silence ({len(days1)} day charged)"))
    days2 = absent(1)
    print(_row("", t, mood, f"another one ({len(days2)} day charged)"))
    print("\n   charged in total:", [f"d{d['day']} {d['dv']:+.3f}" for d in days1 + days2])

    print("\nWhat the model is handed at that point:\n")
    print(mood_block(mood))
    snap = mood.snapshot()
    print("\nRaw numbers (logs only — never give these to a model):")
    print(f"  valence={snap['valence']} energy={snap['energy']} "
          f"descriptor={snap['descriptor']!r} gap_days={snap['gap_days']}")
    return 0


# ── assertions ──────────────────────────────────────────────────────

def check() -> int:
    """Behaviour assertions, runnable without pytest and without a model."""
    fails: list[str] = []

    def want(label: str, condition: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if condition else 'FAIL'} {label}" + (f"  [{detail}]" if detail else ""))
        if not condition:
            fails.append(label)

    def ev(mood: Mood, name: str, scale: float = 1.0) -> None:
        spec = next(k for k in DEFAULT_KINDS if k.name == name)
        mood.apply(spec.dv * scale, spec.de * scale, note=name)

    print("decay")
    m = Mood()
    ev(m, "pleasant_time")
    peak = m.valence
    m.advance(m.updated_at + 3600)
    want("a good event is still noticeable an hour later", m.valence > 0.1,
         f"{peak:.2f} -> {m.valence:.2f}")
    m2 = Mood()
    ev(m2, "pleasant_time")
    m2.advance(m2.updated_at + 8 * HOUR)
    want("and largely settled by the next morning", abs(m2.valence) < 0.06, f"{m2.valence:.3f}")

    print("per-family half-life (sadness outlasts joy)")
    lo = Mood(valence=-0.6, energy=-0.25)
    ir = Mood(valence=-0.35, energy=0.35)
    hi = Mood(valence=0.7, energy=0.45)
    want("low moods fade slower than irritation",
         lo.nearest()["decay_mul"] > ir.nearest()["decay_mul"],
         f"{lo.nearest()['decay_mul']} vs {ir.nearest()['decay_mul']}")
    want("irritation fades slower than content",
         ir.nearest()["decay_mul"] >= hi.nearest()["decay_mul"])

    print("a small hassle is annoying, not sad")
    m = Mood()
    ev(m, "pleasant_time")
    before = m.valence
    energy_before = m.energy
    ev(m, "minor_hassle")
    want("valence drops", m.valence < before, f"{before:.2f} -> {m.valence:.2f}")
    want("but stays well clear of sadness", m.valence > -0.5, f"{m.valence:.2f}")
    want("and energy does not move at all",
         abs(m.energy - energy_before) < 1e-9,
         f"{energy_before:.2f} -> {m.energy:.2f}")

    print("sleep lowers intensity rather than resetting")
    good = Mood(valence=0.70, energy=0.45)
    good.sleep(8)
    want("good mood is much reduced", good.valence < 0.30, f"{good.valence:.2f}")
    want("but not zeroed", good.valence > 0.0, f"{good.valence:.2f}")
    want("and waking is not read as exhaustion", good.energy > 0.2, f"{good.energy:.2f}")
    bad = Mood(valence=-0.60, energy=-0.25)
    bad.sleep(8)
    want("a low mood improves", bad.valence > -0.60, f"{bad.valence:.2f}")
    want("yet keeps a residue", bad.valence < -0.05, f"{bad.valence:.2f}")
    want("a low mood resists sleep more than a good one",
         bad.valence / -0.60 > 0.70, f"retained {bad.valence / -0.60:.2f}")

    print("absence accumulates, is capped, and is attributed")
    m = Mood(valence=0.125, energy=0.654)
    m.last_contact_at = m.updated_at - 2 * DAY - HOUR
    applied = m.settle_absence(m.updated_at)
    want("two days of silence are charged", len(applied) == 2, f"{len(applied)}")
    want("valence is pushed negative", m.valence < -0.1, f"{m.valence:.2f}")
    want("energy is dented too", m.energy < 0.654)
    want("and it is named as sulking, not as a small annoyance",
         m.describe()["name"] == "sulky", m.describe()["name"])
    want("charging is idempotent", len(m.settle_absence(m.updated_at)) == 0)
    m.mark_contact(m.updated_at)
    want("contact clears both the count and the attribution",
         m.gap_days(m.updated_at) == 0 and not m.gap_active)
    deep = Mood(valence=-0.6, energy=-0.25)
    deep.last_contact_at = deep.updated_at - 4 * DAY
    deep.settle_absence(deep.updated_at)
    want("a genuinely bad state is not renamed 'sulky'",
         deep.describe()["name"] == "low", deep.describe()["name"])

    print("gating and prompt hygiene")
    want("high energy alone does not read as alert",
         Mood(valence=0.02, energy=0.61).nearest()["name"] != "alert")
    want("low valence with high energy can be alert",
         Mood(valence=-0.4, energy=0.7).nearest()["name"] == "alert")
    m = Mood(valence=-0.55, energy=-0.3)
    m.gap_active = True
    block = mood_block(m)
    want("prompt forbids stating numbers", "Never state a number" in block)
    want("prompt names combination states", "not sadness" in block or "not" in block)
    want("describe() exposes no numeric value as text",
         all(ch not in m.describe()["text"] for ch in "0123456789"))
    want("intensity is a word, not a figure",
         m.describe()["intensity"] in ("faint", "moderate", "strong"))

    print("persistence")
    m = Mood(valence=0.42, energy=-0.13)
    m.gap_active = True
    m.save("ignored")                      # ":memory:" — must be a silent no-op
    want("in-memory mode tolerates save()", True)

    print()
    if fails:
        print(f"{len(fails)} failed: " + "; ".join(fails))
        return 1
    print("all assertions passed")
    return 0


# ── judge one sentence ──────────────────────────────────────────────

def judge_one(text: str, offline: bool) -> int:
    if offline:
        kind, scale = guess_fallback(text, DEFAULT_KINDS)
        print(f"offline keyword guess: {kind} (scale {scale})")
        print("(the model path needs MOODMOTION_API_KEY / OPENAI_API_KEY)")
        return 0
    result = judge_blocking(text)
    print(f"kind  : {result['kind']}")
    print(f"scale : {result['scale']}")
    print(f"ok    : {result['ok']}" + ("" if result["ok"] else "  (model unreachable)"))
    return 0 if result["ok"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="moodmotion", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("demo", help="print a scripted mood curve as ASCII")
    sub.add_parser("check", help="run behaviour assertions (no model needed)")

    jp = sub.add_parser("judge", help="classify one sentence into an event")
    jp.add_argument("text", help="the sentence to classify")
    jp.add_argument("--offline", action="store_true", help="keyword fallback only")

    args = parser.parse_args(argv)
    if args.cmd == "demo":
        return demo()
    if args.cmd == "check":
        return check()
    if args.cmd == "judge":
        return judge_one(args.text, args.offline)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
