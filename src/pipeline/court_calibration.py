"""Adaptive court calibration — derive play-area bounds and the net line from
observed player positions, instead of fixed frame-ratio constants.

This replaces the hardcoded `court_top/bottom/left/right` ratios that
previously lived in config.py / shot_detector.py / zone_mapper.py and were
tuned to one specific video's camera framing. Those ratios produced a
collapsed, implausible zone distribution the moment the camera framing or
resolution changed (see docs/PRD_v2.3.md, Section 14.3).
"""

from dataclasses import dataclass, replace

import cv2
import numpy as np

from src.pipeline.court_detector import (
    calibrate_homography,
    pixel_to_court_coords,
    zone_from_court_coords,
)
from src.pipeline.player_detector import detect_players
from src.pipeline.zone_grid import zone_number


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

        if y < self.net_y:
            half = "top"
            span = max(1.0, self.net_y - self.top)
            # far player: 0 = baseline (back), 1 = net (front)
            net_axis_frac = (y - self.top) / span
        else:
            half = "bottom"
            span = max(1.0, self.bottom - self.net_y)
            # near player: 0 = net (front), 1 = baseline (back) — inverted
            # relative to the top half so net_axis_frac always means
            # "0 = this half's own baseline, 1 = net" for zone_number.
            net_axis_frac = 1.0 - (y - self.net_y) / span

        zone = zone_number(net_axis_frac, col_frac, half)
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


