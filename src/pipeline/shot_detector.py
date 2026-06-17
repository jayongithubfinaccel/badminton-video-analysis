"""Shot detection — detect individual shuttle exchanges within a rally.

Phase B approach:
A "shot" is detected when the shuttle crosses from one court half to the other.
Since the shuttle is hard to track at broadcast resolution, we use a combination of:
1. Motion direction analysis (optical flow in the court region)
2. Player movement patterns (players move toward the shuttle)
3. Alternation rule enforcement (shots must alternate between players)

The primary signal is vertical motion direction changes in the court area,
since the shuttle travels primarily up/down in broadcast view.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np


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
    shuttle_x: int = 0  # Estimated shuttle x position
    shuttle_y: int = 0  # Estimated shuttle y position
    confidence: float = 0.5


@dataclass
class ShotDetector:
    """Detect individual shots within a rally using motion analysis.

    Strategy:
    - Divide the court into top half (Player 1 / far court) and bottom half (Player 2 / near court)
    - Track dominant motion direction in the court area
    - When motion shifts from "going down" to "going up" (or vice versa), a shot boundary is detected
    - Apply alternation: if last shot was received by P1, next must be received by P2
    """

    frame_height: int = 480
    frame_width: int = 908
    fps: float = 30.0

    # Court boundaries (relative to frame)
    court_top: float = 0.15
    court_bottom: float = 0.85
    court_left: float = 0.20
    court_right: float = 0.80

    def detect_shots_in_rally(
        self,
        cap: cv2.VideoCapture,
        start_frame: int,
        end_frame: int,
        score_sequence: int,
        first_receiver: int = 2,  # Who receives the serve
    ) -> list[Shot]:
        """Detect all shots within a rally's frame range.

        Uses optical flow to detect shuttle direction changes.
        """
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        # Read frames and compute motion
        prev_gray = None
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

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Crop to court region
            y1 = int(self.frame_height * self.court_top)
            y2 = int(self.frame_height * self.court_bottom)
            x1 = int(self.frame_width * self.court_left)
            x2 = int(self.frame_width * self.court_right)
            court_gray = gray[y1:y2, x1:x2]

            if prev_gray is not None:
                # Compute optical flow
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, court_gray,
                    None, 0.5, 3, 15, 3, 5, 1.2, 0
                )

                # Analyze vertical motion (flow[..., 1] = vertical component)
                vy = flow[..., 1]

                # Use full court area for motion detection
                # Higher pixel velocity threshold filters slow player movement
                up_motion = float(np.mean(np.abs(vy[vy < -0.8]))) if np.any(vy < -0.8) else 0
                down_motion = float(np.mean(np.abs(vy[vy > 0.8]))) if np.any(vy > 0.8) else 0

                motion_history.append((frame_idx, up_motion, down_motion))

            prev_gray = court_gray.copy()
            frame_idx += 1

        if not motion_history:
            return []

        # Detect shot boundaries from motion direction changes
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

        A shot boundary occurs when the dominant motion direction changes
        (up → down or down → up), indicating the shuttle changed direction.
        """
        if len(motion_history) < 10:
            return []

        # Smooth motion signals - adaptive window based on rally length
        rally_duration_frames = end_frame - start_frame
        if rally_duration_frames < 300:  # < 10s at 30fps
            window = 2  # Less smoothing for short rallies
            min_magnitude = 0.12  # More sensitive
        elif rally_duration_frames < 600:  # 10-20s
            window = 3
            min_magnitude = 0.14  # High-density rallies need sensitivity
        else:  # > 20s
            window = 3
            min_magnitude = 0.27  # Long rallies: slightly lower to catch more

        smoothed = []
        for i in range(window, len(motion_history) - window):
            frames_slice = motion_history[i - window:i + window + 1]
            avg_up = np.mean([f[1] for f in frames_slice])
            avg_down = np.mean([f[2] for f in frames_slice])
            smoothed.append((motion_history[i][0], avg_up, avg_down))

        if not smoothed:
            return []

        # Compute net direction: positive = down, negative = up
        net_direction = [(f, down - up) for f, up, down in smoothed]

        # Detect zero crossings (direction changes)
        direction_changes = []
        for i in range(1, len(net_direction)):
            prev_dir = net_direction[i - 1][1]
            curr_dir = net_direction[i][1]

            # Sign change with sufficient magnitude (uses adaptive threshold)
            if prev_dir * curr_dir < 0 and (abs(prev_dir) > min_magnitude or abs(curr_dir) > min_magnitude):
                direction_changes.append(net_direction[i][0])

        # Minimum gap between shots: adaptive based on rally length
        if rally_duration_frames < 300:
            min_gap_sec = 0.3  # Fast exchanges in short rallies
        elif rally_duration_frames < 600:
            min_gap_sec = 0.35  # Medium rallies
        else:
            min_gap_sec = 0.55  # Long rallies have more dead time between shots
        min_gap_frames = int(self.fps * min_gap_sec)
        filtered_changes = []
        for frame in direction_changes:
            if not filtered_changes or (frame - filtered_changes[-1]) >= min_gap_frames:
                filtered_changes.append(frame)

        # Build shots from direction changes
        shots = []
        current_receiver = first_receiver

        # First shot: the serve (at rally start)
        shots.append(Shot(
            shot_number=0,  # Will be renumbered globally later
            sequence_in_rally=1,
            score_sequence=score_sequence,
            frame_idx=start_frame,
            timestamp=start_frame / self.fps,
            receive_by=current_receiver,
            zone=5,  # Default center, will be updated
        ))
        current_receiver = 3 - current_receiver  # Alternate: 1→2, 2→1

        # Subsequent shots at each direction change
        for i, change_frame in enumerate(filtered_changes):
            shots.append(Shot(
                shot_number=0,
                sequence_in_rally=i + 2,  # +2 because serve is shot 1
                score_sequence=score_sequence,
                frame_idx=change_frame,
                timestamp=change_frame / self.fps,
                receive_by=current_receiver,
                zone=5,  # Default, updated later
            ))
            current_receiver = 3 - current_receiver

        return shots

    def estimate_shuttle_position(
        self,
        cap: cv2.VideoCapture,
        frame_idx: int,
    ) -> tuple[int, int] | None:
        """Estimate shuttle position at a specific frame using brightness detection."""
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Court region only
        y1 = int(h * self.court_top)
        y2 = int(h * self.court_bottom)
        x1 = int(w * self.court_left)
        x2 = int(w * self.court_right)

        court = gray[y1:y2, x1:x2]

        # Find brightest small blob (shuttle candidate)
        _, bright = cv2.threshold(court, 200, 255, cv2.THRESH_BINARY)

        # Morphological to isolate small objects
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter by size (shuttle is small)
        candidates = []
        for c in contours:
            area = cv2.contourArea(c)
            if 5 <= area <= 200:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"]) + x1
                    cy = int(M["m01"] / M["m00"]) + y1
                    candidates.append((cx, cy, area))

        if candidates:
            # Pick the one closest to frame center vertically (more likely shuttle)
            mid_y = h // 2
            candidates.sort(key=lambda p: abs(p[1] - mid_y))
            return candidates[0][0], candidates[0][1]

        return None
