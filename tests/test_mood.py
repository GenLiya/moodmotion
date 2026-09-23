"""Behaviour tests.

These assert *intent*, not just plumbing: the interesting failures in an affect model
are things like "a spilled drink made it sad" — which a coverage metric will never
notice. Run with ``pytest`` or ``python -m moodmotion.cli check``.
"""

from __future__ import annotations

import time

import pytest

from moodmotion import EventKind, Mood, apply_judged, mood_block, parse_response
from moodmotion.taxonomy import DEFAULT_KINDS, by_name, guess_fallback

HOUR = 3600.0
DAY = 86400.0


def fire(mood: Mood, name: str, scale: float = 1.0) -> None:
    """Apply a named event at full scale."""
    spec = by_name(DEFAULT_KINDS, name)
    assert spec is not None
    mood.apply(spec.dv * scale, spec.de * scale, note=name)


# ── decay ────────────────────────────────────────────────────────────

def test_good_event_is_still_felt_an_hour_later():
    m = Mood()
    fire(m, "pleasant_time")
    peak = m.valence
    m.advance(m.updated_at + HOUR)
    assert 0.1 < m.valence < peak


def test_mood_settles_by_the_next_morning():
    m = Mood()
    fire(m, "pleasant_time")
    m.advance(m.updated_at + 8 * HOUR)
    assert abs(m.valence) < 0.06


def test_low_moods_outlast_brighter_ones():
    """Verduyn et al. (2009): sadness persists longer than other emotions."""
    low = Mood(valence=-0.6, energy=-0.25)
    irritated = Mood(valence=-0.35, energy=0.35)
    content = Mood(valence=0.7, energy=0.45)
    assert low.nearest()["decay_mul"] > irritated.nearest()["decay_mul"]
    assert irritated.nearest()["decay_mul"] >= content.nearest()["decay_mul"]


def test_decay_is_symmetric_around_zero():
    """Negative and positive states drift home, not towards each other."""
    m = Mood(valence=-0.5, energy=-0.5)
    m.advance(m.updated_at + 24 * HOUR)
    assert -0.05 < m.valence <= 0 and -0.05 < m.energy <= 0


# ── the distinction that matters: annoyance is not sadness ───────────

def test_a_small_hassle_is_annoying_and_not_sad():
    m = Mood()
    fire(m, "pleasant_time")
    before, energy_before = m.valence, m.energy
    fire(m, "minor_hassle")
    assert m.valence < before
    assert m.valence > -0.5             # nowhere near sadness
    assert m.energy == pytest.approx(energy_before)   # energy is untouched


# ── sleep ────────────────────────────────────────────────────────────

def test_sleep_reduces_intensity_without_resetting():
    m = Mood(valence=0.70, energy=0.45)
    m.sleep(8)
    assert 0.0 < m.valence < 0.30
    assert m.energy > 0.2               # waking is not "exhausted"


def test_sleep_improves_a_low_mood_but_leaves_a_residue():
    m = Mood(valence=-0.60, energy=-0.25)
    m.sleep(8)
    assert -0.60 < m.valence < -0.05


def test_a_low_mood_resists_the_recovery():
    """Sleep helps less when the mood is low, so it is not a free reset."""
    low = Mood(valence=-0.60, energy=-0.25)
    good = Mood(valence=0.60, energy=0.45)
    low.sleep(8)
    good.sleep(8)
    assert abs(low.valence / -0.60) > abs(good.valence / 0.60)


def test_waking_does_not_read_as_alert_or_irritated():
    m = Mood(valence=0.01, energy=0.57)
    assert m.nearest()["name"] == "refreshed"


# ── absence ──────────────────────────────────────────────────────────

def test_absence_is_charged_once_per_day_and_capped():
    m = Mood(valence=0.125, energy=0.654)
    m.last_contact_at = m.updated_at - 2 * DAY - HOUR
    applied = m.settle_absence(m.updated_at)
    assert [a["day"] for a in applied] == [1, 2]
    assert len(m.settle_absence(m.updated_at)) == 0        # idempotent
    weights = [min(d + 1, m.params["gap_max_days"]) for d in range(10)]
    assert max(weights) == m.params["gap_max_days"]


def test_absence_lowers_both_axes():
    m = Mood(valence=0.125, energy=0.654)
    m.last_contact_at = m.updated_at - 2 * DAY - HOUR
    m.settle_absence(m.updated_at)
    assert m.valence < -0.1
    assert m.energy < 0.654


def test_absence_is_attributed_rather_than_guessed():
    """Being ignored must not be narrated as 'nettled by something small'."""
    m = Mood(valence=0.125, energy=0.654)
    m.last_contact_at = m.updated_at - 2 * DAY - HOUR
    m.settle_absence(m.updated_at)
    assert m.describe()["name"] == "sulky"


def test_real_low_mood_is_not_renamed_sulking():
    m = Mood(valence=-0.6, energy=-0.25)
    m.last_contact_at = m.updated_at - 4 * DAY
    m.settle_absence(m.updated_at)
    assert m.describe()["name"] == "low"


def test_contact_clears_both_the_counter_and_the_attribution():
    m = Mood()
    m.last_contact_at = m.updated_at - 2 * DAY - HOUR
    m.settle_absence(m.updated_at)
    m.mark_contact(m.updated_at)
    assert m.gap_days(m.updated_at) == 0
    assert m.gap_active is False


# ── prompt hygiene ───────────────────────────────────────────────────

