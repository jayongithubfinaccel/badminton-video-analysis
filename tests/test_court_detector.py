"""Tests for court_detector.py's real-court-plane zone mapping.

Focused on court_coords_to_zone()/zone_from_court_coords() using the real
BWF short service line position for the front boundary, and the Phase
G.5-adjusted (not literal long-service-line) back boundary (docs/PRD_v2.6.md)
instead of equal thirds — the row-axis behavior that's unique to the
homography path, not covered by test_zone_grid.py's banding-function-level
tests.

Y-coordinates below are derived from zone_grid's own BACK_BAND_FRAC /
FRONT_BAND_FRAC rather than hardcoded, so this file can't silently drift out
of sync if those constants are tuned again.
"""

import cv2
import numpy as np

from src.pipeline.court_detector import (
    COURT_LENGTH,
    COURT_WIDTH,
    HALF_COURT_LENGTH,
    court_coords_to_zone,
    refine_corners_with_lines,
    zone_from_court_coords,
)
from src.pipeline.zone_grid import BACK_BAND_FRAC, FRONT_BAND_FRAC

assert HALF_COURT_LENGTH == COURT_LENGTH / 2 == 670

# Absolute y-coordinates of the two row-band boundaries, for each half.
# Top half: net_axis_frac = y / HALF_COURT_LENGTH (0=baseline, 1=net).
_TOP_FRONT_Y = HALF_COURT_LENGTH * FRONT_BAND_FRAC  # ~472: literal short service line
_TOP_BACK_Y = HALF_COURT_LENGTH * BACK_BAND_FRAC  # ~155.2: Phase G.5-adjusted
# Bottom half: net_axis_frac = 1 - (y - HALF_COURT_LENGTH) / HALF_COURT_LENGTH.
_BOTTOM_FRONT_Y = HALF_COURT_LENGTH + HALF_COURT_LENGTH * (1.0 - FRONT_BAND_FRAC)  # ~868
_BOTTOM_BACK_Y = HALF_COURT_LENGTH + HALF_COURT_LENGTH * (1.0 - BACK_BAND_FRAC)  # ~1184.8

_LEFT_X, _CENTER_X, _RIGHT_X = COURT_WIDTH * 0.1, COURT_WIDTH * 0.5, COURT_WIDTH * 0.9


def test_top_half_back_zone_extends_past_the_literal_long_service_line():
    # Just inside the baseline -> back.
    assert court_coords_to_zone(_LEFT_X, 10.0, "top") == 3  # mirrored: screen-left -> zone 3
    # 100cm depth from baseline is PAST the literal long service line (76cm)
    # but still inside the Phase G.5-adjusted back band (~155.2cm) -> still back.
    assert court_coords_to_zone(_LEFT_X, 100.0, "top") == 3
    # Just past the adjusted boundary -> now mid.
    assert court_coords_to_zone(_LEFT_X, _TOP_BACK_Y + 5.0, "top") == 6


def test_top_half_front_zone_starts_at_short_service_line():
    assert court_coords_to_zone(_LEFT_X, _TOP_FRONT_Y - 5.0, "top") == 6  # still mid
    assert court_coords_to_zone(_LEFT_X, _TOP_FRONT_Y + 5.0, "top") == 9  # now front


def test_bottom_half_front_zone_starts_at_short_service_line():
    # For the bottom half, LOWER y is closer to the net (front); the short
    # service line sits at y=_BOTTOM_FRONT_Y, so just below it is still
    # front, and just past it (further from net) drops into mid.
    assert court_coords_to_zone(_LEFT_X, _BOTTOM_FRONT_Y - 5.0, "bottom") == 7  # front
    assert court_coords_to_zone(_LEFT_X, _BOTTOM_FRONT_Y + 5.0, "bottom") == 4  # now mid

    # (front-most for bottom half is zone 7/8/9, nearest net at low y)
    assert court_coords_to_zone(_CENTER_X, HALF_COURT_LENGTH + 1.0, "bottom") == 8


def test_bottom_half_back_zone_extends_past_the_literal_long_service_line():
    assert court_coords_to_zone(_CENTER_X, COURT_LENGTH - 5.0, "bottom") == 2  # inside back band
    # 100cm depth from baseline (COURT_LENGTH-100) is past the literal long
    # service line but still inside the adjusted back band -> still back.
    assert court_coords_to_zone(_CENTER_X, COURT_LENGTH - 100.0, "bottom") == 2
    assert court_coords_to_zone(_CENTER_X, _BOTTOM_BACK_Y - 5.0, "bottom") == 5  # still mid


