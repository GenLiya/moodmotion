"""The engine: a continuous, decaying, persistent affect state.

Why this is not just "detect the sentiment of the last message":

* **It is a state, not a reading.** Two variables persist across turns and across
  process restarts, so the same sentence can be answered differently depending on
  what happened earlier.
* **It decays.** Mood returns to baseline on its own, at a rate that differs per
  mood family — sadness outlasts joy (Verduyn et al., 2009).
* **Sleep lowers intensity rather than resetting.** Waking up blunts yesterday's
  mood but does not erase it, and a low mood resists the recovery.
* **Absence accumulates.** Not being talked to for days nudges the state down and
  is *attributed*, so the model can name the right cause instead of guessing.

See ``docs/design.md`` for the parameter table and the reasoning behind each number,
and ``docs/evidence.md`` for what is literature-backed versus hand-tuned.
"""

from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass, field

from .descriptors import DEFAULT_DESCRIPTORS, NEUTRAL, Descriptor

#: Every number here is a tuning decision, not a law of nature. Sources are marked
#: ``lit`` (supported by published findings), ``derive`` (follows from a lit result)
#: or ``tuned`` (chosen by hand and validated against a simulator).
PARAMS: dict[str, float] = {
    # ── decay ──
    "half_valence": 180.0,   # minutes; tuned. 3h keeps a good event noticeable for
                             # about an hour without lingering all day.
    "half_energy": 240.0,    # tuned. Energy recovers slower than mood settles.
    # ── sleep ──
    "sleep_recover": 0.70,   # tuned. Fraction of mood *intensity* removed by a night.
    "sleep_energy": 0.55,    # tuned.
    "wake_floor_energy": 0.15,  # derive. Waking up should read as rested, not as
                             # "wound up" — a high floor starts colliding with the
                             # alert/anticipating descriptors.
    "depress_mul": 0.70,     # derive from lit (sadness persists) — how much of the
                             # sleep recovery a low mood is allowed to refuse.
    # ── events ──
    "event_k": 0.65,         # tuned. Effect is scaled by this before applying, so a
                             # run of small events cannot slam the state to ±1.
    # ── absence ──
    "gap_valence": 0.14,     # tuned. Per day of silence, weighted by how many days.
    "gap_energy": 0.08,      # tuned.
    "gap_max_days": 3,       # tuned. Beyond this the penalty stops growing.
    # ── bounds ──
    "clamp": 1.0,
}

