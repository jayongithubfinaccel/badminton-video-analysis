"""Shot detection — detect individual shuttle exchanges within a rally.

Phase C approach (replaces Phase B's fixed-ratio, fixed-threshold version):
A "shot" is detected when the dominant motion in the court region reverses
direction (shuttle going up <-> down). Two changes from Phase B:

1. The analyzed court region now comes from a `CourtCalibration` derived
   from observed player positions (see court_calibration.py) instead of a
   fixed `court_top/bottom/left/right` ratio tuned to one video.
2. The direction-change magnitude threshold is now computed per-rally from
   that rally's own motion statistics (a percentile of its own signal)
   instead of a fixed value picked per duration bucket. The minimum gap
   between shots remains a small fixed constant — that one IS a genuine
   domain fact (badminton's physical floor on how fast two consecutive
   hits can occur), not a per-video calibration value.

A scene-cut guard discards motion samples that span a camera cut (replay
insert, angle change) rather than letting the resulting garbage optical-flow
vector get misread as a shot boundary — this was confirmed to be a real
source of false positives on a second test video with mid-rally camera cuts.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from src.pipeline.court_calibration import CourtCalibration
from src.pipeline.frame_filter import detect_scene_change
from src.pipeline.player_detector import detect_players, find_lunge_apex

MIN_SHOT_GAP_SEC = 0.25  # physical floor: fastest plausible consecutive exchanges


@dataclass
class Shot:
    """A single detected shot (shuttle exchange)."""

    shot_number: int  # Global shot number across entire video
    sequence_in_rally: int  # Position within current rally (1, 2, 3, ...)
    score_sequence: int  # Which rally this belongs to
    frame_idx: int  # Frame where shot was detected
    timestamp: float  # Time in seconds
    receive_by: int  # Player who receives (1 or 2)
    zone: int  # Zone 1-9 on receiver's court
    shuttle_x: int = 0  # Estimated landing x position (receiver foot-point proxy)
    shuttle_y: int = 0  # Estimated landing y position (receiver foot-point proxy)
    confidence: float = 0.5


@dataclass
class ShotDetector:
    """Detect individual shots within a rally using motion + player position.

    Strategy:
    - Crop to the calibration-derived play area (not a fixed ratio)
    - Track dominant vertical motion direction within that area
    - A direction reversal exceeding this rally's own adaptive magnitude
      threshold marks a shot boundary
    - Discard samples that straddle a detected camera cut
    - Apply alternation: if last shot was received by P1, next must be P2
    - Zone is taken from the receiving player's foot position (YOLO) at the
      shot frame, mapped through the calibration's bounds/net line
    """

    frame_height: int = 480
    frame_width: int = 908
    fps: float = 30.0
    calibration: CourtCalibration | None = None

    def __post_init__(self):
        if self.calibration is None:
            # Generous full-frame fallback — not a video-tuned ratio.
            self.calibration = CourtCalibration(
                top=self.frame_height * 0.05,
                bottom=self.frame_height * 0.95,
                left=self.frame_width * 0.05,
                right=self.frame_width * 0.95,
                net_y=self.frame_height / 2.0,
                frame_width=self.frame_width,
                frame_height=self.frame_height,
                samples_used=0,
            )

    def detect_shots_in_rally(
        self,
        cap: cv2.VideoCapture,
        start_frame: int,
        end_frame: int,
        score_sequence: int,
        first_receiver: int = 2,
    ) -> list[Shot]:
        """Detect all shots within a rally's frame range using optical flow,
        guarded against camera-cut artifacts.
        """
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        cal = self.calibration
        y1, y2 = int(cal.top), int(cal.bottom)
        x1, x2 = int(cal.left), int(cal.right)

        prev_gray = None
        prev_frame = None
        motion_history: list[tuple[int, float, float]] = []  # (frame, up_motion, down_motion)

        frame_idx = start_frame
        frame_skip = 2  # Process every 2nd frame for speed

        while frame_idx < end_frame:
            ret, frame = cap.read()
            if not ret:
                break

            if (frame_idx - start_frame) % frame_skip != 0:
                frame_idx += 1
                continue

            # Scene-cut guard: a camera cut between this sample and the last
            # produces a meaningless flow vector — treat it as a gap, not motion.
            if prev_frame is not None and detect_scene_change(prev_frame, frame):
                prev_gray = None
                prev_frame = frame
                frame_idx += 1
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            court_gray = gray[y1:y2, x1:x2]

            if prev_gray is not None and prev_gray.shape == court_gray.shape:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, court_gray,
                    None, 0.5, 3, 15, 3, 5, 1.2, 0
                )
                vy = flow[..., 1]

                up_motion = float(np.mean(np.abs(vy[vy < -0.8]))) if np.any(vy < -0.8) else 0
                down_motion = float(np.mean(np.abs(vy[vy > 0.8]))) if np.any(vy > 0.8) else 0

                motion_history.append((frame_idx, up_motion, down_motion))

            prev_gray = court_gray.copy()
            prev_frame = frame
            frame_idx += 1

        if not motion_history:
            return []

        shots = self._extract_shots_from_motion(
            motion_history, start_frame, end_frame,
            score_sequence, first_receiver,
        )

        return shots

    def _extract_shots_from_motion(
        self,
        motion_history: list[tuple[int, float, float]],
        start_frame: int,
        end_frame: int,
        score_sequence: int,
        first_receiver: int,
    ) -> list[Shot]:
        """Extract shot boundaries from motion direction history.

        The magnitude threshold is derived from this rally's own motion
        distribution (a percentile), not a fixed value tied to a duration
        bucket calibrated against one video.
        """
        if len(motion_history) < 10:
            return []

        window = 3 if len(motion_history) > 40 else 2

        smoothed = []
        for i in range(window, len(motion_history) - window):
            frames_slice = motion_history[i - window:i + window + 1]
            avg_up = np.mean([f[1] for f in frames_slice])
            avg_down = np.mean([f[2] for f in frames_slice])
            smoothed.append((motion_history[i][0], avg_up, avg_down))

        if not smoothed:
            return []

        net_direction = [(f, down - up) for f, up, down in smoothed]
        magnitudes = np.abs([d for _, d in net_direction])

        # Adaptive threshold: a direction reversal only counts as a shot if
        # its magnitude clears this rally's own 30th-percentile motion level
        # (calibrated empirically against ground truth — see docs/RESULTS.md).
        # Floor of 0.05 avoids near-zero thresholds on near-static stretches.
        min_magnitude = max(0.05, float(np.percentile(magnitudes, 30)))

        direction_changes = []
        for i in range(1, len(net_direction)):
            prev_dir = net_direction[i - 1][1]
            curr_dir = net_direction[i][1]

            if prev_dir * curr_dir < 0 and (abs(prev_dir) > min_magnitude or abs(curr_dir) > min_magnitude):
                direction_changes.append(net_direction[i][0])

        min_gap_frames = int(self.fps * MIN_SHOT_GAP_SEC)
        filtered_changes = []
        for frame in direction_changes:
            if not filtered_changes or (frame - filtered_changes[-1]) >= min_gap_frames:
                filtered_changes.append(frame)

        shots = []
        current_receiver = first_receiver

        shots.append(Shot(
            shot_number=0,
            sequence_in_rally=1,
            score_sequence=score_sequence,
            frame_idx=start_frame,
            timestamp=start_frame / self.fps,
            receive_by=current_receiver,
            zone=5,
        ))
        current_receiver = 3 - current_receiver

        for i, change_frame in enumerate(filtered_changes):
            shots.append(Shot(
                shot_number=0,
                sequence_in_rally=i + 2,
                score_sequence=score_sequence,
                frame_idx=change_frame,
                timestamp=change_frame / self.fps,
                receive_by=current_receiver,
                zone=5,
            ))
            current_receiver = 3 - current_receiver

        return shots

    def estimate_shuttle_position(
        self,
        cap: cv2.VideoCapture,
        frame_idx: int,
        receive_by: int,
    ) -> tuple[int, int] | None:
        """Estimate the shot's landing position using the receiving player's
        foot position at the shot frame, rather than a brightness-blob guess.

        This is a proxy, not the true shuttle landing pixel (see
        docs/PRD_v2.3.md Phase C) — a player is generally standing near where
        they contact the shuttle, which is a much more reliable signal than
        chasing a few bright pixels at broadcast resolution.

        Kept as the single-frame fallback; estimate_shuttle_position_apex
        below is the preferred path when a calibration with home positions
        is available.
        """
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            return None

        players = detect_players(frame)
        if len(players) != 2:
            return None

        far, near = players  # sorted top-to-bottom
        # receive_by 1 = far/top court, 2 = near/bottom court (matches existing convention)
        target = far if receive_by == 1 else near
        x, y = target.foot_point
        return int(x), int(y)

    def estimate_shuttle_position_apex(
        self,
        cap: cv2.VideoCapture,
        frame_idx: int,
        receive_by: int,
        window_before: int,
        window_after: int,
    ) -> tuple[int, int] | None:
        """Lunge-apex variant: search a window around frame_idx for the
        receiving player's most-extended position relative to their home
        base, instead of trusting one fixed frame. See player_detector.find_lunge_apex
        for why this corrects the "everything collapses toward center" bias.

        window_before/window_after must already be capped by the caller to
        not cross into a neighboring shot's reach-and-recover arc.
        """
        home = self.calibration.home_for(receive_by)
        result = find_lunge_apex(
            cap, receive_by, frame_idx, home, window_before, window_after
        )
        if result is not None:
            return result
        # No detection anywhere in the window — fall back to the single-frame lookup.
        return self.estimate_shuttle_position(cap, frame_idx, receive_by)
