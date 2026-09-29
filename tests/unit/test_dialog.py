"""Dialog merge/minimize tests."""

from __future__ import annotations

from a_wizard.application.dialog import (
    apply_speaker_map,
    default_speaker_glyph,
    merge_by_time,
    minimize_segments,
)
from a_wizard.domain.models import Segment


def test_merge_and_minimize_fixed_ids():
    a = [
        Segment(0, 1000, "hello", "SPEAKER_T0D0"),
        Segment(2000, 3000, "again", "SPEAKER_T0D0"),
    ]
    b = [Segment(500, 1500, "hi", "SPEAKER_T1")]
    merged = merge_by_time(a, b)
    assert [s.speaker for s in merged] == ["SPEAKER_T0D0", "SPEAKER_T1", "SPEAKER_T0D0"]
    text = minimize_segments(merged, {})
    assert "[ST0D0]: SPEAKER_T0D0" in text
    assert "[ST1]: SPEAKER_T1" in text
    body = text.split("\n\n", 1)[-1]
    assert "–" not in body
    assert "[ST0D0]: hello again" in body or "[ST0D0]: hello" in body


def test_legacy_speaker_map_still_applies():
    a = [Segment(0, 1000, "hello", "SPEAKER_T0D0")]
    mapped = apply_speaker_map(a, {"SPEAKER_T0D0": "__MANAGER__"})
    assert mapped[0].speaker == "__MANAGER__"


def test_default_glyph_short_form():
    g = default_speaker_glyph("SPEAKER_T2D1", 0, set())
    assert g == "[ST2D1]"


def test_minimize_with_start_timestamps():
    segs = [
        Segment(0, 1000, "hello", "SPEAKER_T0"),
        Segment(1500, 2000, "again", "SPEAKER_T0"),
        Segment(2500, 3000, "hi", "SPEAKER_T1"),
    ]
    text = minimize_segments(segs, {}, include_start_ts=True)
    assert "[ST0]: SPEAKER_T0" in text
    assert "[ST1]: SPEAKER_T1" in text
    body = text.split("\n\n", 1)[-1]
    assert "–" not in body
    assert "[00:00:00.000] [ST0]: hello again" in body
    assert "[00:00:02.500] [ST1]: hi" in body
    untimed = minimize_segments(segs, {})
    timed_body = [ln for ln in body.splitlines() if ln]
    plain_body = [ln for ln in untimed.split("\n\n", 1)[-1].splitlines() if ln]
    stripped = [ln.split("] ", 1)[1] for ln in timed_body]
    assert stripped == plain_body
