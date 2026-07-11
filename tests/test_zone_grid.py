"""Tests for the canonical 9-zone numbering (zone_grid.py, docs/PRD_v2.5.md).

The whole point of this module is to be the one place the top/bottom
column-mirror rule lives, so these tests pin it down against
badminton_court_9zone.png (the project's reference image) explicitly,
cell by cell — this is the exact bug (missing mirror for the "top" half)
that survived three separate, duplicated implementations across four
phases before being caught visually.
"""

import pytest

from src.pipeline.zone_grid import (
    BACK_BAND_FRAC,
    FRONT_BAND_FRAC,
    _band,
    _row_band_real,
    zone_for_bands,
    zone_number,
    zone_number_real,
)

# Reference layout (badminton_court_9zone.png), screen left-to-right per row.
TOP_HALF_SCREEN_LTR = {
    0: [3, 2, 1],  # back row (nearest top-of-frame baseline)
    1: [6, 5, 4],  # mid row
    2: [9, 8, 7],  # front row (nearest net)
}
BOTTOM_HALF_SCREEN_LTR = {
    2: [7, 8, 9],  # front row (nearest net) -- net_axis_band 2
    1: [4, 5, 6],  # mid row
    0: [1, 2, 3],  # back row (nearest bottom-of-frame baseline) -- net_axis_band 0
}


@pytest.mark.parametrize("net_axis_band", [0, 1, 2])
@pytest.mark.parametrize("side_axis_band", [0, 1, 2])
def test_top_half_matches_reference_image(net_axis_band, side_axis_band):
    expected = TOP_HALF_SCREEN_LTR[net_axis_band][side_axis_band]
    assert zone_for_bands(net_axis_band, side_axis_band, "top") == expected


@pytest.mark.parametrize("net_axis_band", [0, 1, 2])
@pytest.mark.parametrize("side_axis_band", [0, 1, 2])
def test_bottom_half_matches_reference_image(net_axis_band, side_axis_band):
    expected = BOTTOM_HALF_SCREEN_LTR[net_axis_band][side_axis_band]
    assert zone_for_bands(net_axis_band, side_axis_band, "bottom") == expected


def test_each_half_covers_all_nine_zones_exactly_once():
    for half in ("top", "bottom"):
        zones = {
            zone_for_bands(row, col, half) for row in range(3) for col in range(3)
        }
        assert zones == set(range(1, 10))


def test_band_thresholds():
    assert _band(0.0) == 0
    assert _band(0.32) == 0
    assert _band(1 / 3) == 1
    assert _band(0.5) == 1
    assert _band(2 / 3) == 2
    assert _band(0.99) == 2
    assert _band(1.0) == 2


def test_band_clamps_out_of_range_fractions():
    assert _band(-5.0) == 0
    assert _band(5.0) == 2


def test_zone_number_delegates_through_band_and_mirror():
    # side_axis_frac=0.1 (band 0, on-screen-left), net_axis_frac=0.1 (band 0, own baseline)
    assert zone_number(0.1, 0.1, "top") == 3  # mirrored: on-screen-left -> zone 3
    assert zone_number(0.1, 0.1, "bottom") == 1  # not mirrored

    # side_axis_frac=0.9 (band 2, on-screen-right), net_axis_frac=0.9 (band 2, near net)
    assert zone_number(0.9, 0.9, "top") == 7
    assert zone_number(0.9, 0.9, "bottom") == 9


def test_band_fracs_are_asymmetric_and_bwf_derived():
    """BACK_BAND_FRAC (long service line, 76cm from baseline / 670cm depth)
    and FRONT_BAND_FRAC (short service line, 198cm from net / 670cm depth)
    should NOT be the 1/3, 2/3 of equal-thirds banding — that's the whole
    point of this refinement (docs/PRD_v2.6.md).
    """
    assert BACK_BAND_FRAC == pytest.approx(76.0 / 670.0)
    assert FRONT_BAND_FRAC == pytest.approx(1.0 - 198.0 / 670.0)
    assert BACK_BAND_FRAC < 1 / 3
    assert FRONT_BAND_FRAC > 2 / 3
    # back+mid+front bands must still partition [0, 1] with no gap/overlap
    assert 0.0 < BACK_BAND_FRAC < FRONT_BAND_FRAC < 1.0


def test_row_band_real_thresholds():
    assert _row_band_real(0.0) == 0  # own baseline -> back
    assert _row_band_real(BACK_BAND_FRAC - 0.001) == 0
    assert _row_band_real(BACK_BAND_FRAC + 0.001) == 1
    assert _row_band_real(0.5) == 1  # deep in mid court
    assert _row_band_real(FRONT_BAND_FRAC - 0.001) == 1
    assert _row_band_real(FRONT_BAND_FRAC + 0.001) == 2
    assert _row_band_real(1.0) == 2  # at the net -> front


def test_row_band_real_clamps_out_of_range_fractions():
    assert _row_band_real(-5.0) == 0
    assert _row_band_real(5.0) == 2


@pytest.mark.parametrize("net_axis_band", [0, 1, 2])
@pytest.mark.parametrize("side_axis_band", [0, 1, 2])
def test_zone_number_real_matches_zone_for_bands(net_axis_band, side_axis_band):
    """zone_number_real must agree with zone_for_bands at the center of each
    real-BWF band, for both halves — same coverage as the equal-thirds
    zone_number tests above, just through the BWF-derived thresholds.
    """
    band_reps = {0: BACK_BAND_FRAC / 2, 1: (BACK_BAND_FRAC + FRONT_BAND_FRAC) / 2,
                 2: (FRONT_BAND_FRAC + 1.0) / 2}
    net_axis_frac = band_reps[net_axis_band]
    side_axis_frac = [0.1, 0.5, 0.9][side_axis_band]

    for half in ("top", "bottom"):
        expected = zone_for_bands(net_axis_band, side_axis_band, half)
        assert zone_number_real(net_axis_frac, side_axis_frac, half) == expected


def test_zone_number_real_differs_from_equal_thirds_zone_number_near_boundaries():
    """A point just past the short service line (front-band boundary under
    the real BWF fractions) sits in a DIFFERENT band than equal-thirds would
    put it — this is the concrete behavior change this refinement makes.
    """
    frac = 0.75  # past 2/3 (equal-thirds front) AND past FRONT_BAND_FRAC (~0.7045)
    assert zone_number(frac, 0.5, "bottom") == zone_number_real(frac, 0.5, "bottom")

    frac = 0.68  # past equal-thirds' 2/3 boundary, but NOT past FRONT_BAND_FRAC
    assert zone_number(frac, 0.5, "bottom") != zone_number_real(frac, 0.5, "bottom")
