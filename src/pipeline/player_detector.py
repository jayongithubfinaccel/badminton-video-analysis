"""Player detection — YOLO person detection (Phase C).

Replaces the old color/contour-based player_tracker.py, which relied on
fixed frame-ratio ROIs and a "non-green = player" heuristic that broke down
on banners/crowd/shadows and did not generalize across videos.

Uses the pretrained "person" class directly — no badminton-specific
training required. A player's bounding box is large and high-contrast
compared to the shuttlecock, which is why this is far more reliable than
shuttle tracking at broadcast resolution.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

_MODEL_PATH = Path(__file__).parent.parent.parent / "data" / "models" / "yolov8n.pt"
_PERSON_CLASS = 0
_RACKET_CLASS = 38  # COCO "tennis racket" — see detect_rackets() docstring

_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO(str(_MODEL_PATH))
    return _model


@dataclass
class PlayerBox:
    """A detected player bounding box in a single frame."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def foot_point(self) -> tuple[float, float]:
        """Bottom-center of the box — approximates where the player stands on court."""
        return ((self.x1 + self.x2) / 2.0, self.y2)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


def detect_players(frame: np.ndarray, conf_threshold: float = 0.35) -> list[PlayerBox]:
    """Detect the two players in a broadcast frame.

    Returns at most 2 boxes, sorted top-to-bottom (far-court player first,
    near-court player second). Court is enclosed and the two players are
    consistently the most prominent/highest-confidence "person" detections
    at this camera distance — ball boys, line judges, and crowd are smaller
    and lower-confidence at broadcast resolution.

    Returns an empty list if fewer than 2 confident detections are found
    (e.g. during a replay cut or a player temporarily occluded).
    """
    model = _get_model()
    results = model(frame, classes=[_PERSON_CLASS], verbose=False)[0]

    candidates = []
    for box in results.boxes:
        conf = float(box.conf[0])
        if conf < conf_threshold:
            continue
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        candidates.append(PlayerBox(x1, y1, x2, y2, conf))

    if len(candidates) < 2:
        return []

    candidates.sort(key=lambda b: b.confidence, reverse=True)
    top_two = candidates[:2]
    top_two.sort(key=lambda b: b.center[1])  # top-to-bottom: far court first
    return top_two


@dataclass
class RacketBox:
    """A detected racket bounding box in a single frame (Phase F, best-effort)."""

    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)


def detect_rackets(frame: np.ndarray, conf_threshold: float = 0.15) -> list[RacketBox]:
    """Best-effort racket detection for the visual debug overlay (Phase F).

    Uses YOLOv8n's pretrained COCO class 38 ("tennis racket") — there is no
    badminton-specific racket model or training data in this project. A
    badminton racket has a much thinner frame and smaller head than a tennis
    racket, and is a small, fast-moving object at broadcast camera distance,
    so recall/precision here is UNVALIDATED (no ground truth exists for
    racket position). This is why the confidence threshold is deliberately
    lower than detect_players' 0.35: a stricter threshold would likely
    suppress the already-scarce true positives along with false ones, and
    since this signal is diagnostic-overlay-only (never consumed by shot
    detection, zone mapping, or outcome logic — see docs/PRD_v2.4.md Phase
    F), a noisier but non-empty overlay is more useful for visual QA than an
    empty one.

    Returns at most 2 boxes (at most one racket per player), sorted by
    confidence descending. No attempt is made here to associate a given box
    with a specific player.
    """
    model = _get_model()
    results = model(frame, classes=[_RACKET_CLASS], verbose=False)[0]

    candidates = []
    for box in results.boxes:
        conf = float(box.conf[0])
        if conf < conf_threshold:
            continue
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        candidates.append(RacketBox(x1, y1, x2, y2, conf))

    candidates.sort(key=lambda b: b.confidence, reverse=True)
    return candidates[:2]


def find_lunge_apex(
    cap: cv2.VideoCapture,
    receive_by: int,
    center_frame: int,
    home: tuple[float, float],
    window_before: int,
    window_after: int,
    frame_stride: int = 2,
) -> tuple[int, int] | None:
    """Find the receiving player's most-extended position in a window around
    a detected shot frame, instead of trusting the single frame the shot was
    detected on.

    A player's foot position traces "home -> reach toward the shuttle ->
    recover back to home" around every shot. Contact happens at or very near
    the outward extreme of that arc, not at an arbitrary frame — and the
    exact detected shot frame tends to land slightly after contact (the
    optical-flow signal that timed it has its own smoothing lag), which
    biases a single-frame lookup back toward "home" on both axes. Scanning a
    window and picking the point furthest from `home` corrects for that.

    Args:
        receive_by: 1 = far/top court, 2 = near/bottom court.
        center_frame: the shot's detected frame index.
        home: that player's resting/ready-stance position (CourtCalibration.far_home
            or near_home), used as the reference point for "how far did they reach".
        window_before/window_after: how many frames to search on each side of
            center_frame. Callers should cap these so the window doesn't
            cross into a neighboring shot's reach-and-recover arc.

    Returns the (x, y) at the apex, or None if no player was detected
    anywhere in the window (caller should fall back to a single-frame
    lookup at center_frame in that case).
    """
    start = max(0, center_frame - window_before)
    end = center_frame + window_after

    best_point: tuple[float, float] | None = None
    best_dist = -1.0

    for frame_idx in range(start, end + 1, frame_stride):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        players = detect_players(frame)
        if len(players) != 2:
            continue

        far, near = players
        target = far if receive_by == 1 else near
        x, y = target.foot_point
        dist = ((x - home[0]) ** 2 + (y - home[1]) ** 2) ** 0.5
        if dist > best_dist:
            best_dist = dist
            best_point = (x, y)

    if best_point is None:
        return None
    return int(best_point[0]), int(best_point[1])