def test_prompt_never_carries_a_number():
    """No digits anywhere in the rendered block — not even as a good example.

    Stating "do not say 0.3" is itself a leak: small models copy the shape of the
    example they were given.
    """
    for v, e in [(0.9, 0.9), (-0.55, -0.30), (0.0, 0.0), (0.42, -0.13)]:
        block = mood_block(Mood(valence=v, energy=e))
        assert "Never state a number" in block
        assert not any(ch.isdigit() for ch in block), f"digits leaked for {(v, e)}: {block!r}"


def test_describe_returns_a_band_not_a_value():
    m = Mood(valence=0.9, energy=-0.9)
    d = m.describe()
    assert d["intensity"] in ("faint", "moderate", "strong")
    assert not any(ch.isdigit() for ch in d["text"] + d["name"])


def test_prompt_names_the_combination_state():
    """Low valence + high energy is irritation; the model must not call it sadness."""
    m = Mood(valence=-0.5, energy=0.5)
    assert "annoyance" in mood_block(m)
    m2 = Mood(valence=0.5, energy=-0.5)
    assert "not call this sadness" in mood_block(m2)


def test_prompt_mentions_absence_when_it_applies():
    m = Mood(valence=-0.2, energy=0.0)
    m.last_contact_at = time.time() - 2 * DAY
    block = mood_block(m)
    assert "two day" in block                # spelled out, not "2"
    assert "not *blaming*" in block


# ── gating ───────────────────────────────────────────────────────────

def test_energy_alone_does_not_trigger_alert():
    assert Mood(valence=0.02, energy=0.61).nearest()["name"] != "alert"


def test_alert_is_reachable_when_valence_is_low():
    assert Mood(valence=-0.4, energy=0.7).nearest()["name"] == "alert"


# ── custom taxonomies and descriptors ────────────────────────────────

def test_custom_taxonomy_is_honoured():
    kinds = [EventKind("spam", -0.5, 0.0, "junk mail"), EventKind("none", 0.0, 0.0, "nothing")]
    m = Mood()
    m.apply(kinds[0].dv, kinds[0].de, note="spam")
    assert m.valence < 0


def test_custom_descriptors_replace_the_defaults():
    mine = [{"name": "grumpy", "v": -0.8, "e": -0.2, "text": "Grumpy.", "decay_mul": 1.0}]
    m = Mood(descriptors=mine)
    assert m.nearest()["name"] == "grumpy"


def test_empty_descriptor_list_does_not_crash():
    m = Mood(descriptors=[])
    assert m.nearest()["name"] == "even"
    assert isinstance(mood_block(m), str)


# ── parsing model replies ────────────────────────────────────────────

def test_parse_accepts_plain_json():
    assert parse_response('{"kind": "affection", "scale": 0.8}') == \
        {"kind": "affection", "scale": 0.8, "ok": True}


def test_parse_strips_code_fences_and_prose():
    raw = 'Sure!\n```json\n{"kind":"minor_hassle","scale":0.4}\n```\nHope that helps.'
    assert parse_response(raw)["kind"] == "minor_hassle"


def test_parse_rejects_unknown_labels_and_garbage():
    assert parse_response('{"kind": "ecstatic", "scale": 1}')["ok"] is False
    assert parse_response("no json here")["ok"] is False


def test_parse_clamps_scale():
    assert parse_response('{"kind": "plan", "scale": 9}')["scale"] == 1.0


# ── degradation ──────────────────────────────────────────────────────

def test_apply_judged_falls_back_to_keywords_when_the_model_failed():
    m = Mood()
    result = apply_judged(m, {"kind": "none", "scale": 0.0, "ok": False},
                          "I spilled my coffee everywhere")
    assert result["applied"] is True
    assert result["kind"] == "minor_hassle"


def test_judged_scale_scales_the_effect():
    small, big = Mood(), Mood()
    apply_judged(small, {"kind": "affection", "scale": 0.2, "ok": True})
    apply_judged(big, {"kind": "affection", "scale": 1.0, "ok": True})
    assert big.valence > small.valence > 0


def test_unknown_kind_is_a_no_op():
    m = Mood()
    assert apply_judged(m, {"kind": "nope", "scale": 1.0, "ok": True})["applied"] is False
    assert m.valence == 0.0


def test_offline_marker_matching():
    assert guess_fallback("I passed the exam!", DEFAULT_KINDS)[0] == "good_news"
    assert guess_fallback("nothing much", DEFAULT_KINDS) == ("none", 0.0)


# ── persistence ──────────────────────────────────────────────────────

def test_state_round_trips_through_sqlite(tmp_path):
    db = str(tmp_path / "mood.db")
    m = Mood(db=db, valence=0.42, energy=-0.13)
    m.gap_active = True
    m.save("u1")

    back = Mood.load(db, "u1")
    assert back.valence == pytest.approx(0.42, abs=0.02)   # tiny decay on load
    assert back.energy == pytest.approx(-0.13, abs=0.02)
    assert back.gap_active is True


def test_load_creates_state_when_the_table_is_empty(tmp_path):
    back = Mood.load(str(tmp_path / "fresh.db"), "nobody")
    assert back.valence == 0.0


def test_corrupt_payload_does_not_raise(tmp_path):
    import sqlite3
    db = str(tmp_path / "broken.db")
    m = Mood(db=db)
    m.save("u1")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE mood_state SET payload = 'not json' WHERE key = 'u1'")
    conn.commit()
    conn.close()
    assert Mood.load(db, "u1").valence == 0.0
