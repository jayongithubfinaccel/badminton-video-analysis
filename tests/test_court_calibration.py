"""Tests for the shuttle-position row-axis recalibration (court_calibration.py).

Covers recalibrate_from_shuttle_positions(): the second-pass fix that
re-derives top/bottom/net_y from real TrackNetV3 shuttle landing positions
instead of the player-foot-derived values calibrate_from_video() must use
before any shot exists (see that function's docstring for the root-cause
rationale — a visual audit found the player-foot-derived back-row boundary
sits only ~3px from the real baseline, off the actual court surface).
"""

import numpy as np
import pytest

from src.pipeline.court_calibration import CourtCalibration, recalibrate_from_shuttle_positions


def make_calibration(**overrides) -> CourtCalibration:
    defaults = dict(
        top=100.0,
        bottom=450.0,
        left=250.0,
        right=650.0,
        net_y=350.0,
        frame_width=908,
        frame_height=480,
        samples_used=80,
    )
    defaults.update(overrides)
    return CourtCalibration(**defaults)


def test_too_few_samples_returns_original_calibration_unchanged():
    """Fewer than 5 real-shuttle samples on either half is not enough to
    compute a stable percentile — must fall back to the original
    calibration object itself (not a copy), mirroring calibrate_from_video's
    own too-few-samples posture.
    """
    calibration = make_calibration()
    # Only 3 far-side samples, 10 near-side — far side is under the floor.
    samples = [(1, 400.0, y) for y in [90.0, 95.0, 100.0]]
    samples += [(2, 400.0, y) for y in range(400, 410)]

    result = recalibrate_from_shuttle_positions(calibration, samples)

    assert result is calibration


def test_recalibrates_top_bottom_net_y_from_shuttle_percentiles():
    """With enough samples on both halves and alpha=1.0 (default), the new
    bounds should match the documented formula exactly: percentile of the
    real shuttle Y values, pushed out by margin_frac * frame_height.
    """
    calibration = make_calibration()
    far_y = [80.0, 85.0, 88.0, 90.0, 92.0, 95.0, 98.0, 100.0, 105.0, 110.0]
    near_y = [370.0, 380.0, 385.0, 390.0, 395.0, 400.0, 405.0, 410.0, 415.0, 420.0]
    samples = [(1, 300.0, y) for y in far_y] + [(2, 300.0, y) for y in near_y]

    result = recalibrate_from_shuttle_positions(calibration, samples)

    margin_y = calibration.frame_height * 0.10
    expected_top = max(0.0, float(np.percentile(far_y, 5)) - margin_y)
    expected_bottom = min(
        float(calibration.frame_height), float(np.percentile(near_y, 95)) + margin_y
    )
    expected_net_y = (float(np.percentile(far_y, 95)) + float(np.percentile(near_y, 5))) / 2.0

    assert result.top == pytest.approx(expected_top)
    assert result.bottom == pytest.approx(expected_bottom)
    assert result.net_y == pytest.approx(expected_net_y)


def test_leaves_left_right_and_other_fields_untouched():
    """This is a row-axis-only fix — column bounds and other calibration
    metadata must pass through unchanged.
    """
    calibration = make_calibration(
        left=111.0, right=777.0, far_home=(1.0, 2.0), near_home=(3.0, 4.0), samples_used=42
    )
    far_y = list(range(80, 100, 2))  # 10 samples
    near_y = list(range(380, 420, 4))  # 10 samples
    samples = [(1, 0.0, y) for y in far_y] + [(2, 0.0, y) for y in near_y]

    result = recalibrate_from_shuttle_positions(calibration, samples)

    assert result.left == calibration.left
    assert result.right == calibration.right
    assert result.far_home == calibration.far_home
    assert result.near_home == calibration.near_home
    assert result.samples_used == calibration.samples_used
    assert result.frame_width == calibration.frame_width
    assert result.frame_height == calibration.frame_height


def test_preserves_homography_on_the_recalibrated_result():
    """Homography (when present) must survive the recalibration unchanged —
    zone_for() tries homography first and only falls through to the
    proportional grid for off-court points, so this second pass should only
    tighten that fallback's own bounds, not silently disable the more
    accurate homography path.
    """
    calibration = make_calibration(homography=np.eye(3), homography_samples=50)
    far_y = list(range(80, 100, 2))
    near_y = list(range(380, 420, 4))
    samples = [(1, 0.0, y) for y in far_y] + [(2, 0.0, y) for y in near_y]

    result = recalibrate_from_shuttle_positions(calibration, samples)

    assert result.homography is not None
    np.testing.assert_array_equal(result.homography, np.eye(3))
    assert result.homography_samples == 50


def test_alpha_zero_reproduces_original_bounds():
    """alpha=0.0 should blend fully toward the original (unchanged) bounds,
    i.e. behave like a no-op on top/bottom/net_y.
    """
    calibration = make_calibration()
    far_y = list(range(50, 70, 2))
    near_y = list(range(430, 470, 4))
    samples = [(1, 0.0, y) for y in far_y] + [(2, 0.0, y) for y in near_y]

    result = recalibrate_from_shuttle_positions(calibration, samples, alpha=0.0)

    assert result.top == pytest.approx(calibration.top)
    assert result.bottom == pytest.approx(calibration.bottom)
    assert result.net_y == pytest.approx(calibration.net_y)


def test_ignores_shots_from_other_receive_by_values():
    """Only receive_by 1 (far/top) and 2 (near/bottom) are meaningful halves
    — the far/near split must not silently include garbage from an
    unexpected receive_by value.
    """
    calibration = make_calibration()
    far_y = list(range(80, 100, 2))
    near_y = list(range(380, 420, 4))
    samples = [(1, 0.0, y) for y in far_y] + [(2, 0.0, y) for y in near_y]
    # Bogus receive_by values that must be excluded from both percentile calcs.
    samples += [(3, 0.0, 5.0), (0, 0.0, 999.0)]

    result_with_garbage = recalibrate_from_shuttle_positions(calibration, samples)
    result_without_garbage = recalibrate_from_shuttle_positions(
        calibration, [(1, 0.0, y) for y in far_y] + [(2, 0.0, y) for y in near_y]
    )

    assert result_with_garbage.top == pytest.approx(result_without_garbage.top)
    assert result_with_garbage.bottom == pytest.approx(result_without_garbage.bottom)
    assert result_with_garbage.net_y == pytest.approx(result_without_garbage.net_y)