def recalibrate_from_shuttle_positions(
    calibration: CourtCalibration,
    shots_with_real_shuttle_pos: list[tuple[int, float, float]],
    lo_percentile: float = 5.0,
    hi_percentile: float = 95.0,
    margin_frac: float = 0.10,
    alpha: float = 1.0,
) -> CourtCalibration:
    """Second-pass calibration fix: re-derive top/bottom/net_y from real
    shuttle-landing Y values instead of the player-foot-derived values
    `calibrate_from_video` produces (necessarily) before any shot exists.

    Rationale (docs/PRD_v2.3.md, 2026-06-30 decision log; confirmed in
    docs/RESULTS.md Phase D "Root cause"): a standing player's feet during
    calibration sampling don't reach as far toward the baseline as the
    shuttle itself does — video 2's calibration measured `top=176` from
    player positions, while the real shuttle's landing Y median was 134,
    outside that box, which then clamped every deep shot toward the back
    row. Once real shuttle positions exist (post shot-detection, from
    `ShuttleTracker.landing_point`), this lets a second pass fix the row
    axis using that more direct signal.

    Only top/bottom/net_y change. left/right are deliberately left
    untouched — the proportional grid's column axis was already close to
    ground truth (Phase D: 0.04 divergence) and this is a row-axis-only
    fix; widening left/right here as well was not tested and is not
    implied by the evidence that motivated this function.

    Args:
        calibration: the original player-foot-derived calibration (as
            returned by calibrate_from_video).
        shots_with_real_shuttle_pos: (receive_by, x, y) tuples, one per
            shot, for shots where `ShuttleTracker.landing_point()` itself
            returned a non-None position — i.e. the real TrackNetV3 shuttle
            signal, NOT a shot that fell back to the player-position
            lunge-apex proxy (mixing the two back in would reintroduce the
            exact bias this function exists to correct). receive_by: 1 =
            far/top half, 2 = near/bottom half (matches
            CourtCalibration.home_for's convention). x is accepted for
            caller convenience but unused — only Y feeds the row axis.
        lo_percentile / hi_percentile: outlier-trimming percentile pair
            applied to the real shuttle Y values, analogous to
            `calibrate_from_video`'s 5th/95th on player positions.
        margin_frac: buffer pushed outward from the percentile bounds, as a
            fraction of `frame_height` — same convention as
            `calibrate_from_video`'s `margin_frac` (applied there to
            player-foot bounds; here to shuttle-derived bounds instead).
        alpha: blend factor between the shuttle-derived bounds and the
            original player-foot bounds already on `calibration`.
            `final = alpha * shuttle_derived + (1 - alpha) * original`.
            alpha=1.0 uses the shuttle-derived bounds outright; alpha=0.0
            reproduces the original calibration unchanged.

    Defaults (lo/hi=5/95, margin_frac=0.10, alpha=1.0) are the result of a
    parameter sweep against video 1 ground truth (n=53 shots, matched by
    (rally, position-within-rally); see docs/RESULTS.md "Court Calibration
    Variants" for the fuller history). Starting from the plain "Variant A"
    anchor (5/95, margin=0, alpha=1.0: zone exact 20.8%, exact-or-adjacent
    58.5%, row divergence 0.377, col divergence 0.038 — an improvement over
    the shipped baseline's 13.2% / 60.4% / 0.528 / 0.038 on every axis
    except exact-or-adjacent), varying margin_frac alone from 0 up to 0.16
    surfaced a local optimum at 0.10: exact-or-adjacent 64.2% (clears and
    exceeds the baseline's 60.4%) with row divergence 0.340 — better than
    both the baseline (0.528) *and* the Variant A anchor (0.377) — and
    column divergence unchanged at 0.038 (left/right are never touched by
    this function). Sweeping the percentile pair (2/98, 10/90, 15/85) and
    the alpha blend (0.25-0.9) around this margin did not beat it: tighter
    or wider percentiles traded row divergence for adjacent-% or vice versa
    without clearing both bars simultaneously the way margin=0.10 does, and
    alpha<1.0 blends consistently hurt row divergence for no adjacent-%
    gain. Pushing margin_frac further (0.12-0.16) buys a higher raw
    exact-or-adjacent (up to 67.9% at 0.12-0.14) but row divergence
    degrades past the Variant A anchor's 0.377 (0.415-0.491) — a real
    trade-off, not a strict improvement, so the smaller margin=0.10 point
    was kept as the default since it improves BOTH metrics over Variant A
    rather than trading one for the other. Zone-exact itself (17.0%) sits
    between baseline (13.2%) and the Variant A anchor (20.8%) — a partial
    give-back that was accepted for the adjacent/divergence gains, per this
    project's house style of not overstating results (docs/PRD_v2.3.md
    decision log). Checked for plausibility (no ground truth) on video 2:
    row distribution back/mid/front = 21.5/39.2/39.2 vs the Variant A
    anchor's 46.8/17.7/35.4 and the baseline's 68.4/29.1/2.5 — the
    front-zone fix Variant A achieved (front was nearly erased at 2.5% in
    the baseline) is preserved and slightly extended (39.2%), though the
    larger margin further redistributes back-row mass into mid on this
    video specifically; flagged here rather than hidden, since there's no
    video 2 ground truth to confirm which back/mid split is more correct.

    Returns a NEW CourtCalibration (via dataclasses.replace) with
    top/bottom/net_y adjusted; homography (if any) is deliberately
    preserved, not cleared — zone_for() tries homography first and only
    falls through to this proportional fallback for points the detected
    court quadrilateral doesn't cover, so this recalibration should keep
    improving the fallback's own bounds without disabling the more accurate
    homography path when it's available (see docs/RESULTS.md "Court
    Calibration Variants" for the standalone proportional-grid evaluation
    this function was originally validated against, before homography was
    layered back on top). Falls back to returning the original calibration
    unchanged if there aren't enough real-shuttle samples on both halves to
    compute stable percentiles (mirrors calibrate_from_video's own
    too-few-samples fallback posture).
    """
    far_y = [y for receive_by, _x, y in shots_with_real_shuttle_pos if receive_by == 1]
    near_y = [y for receive_by, _x, y in shots_with_real_shuttle_pos if receive_by == 2]

    if len(far_y) < 5 or len(near_y) < 5:
        return calibration

    margin_y = calibration.frame_height * margin_frac

    shuttle_top = float(np.percentile(far_y, lo_percentile)) - margin_y
    shuttle_bottom = float(np.percentile(near_y, hi_percentile)) + margin_y
    far_hi = float(np.percentile(far_y, hi_percentile))
    near_lo = float(np.percentile(near_y, lo_percentile))
    shuttle_net_y = (far_hi + near_lo) / 2.0

    new_top = alpha * shuttle_top + (1 - alpha) * calibration.top
    new_bottom = alpha * shuttle_bottom + (1 - alpha) * calibration.bottom
    new_net_y = alpha * shuttle_net_y + (1 - alpha) * calibration.net_y

    new_top = max(0.0, new_top)
    new_bottom = min(float(calibration.frame_height), new_bottom)

    return replace(calibration, top=new_top, bottom=new_bottom, net_y=new_net_y)