def test_mid_zone_is_smaller_than_the_literal_bwf_span_but_still_the_largest_band():
    """Mid (short service line to the Phase G.5-adjusted back boundary) is
    20% shallower than the literal BWF short-to-long-service-line span, but
    still the largest of the three bands."""
    front_depth = HALF_COURT_LENGTH * (1.0 - FRONT_BAND_FRAC)
    back_depth = HALF_COURT_LENGTH * BACK_BAND_FRAC
    mid_depth = HALF_COURT_LENGTH - front_depth - back_depth

    assert mid_depth < 396.0  # literal BWF mid depth (short-to-long service line)
    assert mid_depth > front_depth
    assert mid_depth > back_depth

    midpoint_y = (_TOP_FRONT_Y + _TOP_BACK_Y) / 2
    assert court_coords_to_zone(_CENTER_X, midpoint_y, "top") == 5


def test_zone_from_court_coords_picks_the_half_from_y():
    half, zone = zone_from_court_coords(_CENTER_X, 200.0)
    assert half == "top"
    half, zone = zone_from_court_coords(_CENTER_X, 900.0)
    assert half == "bottom"


def test_out_of_half_returns_zero():
    # A "top" half point queried with player_half="bottom" is out of range.
    assert court_coords_to_zone(_CENTER_X, 200.0, "bottom") == 0


def _draw_rectangular_court(true_corners, thickness=3):
    """A synthetic axis-aligned white-on-green court boundary, so
    refine_corners_with_lines() has real Hough-detectable lines to snap to
    without needing a real broadcast frame."""
    frame = np.zeros((400, 400, 3), dtype=np.uint8)
    frame[:, :] = (0, 140, 0)  # green (BGR)
    tl, tr, br, bl = [tuple(int(v) for v in p) for p in true_corners]
    white = (255, 255, 255)
    cv2.line(frame, tl, tr, white, thickness)
    cv2.line(frame, tr, br, white, thickness)
    cv2.line(frame, br, bl, white, thickness)
    cv2.line(frame, bl, tl, white, thickness)
    return frame


def test_refine_corners_snaps_shifted_coarse_corners_to_the_true_lines():
    true_corners = np.array([[50, 50], [350, 50], [350, 350], [50, 350]], dtype=np.float32)
    frame = _draw_rectangular_court(true_corners)

    # Simulate a coarse green-mask estimate that overshot outward by ~12px
    # on every edge (a plausible real failure mode — see docs/PRD_v2.6.md).
    shift = np.array([[-12, -12], [12, -12], [12, 12], [-12, 12]], dtype=np.float32)
    coarse_corners = true_corners + shift

    refined = refine_corners_with_lines(frame, coarse_corners)

    # Refined corners should land much closer to the true boundary than
    # the coarse (shifted) estimate did.
    coarse_error = np.linalg.norm(coarse_corners - true_corners, axis=1).mean()
    refined_error = np.linalg.norm(refined - true_corners, axis=1).mean()
    assert refined_error < coarse_error
    assert refined_error < 3.0  # sub-pixel-ish snap onto a thick, clean line


def test_refine_corners_falls_back_when_no_lines_present():
    coarse_corners = np.array([[50, 50], [350, 50], [350, 350], [50, 350]], dtype=np.float32)
    blank_green_frame = np.zeros((400, 400, 3), dtype=np.uint8)
    blank_green_frame[:, :] = (0, 140, 0)  # no white lines anywhere

    refined = refine_corners_with_lines(blank_green_frame, coarse_corners)

    np.testing.assert_array_equal(refined, coarse_corners)


def test_refine_corners_ignores_an_implausibly_large_snap():
    true_corners = np.array([[50, 50], [350, 50], [350, 350], [50, 350]], dtype=np.float32)
    frame = _draw_rectangular_court(true_corners)

    # A coarse estimate wildly off from the true boundary (e.g. a
    # misdetection) should not get "corrected" into the true corners —
    # that would silently paper over a bad upstream detection instead of
    # surfacing it as a rejected/None case.
    coarse_corners = np.array([[150, 150], [250, 150], [250, 250], [150, 250]], dtype=np.float32)

    refined = refine_corners_with_lines(frame, coarse_corners)

    np.testing.assert_array_equal(refined, coarse_corners)
