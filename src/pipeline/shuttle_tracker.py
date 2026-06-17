"""Shuttle tracking — detect and track the shuttlecock in each frame.

Uses background subtraction and blob detection to find the bright white
shuttlecock against the court surface.
"""

import cv2
import numpy as np

from src.config import (
    SHUTTLE_BRIGHTNESS_THRESHOLD,
    SHUTTLE_MAX_AREA,
    SHUTTLE_MIN_AREA,
)


class ShuttlePosition:
    """A detected shuttle position in a single frame."""

    def __init__(self, x: int, y: int, frame_idx: int, confidence: float):
        self.x = x
        self.y = y
        self.frame_idx = frame_idx
        self.confidence = confidence

    def __repr__(self) -> str:
        return f"ShuttlePos(x={self.x}, y={self.y}, frame={self.frame_idx}, conf={self.confidence:.2f})"


class ShuttleTracker:
    """Track shuttlecock position across frames using blob detection."""

    def __init__(self):
        self.positions: list[ShuttlePosition] = []
        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=30, varThreshold=50, detectShadows=False
        )
        self._prev_position: ShuttlePosition | None = None

    def detect_shuttle(
        self,
        frame: np.ndarray,
        frame_idx: int,
        court_mask: np.ndarray | None = None,
    ) -> ShuttlePosition | None:
        """Detect shuttlecock in a single frame.

        Strategy:
        1. Background subtraction to find moving objects
        2. Filter by brightness (shuttle is white/bright)
        3. Filter by size (shuttle is small)
        4. Use proximity to previous position for continuity
        """
        h, w = frame.shape[:2]

        # Background subtraction
        fg_mask = self._bg_subtractor.apply(frame)

        # Convert to grayscale for brightness check
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Find bright regions (shuttle is white)
        _, bright_mask = cv2.threshold(gray, SHUTTLE_BRIGHTNESS_THRESHOLD, 255, cv2.THRESH_BINARY)

        # Combine: moving AND bright
        combined = cv2.bitwise_and(fg_mask, bright_mask)

        # Apply court mask if available (only look within court area)
        if court_mask is not None:
            combined = cv2.bitwise_and(combined, court_mask)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

        # Find contours
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter candidates by size
        candidates = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if SHUTTLE_MIN_AREA <= area <= SHUTTLE_MAX_AREA:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])

                    # Confidence based on brightness and size
                    brightness = gray[cy, cx] / 255.0
                    size_score = 1.0 - abs(area - 50) / SHUTTLE_MAX_AREA
                    confidence = (brightness + size_score) / 2.0

                    candidates.append(ShuttlePosition(cx, cy, frame_idx, confidence))

        if not candidates:
            return None

        # Select best candidate
        best = self._select_best_candidate(candidates)
        if best is not None:
            self.positions.append(best)
            self._prev_position = best

        return best

    def _select_best_candidate(self, candidates: list[ShuttlePosition]) -> ShuttlePosition | None:
        """Select the most likely shuttle from candidates.

        Uses proximity to previous detection and confidence score.
        """
        if not candidates:
            return None

        if self._prev_position is None:
            # No previous — pick highest confidence
            return max(candidates, key=lambda c: c.confidence)

        # Score each candidate based on proximity to previous + confidence
        scored = []
        for c in candidates:
            dist = np.sqrt(
                (c.x - self._prev_position.x) ** 2 +
                (c.y - self._prev_position.y) ** 2
            )
            # Normalize distance (closer is better), max reasonable jump ~200px
            proximity_score = max(0, 1.0 - dist / 200.0)
            total_score = 0.4 * c.confidence + 0.6 * proximity_score
            scored.append((c, total_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0] if scored[0][1] > 0.2 else None

    def get_landing_positions(self) -> list[ShuttlePosition]:
        """Detect likely landing positions (where shuttle changes direction or stops).

        A landing is detected when the shuttle's vertical velocity reverses
        (going down then up = bounce/land).
        """
        if len(self.positions) < 3:
            return self.positions

        landings = []
        for i in range(1, len(self.positions) - 1):
            prev_p = self.positions[i - 1]
            curr_p = self.positions[i]
            next_p = self.positions[i + 1]

            # Check for direction change in y (vertical)
            dy_before = curr_p.y - prev_p.y
            dy_after = next_p.y - curr_p.y

            # Landing: was going down (dy>0 in image coords), now going up or stopped
            if dy_before > 2 and dy_after < -2:
                landings.append(curr_p)

            # Also detect when shuttle suddenly disappears then reappears far away
            frame_gap = next_p.frame_idx - curr_p.frame_idx
            if frame_gap > 5:
                landings.append(curr_p)

        # If no landings detected, use positions at regular intervals
        if not landings and self.positions:
            step = max(1, len(self.positions) // 6)
            landings = self.positions[::step]

        return landings

    def reset(self) -> None:
        """Reset tracker for a new rally."""
        self.positions = []
        self._prev_position = None
