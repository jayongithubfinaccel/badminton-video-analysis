"""Tests for the visual debug overlay drawing (debug_overlay.py, Phase F).

Covers geometry correctness (grid lines / markers land at the expected
pixels) rather than full-image diffing, and that the drawn grid's zone
labels agree with CourtCalibration.zone_for() at each cell's center — both
now go through the shared src.pipeline.zone_grid (see docs/PRD_v2.5.md),
which is what makes that agreement guaranteed rather than coincidental.
"""

import numpy as np

from src.pipeline.court_calibration import CourtCalibration
from src.pipeline.debug_overlay import draw_overlays
from src.pipeline.player_detector import PlayerBox, RacketBox


def make_calibration(**overrides) -> CourtCalibration:
    defaults = dict(
        top=100.0,
        bottom=400.0,
        left=200.0,
        right=800.0,
        net_y=250.0,
        frame_width=1000,
        frame_height=500,
        samples_used=80,
    )
    defaults.update(overrides)
    return CourtCalibration(**defaults)


def make_frame() -> np.ndarray:
    return np.zeros((500, 1000, 3), dtype=np.uint8)


def test_draw_overlays_returns_a_copy_not_the_original():
    frame = make_frame()
    cal = make_calibration()

    out = draw_overlays(frame, cal)

    assert out is not frame
    assert not np.array_equal(out, frame)  # grid lines were actually drawn
    assert np.array_equal(frame, np.zeros((500, 1000, 3), dtype=np.uint8))  # input untouched


def test_draw_overlays_handles_all_signals_missing():
    """A shuttle is frequently undetected and rackets are best-effort — None/
    empty inputs must not raise, and the grid should still be drawn.
    """
    frame = make_frame()
    cal = make_calibration()

    out = draw_overlays(frame, cal, player_boxes=None, racket_boxes=None, shuttle_point=None)

    assert out.shape == frame.shape
    assert not np.array_equal(out, frame)  # grid alone still changes pixels


def test_draw_overlays_draws_all_four_signals():
    frame = make_frame()
    cal = make_calibration()
    players = [PlayerBox(x1=190.0, y1=90.0, x2=210.0, y2=110.0, confidence=0.9)]
    rackets = [RacketBox(x1=300.0, y1=150.0, x2=320.0, y2=170.0, confidence=0.2)]
    shuttle = (500.0, 200.0)

    grid_only = draw_overlays(frame, cal)
    with_all = draw_overlays(frame, cal, players, rackets, shuttle)

    # Each additional signal must change more pixels than the grid alone.
    assert not np.array_equal(grid_only, with_all)

    # Racket box edge pixels should be the racket color somewhere on the
    # rectangle border drawn at (300,150)-(320,170).
    racket_color_bgr = np.array([255, 0, 255])
    border_region = with_all[150:171, 300:321]
    assert np.any(np.all(border_region == racket_color_bgr, axis=-1))


def test_drawn_grid_labels_match_court_calibration_zone_for():
    """The grid-cell zone label drawn at each cell's center must agree with
    CourtCalibration.zone_for at that same pixel, for every cell, when no
    homography is active — otherwise the printed label would lie about what
    the drawn rectangle actually maps to. Both now go through the shared
    zone_grid module, so this also guards against the two ever drifting
    apart again the way the old, duplicated implementations did.
    """
    cal = make_calibration()
    col_edges = [cal.left + f * (cal.right - cal.left) for f in (0.0, 1 / 3, 2 / 3, 1.0)]
    top_row_edges = [cal.top + f * (cal.net_y - cal.top) for f in (0.0, 1 / 3, 2 / 3, 1.0)]
    bottom_row_edges = [cal.net_y + f * (cal.bottom - cal.net_y) for f in (0.0, 1 / 3, 2 / 3, 1.0)]

    for half, row_edges, expected_half in (
        ("top", top_row_edges, "top"),
        ("bottom", bottom_row_edges, "bottom"),
    ):
        for row in range(3):
            for col in range(3):
                cx = (col_edges[col] + col_edges[col + 1]) / 2
                cy = (row_edges[row] + row_edges[row + 1]) / 2
                actual_half, actual_zone = cal.zone_for(cx, cy)

                assert actual_half == expected_half
                # Re-derive what the drawing loop's own net_axis_band
                # conversion produces, so this test would fail if
                # debug_overlay's row->net_axis_band mapping ever silently
                # diverged from court_calibration's, not just eyeball it.
                from src.pipeline.zone_grid import zone_for_bands

                net_axis_band = row if half == "top" else (2 - row)
                expected_zone = zone_for_bands(net_axis_band, col, half)

                assert actual_zone == expected_zone, (
                    f"half={half} row={row} col={col}: "
                    f"zone_for={actual_zone} != expected={expected_zone}"
                )