_MEMORY = ":memory:"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class Mood:
    """A persistent two-variable affect state.

    Args:
        descriptors: Mood descriptors to use. Defaults to
            :data:`moodmotion.descriptors.DEFAULT_DESCRIPTORS`. Supply your own to
            give the state a voice.
        params: Overrides merged over :data:`PARAMS`.
        db: SQLite path, or ``":memory:"`` (default) to skip persistence.

    The state advances lazily: :meth:`advance` is called before every read and every
    mutation, so no background task is needed and a long idle period costs nothing.
    """

    valence: float = 0.0
    energy: float = 0.0
    descriptors: list[Descriptor] = field(default_factory=lambda: list(DEFAULT_DESCRIPTORS))
    params: dict[str, float] = field(default_factory=lambda: dict(PARAMS))
    db: str = _MEMORY
    updated_at: float = field(default_factory=time.time)
    last_contact_at: float = field(default_factory=time.time)
    gap_paid: int = 0
    gap_active: bool = False
    log: list = field(default_factory=list)

    # ── construction helpers ────────────────────────────────────────

    def __post_init__(self) -> None:
        if not self.descriptors:
            self.descriptors = [NEUTRAL]
        merged = dict(PARAMS)
        merged.update(self.params or {})
        self.params = merged

    @classmethod
    def load(cls, db: str, key: str = "default", **kwargs) -> "Mood":
        """Load from ``db`` under ``key``, or create a fresh state.

        Time passed since the last save is applied on load (``advance``), which is
        what makes lazy advancement work across restarts.
        """
        if db == _MEMORY:
            state = cls(db=db, **kwargs)
            state.advance()
            return state
        try:
            conn = _connect(db)
            row = conn.execute("SELECT payload FROM mood_state WHERE key = ?", (key,)).fetchone()
            conn.close()
            if row:
                payload = json.loads(row[0])
                payload.pop("descriptors", None)  # descriptors are code, not data
                payload.pop("params", None)
                state = cls(db=db, **kwargs, **payload)
            else:
                state = cls(db=db, **kwargs)
        except Exception:  # a corrupt row must never take the host app down
            state = cls(db=db, **kwargs)
        state.advance()
        return state

    def save(self, key: str = "default") -> None:
        """Persist to :attr:`db`. No-op when ``db`` is ``":memory:"``."""
        if self.db == _MEMORY:
            return
        payload = {k: v for k, v in asdict(self).items()
                   if k not in ("descriptors", "params", "db", "log")}
        try:
            conn = _connect(self.db)
            conn.execute(
                "INSERT INTO mood_state (key, payload, updated_at) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, "
                "updated_at = excluded.updated_at",
                (key, json.dumps(payload, ensure_ascii=False)))
            conn.commit()
            conn.close()
        except Exception:
            pass  # persistence failing must not break the caller's conversation

    # ── time ────────────────────────────────────────────────────────

    def advance(self, now: float | None = None) -> None:
        """Apply elapsed-time decay up to ``now``.

        The step is subdivided so that a jump of several days cannot apply the wrong
        per-family multiplier (the family can change mid-jump).
        """
        now = time.time() if now is None else now
        dt_min = (now - self.updated_at) / 60.0
        if dt_min <= 0:
            self.updated_at = now
            return
        left = dt_min
        while left > 0:
            step = min(left, 30.0)
            d = self.nearest()
            self.valence *= math.pow(0.5, step / (self.params["half_valence"] * d["decay_mul"]))
            self.energy *= math.pow(0.5, step / self.params["half_energy"])
            left -= step
        self.updated_at = now

    # ── mood descriptors ────────────────────────────────────────────

    def nearest(self, v: float | None = None, e: float | None = None) -> Descriptor:
        """Descriptor closest to (``v``, ``e``) — defaults to the current state.

        Descriptors with a ``need_v`` gate are skipped when valence is above it.
        """
        v = self.valence if v is None else v
        e = self.energy if e is None else e
        best, best_d = NEUTRAL, float("inf")
        for d in self.descriptors:
            gate = d.get("need_v")
            if gate is not None and v > gate:
                continue
            dist = (d["v"] - v) ** 2 + (d["e"] - e) ** 2
            if dist < best_d:
                best, best_d = d, dist
        return best

    def describe(self) -> dict:
        """Feed this to your model.

        Returns ``name``, ``text``, an ``intensity`` **band**, and the two raw
        coordinates so callers can build their own wording.

        The returned ``text`` never contains a number, and the band is a word
        (``"faint"`` / ``"moderate"`` / ``"strong"``) rather than a figure — a model
        that is told "valence 0.42" tends to say so out loud.
        """
        d = self.nearest()
        # A state that exists because of absence is *about* the absence; saying
        # "irritated by something small" would misname the cause. Real depression
        # still wins over sulking.
        if self.gap_active and d["name"] != "low":
            d = self._by_name("sulky", fallback=d)
        intensity = max(abs(self.valence), abs(self.energy))
        band = "faint" if intensity < 0.25 else ("moderate" if intensity < 0.55 else "strong")
        return {"name": d["name"], "text": d["text"], "intensity": band,
                "valence": self.valence, "energy": self.energy}

    def snapshot(self) -> dict:
        """Raw numbers for logs, dashboards and tests. **Never** feed this to a model."""
        d = self.nearest()
        return {"valence": round(self.valence, 4), "energy": round(self.energy, 4),
                "descriptor": d["name"], "decay_mul": d["decay_mul"],
                "gap_days": self.gap_days(), "gap_active": self.gap_active,
                "log": self.log[-20:]}

    def _by_name(self, name: str, fallback: Descriptor) -> Descriptor:
        for d in self.descriptors:
            if d["name"] == name:
                return d
        return fallback

    # ── events ──────────────────────────────────────────────────────

    def apply(self, dv: float, de: float, note: str = "",
              now: float | None = None) -> tuple[float, float]:
        """Apply one event. ``dv``/``de`` are intended magnitudes in −1..1.

        They are scaled by ``event_k`` internally. Returns the actual delta applied.
        """
        self.advance(now)
        k = self.params["event_k"]
        c = self.params["clamp"]
        before = (self.valence, self.energy)
        self.valence = _clamp(self.valence + dv * k, -c, c)
        self.energy = _clamp(self.energy + de * k, -c, c)
        self._record("event", note, self.valence - before[0], self.energy - before[1])
        return self.valence - before[0], self.energy - before[1]

    # ── sleep ───────────────────────────────────────────────────────

    def sleep(self, hours: float = 8.0, now: float | None = None) -> tuple[float, float]:
        """Simulate a night's sleep: *reduce intensity*, do not reset.

        A low mood gets to refuse part of the recovery (``depress_mul``), which is
        what makes "slept on it and it's still there" reproducible.
        """
        self.advance(now)
        d = self.nearest()
        depress = self.params["depress_mul"] if (d["name"] == "low" or self.valence < -0.3) else 0.0
        retain = 1.0 - self.params["sleep_recover"] * (1.0 - depress)
        c = self.params["clamp"]
        before = (self.valence, self.energy)
        self.valence = _clamp(self.valence * retain, -c, c)
        floor = self.params["wake_floor_energy"] * (0.6 if d["name"] == "low" else 1.0)
        self.energy = _clamp(max(self.energy + self.params["sleep_energy"], floor), -c, c)
        self._record("sleep", f"slept {hours:g}h (was {d['name']})",
                     self.valence - before[0], self.energy - before[1])
        # Waking up should not immediately read as "you have been absent".
        self.last_contact_at = max(self.last_contact_at, (time.time() if now is None else now) - 600)
        return self.valence - before[0], self.energy - before[1]

    # ── absence ─────────────────────────────────────────────────────

    def gap_days(self, now: float | None = None) -> int:
        """Whole days since :meth:`mark_contact` was last called."""
        return int(((time.time() if now is None else now) - self.last_contact_at) // 86400)

    def settle_absence(self, now: float | None = None) -> list[dict]:
        """Charge any not-yet-charged days of silence. Idempotent per day.

        Returns the newly applied days, so a caller can decide to mention them.
        """
        now = time.time() if now is None else now
        self.advance(now)
        days = self.gap_days(now)
        applied: list[dict] = []
        if days > self.gap_paid:
            k, c = self.params["event_k"], self.params["clamp"]
            for i in range(self.gap_paid + 1, days + 1):
                weight = min(i, self.params["gap_max_days"])
                dv = -self.params["gap_valence"] * weight * k
                de = -self.params["gap_energy"] * weight * k
                self.valence = _clamp(self.valence + dv, -c, c)
                self.energy = _clamp(self.energy + de, -c, c)
                applied.append({"day": i, "dv": dv, "de": de})
                self._record("absence", f"day {i} of silence", dv, de)
            self.gap_paid = days
            self.gap_active = True
        return applied

    def mark_contact(self, now: float | None = None) -> None:
        """Record that the user showed up: clears the absence counter *and* its
        attribution."""
        self.last_contact_at = time.time() if now is None else now
        self.gap_paid = 0
        self.gap_active = False

    # ── internals ───────────────────────────────────────────────────

    def _record(self, kind: str, note: str, dv: float, de: float) -> None:
        self.log.append({"kind": kind, "note": note, "dv": round(dv, 4), "de": round(de, 4),
                         "v": round(self.valence, 4), "e": round(self.energy, 4),
                         "at": time.time()})
        if len(self.log) > 64:
            self.log = self.log[-64:]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS mood_state (
    key        TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def _connect(db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn
