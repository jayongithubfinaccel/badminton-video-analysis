"""Adaptive court calibration — derive play-area bounds and the net line from
observed player positions, instead of fixed frame-ratio constants.

This replaces the hardcoded `court_top/bottom/left/right` ratios that
previously lived in config.py / shot_detector.py / zone_mapper.py and were
tuned to one specific video's camera framing. Those ratios produced a
collapsed, implausible zone distribution the moment the camera framing or
resolution changed (see docs/PRD_v2.3.md, Section 14.3).
"""

from dataclasses import dataclass

import cv2
import numpy as np

from src.pipeline.court_detector import (
    calibrate_homography,
    pixel_to_court_coords,
    zone_from_court_coords,
)
from src.pipeline.player_detector import detect_players


@dataclass
class CourtCalibration:
    """Per-video play-area bounds derived from where players were observed.

    If a validated homography was found (see calibrate_homography in
    court_detector.py, built from the actual court boundary line, not
    player positions), zone_for() uses that instead — it's a real
    perspective-correct coordinate system rather than a proportional grid
    fitted to where players happened to stand. The proportional grid below
    remains the fallback when court-line detection isn't reliable enough
    for a given video.
    """

    top: float
    bottom: float
    left: float
    right: float
    net_y: float
    frame_width: int
    frame_height: int
    samples_used: int
    far_home: tuple[float, float] = (0.0, 0.0)
    near_home: tuple[float, float] = (0.0, 0.0)
    homography: np.ndarray | None = None
    homography_samples: int = 0

    def in_bounds(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def home_for(self, receive_by: int) -> tuple[float, float]:
        """receive_by 1 = far/top court, 2 = near/bottom court."""
        return self.far_home if receive_by == 1 else self.near_home

    def zone_for(self, x: float, y: float) -> tuple[str, int]:
        """Map a pixel position to (half, zone 1-9).

        Uses the homography (real court-line geometry) when available and
        validated; otherwise falls back to this calibration's
        player-position-derived bounds and net line.
        """
        if self.homography is not None:
            court_pos = pixel_to_court_coords((x, y), self.homography)
            if court_pos is not None:
                half, zone = zone_from_court_coords(*court_pos)
                if zone > 0:
                    return half, zone
                # Point fell outside the detected court entirely (e.g. a
                # player chasing a shot beyond the lines) — fall through to
                # the proportional grid rather than returning an invalid zone.

        col_frac = (x - self.left) / max(1.0, (self.right - self.left))
        col_frac = max(0.0, min(1.0, col_frac))
        col = 0 if col_frac < 1 / 3 else (1 if col_frac < 2 / 3 else 2)

        if y < self.net_y:
            half = "top"
            span = max(1.0, self.net_y - self.top)
            rel = max(0.0, min(1.0, (y - self.top) / span))
            # far player: rel near 0 = baseline (back), rel near 1 = net (front)
            row = 0 if rel < 1 / 3 else (1 if rel < 2 / 3 else 2)
        else:
            half = "bottom"
            span = max(1.0, self.bottom - self.net_y)
            rel = max(0.0, min(1.0, (y - self.net_y) / span))
            # near player: rel near 0 = net (front), rel near 1 = baseline (back)
            row = 2 if rel < 1 / 3 else (1 if rel < 2 / 3 else 0)

        zone = row * 3 + col + 1
        return half, zone


def calibrate_from_video(
    cap: cv2.VideoCapture,
    frame_width: int,
    frame_height: int,
    total_frames: int,
    fps: float,
    sample_stride_sec: float = 1.0,
    margin_frac: float = 0.06,
    rally_ranges: list[tuple[int, int]] | None = None,
    use_homography: bool = False,
) -> CourtCalibration:
    """Sample frames, detect both players, and derive the active court bounds
    + net line from their observed positions. Can also detect the real court
    boundary (white lines) and compute a homography from it (see
    court_detector.calibrate_homography) — mathematically that's the more
    "correct" coordinate system, and it IS wired into CourtCalibration.zone_for
    to take priority when present. It defaults to OFF here (use_homography=False)
    based on an empirical finding, not a guess:

    Using a standing player's *foot position* as input to a ground-plane
    homography from a single elevated camera has a known failure mode —
    perspective foreshortening means a few pixels of foot-detection noise
    near the far baseline corresponds to a large real-world distance error,
    and a person's height (vs. the camera's elevated angle) systematically
    biases the detected foot point away from their true ground-contact
    point. Tested empirically against this project's ground truth: enabling
    homography for this specific use (player-position-as-shuttle-proxy) made
    "front" zone predictions disappear almost entirely (the opposite of what
    we wanted), because that systematic bias pushes points toward the
    baseline. The proportional, player-position-percentile grid below
    doesn't have this failure mode for this purpose, and was the better
    choice on every distributional metric. See docs/RESULTS.md "Phase C.1"
    for the full comparison. Homography remains available (and correctly
    implemented — the old detect_court_corners had a separate, now-fixed bug
    of its own) for future use where it doesn't carry this proxy-specific
    bias, e.g. Phase D mapping real shuttle positions instead of player feet.

    Args:
        rally_ranges: if given, only sample within these (start_frame,
            end_frame) windows. This is important — without it, sampling
            blindly across the whole video picks up replay cuts, close-ups,
            and crowd shots between rallies, which pollute the calibration
            with non-court player positions (confirmed empirically: this
            produced a near-full-frame, unusable calibration on a test video
            before this fix). If omitted, samples the whole video.

    Uses the 5th/95th percentile of observed positions rather than raw
    min/max, so a handful of misdetections (occlusion, motion blur) don't
    blow out the bounds.

    Falls back to a generous full-frame box (not a video-specific ratio) if
    too few confident player detections are found, so behavior degrades
    gracefully instead of silently mis-calibrating to a different video's
    geometry.
    """
    stride = max(1, int(fps * sample_stride_sec))
    far_x: list[float] = []
    far_y: list[float] = []
    near_x: list[float] = []
    near_y: list[float] = []

    ranges = rally_ranges if rally_ranges else [(0, total_frames)]

    for start, end in ranges:
        for frame_idx in range(start, min(end, total_frames), stride):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            players = detect_players(frame)
            if len(players) == 2:
                far, near = players  # already sorted top-to-bottom
                fx, fy = far.foot_point
                nx, ny = near.foot_point
                far_x.append(fx)
                far_y.append(fy)
                near_x.append(nx)
                near_y.append(ny)

    homography, hom_samples = (None, 0)
    if use_homography:
        homography, hom_samples = calibrate_homography(
            cap, fps, total_frames, rally_ranges=rally_ranges
        )

    if len(far_y) < 5 or len(near_y) < 5:
        margin_x = frame_width * 0.05
        margin_y = frame_height * 0.05
        return CourtCalibration(
            top=margin_y,
            bottom=frame_height - margin_y,
            left=margin_x,
            right=frame_width - margin_x,
            net_y=frame_height / 2.0,
            frame_width=frame_width,
            frame_height=frame_height,
            samples_used=0,
            homography=homography,
            homography_samples=hom_samples,
        )

    margin_y = frame_height * margin_frac
    margin_x = frame_width * margin_frac
    xs = far_x + near_x

    far_y_lo = float(np.percentile(far_y, 5))
    near_y_hi = float(np.percentile(near_y, 95))
    xs_lo = float(np.percentile(xs, 5))
    xs_hi = float(np.percentile(xs, 95))

    top = max(0.0, far_y_lo - margin_y)
    bottom = min(float(frame_height), near_y_hi + margin_y)
    left = max(0.0, xs_lo - margin_x)
    right = min(float(frame_width), xs_hi + margin_x)

    # Net line: where the far player's deepest forward reach and the near
    # player's deepest forward reach meet — i.e. the midpoint of the gap
    # between the two players' observed movement ranges.
    far_y_hi = float(np.percentile(far_y, 95))
    near_y_lo = float(np.percentile(near_y, 5))
    net_y = (far_y_hi + near_y_lo) / 2.0

    # Each player's "home"/ready-stance position — the median of where they
    # were observed, used as the reference point for lunge-apex detection
    # (the frame where a player is furthest from home is a much better
    # contact-position proxy than their position at a single fixed frame).
    far_home = (float(np.median(far_x)), float(np.median(far_y)))
    near_home = (float(np.median(near_x)), float(np.median(near_y)))

    return CourtCalibration(
        top=top,
        bottom=bottom,
        left=left,
        right=right,
        net_y=net_y,
        frame_width=frame_width,
        frame_height=frame_height,
        samples_used=len(far_y),
        far_home=far_home,
        near_home=near_home,
        homography=homography,
        homography_samples=hom_samples,
    )
