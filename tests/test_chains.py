"""Line loads that follow on end to end (polylines) drawn as one load."""

import pytest

import beamz9000 as bz
from beamz9000.diagram.compose import line_chains, load_bands
from beamz9000.graphics.elements import Text, flatten
from beamz9000.spec import from_scheme


def _spec(loads, spans=(10.0,)):
    return from_scheme(bz.parse_scheme({"B": {"spans": list(spans), "loads": loads}})["B"])


def _dist(x1, x2, w1, w2, **kw):
    return {"dist": {"x1": x1, "x2": x2, "mag1": w1, "mag2": w2, **kw}}


POLYLINE = [_dist(0, 2, 2.0, 3.0), _dist(2, 5, 3.0, 6.0), _dist(5, 7, 6.0, 4.0), _dist(7, 10, 4.0, 4.0)]


def _chains(spec):
    return [len(c) for c in line_chains(list(spec.loads), 1e-6 * spec.length)]


def test_a_polyline_is_one_chain():
    assert _chains(_spec(POLYLINE)) == [4]


@pytest.mark.parametrize("loads, expected", [
    ([_dist(0, 2, 2.0, 3.0), _dist(2, 5, 4.0, 6.0)], [1, 1]),           # A step in magnitude
    ([_dist(0, 2, 2.0, 3.0), _dist(2.5, 5, 3.0, 6.0)], [1, 1]),         # A gap
    ([_dist(0, 2, 2.0, 3.0, case="D"), _dist(2, 5, 3.0, 6.0, case="L")], [1, 1]),  # Other cases
    ([_dist(0, 2, 1.0, 1.0, label="J1"), _dist(2, 5, 1.0, 1.0, label="J2")], [1, 1]),  # Own labels
    ([_dist(0, 2, -2.0, -3.0), _dist(2, 5, 3.0, 6.0)], [1, 1]),          # Up, then down
])
def test_loads_that_do_not_chain(loads, expected):
    assert _chains(_spec(loads)) == expected


def test_a_chain_is_drawn_in_one_row_with_labels_that_fit():
    spec = _spec(POLYLINE)
    band = load_bands(spec, bz.Layout()).children[0]
    assert len(band.children) == 1  # One load, so one row.
    texts = [t for t in flatten(band) if isinstance(t, Text)]
    # The ends, then the bends, largest first, where they fit: the peak of 6
    # and the 3 at 2 m. The level 4 from 7 m to the end is labelled once.
    assert [t.text for t in texts] == ["2", "4", "6", "3"]
    for a in texts:
        for b in texts:
            if a is not b:
                ax0, ay0, ax1, ay1 = a.bounds
                bx0, by0, bx1, by1 = b.bounds
                assert ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0


def test_a_uniform_chain_has_one_label():
    spec = _spec([_dist(0, 4, 3.0, 3.0), _dist(4, 10, 3.0, 3.0)])
    band = load_bands(spec, bz.Layout()).children[0]
    assert [t.text for t in flatten(band) if isinstance(t, Text)] == ["3"]


def test_chained_loads_still_analyse_as_given():
    pytest.importorskip("pycba_tools")
    from beamz9000 import analysis

    beam = bz.parse_scheme({"B": {"spans": [10.0], "loads": POLYLINE}})["B"]
    total = sum(r.fy for r in analysis.analyze(beam).reactions)
    assert total == pytest.approx(2 * 2.5 + 3 * 4.5 + 2 * 5.0 + 3 * 4.0)
